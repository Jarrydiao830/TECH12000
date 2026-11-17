import Foundation
import SwiftUI
import UserNotifications

/// 全局状态。App 只做展示：不参与判断，不发送任何控制指令。
enum AppTab: Hashable { case status, events, settings }

@MainActor
final class AppState: ObservableObject {
    @Published var tab: AppTab = .status
    @Published var pairing: Pairing? = Pairing.load()
    @Published var status: SystemStatus?
    @Published var events: [FallEvent] = []
    @Published var online = false               // 与电脑的实时连接是否在线
    @Published var lastUpdate: Date?
    @Published var lastError: String?
    @Published var alert: FallEvent?            // 前台醒目告警（不是锁屏推送）
    @Published var notificationAuth: UNAuthorizationStatus = .notDetermined

    private var socket: URLSessionWebSocketTask?
    private var loopTask: Task<Void, Never>?
    private var seenEventIDs = Set<String>()    // 按 event_id 去重，避免同一事件重复告警
    private var staleTimer: Timer?
    private var lastState: String?
    private var offlineNotified = false          // 断线提醒只发一次，重新连上后复位
    private var bgTask: UIBackgroundTaskIdentifier = .invalid

    func start() {
        stop()
        // Demo mode: keep the screen on while the app is in front (toggle in Settings, on by default).
        UIApplication.shared.isIdleTimerDisabled = UserDefaults.standard.object(forKey: "keepAwake") as? Bool ?? true
        guard let pairing else { return }
        loopTask = Task { await self.runLoop(pairing) }
        staleTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.checkStale() }
        }
        Task {
            await refreshNotificationAuth()
            if notificationAuth == .notDetermined { await requestNotificationAuth() }
        }
    }

    /// 切到后台时向系统多要一点运行时间（通常几十秒），期间仍能收到事件并发本地通知；
    /// 时间用完或系统挂起 App 后就收不到了。
    func enterBackground() {
        guard bgTask == .invalid else { return }
        bgTask = UIApplication.shared.beginBackgroundTask(withName: "keep-ws") { [weak self] in
            Task { @MainActor in self?.endBackground(stopping: true) }
        }
    }

    func endBackground(stopping: Bool = false) {
        if stopping { stop() }
        if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask); bgTask = .invalid }
    }

    func stop() {
        loopTask?.cancel()
        socket?.cancel(with: .goingAway, reason: nil)
        staleTimer?.invalidate()
        online = false
    }

    func apply(_ p: Pairing) {
        p.save()
        pairing = p
        seenEventIDs.removeAll()
        tab = .status
        start()
    }

    func unpair() {
        stop()
        Pairing.clear()
        pairing = nil
        status = nil
        events = []
    }

    /// 超过 5 秒没有任何更新就显示离线，不把旧状态当作实时状态。
    private func checkStale() {
        guard let t = lastUpdate else { return }
        let age = Date().timeIntervalSince(t)
        if age > 5 { online = false }
        if age > 15 && !offlineNotified {
            offlineNotified = true
            Notifier.shared.notifyOffline()
        }
    }

    private func update(_ s: SystemStatus) {
        if s.state == "fault" && lastState != nil && lastState != "fault" {
            Notifier.shared.notifyFault(reason: s.state_reason)
        }
        lastState = s.state
        status = s
        lastUpdate = Date()
        offlineNotified = false
    }

    func refresh() async {
        guard let pairing else { return }
        let api = APIClient(pairing: pairing)
        do {
            update(try await api.status())
            let list = try await api.events()
            // 首次拉取的历史事件只入列表，不当作新告警弹出
            if seenEventIDs.isEmpty { list.forEach { seenEventIDs.insert($0.event_id) } }
            events = list
            lastError = nil
        } catch let e as URLError where e.code == .userAuthenticationRequired {
            lastError = "Pairing token is invalid. Please pair again."
        } catch {
            lastError = "Can't reach the computer: \(error.localizedDescription)"
        }
    }

    private func runLoop(_ pairing: Pairing) async {
        while !Task.isCancelled {
            await refresh()
            guard let url = pairing.wsURL else { return }
            var req = URLRequest(url: url)
            req.setValue("Bearer \(pairing.token)", forHTTPHeaderField: "Authorization")
            let ws = URLSession.shared.webSocketTask(with: req)
            socket = ws
            ws.resume()
            do {
                while !Task.isCancelled {
                    let msg = try await ws.receive()
                    guard case .string(let text) = msg,
                          let m = try? JSONDecoder().decode(WSMessage.self, from: Data(text.utf8)) else { continue }
                    online = true
                    lastUpdate = Date()
                    lastError = nil
                    if let s = m.status { update(s) }
                    if m.type == "event", let ev = m.event { handle(ev) }
                }
            } catch {
                online = false
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)   // 断线后 2 秒重连
        }
    }

    private func handle(_ ev: FallEvent) {
        if let i = events.firstIndex(where: { $0.event_id == ev.event_id }) {
            events[i] = ev                       // 同一事件的状态更新，不再次告警
        } else {
            events.insert(ev, at: 0)
        }
        if seenEventIDs.insert(ev.event_id).inserted {
            alert = ev
            Notifier.shared.notify(event: ev)
        }
    }

    func refreshNotificationAuth() async {
        notificationAuth = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    func requestNotificationAuth() async {
        _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
        await refreshNotificationAuth()
        // 第二阶段（APNs）：授权后调用 UIApplication.shared.registerForRemoteNotifications()，
        // 在 AppDelegate 拿到 device token 后 POST 到电脑的 /api/v1/apns/token。
    }
}

import Foundation
import UserNotifications

/// 本地通知提醒（由 App 自己发出，不经过 APNs）。
///
/// 只有 App 正在运行时才能发出：前台，或刚切到后台、系统还没把 App 挂起的那几十秒。
/// App 被挂起或被划掉后收不到——那需要第二阶段的 APNs 锁屏推送。
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    static let shared = Notifier()
    private let center = UNUserNotificationCenter.current()

    func install() { center.delegate = self }

    /// 跌倒事件提醒。通知标识用 event_id，同一事件即使重复送达，系统里也只保留一条。
    func notify(event ev: FallEvent) {
        let c = UNMutableNotificationContent()
        if ev.airbagTriggered {
            c.title = ev.airbagDemo ? "Airbag triggered (demo)" : "Airbag triggered"
        } else {
            c.title = ev.is_test ? "Simulated test event" : "Possible fall"
        }
        c.body = ev.englishMessage
        c.sound = .default
        c.interruptionLevel = .active
        c.threadIdentifier = "events"
        post(id: "event-\(ev.event_id)", c)
    }

    /// 系统进入故障（数据源断联或过期）时提醒一次。
    func notifyFault(reason: String) {
        let c = UNMutableNotificationContent()
        c.title = "Monitoring fault"
        c.body = "The computer reports a fault (sensor data missing or stale). Falls may not be detected right now."
        c.sound = .default
        c.threadIdentifier = "system"
        post(id: "fault", c)
    }

    /// 与电脑断开较长时间时提醒一次。
    func notifyOffline() {
        let c = UNMutableNotificationContent()
        c.title = "Disconnected from computer"
        c.body = "The phone isn't receiving status. Check that the monitoring program is running and that the phone and computer are on the same Wi-Fi."
        c.sound = .default
        c.threadIdentifier = "system"
        post(id: "offline", c)
    }

    private func post(id: String, _ c: UNMutableNotificationContent) {
        center.add(UNNotificationRequest(identifier: id, content: c, trigger: nil))
    }

    // App 在前台时也显示横幅并响铃（默认前台不显示）。
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }
}

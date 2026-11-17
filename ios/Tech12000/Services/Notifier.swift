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
        c.title = ev.is_test ? "模拟测试事件" : "疑似跌倒"
        c.body = ev.message
        c.sound = .default
        c.interruptionLevel = .active
        c.threadIdentifier = "events"
        post(id: "event-\(ev.event_id)", c)
    }

    /// 系统进入故障（数据源断联或过期）时提醒一次。
    func notifyFault(reason: String) {
        let c = UNMutableNotificationContent()
        c.title = "监测系统故障"
        c.body = reason.isEmpty ? "电脑端报告故障，当前可能无法检测跌倒。" : "当前可能无法检测跌倒：\(reason)"
        c.sound = .default
        c.threadIdentifier = "system"
        post(id: "fault", c)
    }

    /// 与电脑断开较长时间时提醒一次。
    func notifyOffline() {
        let c = UNMutableNotificationContent()
        c.title = "与电脑断开连接"
        c.body = "手机暂时收不到监测状态，请检查电脑程序是否在运行、手机与电脑是否在同一网络。"
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

import Foundation

/// 与电脑端 /api/v1 的 JSON 一一对应。App 只读，不含任何控制指令。
struct DeviceStatus: Codable {
    var connected: Bool?
    var fresh: Bool?
    var last_rx_wall: Double?
    var detail: String?
    var simulated: Bool?
}

struct FallEvent: Codable, Identifiable, Equatable {
    var event_id: String
    var t_wall: Double            // 事件实际发生时间（延迟补发时也保持原值）
    var mode: String
    var deploy_status: String
    var deploy_outcome: String
    var is_test: Bool
    var message: String

    var id: String { event_id }
    var date: Date { Date(timeIntervalSince1970: t_wall) }

    /// English alert text, mirroring event_message() in pc/tech12000/models.py.
    /// States only what actually happened; never claims the airbag deployed.
    var englishMessage: String {
        let prefix = is_test ? "[Simulated test] " : ""
        let body: String
        switch deploy_status {
        case "command_sent", "controller_acked":
            body = "Possible fall detected. Deploy command sent. Check on the person now."
        case "demo_command_sent":
            body = "Possible fall detected. Demo command sent (no real release mechanism connected)."
        case "send_failed":
            body = "Possible fall detected. Deploy command FAILED to send. Check on the person now."
        default:
            body = "Possible fall detected. Monitor-only mode, no deploy command sent. Check on the person now."
        }
        return prefix + body
    }
}

struct SystemStatus: Codable {
    var server_time: Double
    var state: String
    var state_reason: String
    var mode: String
    var monitoring: Bool
    var devices: [String: DeviceStatus]
    var deploy_status: String
    var deploy_outcome: String?
    var last_event: FallEvent?
    var simulated_input: Bool
}

struct EventList: Codable { var events: [FallEvent] }

struct WSMessage: Codable {
    var type: String
    var status: SystemStatus?
    var event: FallEvent?
}

enum Labels {
    static func state(_ s: String) -> String {
        ["initializing": "Starting up", "ready": "Monitoring", "suspected_fall": "Possible fall",
         "triggered": "Triggered", "fault": "Fault"][s] ?? s
    }
    static func mode(_ s: String) -> String {
        ["monitor": "Monitor only", "demo": "Demo", "armed": "Armed"][s] ?? s
    }
    /// 只陈述指令状态；没有展开反馈，绝不显示"已展开/保护成功"。
    static func deploy(_ s: String) -> String {
        ["none": "None", "not_sent_monitor_mode": "Not sent (monitor only)", "demo_command_sent": "Demo command sent",
         "command_sent": "Deploy command sent", "controller_acked": "Controller acknowledged",
         "send_failed": "Command failed to send", "skipped_duplicate": "Duplicate event skipped"][s] ?? s
    }
    static func device(_ k: String) -> String {
        ["wristband": "Wristband", "radar": "Radar", "receiver": "Receiver", "servo": "Airbag"][k] ?? k
    }
}

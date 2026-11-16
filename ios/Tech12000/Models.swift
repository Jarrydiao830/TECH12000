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
        ["initializing": "初始化", "ready": "监测中", "suspected_fall": "疑似异常",
         "triggered": "已触发", "fault": "故障"][s] ?? s
    }
    static func mode(_ s: String) -> String {
        ["monitor": "仅监测", "demo": "演示", "armed": "已使能"][s] ?? s
    }
    /// 只陈述指令状态；没有展开反馈，绝不显示"已展开/保护成功"。
    static func deploy(_ s: String) -> String {
        ["none": "无", "not_sent_monitor_mode": "未发送（仅监测）", "demo_command_sent": "演示指令已发送",
         "command_sent": "部署指令已发送", "controller_acked": "控制器确认接收",
         "send_failed": "指令发送失败", "skipped_duplicate": "重复事件已跳过"][s] ?? s
    }
    static func device(_ k: String) -> String {
        ["wristband": "手环", "radar": "雷达", "receiver": "接收板", "servo": "舵机控制器"][k] ?? k
    }
}

import SwiftUI
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @State private var host = ""
    @State private var port = "8000"
    @State private var token = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("电脑地址，如 192.168.1.20", text: $host)
                        .keyboardType(.numbersAndPunctuation).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("端口", text: $port).keyboardType(.numberPad)
                    SecureField("配对令牌", text: $token)
                    Button("保存并连接") {
                        if let p = Int(port) { app.apply(Pairing(host: host.trimmingCharacters(in: .whitespaces), port: p, token: token)) }
                    }.disabled(host.isEmpty || token.isEmpty || Int(port) == nil)
                    if app.pairing != nil { Button("取消配对", role: .destructive) { app.unpair() } }
                } header: { Text("连接设置") } footer: {
                    Text("也可以用系统相机扫描电脑监控台上的二维码自动配对。手机与电脑需在同一局域网，且网络允许设备互访。")
                }
                Section {
                    LabeledContent("通知权限", value: authText)
                    if app.notificationAuth == .notDetermined {
                        Button("请求通知权限") { Task { await app.requestNotificationAuth() } }
                    }
                } header: { Text("通知") } footer: {
                    Text("当前版本只在 App 打开时显示告警；锁屏/后台推送尚未启用。")
                }
            }
            .navigationTitle("设置")
            .onAppear {
                if let p = app.pairing { host = p.host; port = String(p.port); token = p.token }
                Task { await app.refreshNotificationAuth() }
            }
        }
    }

    private var authText: String {
        switch app.notificationAuth {
        case .authorized, .provisional, .ephemeral: "已允许"
        case .denied: "已拒绝（请到系统设置中开启）"
        default: "未请求"
        }
    }
}

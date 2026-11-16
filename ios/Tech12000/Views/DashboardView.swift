import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            List {
                if app.pairing == nil {
                    Section { Text("尚未配对。请到「设置」页输入电脑地址，或用相机扫描电脑界面上的二维码。") }
                } else {
                    Section("气囊盒") {
                        row("连接", app.online ? "在线" : "离线", app.online ? .green : .red)
                        row("最后更新", app.lastUpdate.map { $0.formatted(date: .omitted, time: .standard) } ?? "—")
                        if let e = app.lastError { Text(e).foregroundStyle(.red).font(.footnote) }
                    }
                    if let s = app.status {
                        Section("系统") {
                            row("风险状态", Labels.state(s.state), stateColor(s.state))
                            row("执行模式", Labels.mode(s.mode))
                            row("部署指令", Labels.deploy(s.deploy_status))
                            if s.last_event != nil { row("实际展开状态", "未知 / 待现场检查", .orange) }
                            if s.simulated_input { Text("当前输入为模拟数据").font(.footnote).foregroundStyle(.orange) }
                        }
                        Section("设备") {
                            ForEach(s.devices.keys.sorted(), id: \.self) { k in
                                let d = s.devices[k]!
                                let ok = (d.connected ?? false) && (d.fresh ?? true)
                                row(Labels.device(k), ok ? "正常" : (d.connected == true ? "数据过期" : "未连接"),
                                    ok ? .green : .red)
                            }
                        }
                        Section("最近跌倒事件") {
                            if let ev = s.last_event {
                                Text(ev.date.formatted(date: .abbreviated, time: .standard))
                                Text(ev.message).font(.footnote)
                            } else {
                                Text("无").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .opacity(app.online || app.pairing == nil ? 1 : 0.5)   // 离线时旧数据变灰
            .navigationTitle("TECH12000")
            .refreshable { await app.refresh() }
        }
    }

    private func row(_ k: String, _ v: String, _ c: Color = .primary) -> some View {
        HStack { Text(k); Spacer(); Text(v).foregroundStyle(c) }
    }

    private func stateColor(_ s: String) -> Color {
        switch s { case "ready": .green; case "suspected_fall": .orange; case "triggered", "fault": .red; default: .secondary }
    }
}

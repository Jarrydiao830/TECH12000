import SwiftUI

struct EventListView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            List(app.events) { ev in
                NavigationLink { EventDetailView(event: ev) } label: {
                    VStack(alignment: .leading) {
                        HStack {
                            if ev.is_test { Text("模拟测试").font(.caption).padding(.horizontal, 6)
                                .background(.orange.opacity(0.25), in: Capsule()) }
                            Text(ev.date.formatted(date: .abbreviated, time: .standard))
                        }
                        Text(Labels.deploy(ev.deploy_status)).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .overlay { if app.events.isEmpty { Text("暂无事件").foregroundStyle(.secondary) } }
            .navigationTitle("事件历史")
            .refreshable { await app.refresh() }
        }
    }
}

struct EventDetailView: View {
    @EnvironmentObject var app: AppState
    @State var event: FallEvent
    @State private var note: String?

    var body: some View {
        List {
            Section { Text(event.message) }
            Section("详情") {
                LabeledContent("发生时间", value: event.date.formatted(date: .abbreviated, time: .standard))
                LabeledContent("当时模式", value: Labels.mode(event.mode))
                LabeledContent("部署指令", value: Labels.deploy(event.deploy_status))
                LabeledContent("实际展开状态", value: "未知 / 待现场检查")
                LabeledContent("事件编号", value: String(event.event_id.prefix(8)))
            }
            if let note { Section { Text(note).font(.footnote).foregroundStyle(.secondary) } }
        }
        .navigationTitle(event.is_test ? "模拟测试事件" : "跌倒事件")
        .task {
            // 打开详情时尝试从电脑读取最新状态；读不到就明确说明显示的是本地缓存
            guard let p = app.pairing else { return }
            do { event = try await APIClient(pairing: p).event(id: event.event_id) }
            catch { note = "无法连接电脑，以上为手机上保存的信息，可能不是最新。" }
        }
    }
}

/// 前台全屏告警。仅在 App 打开时出现，不是锁屏推送。
struct AlertView: View {
    @Environment(\.dismiss) private var dismiss
    let event: FallEvent

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 72))
            Text(event.is_test ? "模拟测试" : "疑似跌倒").font(.largeTitle.bold())
            Text(event.message).multilineTextAlignment(.center)
            Text(event.date.formatted(date: .abbreviated, time: .standard)).font(.footnote)
            Button("我知道了") { dismiss() }.buttonStyle(.borderedProminent).tint(.white).foregroundStyle(.red)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(event.is_test ? Color.orange : Color.red)
        .foregroundStyle(.white)
    }
}

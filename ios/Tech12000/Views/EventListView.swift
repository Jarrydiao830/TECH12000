import SwiftUI

struct EventListView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            List(app.events) { ev in
                NavigationLink { EventDetailView(event: ev) } label: {
                    VStack(alignment: .leading) {
                        HStack {
                            if ev.is_test { Text("Simulated test").font(.caption).padding(.horizontal, 6)
                                .background(.orange.opacity(0.25), in: Capsule()) }
                            Text(ev.date.formatted(date: .abbreviated, time: .standard))
                        }
                        Text(Labels.deploy(ev.deploy_status)).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .overlay { if app.events.isEmpty { Text("No events yet").foregroundStyle(.secondary) } }
            .navigationTitle("Event history")
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
            Section { Text(event.englishMessage) }
            Section("Details") {
                LabeledContent("Time", value: event.date.formatted(date: .abbreviated, time: .standard))
                LabeledContent("Mode at the time", value: Labels.mode(event.mode))
                LabeledContent("Deploy command", value: Labels.deploy(event.deploy_status))
                LabeledContent("Actual deployment", value: "Unknown / check on site")
                LabeledContent("Event ID", value: String(event.event_id.prefix(8)))
            }
            if let note { Section { Text(note).font(.footnote).foregroundStyle(.secondary) } }
        }
        .navigationTitle(event.is_test ? "Simulated test event" : "Fall event")
        .task {
            // 打开详情时尝试从电脑读取最新状态；读不到就明确说明显示的是本地缓存
            guard let p = app.pairing else { return }
            do { event = try await APIClient(pairing: p).event(id: event.event_id) }
            catch { note = "Can't reach the computer. This is the copy saved on the phone and may be out of date." }
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
            Text(event.is_test ? "Simulated test" : "Possible fall").font(.largeTitle.bold())
            Text(event.englishMessage).multilineTextAlignment(.center)
            Text(event.date.formatted(date: .abbreviated, time: .standard)).font(.footnote)
            Button("Got it") { dismiss() }.buttonStyle(.borderedProminent).tint(.white).foregroundStyle(.red)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(event.is_test ? Color.orange : Color.red)
        .foregroundStyle(.white)
    }
}

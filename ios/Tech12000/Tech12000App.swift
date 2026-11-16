import SwiftUI

@main
struct Tech12000App: App {
    @StateObject private var app = AppState()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .onOpenURL { url in if let p = Pairing.from(url: url) { app.apply(p) } }
                .onChange(of: phase) { _, new in
                    // 后台不保证 WebSocket 存活；回到前台时重新连接并拉取最新状态
                    if new == .active { app.start() } else if new == .background { app.stop() }
                }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        TabView {
            DashboardView().tabItem { Label("状态", systemImage: "waveform.path.ecg.rectangle") }
            EventListView().tabItem { Label("事件", systemImage: "list.bullet") }
            SettingsView().tabItem { Label("设置", systemImage: "gear") }
        }
        .fullScreenCover(item: $app.alert) { ev in AlertView(event: ev) }
    }
}

import SwiftUI

@main
struct Tech12000App: App {
    @StateObject private var app = AppState()
    @Environment(\.scenePhase) private var phase

    init() { Notifier.shared.install() }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .onOpenURL { url in if let p = Pairing.from(url: url) { app.apply(p) } }
                .onChange(of: phase) { _, new in
                    // 后台只在系统给的短暂时间内保持连接；回到前台时重新连接并拉取最新状态
                    if new == .active { app.endBackground(); app.start() }
                    else if new == .background { app.enterBackground() }
                }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        TabView(selection: $app.tab) {
            DashboardView().tabItem { Label("Status", systemImage: "shield.lefthalf.filled") }.tag(AppTab.status)
            EventListView().tabItem { Label("Events", systemImage: "list.bullet.rectangle") }.tag(AppTab.events)
            SettingsView().tabItem { Label("Settings", systemImage: "gearshape") }.tag(AppTab.settings)
        }
        .tint(Theme.blue)
        .fullScreenCover(item: $app.alert) { ev in AlertView(event: ev) }
    }
}

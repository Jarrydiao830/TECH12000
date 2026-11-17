import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            List {
                if app.pairing == nil {
                    Section { Text("Not paired yet. Enter the computer's address in Settings, or scan the QR code on the computer's monitor page with the Camera app.") }
                } else {
                    Section("Airbag unit") {
                        row("Connection", app.online ? "Online" : "Offline", app.online ? .green : .red)
                        row("Last update", app.lastUpdate.map { $0.formatted(date: .omitted, time: .standard) } ?? "—")
                        if let e = app.lastError { Text(e).foregroundStyle(.red).font(.footnote) }
                    }
                    if let s = app.status {
                        Section("System") {
                            row("Risk state", Labels.state(s.state), stateColor(s.state))
                            row("Mode", Labels.mode(s.mode))
                            row("Deploy command", Labels.deploy(s.deploy_status))
                            if s.last_event != nil { row("Actual deployment", "Unknown / check on site", .orange) }
                            if s.simulated_input { Text("Input is simulated data").font(.footnote).foregroundStyle(.orange) }
                        }
                        Section("Devices") {
                            ForEach(s.devices.keys.sorted(), id: \.self) { k in
                                let d = s.devices[k]!
                                let ok = (d.connected ?? false) && (d.fresh ?? true)
                                row(Labels.device(k), ok ? "OK" : (d.connected == true ? "Stale data" : "Not connected"),
                                    ok ? .green : .red)
                            }
                        }
                        Section("Latest fall event") {
                            if let ev = s.last_event {
                                Text(ev.date.formatted(date: .abbreviated, time: .standard))
                                Text(ev.englishMessage).font(.footnote)
                            } else {
                                Text("None").foregroundStyle(.secondary)
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

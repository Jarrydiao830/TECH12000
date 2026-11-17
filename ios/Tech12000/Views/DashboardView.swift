import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if app.pairing == nil {
                        NotPairedCard()
                    } else {
                        HeroCard()
                        if let e = app.lastError { ErrorBanner(text: e) }
                        if let s = app.status {
                            InfoRow(status: s)
                            DevicesGrid(status: s)
                            LatestEventCard(status: s)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("TECH12000")
            .refreshable { await app.refresh() }
        }
    }
}

// MARK: - Hero

private struct HeroCard: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        let style = Theme.style(state: app.status?.state, online: app.online,
                                airbag: app.status?.last_event?.airbagTriggered == true)
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                LiveDot(live: app.online)
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    Text(updatedText).font(.footnote.weight(.medium))
                }
                Spacer()
                if app.status?.simulated_input == true {
                    Text("SIMULATED").font(.caption2.weight(.heavy)).tracking(0.8)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(.white.opacity(0.22), in: Capsule())
                }
            }
            .opacity(0.9)

            HStack(alignment: .center, spacing: 16) {
                Image(systemName: style.icon)
                    .font(.system(size: 44, weight: .semibold))
                    .symbolRenderingMode(.hierarchical)
                    .frame(width: 64, height: 64)
                    .background(.white.opacity(0.18), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .contentTransition(.symbolEffect(.replace))
                VStack(alignment: .leading, spacing: 4) {
                    Text(style.title).font(.system(.largeTitle, design: .rounded).weight(.bold))
                        .minimumScaleFactor(0.7).lineLimit(1)
                    Text(subtitle).font(.subheadline).opacity(0.85).lineLimit(2)
                }
            }
        }
        .foregroundStyle(.white)
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(style.gradient, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .shadow(color: style.tint.opacity(0.35), radius: 16, y: 8)
        .animation(.easeInOut(duration: 0.35), value: style.title)
    }

    private var updatedText: String {
        guard let t = app.lastUpdate else { return "Waiting for computer…" }
        let s = max(0, Int(Date().timeIntervalSince(t)))
        return app.online ? (s <= 1 ? "Live" : "Live · \(s)s ago") : "Last update \(t.formatted(date: .omitted, time: .shortened))"
    }

    private var subtitle: String {
        guard app.online else { return "Not receiving status from the computer." }
        guard let s = app.status else { return "Connecting…" }
        switch s.state {
        case "ready": return s.monitoring ? "Monitoring the bathroom." : "Monitoring is paused on the computer."
        case "suspected_fall": return "Checking sensor data…"
        case "triggered": return "Check on the person now."
        case "fault": return "Falls may not be detected right now."
        default: return "Waiting for sensors."
        }
    }
}

private struct ErrorBanner: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "exclamationmark.circle.fill")
            .font(.footnote)
            .foregroundStyle(Theme.bad)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.bad.opacity(0.1), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

// MARK: - Mode / deploy

private struct InfoRow: View {
    let status: SystemStatus
    var body: some View {
        HStack(spacing: 12) {
            tile("Mode", Labels.mode(status.mode), "slider.horizontal.3",
                 status.mode == "armed" ? Theme.bad : Theme.blue)
            tile("Airbag command", Labels.deploy(status.deploy_status), "paperplane.fill",
                 status.deploy_status == "send_failed" ? Theme.bad : Theme.teal)
        }
        .fixedSize(horizontal: false, vertical: true)   // both tiles take the taller one's height
    }

    private func tile(_ title: String, _ value: String, _ icon: String, _ color: Color) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: icon).font(.headline).foregroundStyle(color)
                Text(title).font(.caption).foregroundStyle(.secondary)
                Text(value).font(.subheadline.weight(.semibold)).lineLimit(2).minimumScaleFactor(0.8)
            }
        }
    }
}

// MARK: - Devices

private struct DevicesGrid: View {
    let status: SystemStatus
    private let cols = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel(text: "Devices")
            LazyVGrid(columns: cols, spacing: 12) {
                ForEach(status.devices.keys.sorted(), id: \.self) { k in
                    let d = status.devices[k]!
                    let ok = (d.connected ?? false) && (d.fresh ?? true)
                    let text = ok ? "OK" : (d.connected == true ? "Stale data" : "Not connected")
                    Card {
                        HStack(spacing: 12) {
                            Image(systemName: Theme.deviceIcon(k))
                                .font(.title3)
                                .foregroundStyle(ok ? Theme.ok : Theme.bad)
                                .frame(width: 36, height: 36)
                                .background((ok ? Theme.ok : Theme.bad).opacity(0.12), in: Circle())
                            VStack(alignment: .leading, spacing: 2) {
                                Text(Labels.device(k)).font(.subheadline.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
                                Text(text).font(.caption).foregroundStyle(ok ? Theme.ok : Theme.bad)
                            }
                            Spacer(minLength: 0)
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Latest event

private struct LatestEventCard: View {
    let status: SystemStatus
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel(text: "Latest fall event")
            Card {
                if let ev = status.last_event {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Image(systemName: "figure.fall").foregroundStyle(ev.is_test ? Theme.warn : Theme.bad)
                            Text(ev.date.formatted(date: .abbreviated, time: .standard)).font(.subheadline.weight(.semibold))
                            Spacer()
                            if ev.is_test { Pill(text: "TEST") }
                        }
                        Text(ev.englishMessage).font(.footnote).foregroundStyle(.secondary)
                        Divider()
                        HStack {
                            Text("Actual deployment").font(.footnote)
                            Spacer()
                            Text("Unknown / check on site").font(.footnote.weight(.semibold)).foregroundStyle(Theme.warn)
                        }
                    }
                } else {
                    HStack(spacing: 10) {
                        Image(systemName: "checkmark.circle").foregroundStyle(Theme.ok)
                        Text("No fall events").foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}

// MARK: - Not paired

private struct NotPairedCard: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "qrcode.viewfinder")
                .font(.system(size: 56, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 104, height: 104)
                .background(Theme.brandGradient, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
            Text("Pair with your computer").font(.title2.weight(.bold))
            VStack(alignment: .leading, spacing: 10) {
                step(1, "Start the monitoring program on the computer.")
                step(2, "Open the Camera app and scan the QR code on the computer's monitor page.")
                step(3, "Tap the TECH12000 banner to finish pairing.")
            }
            Button { app.tab = .settings } label: {
                Text("Enter address manually").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .padding(.top, 8)
    }

    private func step(_ n: Int, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(n)").font(.footnote.weight(.bold)).foregroundStyle(.white)
                .frame(width: 24, height: 24).background(Theme.blue, in: Circle())
            Text(text).font(.subheadline)
        }
    }
}

import SwiftUI

struct EventListView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            List(app.events) { ev in
                NavigationLink { EventDetailView(event: ev) } label: { EventRow(event: ev) }
            }
            .listStyle(.insetGrouped)
            .overlay {
                if app.events.isEmpty {
                    ContentUnavailableView("No events yet", systemImage: "checkmark.shield",
                                           description: Text("Fall events detected by the computer will appear here."))
                }
            }
            .navigationTitle("Events")
            .refreshable { await app.refresh() }
        }
    }
}

private struct EventRow: View {
    let event: FallEvent
    var body: some View {
        let color = event.is_test ? Theme.warn : Theme.bad
        HStack(spacing: 12) {
            Image(systemName: "figure.fall")
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 38, height: 38)
                .background(color.gradient, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(event.is_test ? "Simulated test" : "Possible fall").font(.subheadline.weight(.semibold))
                    if event.is_test { Pill(text: "TEST") }
                }
                Text(Labels.deploy(event.deploy_status)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 3) {
                Text(event.date, style: .time).font(.caption.weight(.medium))
                Text(event.date, format: .dateTime.month(.abbreviated).day()).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct EventDetailView: View {
    @EnvironmentObject var app: AppState
    @State var event: FallEvent
    @State private var note: String?

    var body: some View {
        let color = event.is_test ? Theme.warn : Theme.bad
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Image(systemName: "figure.fall")
                        .font(.system(size: 34, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 64, height: 64)
                        .background(color.gradient, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    Text(event.englishMessage).font(.body)
                }
                .padding(.vertical, 6)
            }
            Section("Details") {
                LabeledContent("Time", value: event.date.formatted(date: .abbreviated, time: .standard))
                LabeledContent("Mode at the time", value: Labels.mode(event.mode))
                LabeledContent("Deploy command", value: Labels.deploy(event.deploy_status))
                LabeledContent("Actual deployment") {
                    Text("Unknown / check on site").foregroundStyle(Theme.warn)
                }
                LabeledContent("Event ID", value: String(event.event_id.prefix(8)))
            }
            if let note { Section { Label(note, systemImage: "info.circle").font(.footnote).foregroundStyle(.secondary) } }
        }
        .navigationTitle(event.is_test ? "Simulated test" : "Fall event")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            // Try to fetch the latest copy from the computer; if that fails, say clearly that this is the local copy.
            guard let p = app.pairing else { return }
            do { event = try await APIClient(pairing: p).event(id: event.event_id) }
            catch { note = "Can't reach the computer. This is the copy saved on the phone and may be out of date." }
        }
    }
}

/// Full-screen alert shown while the app is open. This is not a lock-screen push.
struct AlertView: View {
    @Environment(\.dismiss) private var dismiss
    let event: FallEvent
    @State private var pulse = false

    var body: some View {
        let colors: [Color] = event.is_test
            ? [Color.orange, Color(red: 0.85, green: 0.35, blue: 0.05)]
            : [Theme.bad, Color(red: 0.45, green: 0.05, blue: 0.12)]
        VStack(spacing: 28) {
            Spacer()
            ZStack {
                Circle().fill(.white.opacity(0.12)).frame(width: 220, height: 220).scaleEffect(pulse ? 1.15 : 0.9)
                Circle().fill(.white.opacity(0.18)).frame(width: 160, height: 160).scaleEffect(pulse ? 1.05 : 0.95)
                Image(systemName: "figure.fall").font(.system(size: 76, weight: .bold))
            }
            .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever()) { pulse = true } }

            VStack(spacing: 10) {
                if event.is_test {
                    Text("SIMULATED TEST").font(.caption.weight(.heavy)).tracking(1.2)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(.white.opacity(0.25), in: Capsule())
                }
                Text("Possible fall").font(.system(size: 40, weight: .bold, design: .rounded))
                Text(event.englishMessage).font(.body).multilineTextAlignment(.center).opacity(0.92)
                Text(event.date.formatted(date: .abbreviated, time: .standard)).font(.footnote).opacity(0.75)
            }
            .padding(.horizontal, 28)
            Spacer()
            Button { dismiss() } label: {
                Text("Got it").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 16)
                    .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .foregroundStyle(colors[0])
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 12)
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LinearGradient(colors: colors, startPoint: .top, endPoint: .bottom).ignoresSafeArea())
    }
}

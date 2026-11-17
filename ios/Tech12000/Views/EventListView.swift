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
        let color = event.airbagTriggered ? Theme.bad : (event.is_test ? Theme.warn : Theme.bad)
        HStack(spacing: 12) {
            Image(systemName: event.airbagTriggered ? "exclamationmark.shield.fill" : "figure.fall")
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 38, height: 38)
                .background(color.gradient, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(event.airbagTriggered ? "Airbag triggered" : (event.is_test ? "Simulated test" : "Possible fall"))
                        .font(.subheadline.weight(.semibold))
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
/// For airbag events the siren keeps sounding until the user acknowledges.
struct AlertView: View {
    @Environment(\.dismiss) private var dismiss
    let event: FallEvent
    @State private var pulse = false

    var body: some View {
        let airbag = event.airbagTriggered
        let colors: [Color] = airbag
            ? [Color(red: 0.75, green: 0.02, blue: 0.08), Color(red: 0.30, green: 0.0, blue: 0.05)]
            : event.is_test
                ? [Color.orange, Color(red: 0.85, green: 0.35, blue: 0.05)]
                : [Theme.bad, Color(red: 0.45, green: 0.05, blue: 0.12)]
        VStack(spacing: 28) {
            Spacer()
            ZStack {
                Circle().fill(.white.opacity(0.12)).frame(width: 220, height: 220).scaleEffect(pulse ? 1.15 : 0.9)
                Circle().fill(.white.opacity(0.18)).frame(width: 160, height: 160).scaleEffect(pulse ? 1.05 : 0.95)
                Image(systemName: airbag ? "exclamationmark.shield.fill" : "figure.fall")
                    .font(.system(size: 76, weight: .bold))
                    .symbolEffect(.pulse, options: .repeating, isActive: airbag)
            }
            .onAppear { withAnimation(.easeInOut(duration: airbag ? 0.5 : 0.9).repeatForever()) { pulse = true } }

            VStack(spacing: 10) {
                HStack(spacing: 6) {
                    if event.is_test { badge("SIMULATED TEST") }
                    if event.airbagDemo { badge("DEMO") }
                }
                Text(airbag ? "Airbag triggered" : "Possible fall")
                    .font(.system(size: 40, weight: .heavy, design: .rounded))
                    .minimumScaleFactor(0.7).lineLimit(1)
                if airbag {
                    Text("Release command sent by the computer.\nActual inflation is unknown — go now.")
                        .font(.headline).multilineTextAlignment(.center)
                }
                Text(event.englishMessage).font(.body).multilineTextAlignment(.center).opacity(0.9)
                Text(event.date.formatted(date: .abbreviated, time: .standard)).font(.footnote).opacity(0.75)
            }
            .padding(.horizontal, 28)
            Spacer()
            Button {
                AlarmPlayer.shared.stop()
                dismiss()
            } label: {
                Label(airbag ? "Stop alarm" : "Got it", systemImage: airbag ? "speaker.slash.fill" : "checkmark")
                    .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 16)
                    .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .foregroundStyle(colors[0])
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 12)
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LinearGradient(colors: colors, startPoint: .top, endPoint: .bottom).ignoresSafeArea())
        .interactiveDismissDisabled(airbag)
        .onDisappear { AlarmPlayer.shared.stop() }
    }

    private func badge(_ t: String) -> some View {
        Text(t).font(.caption.weight(.heavy)).tracking(1.2)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(.white.opacity(0.25), in: Capsule())
    }
}

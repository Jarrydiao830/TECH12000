import SwiftUI
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @AppStorage("keepAwake") private var keepAwake = true
    @State private var host = ""
    @State private var port = "8000"
    @State private var token = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 14) {
                        Image(systemName: app.pairing == nil ? "link.badge.plus" : "desktopcomputer")
                            .font(.title2).foregroundStyle(.white)
                            .frame(width: 48, height: 48)
                            .background(Theme.brandGradient, in: RoundedRectangle(cornerRadius: 13, style: .continuous))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(app.pairing == nil ? "Not paired" : "Paired").font(.headline)
                            Text(app.pairing.map { "\($0.host):\($0.port)" } ?? "Scan the QR code or enter details below")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if app.pairing != nil {
                            Circle().fill(app.online ? Theme.ok : Theme.bad).frame(width: 10, height: 10)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section {
                    TextField("Computer address, e.g. 192.168.1.20", text: $host)
                        .keyboardType(.numbersAndPunctuation).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Port", text: $port).keyboardType(.numberPad)
                    SecureField("Pairing token", text: $token)
                    Button("Save and connect") {
                        if let p = Int(port) { app.apply(Pairing(host: host.trimmingCharacters(in: .whitespaces), port: p, token: token)) }
                    }.disabled(host.isEmpty || token.isEmpty || Int(port) == nil)
                    if app.pairing != nil { Button("Unpair", role: .destructive) { app.unpair() } }
                } header: { Text("Connection") } footer: {
                    Text("You can also pair by scanning the QR code on the computer's monitor page with the Camera app. The phone and computer must be on the same Wi-Fi, and the network must allow devices to reach each other.")
                }

                Section {
                    Toggle(isOn: $keepAwake) {
                        Label("Keep screen on", systemImage: "sun.max.fill")
                    }
                    .onChange(of: keepAwake) { _, on in UIApplication.shared.isIdleTimerDisabled = on }
                } header: { Text("Demo") } footer: {
                    Text("Alerts only arrive while this app is open. Keep the screen on and leave the app in front during a demo.")
                }

                Section {
                    LabeledContent("Notifications", value: authText)
                    if app.notificationAuth == .notDetermined {
                        Button("Allow notifications") { Task { await app.requestNotificationAuth() } }
                    }
                } header: { Text("Notifications") } footer: {
                    Text("Alerts arrive while the app is open, and for a short time after you leave it. They can't arrive once iOS suspends or closes the app — that needs push notifications (APNs), which aren't set up.")
                }

                Section("About") {
                    LabeledContent("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—")
                    Text("Research prototype. \"Command sent\" does not mean the airbag deployed — always check on site.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                if let p = app.pairing { host = p.host; port = String(p.port); token = p.token }
                Task { await app.refreshNotificationAuth() }
            }
        }
    }

    private var authText: String {
        switch app.notificationAuth {
        case .authorized, .provisional, .ephemeral: "Allowed"
        case .denied: "Denied (turn on in iOS Settings)"
        default: "Not asked yet"
        }
    }
}

import SwiftUI
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @State private var host = ""
    @State private var port = "8000"
    @State private var token = ""

    var body: some View {
        NavigationStack {
            Form {
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
                    LabeledContent("Notifications", value: authText)
                    if app.notificationAuth == .notDetermined {
                        Button("Allow notifications") { Task { await app.requestNotificationAuth() } }
                    }
                } header: { Text("Notifications") } footer: {
                    Text("Alerts arrive while the app is open, and for a short time after you leave it. They can't arrive once iOS suspends the app — that needs push notifications (APNs), which aren't set up yet.")
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

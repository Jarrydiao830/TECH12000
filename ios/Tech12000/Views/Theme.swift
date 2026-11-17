import SwiftUI

/// Shared colors and small building blocks for a consistent look.
enum Theme {
    static let teal = Color(red: 0.078, green: 0.722, blue: 0.651)
    static let blue = Color(red: 0.059, green: 0.369, blue: 0.549)
    static let navy = Color(red: 0.043, green: 0.145, blue: 0.271)
    static let ok = Color(red: 0.13, green: 0.70, blue: 0.45)
    static let warn = Color.orange
    static let bad = Color(red: 0.90, green: 0.22, blue: 0.24)
    static let idle = Color.gray

    static let brandGradient = LinearGradient(colors: [teal, blue, navy],
                                              startPoint: .topLeading, endPoint: .bottomTrailing)

    /// Visual style for a system state (or for being offline).
    struct StateStyle {
        let title: String
        let icon: String
        let colors: [Color]
        var gradient: LinearGradient { LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing) }
        var tint: Color { colors.first ?? .gray }
    }

    static func style(state: String?, online: Bool) -> StateStyle {
        guard online, let state else {
            return StateStyle(title: "Offline", icon: "wifi.slash", colors: [Color(white: 0.55), Color(white: 0.35)])
        }
        switch state {
        case "ready":
            return StateStyle(title: "All clear", icon: "checkmark.shield.fill", colors: [teal, blue])
        case "suspected_fall":
            return StateStyle(title: "Possible fall", icon: "exclamationmark.triangle.fill", colors: [.orange, Color(red: 0.85, green: 0.42, blue: 0.1)])
        case "triggered":
            return StateStyle(title: "Fall detected", icon: "figure.fall", colors: [bad, Color(red: 0.6, green: 0.08, blue: 0.15)])
        case "fault":
            return StateStyle(title: "Fault", icon: "xmark.octagon.fill", colors: [Color(red: 0.75, green: 0.25, blue: 0.3), Color(red: 0.35, green: 0.12, blue: 0.2)])
        default:
            return StateStyle(title: "Starting up", icon: "hourglass", colors: [Color(white: 0.6), blue])
        }
    }

    static func deviceIcon(_ key: String) -> String {
        ["wristband": "applewatch", "radar": "dot.radiowaves.left.and.right",
         "receiver": "antenna.radiowaves.left.and.right", "servo": "gearshape.2.fill"][key] ?? "cpu"
    }
}

/// Rounded card container used across screens.
struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

struct SectionLabel: View {
    let text: String
    var body: some View {
        Text(text.uppercased())
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
            .tracking(0.6)
            .padding(.leading, 4)
    }
}

/// Small colored capsule label.
struct Pill: View {
    let text: String
    var color: Color = .orange
    var body: some View {
        Text(text)
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.18), in: Capsule())
            .foregroundStyle(color)
    }
}

/// A dot that gently pulses while the connection is live.
struct LiveDot: View {
    let live: Bool
    @State private var pulse = false
    var body: some View {
        Circle()
            .fill(live ? Color.white : Color.white.opacity(0.4))
            .frame(width: 8, height: 8)
            .overlay(Circle().stroke(Color.white.opacity(live ? 0.6 : 0), lineWidth: 2).scaleEffect(pulse ? 2.4 : 1).opacity(pulse ? 0 : 1))
            .onAppear { withAnimation(.easeOut(duration: 1.4).repeatForever(autoreverses: false)) { pulse = true } }
    }
}

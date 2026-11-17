import AVFoundation
import AudioToolbox

/// Looping two-tone siren plus vibration for the airbag alarm.
/// Uses the .playback audio category so it sounds even when the ring/silent switch is on silent.
/// Runs only while the app is open; stop() is called when the user acknowledges.
@MainActor
final class AlarmPlayer {
    static let shared = AlarmPlayer()

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var buffer: AVAudioPCMBuffer?
    private var vibrateTimer: Timer?
    private(set) var isPlaying = false

    private init() {
        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        buffer = Self.makeSiren(format: format)
    }

    func start() {
        guard !isPlaying, let buffer else { return }
        isPlaying = true
        do {
            let s = AVAudioSession.sharedInstance()
            try s.setCategory(.playback, mode: .default, options: [.duckOthers])
            try s.setActive(true)
            if !engine.isRunning { try engine.start() }
            player.scheduleBuffer(buffer, at: nil, options: .loops)
            player.play()
        } catch {
            // Sound failed (e.g. audio in use); vibration and the screen still alert the user.
        }
        AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)
        vibrateTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { _ in
            AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)
        }
    }

    func stop() {
        guard isPlaying else { return }
        isPlaying = false
        vibrateTimer?.invalidate()
        vibrateTimer = nil
        player.stop()
        engine.stop()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    /// One second of siren: 0.5 s at 960 Hz, then 0.5 s at 720 Hz, with short fades to avoid clicks.
    private static func makeSiren(format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let rate = format.sampleRate
        let frames = AVAudioFrameCount(rate)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames),
              let ch = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = frames
        let half = Int(frames) / 2
        let fade = Int(rate * 0.01)
        var phase = 0.0
        for i in 0..<Int(frames) {
            let freq = i < half ? 960.0 : 720.0
            phase += 2 * .pi * freq / rate
            let pos = i % half
            let env = min(1, Double(pos) / Double(fade), Double(half - pos) / Double(fade))
            // Square-ish tone (sine + odd harmonic) is more piercing than a pure sine.
            let v = sin(phase) + 0.3 * sin(3 * phase)
            ch[i] = Float(0.6 * env * v)
        }
        return buf
    }
}

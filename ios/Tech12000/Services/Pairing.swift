import Foundation
import Security

/// 配对信息：主机/端口存 UserDefaults，令牌存钥匙串。
struct Pairing: Equatable {
    var host: String
    var port: Int
    var token: String

    var httpBase: URL? { URL(string: "http://\(host):\(port)") }
    var wsURL: URL? { URL(string: "ws://\(host):\(port)/api/v1/ws") }

    /// 解析电脑界面二维码里的 tech12000://pair?host=..&port=..&token=..
    static func from(url: URL) -> Pairing? {
        guard url.scheme == "tech12000", url.host == "pair",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        let d = Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { a, _ in a })
        guard let h = d["host"], !h.isEmpty, let p = Int(d["port"] ?? ""), let t = d["token"], !t.isEmpty
        else { return nil }
        return Pairing(host: h, port: p, token: t)
    }

    static func load() -> Pairing? {
        let u = UserDefaults.standard
        guard let h = u.string(forKey: "host"), let t = Keychain.get("pairing_token") else { return nil }
        let p = u.integer(forKey: "port")
        return Pairing(host: h, port: p == 0 ? 8000 : p, token: t)
    }

    func save() {
        UserDefaults.standard.set(host, forKey: "host")
        UserDefaults.standard.set(port, forKey: "port")
        Keychain.set("pairing_token", token)
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: "host")
        UserDefaults.standard.removeObject(forKey: "port")
        Keychain.delete("pairing_token")
    }
}

enum Keychain {
    private static let service = "tech12000"

    static func set(_ key: String, _ value: String) {
        delete(key)
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service, kSecAttrAccount as String: key,
                                kSecValueData as String: Data(value.utf8)]
        SecItemAdd(q as CFDictionary, nil)
    }

    static func get(_ key: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service, kSecAttrAccount as String: key,
                                kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }

    static func delete(_ key: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service, kSecAttrAccount as String: key]
        SecItemDelete(q as CFDictionary)
    }
}

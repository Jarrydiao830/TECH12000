import Foundation

struct APIClient {
    let pairing: Pairing

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let base = pairing.httpBase, let url = URL(string: path, relativeTo: base) else {
            throw URLError(.badURL)
        }
        var req = URLRequest(url: url, timeoutInterval: 5)
        req.setValue("Bearer \(pairing.token)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        if http.statusCode == 401 { throw URLError(.userAuthenticationRequired) }
        guard http.statusCode == 200 else { throw URLError(.badServerResponse) }
        return try JSONDecoder().decode(T.self, from: data)
    }

    func status() async throws -> SystemStatus { try await get("/api/v1/status") }
    func events(limit: Int = 20) async throws -> [FallEvent] {
        let l: EventList = try await get("/api/v1/events?limit=\(limit)")
        return l.events
    }
    func event(id: String) async throws -> FallEvent { try await get("/api/v1/events/\(id)") }
}

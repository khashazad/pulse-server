import Foundation

actor DietTrackerClient {
    private let baseURL: URL
    private let apiKey: String
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: URL, apiKey: String, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.session = session
        self.decoder = JSONDecoder.dietTrackerDefault()
    }

    // MARK: - existing read endpoints

    func summary(date: Date) async throws -> DailySummary {
        let path = "/summary/\(DateOnly.string(from: date))"
        let url = try makeURL(path: path, query: [URLQueryItem(name: "user_key", value: Constants.userKey)])
        return try await fetch(url: url)
    }

    func logs(from: Date, to: Date) async throws -> LogsList {
        let url = try makeURL(
            path: "/logs",
            query: [
                URLQueryItem(name: "from", value: DateOnly.string(from: from)),
                URLQueryItem(name: "to", value: DateOnly.string(from: to)),
                URLQueryItem(name: "user_key", value: Constants.userKey),
            ]
        )
        return try await fetch(url: url)
    }

    // MARK: - containers

    func listContainers() async throws -> [Container] {
        let url = try makeURL(
            path: "/containers",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        let list: ContainersList = try await fetch(url: url)
        return list.containers
    }

    func getContainer(id: UUID) async throws -> Container {
        let url = try makeURL(
            path: "/containers/\(id.uuidString.lowercased())",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        return try await fetch(url: url)
    }

    func createContainer(name: String, tareWeightG: Double) async throws -> Container {
        let url = try makeURL(
            path: "/containers",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        let body: [String: Any] = ["name": name, "tare_weight_g": tareWeightG]
        let data = try JSONSerialization.data(withJSONObject: body, options: [])
        return try await sendJSON(url: url, method: "POST", body: data)
    }

    func updateContainer(id: UUID, name: String?, tareWeightG: Double?) async throws -> Container {
        var fields: [String: Any] = [:]
        if let name { fields["name"] = name }
        if let tareWeightG { fields["tare_weight_g"] = tareWeightG }
        let url = try makeURL(
            path: "/containers/\(id.uuidString.lowercased())",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        let data = try JSONSerialization.data(withJSONObject: fields, options: [])
        return try await sendJSON(url: url, method: "PATCH", body: data)
    }

    func deleteContainer(id: UUID) async throws {
        let url = try makeURL(
            path: "/containers/\(id.uuidString.lowercased())",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        try await sendNoBody(request: req)
    }

    func uploadContainerPhoto(id: UUID, jpegData: Data) async throws {
        let url = try makeURL(
            path: "/containers/\(id.uuidString.lowercased())/photo",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        let boundary = "----DietTrackerBoundary\(UUID().uuidString)"
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.httpBody = Self.multipartBody(
            boundary: boundary,
            fieldName: "file",
            filename: "photo.jpg",
            mimeType: "image/jpeg",
            data: jpegData
        )
        try await sendNoBody(request: req)
    }

    func deleteContainerPhoto(id: UUID) async throws {
        let url = try makeURL(
            path: "/containers/\(id.uuidString.lowercased())/photo",
            query: [URLQueryItem(name: "user_key", value: Constants.userKey)]
        )
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        try await sendNoBody(request: req)
    }

    /// Builds an authorized `URLRequest` for the photo endpoint. Used by views
    /// that fetch image bytes directly through `URLSession`.
    nonisolated func containerPhotoRequest(id: UUID, size: ContainerPhotoSize) -> URLRequest {
        var comps = URLComponents(
            url: baseURL.appendingPathComponent("/containers/\(id.uuidString.lowercased())/photo"),
            resolvingAgainstBaseURL: false
        )!
        comps.queryItems = [
            URLQueryItem(name: "size", value: size.rawValue),
            URLQueryItem(name: "user_key", value: Constants.userKey),
        ]
        var req = URLRequest(url: comps.url!)
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        return req
    }

    // MARK: - private helpers

    private func makeURL(path: String, query: [URLQueryItem]) throws -> URL {
        guard var comps = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw DietTrackerError.notConfigured
        }
        comps.queryItems = query
        guard let url = comps.url else { throw DietTrackerError.notConfigured }
        return url
    }

    private func fetch<T: Decodable>(url: URL) async throws -> T {
        var req = URLRequest(url: url)
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await sendDecoded(request: req)
    }

    private func sendJSON<T: Decodable>(url: URL, method: String, body: Data) async throws -> T {
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.httpBody = body
        return try await sendDecoded(request: req)
    }

    private func sendDecoded<T: Decodable>(request: URLRequest) async throws -> T {
        let (data, http) = try await raw(request: request)
        try mapStatus(http.statusCode)
        do {
            return try decoder.decode(T.self, from: data)
        } catch let decodingError {
            throw DietTrackerError.decoding(String(describing: decodingError))
        }
    }

    private func sendNoBody(request: URLRequest) async throws {
        let (_, http) = try await raw(request: request)
        try mapStatus(http.statusCode)
    }

    private func raw(request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw DietTrackerError.server(status: -1)
            }
            return (data, http)
        } catch let urlError as URLError {
            throw DietTrackerError.network(urlError)
        }
    }

    private func mapStatus(_ status: Int) throws {
        switch status {
        case 200..<300: return
        case 401, 403: throw DietTrackerError.unauthorized
        case 404:      throw DietTrackerError.notFound
        case 413:      throw DietTrackerError.payloadTooLarge
        default:       throw DietTrackerError.server(status: status)
        }
    }

    private static func multipartBody(
        boundary: String,
        fieldName: String,
        filename: String,
        mimeType: String,
        data: Data
    ) -> Data {
        var body = Data()
        let lineBreak = "\r\n"
        body.append("--\(boundary)\(lineBreak)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(filename)\"\(lineBreak)".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\(lineBreak)\(lineBreak)".data(using: .utf8)!)
        body.append(data)
        body.append("\(lineBreak)--\(boundary)--\(lineBreak)".data(using: .utf8)!)
        return body
    }
}

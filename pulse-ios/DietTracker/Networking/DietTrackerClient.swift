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

    func meals() async throws -> [MealSummary] {
        let url = try makeURL(path: "/meals", query: [URLQueryItem(name: "user_key", value: Constants.userKey)])
        let envelope: MealsListResponse = try await fetch(url: url)
        return envelope.meals
    }

    func meal(id: UUID) async throws -> Meal {
        let url = try makeURL(path: "/meals/\(id.uuidString.lowercased())", query: [URLQueryItem(name: "user_key", value: Constants.userKey)])
        return try await fetch(url: url)
    }

    // MARK: - private

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

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch let urlError as URLError {
            throw DietTrackerError.network(urlError)
        }

        guard let http = response as? HTTPURLResponse else {
            throw DietTrackerError.server(status: -1)
        }

        switch http.statusCode {
        case 200..<300:
            do {
                return try decoder.decode(T.self, from: data)
            } catch let decodingError {
                throw DietTrackerError.decoding(String(describing: decodingError))
            }
        case 401, 403:
            throw DietTrackerError.unauthorized
        case 404:
            throw DietTrackerError.notFound
        case 500...:
            throw DietTrackerError.server(status: http.statusCode)
        default:
            throw DietTrackerError.server(status: http.statusCode)
        }
    }
}

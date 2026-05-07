import Foundation
import Observation

@Observable
final class DayMacroModel {
    let date: Date
    private(set) var state: LoadState<DailySummary> = .idle
    private weak var settings: AppSettings?

    init(date: Date, settings: AppSettings) {
        self.date = date
        self.settings = settings
    }

    func load() async {
        guard let client = settings?.makeClient() else {
            state = .failed(.notConfigured)
            return
        }
        state = .loading
        do {
            let summary = try await client.summary(date: date)
            state = .loaded(summary)
        } catch let error as DietTrackerError {
            state = .failed(error)
        } catch {
            state = .failed(.server(status: -1))
        }
    }
}

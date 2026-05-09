import Foundation
import Observation

@Observable
final class MealsModel {
    private(set) var state: LoadState<[MealSummary]> = .idle
    private weak var settings: AppSettings?

    init(settings: AppSettings) {
        self.settings = settings
    }

    func load() async {
        guard let client = settings?.makeClient() else {
            state = .failed(.notConfigured)
            return
        }
        state = .loading
        do {
            let meals = try await client.meals()
            state = .loaded(meals)
        } catch let error as DietTrackerError {
            state = .failed(error)
        } catch {
            state = .failed(.server(status: -1))
        }
    }
}

@Observable
final class MealDetailModel {
    let mealId: UUID
    private(set) var state: LoadState<Meal> = .idle
    private weak var settings: AppSettings?

    init(mealId: UUID, settings: AppSettings) {
        self.mealId = mealId
        self.settings = settings
    }

    func load() async {
        guard let client = settings?.makeClient() else {
            state = .failed(.notConfigured)
            return
        }
        if case .loaded = state {} else { state = .loading }
        do {
            let fresh = try await client.meal(id: mealId)
            state = .loaded(fresh)
        } catch let error as DietTrackerError {
            if case .loaded = state { return }
            state = .failed(error)
        } catch {
            if case .loaded = state { return }
            state = .failed(.server(status: -1))
        }
    }
}

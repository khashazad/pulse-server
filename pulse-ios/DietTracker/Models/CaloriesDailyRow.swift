import Foundation

struct CaloriesDailyRow: Codable, Hashable {
    let date: Date
    let calories: Int

    enum CodingKeys: String, CodingKey {
        case date = "log_date"
        case calories
    }
}

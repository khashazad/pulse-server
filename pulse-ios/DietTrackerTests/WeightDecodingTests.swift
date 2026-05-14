import XCTest
@testable import DietTracker

final class WeightDecodingTests: XCTestCase {

    private func fixture(_ name: String) throws -> Data {
        let url = Bundle(for: Self.self).url(forResource: name, withExtension: "json")!
        return try Data(contentsOf: url)
    }

    func testDecodeWeightEntries() throws {
        let data = try fixture("weight_entries")
        let entries = try JSONDecoder.dietTrackerDefault().decode([WeightEntry].self, from: data)
        XCTAssertEqual(entries.count, 2)
        XCTAssertEqual(entries[0].weightLb, 180.50, accuracy: 0.001)
        XCTAssertEqual(entries[0].sourceUnit, .lb)
        XCTAssertEqual(entries[1].sourceUnit, .kg)
    }

    func testDecodeCaloriesDaily() throws {
        let data = try fixture("calories_daily")
        let rows = try JSONDecoder.dietTrackerDefault().decode([CaloriesDailyRow].self, from: data)
        XCTAssertEqual(rows.count, 3)
        XCTAssertEqual(rows[1].calories, 2100)
    }
}

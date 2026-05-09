import XCTest
@testable import DietTracker

final class PrepModelTests: XCTestCase {

    private func mkContainer(tare: Double, name: String = "X") -> Container {
        Container(
            id: UUID(),
            userKey: "khash",
            name: name,
            normalizedName: name.lowercased(),
            tareWeightG: tare,
            hasPhoto: false,
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    func testNetEqualsTotalMinusTare() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 412)
        m.totalGrams = 1450
        m.portions = 1
        XCTAssertEqual(m.netGrams ?? 0, 1038, accuracy: 0.001)
        XCTAssertEqual(m.perPortionGrams ?? 0, 1038, accuracy: 0.001)
    }

    func testPortionsDivision() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 412)
        m.totalGrams = 1450
        m.portions = 5
        XCTAssertEqual(m.netGrams ?? 0, 1038, accuracy: 0.001)
        XCTAssertEqual(m.perPortionGrams ?? 0, 207.6, accuracy: 0.001)
    }

    func testNegativeNetClampsToZero() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 1000)
        m.totalGrams = 500
        m.portions = 2
        XCTAssertEqual(m.netGrams, 0)
        XCTAssertEqual(m.perPortionGrams, 0)
    }

    func testNoTotalReturnsNil() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 412)
        m.totalGrams = nil
        XCTAssertNil(m.netGrams)
        XCTAssertNil(m.perPortionGrams)
    }

    func testPortionsAtLeastOne() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 100)
        m.totalGrams = 300
        m.portions = 0
        XCTAssertEqual(m.perPortionGrams, 200)
    }

    func testNoSelectionMeansZeroTare() {
        // Regression for the deleted-container drift: with no selection,
        // tare is 0, so net == total. Previously a stale tareWeightG could
        // remain even after the selection was cleared.
        let m = PrepModel()
        m.selectedContainer = nil
        m.totalGrams = 500
        XCTAssertEqual(m.netGrams, 500)
    }

    func testClearingSelectionAlsoZeroesTare() {
        let m = PrepModel()
        m.selectedContainer = mkContainer(tare: 412)
        m.totalGrams = 1000
        XCTAssertEqual(m.netGrams, 588)
        m.selectedContainer = nil
        XCTAssertEqual(m.netGrams, 1000, "tare must drop to 0 when selection clears")
    }
}

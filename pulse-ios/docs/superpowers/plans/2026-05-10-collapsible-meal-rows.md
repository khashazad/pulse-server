# Collapsible Meal Rows on Day View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render meal-sourced entries on the day view as a single tap-to-expand row labelled with the meal name. When the same meal is logged multiple times in one day, collapse all instances into a single row with a `×N` quantity badge on the right and a summed kcal total. Items are shown once (most recent instance) — never duplicated per instance.

**Architecture:** Pure Swift transform `groupDayEntries(_:) -> [DayRow]` turns `[FoodEntry]` into a mixed list of `.single(FoodEntry)` and `.meal(MealGroup)`. `DayMacroView.entriesCard` renders that list, switching between the existing `EntryRow` and a new `MealGroupRow`. No view-model changes; grouping runs at view time off `DailySummary.entries`.

**Tech Stack:** SwiftUI (iOS 17), `@Observable` view models (no Combine), Swift 5.9, XCTest with `StubURLProtocol` for client-layer tests.

**Spec:** `docs/superpowers/specs/2026-05-10-collapsible-meal-rows-design.md`

**Companion plan (server):** `../diet-tracker-server/docs/superpowers/plans/2026-05-10-meal-link-on-entries.md` — server work surfaces the `meal_id`/`meal_name` fields on `/days/{date}`. iOS code treats both as optional, so this plan can be implemented and tested in isolation against fixtures even before the server ships.

---

## File Structure

**Create:**
- `DietTracker/State/DayEntriesGrouping.swift` — pure grouping function and `DayRow` / `MealGroup` types.
- `DietTracker/Views/Components/MealGroupRow.swift` — collapsed/expanded meal row view.
- `DietTrackerTests/DayEntriesGroupingTests.swift` — pure-function unit tests for the grouping algorithm.

**Modify:**
- `DietTracker/Models/FoodEntry.swift` — add `mealId: UUID?` and `mealName: String?`.
- `DietTracker/Views/DayMacroView.swift` — `entriesCard(_:)` switches over `DayRow`; entries-header count becomes logical-row count.
- `DietTrackerTests/Fixtures/summary.json` — add a meal-logged group (3 entries sharing `entry_group_id` + `meal_id`/`meal_name`) and a repeat instance, alongside the existing single entries.
- `DietTrackerTests/DecodingTests.swift` — extend `testDecodeDailySummary` to assert the new optional fields decode correctly.

**No `project.yml` edit needed** — the project uses path-based source discovery (`sources: [path: DietTracker]`), so new files under `DietTracker/State/` and `DietTracker/Views/Components/` are picked up automatically. `xcodegen generate` still must be run after creating new files to refresh the (gitignored) Xcode project.

---

## Task 1: `FoodEntry` model + fixture + decoder test

**Files:**
- Modify: `DietTracker/Models/FoodEntry.swift`
- Modify: `DietTrackerTests/Fixtures/summary.json`
- Modify: `DietTrackerTests/DecodingTests.swift`

- [ ] **Step 1: Update the fixture to include meal-linked and repeat-meal entries**

Replace `DietTrackerTests/Fixtures/summary.json` with:

```json
{
  "date": "2026-05-06",
  "target": {
    "calories": 2200,
    "protein_g": 150.0,
    "carbs_g": 250.0,
    "fat_g": 70.0
  },
  "consumed": {
    "calories": 1280,
    "protein_g": 107.0,
    "carbs_g": 131.0,
    "fat_g": 37.0
  },
  "remaining": {
    "calories": 920,
    "protein_g": 43.0,
    "carbs_g": 119.0,
    "fat_g": 33.0
  },
  "entries": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "33333333-3333-3333-3333-333333333333",
      "display_name": "Oats, raw",
      "quantity_text": "80 g",
      "normalized_quantity_value": 80.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": 173904,
      "usda_description": "Oats, raw",
      "custom_food_id": null,
      "calories": 320,
      "protein_g": 10.0,
      "carbs_g": 54.0,
      "fat_g": 6.0,
      "meal_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "meal_name": "Breakfast Bowl",
      "consumed_at": "2026-05-06T08:30:00+00:00",
      "created_at": "2026-05-06T08:31:00+00:00"
    },
    {
      "id": "44444444-4444-4444-4444-444444444444",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "33333333-3333-3333-3333-333333333333",
      "display_name": "Greek yogurt",
      "quantity_text": "200 g",
      "normalized_quantity_value": 200.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": 748967,
      "usda_description": "Yogurt, Greek",
      "custom_food_id": null,
      "calories": 130,
      "protein_g": 18.0,
      "carbs_g": 9.0,
      "fat_g": 4.0,
      "meal_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "meal_name": "Breakfast Bowl",
      "consumed_at": "2026-05-06T08:30:00+00:00",
      "created_at": "2026-05-06T08:31:00+00:00"
    },
    {
      "id": "55555555-5555-5555-5555-555555555555",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "66666666-6666-6666-6666-666666666666",
      "display_name": "Oats, raw",
      "quantity_text": "80 g",
      "normalized_quantity_value": 80.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": 173904,
      "usda_description": "Oats, raw",
      "custom_food_id": null,
      "calories": 320,
      "protein_g": 10.0,
      "carbs_g": 54.0,
      "fat_g": 6.0,
      "meal_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "meal_name": "Breakfast Bowl",
      "consumed_at": "2026-05-06T13:00:00+00:00",
      "created_at": "2026-05-06T13:01:00+00:00"
    },
    {
      "id": "77777777-7777-7777-7777-777777777777",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "66666666-6666-6666-6666-666666666666",
      "display_name": "Greek yogurt",
      "quantity_text": "200 g",
      "normalized_quantity_value": 200.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": 748967,
      "usda_description": "Yogurt, Greek",
      "custom_food_id": null,
      "calories": 130,
      "protein_g": 18.0,
      "carbs_g": 9.0,
      "fat_g": 4.0,
      "meal_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "meal_name": "Breakfast Bowl",
      "consumed_at": "2026-05-06T13:00:00+00:00",
      "created_at": "2026-05-06T13:01:00+00:00"
    },
    {
      "id": "88888888-8888-8888-8888-888888888888",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "99999999-9999-9999-9999-999999999999",
      "display_name": "Chicken breast",
      "quantity_text": "150 g",
      "normalized_quantity_value": 150.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": null,
      "usda_description": null,
      "custom_food_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "calories": 240,
      "protein_g": 45.0,
      "carbs_g": 0.0,
      "fat_g": 5.0,
      "meal_id": null,
      "meal_name": null,
      "consumed_at": "2026-05-06T18:00:00+00:00",
      "created_at": "2026-05-06T18:01:00+00:00"
    },
    {
      "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "daily_log_id": "22222222-2222-2222-2222-222222222222",
      "user_key": "khash",
      "entry_group_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
      "display_name": "Almond",
      "quantity_text": "30 g",
      "normalized_quantity_value": 30.0,
      "normalized_quantity_unit": "g",
      "usda_fdc_id": 170567,
      "usda_description": "Nuts, almonds",
      "custom_food_id": null,
      "calories": 140,
      "protein_g": 6.0,
      "carbs_g": 5.0,
      "fat_g": 12.0,
      "consumed_at": "2026-05-06T20:00:00+00:00",
      "created_at": "2026-05-06T20:01:00+00:00"
    }
  ]
}
```

The fixture now contains:
- Two instances of "Breakfast Bowl" (meal_id = `aaaa…`), each with two items (Oats + Yogurt). Six entries from the meal split into two `entry_group_id`s.
- One single non-meal entry (Chicken breast, custom food, no meal link).
- One trailing single entry (Almond) with the `meal_id` / `meal_name` keys absent (tests that the decoder treats them as optional).

Numbers were updated for `consumed`/`remaining` so the totals add up: 320+130+320+130+240+140 = 1280 kcal.

- [ ] **Step 2: Write the failing decoder test**

Edit `DietTrackerTests/DecodingTests.swift`. Replace `testDecodeDailySummary` with:

```swift
    func testDecodeDailySummary() throws {
        let data = try loadFixture("summary")
        let summary = try JSONDecoder.dietTrackerDefault().decode(DailySummary.self, from: data)

        XCTAssertEqual(summary.target.calories, 2200)
        XCTAssertEqual(summary.consumed.calories, 1280)
        XCTAssertEqual(summary.remaining.calories, 920)
        XCTAssertEqual(summary.entries.count, 6)

        let oats = summary.entries[0]
        XCTAssertEqual(oats.displayName, "Oats, raw")
        XCTAssertEqual(oats.calories, 320)
        XCTAssertEqual(oats.proteinG, 10.0)
        XCTAssertEqual(oats.usdaFdcId, 173904)
        XCTAssertNil(oats.customFoodId)
        XCTAssertEqual(oats.mealId?.uuidString.lowercased(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        XCTAssertEqual(oats.mealName, "Breakfast Bowl")

        let chicken = summary.entries[4]
        XCTAssertNil(chicken.usdaFdcId)
        XCTAssertEqual(chicken.customFoodId?.uuidString.lowercased(), "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        XCTAssertNil(chicken.mealId)
        XCTAssertNil(chicken.mealName)

        // Trailing entry omits meal_* keys entirely; they decode as nil.
        let almond = summary.entries[5]
        XCTAssertNil(almond.mealId)
        XCTAssertNil(almond.mealName)
    }
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
xcodegen generate
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  test -only-testing:DietTrackerTests/DecodingTests/testDecodeDailySummary
```

Expected: BUILD FAILURE — `Value of type 'FoodEntry' has no member 'mealId'`.

- [ ] **Step 4: Add `mealId` and `mealName` to `FoodEntry`**

Edit `DietTracker/Models/FoodEntry.swift`:

```swift
import Foundation

struct FoodEntry: Codable, Identifiable, Equatable {
    let id: UUID
    let dailyLogId: UUID
    let userKey: String
    let entryGroupId: UUID
    let displayName: String
    let quantityText: String
    let normalizedQuantityValue: Double?
    let normalizedQuantityUnit: String?
    let usdaFdcId: Int?
    let usdaDescription: String?
    let customFoodId: UUID?
    let calories: Int
    let proteinG: Double
    let carbsG: Double
    let fatG: Double
    let mealId: UUID?
    let mealName: String?
    let consumedAt: Date
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case dailyLogId = "daily_log_id"
        case userKey = "user_key"
        case entryGroupId = "entry_group_id"
        case displayName = "display_name"
        case quantityText = "quantity_text"
        case normalizedQuantityValue = "normalized_quantity_value"
        case normalizedQuantityUnit = "normalized_quantity_unit"
        case usdaFdcId = "usda_fdc_id"
        case usdaDescription = "usda_description"
        case customFoodId = "custom_food_id"
        case calories
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
        case mealId = "meal_id"
        case mealName = "meal_name"
        case consumedAt = "consumed_at"
        case createdAt = "created_at"
    }
}
```

Optional `Codable` properties handle both the "key present with null value" and "key absent" cases correctly.

- [ ] **Step 5: Search for and fix any constructor call sites that need the new fields**

```bash
rg "FoodEntry\(" DietTracker DietTrackerTests
```

Expected matches:
- `DietTracker/Views/Components/EntryRow.swift` — the `#Preview` builds two `FoodEntry` literals.

Update both `FoodEntry(...)` constructions in `EntryRow.swift`'s `#Preview` to insert `mealId: nil, mealName: nil,` between `fatG` and `consumedAt`. Example:

```swift
        EntryRow(entry: FoodEntry(
            id: UUID(), dailyLogId: UUID(), userKey: "khash", entryGroupId: UUID(),
            displayName: "Oats, raw", quantityText: "80 g",
            normalizedQuantityValue: 80, normalizedQuantityUnit: "g",
            usdaFdcId: nil, usdaDescription: nil, customFoodId: nil,
            calories: 320, proteinG: 10, carbsG: 54, fatG: 6,
            mealId: nil, mealName: nil,
            consumedAt: .now, createdAt: .now
        ))
```

Apply the same change to the second preview entry. If `rg` reveals additional constructor sites, update them the same way.

- [ ] **Step 6: Run the test to verify it passes**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  test -only-testing:DietTrackerTests/DecodingTests/testDecodeDailySummary
```

Expected: PASS.

- [ ] **Step 7: Run all decoding tests to make sure nothing else regressed**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  test -only-testing:DietTrackerTests/DecodingTests
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add DietTracker/Models/FoodEntry.swift DietTracker/Views/Components/EntryRow.swift \
        DietTrackerTests/Fixtures/summary.json DietTrackerTests/DecodingTests.swift
git commit -m "feat: add mealId/mealName to FoodEntry"
```

---

## Task 2: Pure grouping function (`DayEntriesGrouping`)

**Files:**
- Create: `DietTracker/State/DayEntriesGrouping.swift`
- Create: `DietTrackerTests/DayEntriesGroupingTests.swift`

- [ ] **Step 1: Write the failing tests for the grouping algorithm**

Create `DietTrackerTests/DayEntriesGroupingTests.swift`:

```swift
import XCTest
@testable import DietTracker

final class DayEntriesGroupingTests: XCTestCase {

    // MARK: - helpers

    private func entry(
        id: String = UUID().uuidString,
        groupId: String,
        name: String = "item",
        kcal: Int = 100,
        proteinG: Double = 5,
        carbsG: Double = 10,
        fatG: Double = 2,
        mealId: String? = nil,
        mealName: String? = nil,
        consumedAt: Date
    ) -> FoodEntry {
        FoodEntry(
            id: UUID(uuidString: id)!,
            dailyLogId: UUID(),
            userKey: "khash",
            entryGroupId: UUID(uuidString: groupId)!,
            displayName: name,
            quantityText: "x",
            normalizedQuantityValue: nil,
            normalizedQuantityUnit: nil,
            usdaFdcId: 1,
            usdaDescription: "x",
            customFoodId: nil,
            calories: kcal,
            proteinG: proteinG,
            carbsG: carbsG,
            fatG: fatG,
            mealId: mealId.flatMap(UUID.init(uuidString:)),
            mealName: mealName,
            consumedAt: consumedAt,
            createdAt: consumedAt
        )
    }

    private func date(_ hour: Int) -> Date {
        var comps = DateComponents()
        comps.year = 2026; comps.month = 5; comps.day = 6
        comps.hour = hour; comps.minute = 0
        return Calendar(identifier: .gregorian).date(from: comps)!
    }

    private let mealA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    private let mealB = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    // MARK: - tests

    func testAllSinglesPassThroughInOrder() {
        let entries = [
            entry(groupId: "11111111-1111-1111-1111-111111111111", name: "A", consumedAt: date(8)),
            entry(groupId: "22222222-2222-2222-2222-222222222222", name: "B", consumedAt: date(13)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 2)
        guard case .single(let a) = rows[0], case .single(let b) = rows[1] else {
            return XCTFail("expected two singles")
        }
        XCTAssertEqual(a.displayName, "A")
        XCTAssertEqual(b.displayName, "B")
    }

    func testSingleMealGroupOfThreeCollapsesAndUsesItsItems() {
        let g = "33333333-3333-3333-3333-333333333333"
        let entries = [
            entry(groupId: g, name: "Oats", kcal: 320, mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g, name: "Yogurt", kcal: 130, mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g, name: "Berries", kcal: 60, mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 1)
        guard case .meal(let group) = rows[0] else { return XCTFail("expected meal") }
        XCTAssertEqual(group.count, 1)
        XCTAssertEqual(group.displayName, "Breakfast")
        XCTAssertEqual(group.items.map { $0.displayName }, ["Oats", "Yogurt", "Berries"])
        XCTAssertEqual(group.totals.calories, 510)
    }

    func testSameMealIdRepeatedTwiceMergesWithCountTwoAndSummedTotals() {
        let g1 = "44444444-4444-4444-4444-444444444444"
        let g2 = "55555555-5555-5555-5555-555555555555"
        let entries = [
            entry(groupId: g1, name: "Oats", kcal: 320, mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g1, name: "Yogurt", kcal: 130, mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g2, name: "Oats", kcal: 320, mealId: mealA, mealName: "Breakfast", consumedAt: date(13)),
            entry(groupId: g2, name: "Yogurt", kcal: 130, mealId: mealA, mealName: "Breakfast", consumedAt: date(13)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 1)
        guard case .meal(let group) = rows[0] else { return XCTFail("expected meal") }
        XCTAssertEqual(group.count, 2)
        XCTAssertEqual(group.totals.calories, 900)
        XCTAssertEqual(group.sortDate, date(13))
    }

    func testMostRecentInstanceItemsWinWhenTemplateChanged() {
        let g1 = "66666666-6666-6666-6666-666666666666"
        let g2 = "77777777-7777-7777-7777-777777777777"
        let entries = [
            entry(groupId: g1, name: "Oats v1", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g1, name: "Yogurt v1", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g2, name: "Oats v2", mealId: mealA, mealName: "Breakfast", consumedAt: date(13)),
            entry(groupId: g2, name: "Yogurt v2", mealId: mealA, mealName: "Breakfast", consumedAt: date(13)),
            entry(groupId: g2, name: "Berries v2", mealId: mealA, mealName: "Breakfast", consumedAt: date(13)),
        ]
        let rows = groupDayEntries(entries)
        guard case .meal(let group) = rows[0] else { return XCTFail("expected meal") }
        XCTAssertEqual(group.count, 2)
        XCTAssertEqual(group.items.map { $0.displayName }, ["Oats v2", "Yogurt v2", "Berries v2"])
    }

    func testNilMealIdMultiItemGroupsStaySeparateAndUseFallbackName() {
        let g1 = "88888888-8888-8888-8888-888888888888"
        let g2 = "99999999-9999-9999-9999-999999999999"
        let entries = [
            entry(groupId: g1, name: "X", consumedAt: date(8)),
            entry(groupId: g1, name: "Y", consumedAt: date(8)),
            entry(groupId: g2, name: "X", consumedAt: date(13)),
            entry(groupId: g2, name: "Y", consumedAt: date(13)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 2)
        for row in rows {
            guard case .meal(let group) = row else { return XCTFail("expected meal") }
            XCTAssertEqual(group.count, 1)
            XCTAssertEqual(group.displayName, "Meal")
            XCTAssertNil(group.mealId)
        }
    }

    func testMixedSinglesAndMealsAreSortedByRepresentativeTime() {
        let coffeeGroup = "11111111-1111-1111-1111-111111111111"
        let breakfastGroup = "aaaaaaaa-1aaa-1aaa-1aaa-aaaaaaaaaaaa"
        let appleGroup = "22222222-2222-2222-2222-222222222222"
        let entries = [
            entry(groupId: coffeeGroup, name: "Coffee", consumedAt: date(7)),
            entry(groupId: breakfastGroup, name: "Oats", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: breakfastGroup, name: "Yogurt", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: appleGroup, name: "Apple", consumedAt: date(15)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 3)
        guard case .single(let coffee) = rows[0],
              case .meal(let breakfast) = rows[1],
              case .single(let apple) = rows[2] else {
            return XCTFail("expected single, meal, single")
        }
        XCTAssertEqual(coffee.displayName, "Coffee")
        XCTAssertEqual(breakfast.displayName, "Breakfast")
        XCTAssertEqual(apple.displayName, "Apple")
    }

    func testDifferentMealIdsAreNotMerged() {
        let g1 = "bbbbbbbb-1bbb-1bbb-1bbb-bbbbbbbbbbbb"
        let g2 = "bbbbbbbb-2bbb-2bbb-2bbb-bbbbbbbbbbbb"
        let entries = [
            entry(groupId: g1, name: "Oats", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g1, name: "Yogurt", mealId: mealA, mealName: "Breakfast", consumedAt: date(8)),
            entry(groupId: g2, name: "Rice", mealId: mealB, mealName: "Lunch", consumedAt: date(13)),
            entry(groupId: g2, name: "Beans", mealId: mealB, mealName: "Lunch", consumedAt: date(13)),
        ]
        let rows = groupDayEntries(entries)
        XCTAssertEqual(rows.count, 2)
        guard case .meal(let breakfast) = rows[0], case .meal(let lunch) = rows[1] else {
            return XCTFail("expected two meals")
        }
        XCTAssertEqual(breakfast.displayName, "Breakfast")
        XCTAssertEqual(lunch.displayName, "Lunch")
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
xcodegen generate
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  test -only-testing:DietTrackerTests/DayEntriesGroupingTests
```

Expected: BUILD FAILURE — `Cannot find 'groupDayEntries' in scope`, `Cannot find type 'MealGroup' in scope`, `Cannot find 'DayRow' in scope`.

- [ ] **Step 3: Implement the grouping module**

Create `DietTracker/State/DayEntriesGrouping.swift`:

```swift
import Foundation

enum DayRow: Identifiable {
    case single(FoodEntry)
    case meal(MealGroup)

    var id: String {
        switch self {
        case .single(let e): return "single:\(e.id.uuidString)"
        case .meal(let g):   return g.id
        }
    }

    var sortDate: Date {
        switch self {
        case .single(let e): return e.consumedAt
        case .meal(let g):   return g.sortDate
        }
    }
}

struct MealGroup: Identifiable {
    let id: String
    let mealId: UUID?
    let displayName: String
    let count: Int
    let items: [FoodEntry]
    let totals: MacroTotals
    let sortDate: Date
}

func groupDayEntries(_ entries: [FoodEntry]) -> [DayRow] {
    // 1. Bucket entries by entry_group_id, preserving stable arrival order within each bucket.
    var bucketOrder: [UUID] = []
    var buckets: [UUID: [FoodEntry]] = [:]
    for entry in entries {
        if buckets[entry.entryGroupId] == nil {
            bucketOrder.append(entry.entryGroupId)
        }
        buckets[entry.entryGroupId, default: []].append(entry)
    }

    // 2. First pass: classify each bucket.
    enum Classified {
        case single(FoodEntry)
        case mealInstance(items: [FoodEntry], mealId: UUID?, mealName: String?, time: Date, entryGroupId: UUID)
    }

    var classified: [Classified] = []
    for groupId in bucketOrder {
        let items = buckets[groupId] ?? []
        if items.count == 1 {
            classified.append(.single(items[0]))
        } else {
            let time = items.map(\.consumedAt).max() ?? .distantPast
            // mealId / mealName are taken from the first item; all items in a log_meal call share them.
            let mealId = items.first?.mealId
            let mealName = items.first?.mealName
            classified.append(.mealInstance(items: items, mealId: mealId, mealName: mealName, time: time, entryGroupId: groupId))
        }
    }

    // 3. Merge meal instances by mealId (only when non-nil); nil-mealId instances stay separate.
    var rows: [DayRow] = []
    var mergedByMealId: [UUID: (groupIndex: Int, MealGroup)] = [:]

    for c in classified {
        switch c {
        case .single(let e):
            rows.append(.single(e))
        case .mealInstance(let items, let mealId, let mealName, let time, let entryGroupId):
            let totals = MacroTotals(
                calories: items.reduce(0) { $0 + $1.calories },
                proteinG: items.reduce(0.0) { $0 + $1.proteinG },
                carbsG: items.reduce(0.0) { $0 + $1.carbsG },
                fatG: items.reduce(0.0) { $0 + $1.fatG }
            )
            if let mealId, let existing = mergedByMealId[mealId] {
                let prev = existing.1
                let useNewItems = time >= prev.sortDate
                let merged = MealGroup(
                    id: prev.id,
                    mealId: prev.mealId,
                    displayName: prev.displayName,
                    count: prev.count + 1,
                    items: useNewItems ? items : prev.items,
                    totals: MacroTotals(
                        calories: prev.totals.calories + totals.calories,
                        proteinG: prev.totals.proteinG + totals.proteinG,
                        carbsG: prev.totals.carbsG + totals.carbsG,
                        fatG: prev.totals.fatG + totals.fatG
                    ),
                    sortDate: max(prev.sortDate, time)
                )
                rows[existing.groupIndex] = .meal(merged)
                mergedByMealId[mealId] = (existing.groupIndex, merged)
            } else {
                let group = MealGroup(
                    id: mealId.map { "meal:\($0.uuidString)" } ?? "anon:\(entryGroupId.uuidString)",
                    mealId: mealId,
                    displayName: (mealName?.isEmpty == false ? mealName! : "Meal"),
                    count: 1,
                    items: items,
                    totals: totals,
                    sortDate: time
                )
                rows.append(.meal(group))
                if let mealId {
                    mergedByMealId[mealId] = (rows.count - 1, group)
                }
            }
        }
    }

    // 4. Stable sort by representative time. `Array.sorted(by:)` is stable in Swift 5.0+.
    return rows.sorted { lhs, rhs in
        if lhs.sortDate == rhs.sortDate { return false }  // preserve insertion order on ties
        return lhs.sortDate < rhs.sortDate
    }
}
```

`MacroTotals` already exists in `DietTracker/Models/MacroTotals.swift`; this file uses it directly.

- [ ] **Step 4: Regenerate the Xcode project**

```bash
xcodegen generate
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  test -only-testing:DietTrackerTests/DayEntriesGroupingTests
```

Expected: PASS for all seven test methods.

- [ ] **Step 6: Commit**

```bash
git add DietTracker/State/DayEntriesGrouping.swift \
        DietTrackerTests/DayEntriesGroupingTests.swift
git commit -m "feat: add DayEntriesGrouping pure transform"
```

---

## Task 3: `MealGroupRow` view

**Files:**
- Create: `DietTracker/Views/Components/MealGroupRow.swift`

This component is exercised manually in the simulator. The grouping logic it depends on is already covered by Task 2's tests; the view is presentational.

- [ ] **Step 1: Create the file**

Create `DietTracker/Views/Components/MealGroupRow.swift`:

```swift
import SwiftUI

struct MealGroupRow: View {
    let group: MealGroup
    @State private var isExpanded = false

    var body: some View {
        VStack(spacing: 0) {
            header
            if isExpanded {
                expandedItems
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    // MARK: - header

    private var header: some View {
        Button(action: toggle) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    chevron
                    VStack(alignment: .leading, spacing: 2) {
                        Text(group.displayName)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(Theme.FG.primary)
                        subtitle
                    }
                    Spacer(minLength: 8)
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text("\(group.totals.calories)")
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(Theme.CTP.mauve)
                        Text("cal")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.FG.tertiary)
                    }
                }

                HStack(spacing: 14) {
                    macroLine(.protein, grams: group.totals.proteinG)
                    macroLine(.carbs,   grams: group.totals.carbsG)
                    macroLine(.fat,     grams: group.totals.fatG)
                }
                .font(.system(size: 11, design: .monospaced))
            }
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var chevron: some View {
        Image(systemName: "chevron.right")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(Theme.FG.tertiary)
            .rotationEffect(.degrees(isExpanded ? 90 : 0))
    }

    @ViewBuilder
    private var subtitle: some View {
        HStack(spacing: 6) {
            Text("\(group.items.count) items")
                .font(.system(size: 12))
                .foregroundStyle(Theme.FG.secondary)
            if group.count > 1 {
                Text("×\(group.count)")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(Theme.CTP.mauve)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1.5)
                    .background(
                        Capsule().fill(Theme.CTP.mauve.opacity(0.18))
                    )
            }
        }
    }

    private func macroLine(_ macro: Theme.Macro, grams: Double) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(macro.color)
                .frame(width: 5, height: 5)
            Text(macro.short)
                .foregroundStyle(Theme.FG.secondary)
            Text("\(Int(grams.rounded()))g")
                .monospacedDigit()
                .foregroundStyle(Theme.FG.primary)
        }
    }

    // MARK: - expanded items

    private var expandedItems: some View {
        VStack(spacing: 0) {
            ForEach(Array(group.items.enumerated()), id: \.element.id) { idx, item in
                EntryRow(entry: item)
                    .padding(.leading, 12)
                if idx < group.items.count - 1 {
                    Rectangle()
                        .fill(Theme.separator.opacity(0.5))
                        .frame(height: 0.5)
                        .padding(.leading, 12)
                }
            }
        }
    }

    // MARK: - actions

    private func toggle() {
        withAnimation(.easeInOut(duration: 0.2)) {
            isExpanded.toggle()
        }
    }
}

#Preview {
    let oats = FoodEntry(
        id: UUID(), dailyLogId: UUID(), userKey: "khash", entryGroupId: UUID(),
        displayName: "Oats, raw", quantityText: "80 g",
        normalizedQuantityValue: 80, normalizedQuantityUnit: "g",
        usdaFdcId: 173904, usdaDescription: "Oats, raw", customFoodId: nil,
        calories: 320, proteinG: 10, carbsG: 54, fatG: 6,
        mealId: UUID(), mealName: "Breakfast Bowl",
        consumedAt: .now, createdAt: .now
    )
    let yogurt = FoodEntry(
        id: UUID(), dailyLogId: UUID(), userKey: "khash", entryGroupId: UUID(),
        displayName: "Greek yogurt", quantityText: "200 g",
        normalizedQuantityValue: 200, normalizedQuantityUnit: "g",
        usdaFdcId: 748967, usdaDescription: "Yogurt, Greek", customFoodId: nil,
        calories: 130, proteinG: 18, carbsG: 9, fatG: 4,
        mealId: UUID(), mealName: "Breakfast Bowl",
        consumedAt: .now, createdAt: .now
    )
    let group = MealGroup(
        id: "meal:preview",
        mealId: UUID(),
        displayName: "Breakfast Bowl",
        count: 2,
        items: [oats, yogurt],
        totals: MacroTotals(calories: 900, proteinG: 56, carbsG: 126, fatG: 20),
        sortDate: .now
    )
    return VStack(spacing: 0) {
        MealGroupRow(group: group)
    }
    .padding(.horizontal, 14)
    .ctpCard()
    .padding()
    .background(Theme.BG.primary)
    .preferredColorScheme(.dark)
}
```

- [ ] **Step 2: Regenerate the Xcode project**

```bash
xcodegen generate
```

- [ ] **Step 3: Build to confirm the view compiles**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' build
```

Expected: BUILD SUCCEEDED.

- [ ] **Step 4: Commit**

```bash
git add DietTracker/Views/Components/MealGroupRow.swift
git commit -m "feat: add MealGroupRow component"
```

---

## Task 4: Wire `MealGroupRow` into `DayMacroView`

**Files:**
- Modify: `DietTracker/Views/DayMacroView.swift`

- [ ] **Step 1: Replace the entries renderer with the grouped renderer**

Edit `DietTracker/Views/DayMacroView.swift`:

Locate `entriesCard(_:)` (around line 106) and replace its body:

```swift
    private func entriesCard(_ entries: [FoodEntry]) -> some View {
        let rows = groupDayEntries(entries)
        return VStack(spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { idx, row in
                Group {
                    switch row {
                    case .single(let entry):
                        EntryRow(entry: entry)
                    case .meal(let group):
                        MealGroupRow(group: group)
                    }
                }
                if idx < rows.count - 1 {
                    Rectangle().fill(Theme.separator).frame(height: 0.5)
                }
            }
        }
        .padding(.horizontal, 14)
        .ctpCard()
    }
```

- [ ] **Step 2: Update the entries-header count to reflect logical rows**

Locate `entriesHeader(count:kcal:)` (around line 91) and the call site in `loadedBody` (around line 53):

```swift
                entriesHeader(count: groupDayEntries(summary.entries).count, kcal: summary.consumed.calories)
                    .padding(.horizontal, 20)
                    .padding(.top, 4)
```

(`entriesHeader` itself is unchanged — it just renders the number it's given.)

- [ ] **Step 3: Build and run on the simulator**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' build
```

Then open the project in Xcode (`open DietTracker.xcodeproj`) and run on iPhone 15 simulator. Sign into a configured server with at least one meal-logged group on today's date. Verify:

- The meal renders as a single row labelled with the meal name.
- Tapping the row reveals the items below with smooth animation.
- If the same meal was logged twice, a `×2` chip appears on the right of the subtitle.
- The kcal on the meal row equals the sum across all instances; the day's hero total still matches.
- Single (manually logged) entries render exactly as before.
- Tapping the meal row again collapses it.

If you don't have a real server, you can still verify visually using the `MealGroupRow` `#Preview` from Task 3 and by writing a quick `DayMacroView` preview. This is optional polish.

- [ ] **Step 4: Run all tests to make sure nothing else broke**

```bash
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add DietTracker/Views/DayMacroView.swift
git commit -m "feat: render meal groups collapsibly on day view"
```

---

## Final verification

- [ ] **Step 1: Full test pass + clean build**

```bash
xcodegen generate
xcodebuild -project DietTracker.xcodeproj -scheme DietTracker \
  -destination 'platform=iOS Simulator,name=iPhone 15' clean build test
```

Expected: BUILD SUCCEEDED, all tests PASS.

- [ ] **Step 2: Smoke test against the live server**

Pre-req: the companion server plan has shipped to the dev backend.

Sign into the iOS app pointed at that server, navigate to a day with at least one logged meal (use the Meals tab to log a meal twice if needed), and verify the day-view rendering matches the spec:

- Collapsed meal rows for any meal-logged group.
- `×N` chip when N>1 on the right of the subtitle.
- Items shown once on expansion (most recent instance).
- No timestamps in the expanded body.
- Singles unchanged.

If the server change has *not* shipped, the iOS build still works: meal-logged entries from the legacy server appear with `mealId == nil`, so they render as anonymous `Meal` rows — never merging across instances. That's the spec's "legacy entries" path and is acceptable.

---

## Self-review notes

- Spec sections covered: model fields (Task 1), grouping rules (Task 2 — all spec edge cases have a matching test), collapsed/expanded layout (Task 3), day-view wiring + entries-header count (Task 4), legacy and edge-case behavior (verified via Task 2 tests + Task 4 smoke test).
- No placeholders, no "implement later", no deferred test code.
- Type/property names consistent across tasks: `mealId`, `mealName`, `MealGroup`, `DayRow.single`/`.meal`, `groupDayEntries`, `MealGroupRow`, `MealGroup.totals`, `MealGroup.count`, `MealGroup.items`, `MealGroup.sortDate`.
- The "items from most recent instance" rule is implemented in Task 2's merge step (`useNewItems = time >= prev.sortDate`) and asserted by `testMostRecentInstanceItemsWinWhenTemplateChanged`.
- Stable insertion-order tie-break in the final sort matches the test that mixes singles and meals at distinct times; if you add tie-time scenarios later, the `==` short-circuit preserves the order built up in step 3.
- `xcodegen generate` reminder appears in Tasks 2 and 3 because the Xcode project file is gitignored and regenerated from `project.yml`. New `.swift` files are picked up automatically by the path-based source list, so `project.yml` itself does not need editing.

# Collapsible Meal Rows on Day View — Design

**Date:** 2026-05-10
**Status:** Approved (brainstorming)
**Companion spec:** `diet-tracker-server/docs/superpowers/specs/2026-05-10-meal-link-on-entries-design.md`

## Goal

On the iPhone day view, render food entries that originated from a logged meal as a single collapsed row showing the meal name. Tap expands to show the meal's items. When the same meal is logged multiple times in one day, collapse all instances into a single row with a `×N` quantity badge on the right.

## Scope

In:
- Server: stamp `meal_id` + denormalized `meal_name` on each `food_entries` row created by `log_meal`.
- iOS: group `DailySummary.entries` into top-level rows (singles + meal groups), render meal groups as a tap-to-expand row, merge same-`meal_id` instances into one `×N` row.

Out (v1):
- Backfilling pre-existing rows (legacy meal groups render as anonymous "Meal · N items").
- Editing or re-logging meal instances from the day view.
- Persisting expansion state across navigations or app launches.
- Aggregating across days (week/month views unchanged).
- Manual multi-item entry groups not sourced from a saved meal — they keep working as today (would render as anonymous meal groups; same UX).

## Background

`food_entries` already carries `entry_group_id`: every row from `log_meal` shares one. Manually-logged single entries get a fresh group id with one row in it. There is currently no link from a `food_entries` row to its source `meals` template — `meal_id` is needed to (1) label the collapsed row with the saved meal's name and (2) recognize repeat instances of the same meal.

## Server changes

### Schema

Add two nullable columns to `food_entries`:

| col | type | notes |
|---|---|---|
| `meal_id` | uuid null | FK → `meals.id` `ON DELETE SET NULL` |
| `meal_name` | text null | denormalized at log time; never updated |

Plus index `idx_food_entries_meal_id (meal_id)`.

Old rows stay NULL on both. Manual single-entry logging stays NULL on both. Only `log_meal` populates them.

Surfaces:
- Alembic migration `<rev>_add_meal_link_to_entries.py` adds columns + FK + index.
- `schema.sql` mirrors with `IF NOT EXISTS` guards (matches existing bootstrap pattern).
- `repositories/tables.py` — extend the `food_entries` `Table` definition.

### Service / repository

- `services/meals_service.log_meal` — pass `meal_id=meal.id` and `meal_name=meal.name` into each entry it creates. Captured at log time; renaming the template later does not retroactively change historical entries.
- `repositories/entries.py` — include both columns in inserts and selects.
- `models/entries.py` — `FoodEntryCreate` gains `meal_id: UUID | None = None`, `meal_name: str | None = None`. `FoodEntryRead` gains both, snake_case in the JSON payload.
- `mcp/server.py` — mirror the new fields anywhere a `FoodEntry` shape is exposed.

### Server tests

- `log_meal` round-trip: created entries carry the originating `meal_id` and a frozen `meal_name`.
- Direct entry creation (manual logging path): both fields default to NULL.
- Daily summary integration test: payload includes the new fields.

## iOS changes

### Model

`Models/FoodEntry.swift` adds:

```swift
let mealId: UUID?
let mealName: String?
```

with `CodingKeys` `meal_id`, `meal_name`. Test fixtures updated where applicable (meal-sourced entries get values; manual entries stay null).

### Grouping (pure)

New file `State/DayEntriesGrouping.swift`:

```swift
enum DayRow: Identifiable {
    case single(FoodEntry)
    case meal(MealGroup)
    var id: String { ... }
}

struct MealGroup: Identifiable {
    let id: String              // mealId.uuidString OR "anon:<entryGroupId>"
    let mealId: UUID?
    let displayName: String     // mealName ?? "Meal"
    let count: Int              // number of logged instances (entry_group_ids merged here)
    let items: [FoodEntry]      // items from the MOST RECENT instance — used for display
    let totals: MacroTotals     // summed across all items across all instances
    let sortDate: Date          // latest instance's max consumedAt
}

func groupDayEntries(_ entries: [FoodEntry]) -> [DayRow]
```

Algorithm:

1. Bucket entries by `entry_group_id` (each bucket = one logging instance, with its `consumedAt` time).
2. Size-1 buckets → emit `.single(entry)`.
3. Size-≥2 buckets are meal-instances. Bucket those by `mealId`:
   - Same non-nil `mealId` across multiple instances → one `MealGroup`. `count` is the number of merged instances. `items` comes from the instance with the latest `consumedAt`. `totals` is summed across **all** items in **all** instances.
   - `mealId == nil` → one `MealGroup` per instance, never merged with each other or with named groups (id prefix `"anon:"`).
4. Sort the resulting `[DayRow]`: singles by `consumedAt`; meal groups by `sortDate` (latest instance time). Stable for ties.

Items are intentionally not duplicated per instance: when the same meal is logged 3 times, the user sees the meal's composition once, with `×3` on the header to convey the multiplier and a summed kcal total on the right.

Deterministic and pure — unit-testable without SwiftUI.

### Components

New file `Views/Components/MealGroupRow.swift`:

- Collapsed layout (matches `EntryRow` rhythm so they sit together):
  - Leading 12pt chevron (`▶` rotates to `▼`), `Theme.FG.tertiary`.
  - Title: `displayName`, 15pt medium, `Theme.FG.primary`.
  - Subtitle: `"<itemCount> items"` where `itemCount` = number of items in the **most recent** instance (instances of the same `meal_id` may differ if the template was edited between logs), plus a `×<count>` chip when `count > 1` (mauve-tinted background, 11pt rounded). The two numbers are visually distinct: the chip is a tinted pill on the right of the subtitle, the item count is plain text on the left.
  - Macro line: P/C/F dots with summed grams (across all items across all instances).
  - Trailing: total kcal (summed across instances), styled like `EntryRow`'s calories block.
- Expanded body:
  - Render `MealGroup.items` (the most recent instance) as `EntryRow`s, indented ~12pt, hairline-separated. **No per-instance duplication or timestamps**, regardless of `count`.
  - Inner separators slightly lighter (`Theme.separator.opacity(0.5)`) to read as nested.
  - Per-item kcal/grams shown in `EntryRow` reflect a single instance. The header's `×N` chip + summed kcal explain how this contributes to the day total.
- Tap target: entire collapsed header. `@State private var isExpanded = false` toggled with `withAnimation(.easeInOut(duration: 0.2))`. Chevron via `.rotationEffect`.
- Default collapsed; not persisted across navigation.

### Day view

`Views/DayMacroView.swift::entriesCard` swaps the flat `ForEach` for:

```swift
ForEach(groupDayEntries(entries)) { row in
    switch row {
    case .single(let e): EntryRow(entry: e)
    case .meal(let g):   MealGroupRow(group: g)
    }
    // existing 0.5pt separator between top-level rows
}
```

`entriesHeader` count switches to logical-row count (singles + meal groups), so the count matches what's visible. The kcal total stays the daily total (unchanged).

If `EntryRow`'s P/C/F line formatting needs to be reused inside `MealGroupRow`, extract it into a small `MacroLine` view in `Views/Components/`. Not a hard requirement — duplicate is fine if it stays small.

No changes to `DayMacroModel`, `DietTrackerClient`, or other view-models. Grouping is a pure transform on the already-loaded `DailySummary.entries`.

### iOS tests

New `DayEntriesGroupingTests.swift`:

- All singles pass through, sorted by `consumedAt`.
- Single meal group with 3 items collapses to one `.meal` with `count == 1`; `items` matches the input.
- Two instances with same non-nil `mealId` → one `.meal` with `count == 2`. `items` equals the most-recent instance's items. `totals` equals the sum across both instances. `sortDate` is the later of the two `consumedAt` maxes.
- If two instances of the same meal have **different** item sets (template was edited between logs), `items` reflects the most recent instance only.
- Two instances with `mealId == nil` → two separate `.meal` rows (never merged).
- Mixed: singles + meal merge correctly, sorted by representative time.
- `displayName` falls back to `"Meal"` when `mealName` is nil.

Update existing fixtures so meal-logged samples include `meal_id` / `meal_name`; manual-entry fixtures keep both null. Existing tests that exercise the entries decoder still pass.

## Edge cases

- **Meal template deleted after logging**: `meal_id` set to NULL by the `ON DELETE SET NULL` FK. The historical row keeps `meal_name`, so the collapsed row still labels correctly. Repeat-grouping degrades: post-deletion entries can no longer merge with future logs of a recreated same-name meal (different `meal_id`). Acceptable.
- **Legacy entries (pre-migration)**: `meal_id` and `meal_name` both NULL even for entries originally from a meal. Multi-item groups render as anonymous `"Meal"` rows; never merge across instances. Acceptable per "skip backfill".
- **Single-item meal**: a saved meal with one item. Logging it produces one entry with size-1 group → renders as a `.single`, not a meal row. Acceptable; user can still see the original meal name only after expanding when there are multiple items. (We could special-case size-1 meal groups by detecting non-nil `mealId` on a single entry, but YAGNI for v1.)
- **Daily summary endpoint**: assumed to return entries with the new fields once the server change ships. The iOS decoder must tolerate both presence and absence (Optional types handle this).

## Rollout

1. Server migration + service change ship first; existing iOS app keeps working (ignores new fields).
2. iOS update ships second; on first day-view load it sees the new fields and renders collapsed meals.
3. No coordinated cutover required.

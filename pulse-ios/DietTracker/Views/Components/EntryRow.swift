import SwiftUI

struct EntryRow: View {
    let entry: FoodEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.displayName)
                        .font(.subheadline)
                        .fontWeight(.medium)
                    Text(entry.quantityText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(entry.calories) kcal")
                    .font(.subheadline)
                    .foregroundStyle(.tint)
                    .monospacedDigit()
            }
            HStack(spacing: 12) {
                macro(label: "P", grams: entry.proteinG, color: .blue)
                macro(label: "C", grams: entry.carbsG,   color: .orange)
                macro(label: "F", grams: entry.fatG,     color: .pink)
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
    }

    private func macro(label: String, grams: Double, color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text("\(label) \(Int(grams.rounded()))g")
        }
    }
}

#Preview {
    List {
        EntryRow(entry: FoodEntry(
            id: UUID(), dailyLogId: UUID(), userKey: "khash", entryGroupId: UUID(),
            displayName: "Oats, raw", quantityText: "80 g",
            normalizedQuantityValue: 80, normalizedQuantityUnit: "g",
            usdaFdcId: 173904, usdaDescription: "Oats, raw", customFoodId: nil,
            calories: 320, proteinG: 10, carbsG: 54, fatG: 6,
            consumedAt: Date(), createdAt: Date()
        ))
    }
}

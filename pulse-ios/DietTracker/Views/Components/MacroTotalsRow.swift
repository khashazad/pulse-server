import SwiftUI

struct MacroTotalsRow: View {
    let totals: MacroTotals
    let targets: MacroTargets?

    var body: some View {
        HStack(spacing: 8) {
            cell(label: "Protein", value: totals.proteinG, target: targets?.proteinG, color: .blue)
            cell(label: "Carbs",   value: totals.carbsG,   target: targets?.carbsG,   color: .orange)
            cell(label: "Fat",     value: totals.fatG,     target: targets?.fatG,     color: .pink)
        }
    }

    private func cell(label: String, value: Double, target: Double?, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            HStack(spacing: 2) {
                Text("\(Int(value.rounded()))")
                    .font(.headline)
                    .monospacedDigit()
                Text("g")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let target {
                Text("/ \(Int(target.rounded()))g")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
    }
}

#Preview {
    MacroTotalsRow(
        totals: MacroTotals(calories: 740, proteinG: 67, carbsG: 55, fatG: 25),
        targets: MacroTargets(calories: 2200, proteinG: 150, carbsG: 250, fatG: 70)
    )
    .padding()
}

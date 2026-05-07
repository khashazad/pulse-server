import SwiftUI

struct AverageMacrosTable: View {
    let logs: [DailyLog]

    var body: some View {
        VStack(spacing: 0) {
            row(label: "Avg / day", value: "\(WeekModel.avgCalories(logs)) kcal", isHeader: true)
            row(label: "Protein",   value: "\(Int(WeekModel.avgProtein(logs).rounded())) g")
            row(label: "Carbs",     value: "\(Int(WeekModel.avgCarbs(logs).rounded())) g")
            row(label: "Fat",       value: "\(Int(WeekModel.avgFat(logs).rounded())) g")
        }
    }

    private func row(label: String, value: String, isHeader: Bool = false) -> some View {
        HStack {
            Text(label)
                .font(isHeader ? .subheadline.bold() : .subheadline)
            Spacer()
            Text(value)
                .font(isHeader ? .subheadline.bold() : .subheadline)
                .monospacedDigit()
        }
        .padding(.vertical, 8)
        .overlay(alignment: .bottom) {
            Divider()
        }
    }
}

#Preview {
    let cal = Calendar.current
    let today = Date()
    let logs: [DailyLog] = (0..<7).reversed().map { offset in
        DailyLog(
            date: cal.date(byAdding: .day, value: -offset, to: today)!,
            totalCalories: 2000 + offset * 50,
            totalProteinG: 120,
            totalCarbsG: 220,
            totalFatG: 70,
            entryCount: 4
        )
    }
    return AverageMacrosTable(logs: logs).padding()
}

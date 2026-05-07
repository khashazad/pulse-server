import SwiftUI

struct DailyKcalBars: View {
    /// Logs in chronological (oldest → newest) order — caller passes them this way.
    let logs: [DailyLog]
    let targetCalories: Int?

    private var maxKcal: Int {
        max(logs.map(\.totalCalories).max() ?? 0, targetCalories ?? 0, 1)
    }

    var body: some View {
        VStack(spacing: 4) {
            HStack(alignment: .bottom, spacing: 6) {
                ForEach(logs) { log in
                    VStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(.tint)
                            .frame(height: barHeight(for: log.totalCalories))
                        Text(weekdayLetter(log.date))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .frame(height: 140)
            if let target = targetCalories {
                Text("Target: \(target) kcal")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func barHeight(for kcal: Int) -> CGFloat {
        let ratio = CGFloat(kcal) / CGFloat(maxKcal)
        return max(2, ratio * 120)
    }

    private func weekdayLetter(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "EEEEE"   // narrow weekday: M T W T F S S
        return f.string(from: date)
    }
}

#Preview {
    let cal = Calendar.current
    let today = Date()
    let logs: [DailyLog] = (0..<7).reversed().map { offset in
        DailyLog(
            date: cal.date(byAdding: .day, value: -offset, to: today)!,
            totalCalories: Int.random(in: 1200...2400),
            totalProteinG: Double.random(in: 80...150),
            totalCarbsG: Double.random(in: 150...280),
            totalFatG: Double.random(in: 50...90),
            entryCount: 4
        )
    }
    return DailyKcalBars(logs: logs, targetCalories: 2200).padding()
}

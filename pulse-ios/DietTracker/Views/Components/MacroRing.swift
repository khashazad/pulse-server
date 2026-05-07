import SwiftUI

struct MacroRing: View {
    let consumed: Int
    let target: Int

    private var progress: Double {
        guard target > 0 else { return 0 }
        return min(1.0, Double(consumed) / Double(target))
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(.quaternary, lineWidth: 12)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(.tint, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut, value: progress)
            VStack(spacing: 2) {
                Text("\(consumed)")
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                Text("of \(target) kcal")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 140, height: 140)
    }
}

#Preview {
    MacroRing(consumed: 740, target: 2200)
        .padding()
}

import SwiftUI
import Charts

struct WeightTrendsView: View {
    @Environment(AuthSession.self) private var auth
    @State private var model: WeightTrendsModel?

    @AppStorage(WeightUnit.displayPreferenceKey)
    private var displayUnitRaw: String = WeightUnit.defaultDisplayUnit.rawValue

    var body: some View {
        ZStack {
            Theme.BG.primary.ignoresSafeArea()
            Group {
                switch model?.analytics ?? .idle {
                case .idle, .loading:
                    ProgressView().tint(Theme.CTP.mauve)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .loaded(let result):
                    loadedBody(result)
                case .failed(let err):
                    EmptyStateView(
                        icon: "exclamationmark.triangle",
                        title: "Couldn't load",
                        description: err.userMessage,
                        action: { Task { await model?.load() } },
                        actionLabel: "Retry"
                    )
                }
            }
        }
        .task {
            if model == nil { model = WeightTrendsModel(auth: auth) }
            await model?.load()
        }
        .refreshable { await model?.load() }
    }

    @ViewBuilder
    private func loadedBody(_ result: WeightAnalyticsResult) -> some View {
        let displayUnit = WeightUnit(rawValue: displayUnitRaw) ?? .lb
        ScrollView {
            VStack(spacing: Theme.Layout.sectionSpacing) {
                weightOverTimeCard(entries: model?.entries ?? [], target: model?.targetWeightLb, unit: displayUnit)
                rateVsKcalCard(result: result, unit: displayUnit)
                analyticsCard(result: result, unit: displayUnit)
                Spacer(minLength: Theme.Layout.dockClearance)
            }
            .padding(.horizontal, 16)
            .padding(.top, 4)
        }
    }

    private func weightOverTimeCard(entries: [WeightEntry], target: Double?, unit: WeightUnit) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Weight over time")
                .font(.system(size: 11, weight: .semibold)).tracking(0.8).textCase(.uppercase)
                .foregroundStyle(Theme.FG.secondary)
            if entries.isEmpty {
                Text("Log a few weigh-ins to see your trend here.")
                    .font(.system(size: 13)).foregroundStyle(Theme.FG.tertiary)
                    .frame(height: 160)
            } else {
                Chart {
                    ForEach(entries) { entry in
                        let displayValue = WeightFormatter.fromLb(entry.weightLb, to: unit)
                        LineMark(x: .value("Date", entry.date),
                                 y: .value("Weight", displayValue))
                            .foregroundStyle(Theme.CTP.blue)
                            .interpolationMethod(.monotone)
                        PointMark(x: .value("Date", entry.date),
                                  y: .value("Weight", displayValue))
                            .foregroundStyle(Theme.CTP.blue)
                    }
                    if let target {
                        RuleMark(y: .value("Target", WeightFormatter.fromLb(target, to: unit)))
                            .foregroundStyle(Theme.CTP.green)
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                            .annotation(position: .top, alignment: .trailing) {
                                Text("target")
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundStyle(Theme.CTP.green)
                            }
                    }
                }
                .frame(height: 200)
            }
        }
        .padding(16).ctpCard()
    }

    private func rateVsKcalCard(result: WeightAnalyticsResult, unit: WeightUnit) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Rate vs calories")
                .font(.system(size: 11, weight: .semibold)).tracking(0.8).textCase(.uppercase)
                .foregroundStyle(Theme.FG.secondary)
            if result.regression == nil {
                Text("Collecting data — \(result.validWindowCount)/\(WeightAnalytics.minValidWindows) valid weeks")
                    .font(.system(size: 13)).foregroundStyle(Theme.FG.tertiary)
                    .frame(height: 160, alignment: .leading)
            } else {
                Chart {
                    ForEach(Array(result.scatter.enumerated()), id: \.offset) { _, p in
                        PointMark(x: .value("kcal", p.avgKcal),
                                  y: .value("lb/wk", p.lbPerDay * 7))
                            .foregroundStyle(Theme.CTP.lavender)
                    }
                    if let reg = result.regression, !result.scatter.isEmpty {
                        let minX = result.scatter.map(\.avgKcal).min() ?? 0
                        let maxX = result.scatter.map(\.avgKcal).max() ?? 0
                        LineMark(x: .value("kcal", minX),
                                 y: .value("lb/wk", (reg.slope * minX + reg.intercept) * 7))
                            .foregroundStyle(Theme.CTP.mauve)
                        LineMark(x: .value("kcal", maxX),
                                 y: .value("lb/wk", (reg.slope * maxX + reg.intercept) * 7))
                            .foregroundStyle(Theme.CTP.mauve)
                    }
                    if let kcal = result.maintenanceKcal {
                        RuleMark(x: .value("Maintenance", Double(kcal)))
                            .foregroundStyle(Theme.CTP.green)
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    }
                    RuleMark(y: .value("Zero", 0.0))
                        .foregroundStyle(Theme.FG.tertiary.opacity(0.4))
                }
                .frame(height: 200)
            }
        }
        .padding(16).ctpCard()
    }

    private func analyticsCard(result: WeightAnalyticsResult, unit: WeightUnit) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Analytics")
                .font(.system(size: 11, weight: .semibold)).tracking(0.8).textCase(.uppercase)
                .foregroundStyle(Theme.FG.secondary)
            if let m = result.maintenanceKcal {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text("≈").foregroundStyle(Theme.FG.tertiary)
                    Text(m.formatted())
                        .font(.system(size: 32, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.FG.primary)
                    Text("kcal/day").foregroundStyle(Theme.FG.tertiary)
                    Spacer()
                    if let r2 = result.regression?.rSquared {
                        confidenceChip(r2: r2)
                    }
                }
                Text("Maintenance").font(.system(size: 12)).foregroundStyle(Theme.FG.tertiary)
            } else {
                Text("Need \(WeightAnalytics.minValidWindows - result.validWindowCount) more valid weeks for maintenance estimate.")
                    .font(.system(size: 13)).foregroundStyle(Theme.FG.tertiary)
            }
            if let lbPerWeek = result.trendLbPerWeek {
                let sign = lbPerWeek > 0 ? "+" : ""
                Text("Trend: \(sign)\(String(format: "%.1f", lbPerWeek)) lb/week (last 28 days)")
                    .font(.system(size: 13)).foregroundStyle(Theme.FG.secondary)
            }
            etaLine(result: result, unit: unit)
        }
        .padding(16).ctpCard()
    }

    @ViewBuilder
    private func etaLine(result: WeightAnalyticsResult, unit: WeightUnit) -> some View {
        if model?.targetWeightLb == nil {
            Text("Set a target weight in Settings to see ETA.")
                .font(.system(size: 13)).foregroundStyle(Theme.FG.tertiary)
        } else if let eta = result.etaToTarget {
            switch eta {
            case .stable:
                Text("≈ stable, no ETA").font(.system(size: 13)).foregroundStyle(Theme.FG.secondary)
            case .never:
                Text("Trending away from target")
                    .font(.system(size: 13)).foregroundStyle(Theme.CTP.peach)
            case .date(let d):
                Text("ETA to target: \(d.formatted(date: .abbreviated, time: .omitted))")
                    .font(.system(size: 13)).foregroundStyle(Theme.FG.primary)
            }
        }
    }

    private func confidenceChip(r2: Double) -> some View {
        let (label, color): (String, Color) = {
            switch r2 {
            case 0.5...: return ("R²=\(String(format: "%.2f", r2))", Theme.CTP.green)
            case 0.1..<0.5: return ("R²=\(String(format: "%.2f", r2))", Theme.CTP.peach)
            default: return ("low confidence", Theme.FG.tertiary)
            }
        }()
        return Text(label)
            .font(.system(size: 10, weight: .semibold, design: .monospaced))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Capsule().fill(color.opacity(0.16)))
            .foregroundStyle(color)
    }
}

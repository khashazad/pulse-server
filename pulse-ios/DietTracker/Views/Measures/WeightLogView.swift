import SwiftUI

struct WeightLogView: View {
    @Environment(AuthSession.self) private var auth
    @State private var model: WeightLogModel?
    @State private var sheetState: SheetState?

    @AppStorage(WeightUnit.displayPreferenceKey)
    private var displayUnitRaw: String = WeightUnit.defaultDisplayUnit.rawValue

    enum SheetState: Identifiable {
        case add(Date)
        case edit(WeightEntry)
        var id: String {
            switch self {
            case .add(let d): return "add-\(d)"
            case .edit(let e): return "edit-\(e.id)"
            }
        }
    }

    var body: some View {
        ZStack {
            Theme.BG.primary.ignoresSafeArea()
            Group {
                switch model?.state ?? .idle {
                case .idle, .loading:
                    ProgressView().tint(Theme.CTP.mauve)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .loaded(let entries):
                    loadedBody(entries)
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
            if model == nil { model = WeightLogModel(auth: auth) }
            await model?.load()
        }
        .refreshable { await model?.load() }
        .sheet(item: $sheetState) { state in
            switch state {
            case .add(let date):
                WeightEntrySheet(
                    date: date,
                    existing: nil,
                    onSave: { value, unit in await model?.upsert(date: date, weight: value, unit: unit) },
                    onDelete: nil
                )
            case .edit(let entry):
                WeightEntrySheet(
                    date: entry.date,
                    existing: entry,
                    onSave: { value, unit in await model?.upsert(date: entry.date, weight: value, unit: unit) },
                    onDelete: { await model?.delete(date: entry.date) }
                )
            }
        }
    }

    @ViewBuilder
    private func loadedBody(_ entries: [WeightEntry]) -> some View {
        let displayUnit = WeightUnit(rawValue: displayUnitRaw) ?? .lb
        ScrollView {
            VStack(spacing: Theme.Layout.sectionSpacing) {
                todayCard(entries: entries, unit: displayUnit)
                pastList(entries: entries, unit: displayUnit)
                Spacer(minLength: Theme.Layout.dockClearance)
            }
            .padding(.horizontal, 16)
            .padding(.top, 4)
        }
    }

    private func todayCard(entries: [WeightEntry], unit: WeightUnit) -> some View {
        let today = Calendar.current.startOfDay(for: Date())
        let entry = entries.first {
            Calendar.current.startOfDay(for: $0.date) == today
        }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Today")
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.8)
                .textCase(.uppercase)
                .foregroundStyle(Theme.FG.secondary)
            if let entry {
                HStack {
                    Text(WeightFormatter.display(lb: entry.weightLb, in: unit))
                        .font(.system(size: 32, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.FG.primary)
                    Spacer()
                    Text(entry.updatedAt, style: .relative)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.FG.tertiary)
                }
            } else {
                Button {
                    sheetState = .add(today)
                } label: {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                        Text("Add today's weight")
                    }
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Theme.CTP.mauve)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .ctpCard()
        .onTapGesture {
            if let entry = entries.first(where: {
                Calendar.current.startOfDay(for: $0.date) == today
            }) {
                sheetState = .edit(entry)
            }
        }
    }

    private func pastList(entries: [WeightEntry], unit: WeightUnit) -> some View {
        let today = Calendar.current.startOfDay(for: Date())
        let past = entries.filter { Calendar.current.startOfDay(for: $0.date) != today }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Past")
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.8)
                .textCase(.uppercase)
                .foregroundStyle(Theme.FG.secondary)
            if past.isEmpty {
                Text("No past weigh-ins.")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.FG.tertiary)
            } else {
                ForEach(past) { entry in
                    Button {
                        sheetState = .edit(entry)
                    } label: {
                        HStack {
                            Text(entry.date.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()))
                                .font(.system(size: 14))
                                .foregroundStyle(Theme.FG.primary)
                            Spacer()
                            Text(WeightFormatter.display(lb: entry.weightLb, in: unit))
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                .foregroundStyle(Theme.FG.primary)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(Theme.FG.tertiary)
                        }
                        .padding(.vertical, 8)
                    }
                    .buttonStyle(.plain)
                    Divider().background(Theme.BG.tertiary)
                }
            }
        }
        .padding(16)
        .ctpCard()
    }
}

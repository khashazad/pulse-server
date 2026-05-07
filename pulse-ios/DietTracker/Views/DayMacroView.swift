import SwiftUI

struct DayMacroView: View {
    let date: Date
    @Environment(AppSettings.self) private var settings
    @State private var model: DayMacroModel?

    var body: some View {
        Group {
            switch model?.state ?? .idle {
            case .idle, .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let summary):
                loadedBody(summary)
            case .failed(let error):
                errorBody(error)
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: date) {
            if model == nil { model = DayMacroModel(date: date, settings: settings) }
            await model?.load()
        }
        .refreshable { await model?.load() }
    }

    private var title: String {
        let f = DateFormatter()
        f.dateStyle = .medium
        if Calendar.current.isDateInToday(date) { return "Today" }
        if Calendar.current.isDateInYesterday(date) { return "Yesterday" }
        return f.string(from: date)
    }

    @ViewBuilder
    private func loadedBody(_ summary: DailySummary) -> some View {
        ScrollView {
            VStack(spacing: 16) {
                MacroRing(consumed: summary.consumed.calories, target: summary.target.calories)
                    .padding(.top, 12)
                MacroTotalsRow(totals: summary.consumed, targets: summary.target)
                    .padding(.horizontal)

                if summary.entries.isEmpty {
                    ContentUnavailableView("No entries logged",
                                           systemImage: "fork.knife",
                                           description: Text("Anything you log will appear here."))
                        .padding(.top, 40)
                } else {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(summary.entries) { entry in
                            EntryRow(entry: entry)
                                .padding(.horizontal)
                            Divider().padding(.leading)
                        }
                    }
                    .padding(.top, 8)
                }

                Spacer(minLength: 80) // room for floating dock
            }
        }
    }

    @ViewBuilder
    private func errorBody(_ error: DietTrackerError) -> some View {
        switch error {
        case .notFound:
            ContentUnavailableView {
                Label("No targets set", systemImage: "target")
            } description: {
                Text("Set targets in the server to start tracking.")
            } actions: {
                Button("Retry") { Task { await model?.load() } }
            }
        default:
            ContentUnavailableView {
                Label("Couldn't load", systemImage: "exclamationmark.triangle")
            } description: {
                Text(error.userMessage)
            } actions: {
                Button("Retry") { Task { await model?.load() } }
            }
        }
    }
}

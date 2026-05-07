import SwiftUI

struct WeekView: View {
    @Environment(AppSettings.self) private var settings
    @State private var model: WeekModel?

    var body: some View {
        Group {
            switch model?.state ?? .idle {
            case .idle, .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let list):
                loadedBody(list.logs)
            case .failed(let error):
                ContentUnavailableView {
                    Label("Couldn't load week", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error.userMessage)
                } actions: {
                    Button("Retry") { Task { await model?.loadLast7Days() } }
                }
            }
        }
        .navigationTitle("This week")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if model == nil { model = WeekModel(settings: settings) }
            await model?.loadLast7Days()
        }
        .refreshable { await model?.loadLast7Days() }
    }

    private func loadedBody(_ logs: [DailyLog]) -> some View {
        // Server returns desc; chart wants chronological ascending.
        let chronological = logs.sorted { $0.date < $1.date }
        return ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                DailyKcalBars(logs: chronological, targetCalories: nil)
                    .padding(.horizontal)
                    .padding(.top, 12)
                AverageMacrosTable(logs: chronological)
                    .padding(.horizontal)
                Spacer(minLength: 80) // room for dock
            }
        }
    }
}

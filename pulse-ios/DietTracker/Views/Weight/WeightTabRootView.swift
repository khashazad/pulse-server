import SwiftUI

enum WeightSection: String, CaseIterable, Hashable {
    case log = "Log"
    case trends = "Trends"
}

struct WeightTabRootView: View {
    @State private var section: WeightSection = .log

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $section) {
                ForEach(WeightSection.allCases, id: \.self) { s in
                    Text(s.rawValue).tag(s)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)

            Group {
                switch section {
                case .log:    WeightLogView()
                case .trends: WeightTrendsView()
                }
            }
        }
        .navigationTitle("Weight")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.BG.primary, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
    }
}

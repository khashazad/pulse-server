import SwiftUI

enum MeasureSection: String, CaseIterable, Hashable {
    case log = "Log"
    case photos = "Photos"
    case trends = "Trends"
}

struct MeasuresTabRootView: View {
    @State private var section: MeasureSection = .log

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $section) {
                ForEach(MeasureSection.allCases, id: \.self) { s in
                    Text(s.rawValue).tag(s)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)

            Group {
                switch section {
                case .log:    WeightLogView()
                case .photos: ProgressPhotosView()
                case .trends: WeightTrendsView()
                }
            }
        }
        .navigationTitle("Measures")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.BG.primary, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
    }
}

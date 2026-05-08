import SwiftUI

enum LogSubTab: Hashable {
    case today, week, date
}

struct LogView: View {
    @State private var subTab: LogSubTab = .today
    let onOpenDate: (Date) -> Void

    var body: some View {
        ZStack {
            Theme.BG.primary.ignoresSafeArea()
            VStack(spacing: 0) {
                segmented
                    .padding(.horizontal, 16)
                    .padding(.top, 4)
                    .padding(.bottom, 8)
                content
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.BG.primary, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
    }

    private var title: String {
        switch subTab {
        case .today: "Today"
        case .week:  "This week"
        case .date:  "Pick a date"
        }
    }

    private var segmented: some View {
        Picker("", selection: $subTab) {
            Text("Today").tag(LogSubTab.today)
            Text("Week").tag(LogSubTab.week)
            Text("Date").tag(LogSubTab.date)
        }
        .pickerStyle(.segmented)
    }

    @ViewBuilder
    private var content: some View {
        switch subTab {
        case .today:
            DayMacroView(date: Date())
        case .week:
            WeekView()
        case .date:
            DatePickerInline(onOpen: onOpenDate)
        }
    }
}

struct DatePickerInline: View {
    let onOpen: (Date) -> Void
    @State private var selected: Date = Date()

    var body: some View {
        ZStack {
            Theme.BG.primary.ignoresSafeArea()
            VStack(spacing: 16) {
                DatePicker(
                    "Pick a date",
                    selection: $selected,
                    in: ...Date(),
                    displayedComponents: [.date]
                )
                .datePickerStyle(.graphical)
                .tint(Theme.CTP.mauve)
                .padding(.horizontal, 12)

                Button {
                    onOpen(selected)
                } label: {
                    Text("Open")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.CTP.mauve)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 10)
                        .background(
                            Capsule().fill(Theme.CTP.mauve.opacity(0.16))
                        )
                        .overlay(
                            Capsule().strokeBorder(Theme.CTP.mauve.opacity(0.30), lineWidth: 0.5)
                        )
                }
                .buttonStyle(.plain)

                Spacer(minLength: Theme.Layout.dockClearance)
            }
            .padding(.top, 4)
        }
    }
}

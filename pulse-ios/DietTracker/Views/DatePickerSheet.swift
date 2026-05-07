import SwiftUI

struct DatePickerSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onPick: (Date) -> Void

    @State private var selected: Date = Date()

    var body: some View {
        NavigationStack {
            VStack {
                DatePicker("Pick a date",
                           selection: $selected,
                           in: ...Date(),
                           displayedComponents: [.date])
                    .datePickerStyle(.graphical)
                    .padding()
                Spacer()
            }
            .navigationTitle("Pick a date")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Open") {
                        onPick(selected)
                        dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

#Preview {
    DatePickerSheet { _ in }
}

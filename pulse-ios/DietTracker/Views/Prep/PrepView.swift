import SwiftUI

struct PrepView: View {
    @Environment(AppSettings.self) private var settings
    @State private var model = PrepModel()
    @State private var listModel: ContainersListModel?
    @State private var showPicker = false
    @State private var showManager = false

    var body: some View {
        Form {
            Section("Container") {
                Button { showPicker = true } label: {
                    HStack {
                        if let c = model.selectedContainer {
                            Text(c.name)
                            Spacer()
                            Text("\(Int(c.tareWeightG.rounded())) g")
                                .foregroundStyle(.secondary)
                        } else {
                            Text("Pick a container").foregroundStyle(.tint)
                            Spacer()
                        }
                        Image(systemName: "chevron.up.chevron.down")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section("Total weight on scale") {
                HStack {
                    TextField("0", value: $model.totalGrams, format: .number)
                        .keyboardType(.decimalPad)
                    Text("g").foregroundStyle(.secondary)
                }
            }

            Section("Portions") {
                Stepper(value: $model.portions, in: 1...50) {
                    Text("\(model.portions)")
                }
            }

            Section("Result") {
                row("Net food", value: model.netGrams)
                row("Per portion", value: model.perPortionGrams)
            }
        }
        .navigationTitle("Prep")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showManager = true } label: {
                    Image(systemName: "slider.horizontal.3")
                }
            }
        }
        .sheet(isPresented: $showPicker) {
            ContainerPickerSheet { picked in applyPick(picked) }
                .environment(settings)
        }
        .sheet(isPresented: $showManager) {
            ContainersListView()
                .environment(settings)
                .onDisappear {
                    Task {
                        await listModel?.load()
                        reconcileSelection()
                    }
                }
        }
        .task {
            if listModel == nil { listModel = ContainersListModel(settings: settings) }
            await listModel?.load()
            applyLastUsedIfNeeded()
            reconcileSelection()
        }
    }

    private func applyPick(_ c: Container) {
        model.selectedContainer = c
        UserDefaults.standard.set(c.id.uuidString, forKey: "prep.lastContainerId")
    }

    private func applyLastUsedIfNeeded() {
        guard model.selectedContainer == nil,
              let raw = UserDefaults.standard.string(forKey: "prep.lastContainerId"),
              let id = UUID(uuidString: raw),
              case .loaded(let list) = listModel?.state ?? .idle,
              let match = list.first(where: { $0.id == id })
        else { return }
        applyPick(match)
    }

    /// Re-fetch the selected container from the most recently loaded list so
    /// edits propagate (e.g. tare changed in the manager) and deletions clear
    /// the selection. Without this, `selectedContainer` keeps pointing at a
    /// stale snapshot and the math would silently use an outdated tare.
    private func reconcileSelection() {
        guard let current = model.selectedContainer else { return }
        guard case .loaded(let list) = listModel?.state ?? .idle else { return }
        if let fresh = list.first(where: { $0.id == current.id }) {
            if fresh != current { model.selectedContainer = fresh }
        } else {
            model.selectedContainer = nil
            UserDefaults.standard.removeObject(forKey: "prep.lastContainerId")
        }
    }

    @ViewBuilder
    private func row(_ label: String, value: Double?) -> some View {
        HStack {
            Text(label)
            Spacer()
            if let v = value {
                Text("\(Int(v.rounded())) g").monospacedDigit()
            } else {
                Text("—").foregroundStyle(.secondary)
            }
        }
    }
}

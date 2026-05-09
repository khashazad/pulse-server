import SwiftUI

struct AuthorizedAsyncImage<Content: View, Placeholder: View>: View {
    let request: URLRequest
    let content: (Image) -> Content
    let placeholder: () -> Placeholder

    @State private var loadedImage: UIImage?
    @State private var isLoading = false

    var body: some View {
        Group {
            if let img = loadedImage {
                content(Image(uiImage: img))
            } else {
                placeholder()
            }
        }
        .task(id: request.url) {
            await load()
        }
    }

    private func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            if let img = UIImage(data: data) {
                self.loadedImage = img
            }
        } catch {
            // leave placeholder
        }
    }
}

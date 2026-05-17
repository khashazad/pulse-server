import Foundation
import UIKit

final class ProgressPhotoCache {
    private let root: URL
    private let memory = NSCache<NSString, UIImage>()

    init(rootDirectory: URL? = nil) {
        if let r = rootDirectory {
            self.root = r
        } else {
            let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
            self.root = caches.appendingPathComponent("ProgressPhotos", isDirectory: true)
        }
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        memory.totalCostLimit = 50 * 1024 * 1024
    }

    func image(forSHA sha: String) -> UIImage? {
        if let cached = memory.object(forKey: sha as NSString) { return cached }
        let url = fileURL(forSHA: sha)
        guard let data = try? Data(contentsOf: url), let img = UIImage(data: data) else { return nil }
        memory.setObject(img, forKey: sha as NSString, cost: data.count)
        return img
    }

    func store(data: Data, sha: String) throws {
        let url = fileURL(forSHA: sha)
        try data.write(to: url, options: .atomic)
        if let img = UIImage(data: data) {
            memory.setObject(img, forKey: sha as NSString, cost: data.count)
        }
    }

    func evict(sha: String) {
        memory.removeObject(forKey: sha as NSString)
        try? FileManager.default.removeItem(at: fileURL(forSHA: sha))
    }

    func storePending(data: Data, id: UUID) throws -> URL {
        let url = root.appendingPathComponent("pending-\(id.uuidString).jpg")
        try data.write(to: url, options: .atomic)
        return url
    }

    func renameToSHA(pendingURL: URL, sha: String) throws {
        let finalURL = fileURL(forSHA: sha)
        if FileManager.default.fileExists(atPath: finalURL.path) {
            try? FileManager.default.removeItem(at: finalURL)
        }
        try FileManager.default.moveItem(at: pendingURL, to: finalURL)
        if let data = try? Data(contentsOf: finalURL), let img = UIImage(data: data) {
            memory.setObject(img, forKey: sha as NSString, cost: data.count)
        }
    }

    private func fileURL(forSHA sha: String) -> URL {
        root.appendingPathComponent("\(sha).jpg")
    }
}

import Foundation

enum Constants {
    static let baseURL: URL = {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "BaseURL") as? String,
            !raw.isEmpty,
            let url = URL(string: raw)
        else {
            fatalError("BaseURL missing from Info.plist — set DIET_TRACKER_BASE_URL before xcodegen")
        }
        return url
    }()

    enum Keychain {
        static let sessionService = "com.khxsh.diettracker.session"
        static let sessionAccount = "default"

        // Legacy API-key item identifiers, kept here ONLY so a one-shot deletion
        // in AuthSession.init can clean up old installs. Reference is removed in
        // the next release.
        static let legacyService = "com.khxsh.diettracker.apikey"
        static let legacyAccount = "default"
    }

    enum Auth {
        static let callbackScheme = "diettracker"
        static let startPath = "/auth/google/start"
    }
}

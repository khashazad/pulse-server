import Foundation

enum LoadState<T> {
    case idle
    case loading
    case loaded(T)
    case failed(DietTrackerError)
}

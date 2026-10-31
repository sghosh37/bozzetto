import Foundation
import RealityKit

/// How much detail Object Capture builds. Higher = slower and bigger files.
public enum DetailLevel: String, CaseIterable, Identifiable, Sendable {
    case preview, reduced, medium, full, raw

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .preview: return "Preview (fastest, rough)"
        case .reduced: return "Reduced"
        case .medium: return "Medium"
        case .full: return "Full (recommended for Blender)"
        case .raw: return "Raw (largest, for pro clean-up)"
        }
    }

    var request: PhotogrammetrySession.Request.Detail {
        switch self {
        case .preview: return .preview
        case .reduced: return .reduced
        case .medium: return .medium
        case .full: return .full
        case .raw: return .raw
        }
    }
}

public struct ScanOptions: Sendable {
    public var detail: DetailLevel = .reduced
    /// Photos were taken in order around the object (e.g. on a turntable). Speeds up matching.
    public var sequential: Bool = false
    /// Try harder to find features on plain / low-texture surfaces. Slower.
    public var highSensitivity: Bool = false
    /// Separate the object from the background automatically.
    public var objectMasking: Bool = true
    /// Real height of the object in mm. When set, the OBJ is scaled to exactly this height.
    public var knownHeightMM: Double? = nil
    /// Also write a Blender-friendly OBJ next to the USDZ.
    public var exportOBJ: Bool = true

    public init() {}
}

public enum ScanEvent: Sendable {
    case stage(String)
    case progress(Double)          // 0...1
    case message(String)
}

public enum ScanError: LocalizedError {
    case notSupported(String)
    case noPhotos
    case tooFewPhotos(Int)
    case buildFailed(photos: Int, detail: String)
    case noModel

    public var errorDescription: String? {
        switch self {
        case .notSupported(let why):
            return "Object Capture can’t run on this Mac: \(why)"
        case .noPhotos:
            return "That folder has no JPEG, HEIC or PNG photos."
        case .tooFewPhotos(let n):
            return "Only \(n) photo\(n == 1 ? "" : "s"). Object Capture needs at least \(PhotoFolder.minimumPhotos) overlapping photos of the object; 60–80 gives a good model."
        case .buildFailed(let n, let detail):
            var why = "Object Capture couldn’t build a model from these \(n) photos."
            if n < 10 {
                why += " With so few photos it often can’t work out where each one was taken. Add a few more (10–20 is usually enough for a rough shape), each overlapping the next by about 70%, and use the Quick shape preset."
            } else if n < 20 {
                why += " Try a few more photos, more overlap between neighbours, and “Plain or low-texture product”."
            } else {
                why += " Usually the photos don’t overlap enough, are blurred, or the object has strong reflections or no surface texture. Check the photos, try “Plain or low-texture product”, or reshoot with polarised light."
            }
            return why + "\n(Technical detail: \(detail))"
        case .noModel:
            return "Object Capture finished but no model file was written."
        }
    }
}

public enum PhotoFolder {
    public static let extensions: Set<String> = ["jpg", "jpeg", "heic", "heif", "png"]
    /// The app won't start below this many photos. Object Capture itself usually needs more
    /// (it often rejects sets under ~10); raise this if you want the app to stop you earlier.
    public static let minimumPhotos = 3

    public static func count(in folder: URL) -> Int {
        let items = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
        return items.filter { extensions.contains($0.pathExtension.lowercased()) }.count
    }
}

public enum ScanRunner {
    /// Runs Object Capture on a folder of photos and writes `usdzURL`.
    public static func run(input: URL,
                           usdzURL: URL,
                           options: ScanOptions,
                           onEvent: @escaping @Sendable (ScanEvent) -> Void) async throws {
        let photoCount = PhotoFolder.count(in: input)
        guard photoCount > 0 else { throw ScanError.noPhotos }
        guard photoCount >= PhotoFolder.minimumPhotos else { throw ScanError.tooFewPhotos(photoCount) }

        var config = PhotogrammetrySession.Configuration()
        config.sampleOrdering = options.sequential ? .sequential : .unordered
        config.featureSensitivity = options.highSensitivity ? .high : .normal
        config.isObjectMaskingEnabled = options.objectMasking

        let session: PhotogrammetrySession
        do {
            session = try PhotogrammetrySession(input: input, configuration: config)
        } catch {
            throw ScanError.notSupported(error.localizedDescription)
        }

        try? FileManager.default.removeItem(at: usdzURL)
        try FileManager.default.createDirectory(at: usdzURL.deletingLastPathComponent(), withIntermediateDirectories: true)

        onEvent(.stage("Reading photos…"))
        try session.process(requests: [.modelFile(url: usdzURL, detail: options.detail.request)])

        try await withTaskCancellationHandler {
            for try await output in session.outputs {
                switch output {
                case .inputComplete:
                    onEvent(.stage("Photos read. Building the model…"))
                case .requestProgress(_, let fraction):
                    onEvent(.progress(fraction))
                case .requestComplete(_, _):
                    onEvent(.progress(1))
                    onEvent(.stage("Model built."))
                case .requestError(_, let error):
                    throw ScanError.buildFailed(photos: photoCount, detail: String(describing: error))
                case .invalidSample(let id, let reason):
                    onEvent(.message("Photo #\(id) not used: \(reason)"))
                case .skippedSample(let id):
                    onEvent(.message("Photo #\(id) skipped."))
                case .automaticDownsampling:
                    onEvent(.message("Photos were scaled down automatically to fit in memory."))
                case .processingCancelled:
                    throw CancellationError()
                case .processingComplete:
                    return
                default:
                    break
                }
            }
        } onCancel: {
            session.cancel()
        }

        guard FileManager.default.fileExists(atPath: usdzURL.path) else { throw ScanError.noModel }
    }
}

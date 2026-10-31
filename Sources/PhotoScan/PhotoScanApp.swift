import SwiftUI
import AppKit
import UniformTypeIdentifiers
import PhotoScanCore

@main
struct PhotoScanApp: App {
    init() {
        // Makes the window come to the front even when started from Terminal
        NSApplication.shared.setActivationPolicy(.regular)
        DispatchQueue.main.async { NSApplication.shared.activate(ignoringOtherApps: true) }
    }

    var body: some Scene {
        WindowGroup("PhotoScan") {
            ContentView()
                .frame(minWidth: 600, minHeight: 720)
        }
        .windowResizability(.contentMinSize)
    }
}

// MARK: - State

@MainActor
final class ScanModel: ObservableObject {
    enum Phase: Equatable { case idle, running, done, failed }

    enum Source: String, CaseIterable, Identifiable {
        case photos = "Photo folder"
        case video = "Video"
        var id: String { rawValue }
    }

    @Published var source: Source = .photos
    @Published var inputFolder: URL? { didSet { photoCount = inputFolder.map { PhotoFolder.count(in: $0) } ?? 0; suggestName() } }
    @Published var photoCount = 0
    @Published var videoURL: URL? { didSet { loadVideoInfo() } }
    @Published var videoSeconds: Double = 0
    /// How many frames to pull from the video. ~2 per second of a slow orbit works well.
    @Published var frameCount = 40
    @Published var outputFolder: URL?
    @Published var name = "scan"

    @Published var preset: Preset = .quick { didSet { applyPreset() } }
    @Published var detail: DetailLevel = .reduced
    @Published var sequential = false
    @Published var highSensitivity = true
    @Published var objectMasking = true
    @Published var exportOBJ = true
    @Published var useKnownHeight = false
    @Published var knownHeightMM: Double = 100

    @Published var phase: Phase = .idle
    @Published var stage = ""
    @Published var progress: Double = 0
    @Published var eta = ""
    @Published var log: [String] = []
    @Published var usdzURL: URL?
    @Published var objURL: URL?
    @Published var stats: MeshStats?

    /// Starting points; every setting can still be changed by hand afterwards.
    enum Preset: String, CaseIterable, Identifiable {
        case quick = "Quick shape (3–20 photos)"
        case balanced = "Balanced (20–50 photos)"
        case detailed = "Detailed (60–80 photos)"
        var id: String { rawValue }
    }

    private func applyPreset() {
        switch preset {
        case .quick: detail = .reduced; highSensitivity = true
        case .balanced: detail = .medium; highSensitivity = false
        case .detailed: detail = .full; highSensitivity = false
        }
    }

    private var task: Task<Void, Never>?
    private var started = Date()

    var canStart: Bool {
        guard outputFolder != nil, phase != .running, !name.isEmpty else { return false }
        switch source {
        case .photos: return inputFolder != nil && photoCount >= PhotoFolder.minimumPhotos
        case .video: return videoURL != nil && videoSeconds > 0.5
        }
    }

    func chooseVideo() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie]
        panel.prompt = "Use this video"
        panel.message = "Choose a short video that circles the object (MOV or MP4)"
        if panel.runModal() == .OK, let url = panel.url {
            videoURL = url
            if outputFolder == nil { outputFolder = url.deletingLastPathComponent() }
        }
    }

    private func loadVideoInfo() {
        guard let v = videoURL else { videoSeconds = 0; return }
        name = v.deletingPathExtension().lastPathComponent.replacingOccurrences(of: " ", with: "-")
        videoSeconds = 0
        Task { [weak self] in
            let s = (try? await FrameExtractor.duration(of: v)) ?? 0
            await MainActor.run {
                guard let self, self.videoURL == v else { return }
                self.videoSeconds = s
                // suggest about 2 frames per second, within 20–80
                self.frameCount = min(80, max(20, Int((s * 2).rounded())))
            }
        }
    }

    func chooseInput() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Use these photos"
        panel.message = "Choose the folder that holds your product photos (JPEG, HEIC or PNG)"
        if panel.runModal() == .OK, let url = panel.url {
            inputFolder = url
            if outputFolder == nil { outputFolder = url.deletingLastPathComponent() }
        }
    }

    func chooseOutput() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Save here"
        panel.message = "Choose where to save the 3D model"
        if panel.runModal() == .OK, let url = panel.url { outputFolder = url }
    }

    private func suggestName() {
        if let f = inputFolder { name = f.lastPathComponent.replacingOccurrences(of: " ", with: "-") }
    }

    func start() {
        guard canStart, let outDir = outputFolder else { return }
        let folder = outDir.appendingPathComponent(name, isDirectory: true)
        let fromVideo = source == .video
        let video = videoURL
        let frames = frameCount
        // video frames are written next to the model, then scanned like a photo folder
        guard let input = fromVideo ? folder.appendingPathComponent("frames", isDirectory: true) : inputFolder else { return }
        let usdz = folder.appendingPathComponent("\(name).usdz")
        let obj = folder.appendingPathComponent("\(name).obj")

        var options = ScanOptions()
        options.detail = detail
        options.sequential = fromVideo ? true : sequential      // video frames are always in order
        options.highSensitivity = highSensitivity
        options.objectMasking = objectMasking
        options.exportOBJ = exportOBJ
        options.knownHeightMM = useKnownHeight ? knownHeightMM : nil

        phase = .running
        progress = 0
        eta = ""
        log = fromVideo
            ? ["Video \(video?.lastPathComponent ?? "") → \(frames) frames, detail: \(detail.rawValue)"]
            : ["\(photoCount) photos from \(input.lastPathComponent), detail: \(detail.rawValue)"]
        usdzURL = nil; objURL = nil; stats = nil
        started = Date()

        task = Task { [weak self] in
            do {
                if fromVideo, let video {
                    await MainActor.run { self?.stage = "Pulling frames from the video…" }
                    let n = try await FrameExtractor.extract(video: video, to: input, count: frames) { p in
                        Task { @MainActor in self?.progress = p }
                    }
                    await MainActor.run {
                        self?.log.append("Extracted \(n) sharp frames into \(input.path)")
                        self?.progress = 0
                        self?.started = Date()
                    }
                }
                try await ScanRunner.run(input: input, usdzURL: usdz, options: options) { event in
                    Task { @MainActor in self?.handle(event) }
                }
                await MainActor.run { self?.usdzURL = usdz; self?.log.append("Saved \(usdz.lastPathComponent)") }

                if options.exportOBJ {
                    await MainActor.run { self?.stage = "Writing OBJ for Blender…" }
                    let height = options.knownHeightMM
                    let result = try await Task.detached(priority: .userInitiated) {
                        try OBJExporter.export(usdz: usdz, to: obj, knownHeightMM: height)
                    }.value
                    await MainActor.run {
                        self?.objURL = obj
                        self?.stats = result
                        self?.log.append("Saved \(obj.lastPathComponent)" + (result.textureWritten ? " with colour texture" : " (geometry only)"))
                    }
                }
                await MainActor.run { self?.finish(ok: true, message: "Done") }
            } catch is CancellationError {
                await MainActor.run { self?.finish(ok: false, message: "Cancelled") }
            } catch {
                await MainActor.run { self?.finish(ok: false, message: error.localizedDescription) }
            }
        }
    }

    func cancel() { task?.cancel() }

    private func handle(_ event: ScanEvent) {
        switch event {
        case .stage(let s):
            stage = s
        case .message(let m):
            log.append(m)
        case .progress(let p):
            progress = p
            let elapsed = Date().timeIntervalSince(started)
            if p > 0.03 && p < 1 {
                let remaining = elapsed / p * (1 - p)
                eta = "about " + Self.duration(remaining) + " left"
            } else { eta = "" }
        }
    }

    private func finish(ok: Bool, message: String) {
        phase = ok ? .done : .failed
        stage = message
        if !ok { progress = 0 }
        eta = ""
        log.append(message + " · " + Self.duration(Date().timeIntervalSince(started)))
        if ok { NSSound(named: "Glass")?.play() }
    }

    static func duration(_ s: TimeInterval) -> String {
        let m = Int(s) / 60, sec = Int(s) % 60
        return m > 0 ? "\(m) min \(sec) s" : "\(sec) s"
    }
}

// MARK: - UI

struct ContentView: View {
    @StateObject private var model = ScanModel()

    var body: some View {
        Form {
            Section("Input") {
                Picker("Source", selection: $model.source) {
                    ForEach(ScanModel.Source.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                if model.source == .photos {
                    LabeledContent("Photo folder") {
                        HStack {
                            Text(model.inputFolder?.path ?? "None chosen").lineLimit(1).truncationMode(.middle).foregroundStyle(.secondary)
                            Button("Choose…") { model.chooseInput() }
                        }
                    }
                    if model.inputFolder != nil {
                        Text(photoCountText).foregroundStyle(model.photoCount < 10 ? .orange : .secondary)
                    }
                } else {
                    LabeledContent("Video") {
                        HStack {
                            Text(model.videoURL?.lastPathComponent ?? "None chosen").lineLimit(1).truncationMode(.middle).foregroundStyle(.secondary)
                            Button("Choose…") { model.chooseVideo() }
                        }
                    }
                    if model.videoURL != nil {
                        Stepper(value: $model.frameCount, in: 10...150, step: 5) {
                            Text("Frames to extract: \(model.frameCount)")
                        }
                        Text(videoText).foregroundStyle(model.videoSeconds < 8 ? .orange : .secondary)
                    }
                }
                LabeledContent("Save to") {
                    HStack {
                        Text(model.outputFolder?.path ?? "None chosen").lineLimit(1).truncationMode(.middle).foregroundStyle(.secondary)
                        Button("Choose…") { model.chooseOutput() }
                    }
                }
                TextField("Model name", text: $model.name)
            }

            Section("Quality") {
                Picker("Preset", selection: $model.preset) {
                    ForEach(ScanModel.Preset.allCases) { Text($0.rawValue).tag($0) }
                }
                Picker("Detail", selection: $model.detail) {
                    ForEach(DetailLevel.allCases) { Text($0.title).tag($0) }
                }
                Toggle("Photos were taken in order around the object (turntable)", isOn: $model.sequential)
                Toggle("Plain or low-texture product (slower, finds more detail)", isOn: $model.highSensitivity)
                Toggle("Remove the background automatically", isOn: $model.objectMasking)
            }

            Section("Size and export") {
                Toggle("Also save an OBJ for Blender (mm, Y up, base at 0)", isOn: $model.exportOBJ)
                Toggle("Scale to the real height I measured", isOn: $model.useKnownHeight)
                    .disabled(!model.exportOBJ)
                if model.useKnownHeight && model.exportOBJ {
                    LabeledContent("Real height (mm)") {
                        TextField("mm", value: $model.knownHeightMM, format: .number.precision(.fractionLength(0...2)))
                            .frame(width: 100)
                            .multilineTextAlignment(.trailing)
                    }
                }
            }

            Section {
                HStack {
                    if model.phase == .running {
                        Button("Cancel", role: .cancel) { model.cancel() }
                    } else {
                        Button("Build 3D model") { model.start() }
                            .keyboardShortcut(.defaultAction)
                            .disabled(!model.canStart)
                    }
                    Spacer()
                    if model.phase == .running || model.phase == .done {
                        Text(model.eta).foregroundStyle(.secondary).monospacedDigit()
                    }
                }
                if model.phase != .idle {
                    ProgressView(value: model.progress) { Text(model.stage) }
                }
                if model.phase == .done {
                    if let s = model.stats {
                        Text(String(format: "%.1f × %.1f × %.1f mm (W × H × D) · %@ triangles", s.sizeMM.x, s.sizeMM.y, s.sizeMM.z,
                                    s.triangles.formatted()))
                            .monospacedDigit()
                        if !s.scaledToKnownHeight {
                            Text("Size comes from Object Capture. It is only true to life if the photos carried depth data (e.g. iPhone HEIC). For exact size, turn on “Scale to the real height” and run again.")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                    }
                    HStack {
                        if let u = model.objURL ?? model.usdzURL {
                            Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([u]) }
                        }
                        if let u = model.usdzURL {
                            Button("Preview USDZ") { NSWorkspace.shared.open(u) }
                        }
                    }
                }
            }

            if !model.log.isEmpty {
                Section("Log") {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(Array(model.log.enumerated()), id: \.offset) { _, line in
                                Text(line).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 80, maxHeight: 160)
                }
            }
        }
        .formStyle(.grouped)
    }

    private var videoText: String {
        let s = model.videoSeconds
        if s <= 0 { return "Reading video…" }
        let len = String(format: "%.0f s video", s)
        if s < 8 { return "\(len). That’s short; a slow 15–30 s circle around the object works best." }
        return "\(len) → one frame every \(String(format: "%.1f", s / Double(max(1, model.frameCount)))) s, sharpest of 3 nearby frames each time."
    }

    private var photoCountText: String {
        let n = model.photoCount
        if n == 0 { return "No JPEG, HEIC or PNG photos in this folder." }
        if n < PhotoFolder.minimumPhotos {
            return "\(n) photo\(n == 1 ? "" : "s"). Object Capture needs at least \(PhotoFolder.minimumPhotos); shoot 60–80 in rings around the object."
        }
        if n < 10 { return "\(n) photos. Enough to try a rough shape; if it fails, add a few more." }
        return "\(n) photos"
    }
}

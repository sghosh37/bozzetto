import Foundation
import PhotoScanCore

// photoscan-cli <photos-folder | video.mov> <output-folder> [options]
//   --detail preview|reduced|medium|full|raw   (default reduced)
//   --height-mm <number>                        scale the OBJ to this real height
//   --sequential                                photos taken in order (turntable)
//   --high                                      high feature sensitivity (plain products)
//   --no-mask                                   keep the background
//   --no-obj                                    only write the USDZ
//   --name <name>                               file name (default: photo folder name)
//   --frames <n>                                frames to pull from a video (default 40)

let usage = """
usage: photoscan-cli <photos-folder | video.mov> <output-folder> [--detail reduced] [--height-mm 120]
                     [--sequential] [--high] [--no-mask] [--no-obj] [--name scan] [--frames 40]
"""

var args = Array(CommandLine.arguments.dropFirst())
var positional: [String] = []
var options = ScanOptions()
var name: String? = nil
var frameCount = 40

while !args.isEmpty {
    let a = args.removeFirst()
    switch a {
    case "--detail":
        guard let v = args.first, let d = DetailLevel(rawValue: v) else { print(usage); exit(2) }
        options.detail = d; args.removeFirst()
    case "--height-mm":
        guard let v = args.first, let h = Double(v) else { print(usage); exit(2) }
        options.knownHeightMM = h; args.removeFirst()
    case "--name":
        guard let v = args.first else { print(usage); exit(2) }
        name = v; args.removeFirst()
    case "--frames":
        guard let v = args.first, let n = Int(v), n > 0 else { print(usage); exit(2) }
        frameCount = n; args.removeFirst()
    case "--sequential": options.sequential = true
    case "--high": options.highSensitivity = true
    case "--no-mask": options.objectMasking = false
    case "--no-obj": options.exportOBJ = false
    case "-h", "--help": print(usage); exit(0)
    default: positional.append(a)
    }
}

guard positional.count == 2 else { print(usage); exit(2) }
let source = URL(fileURLWithPath: (positional[0] as NSString).expandingTildeInPath)
let isVideo = FrameExtractor.isVideo(source)
let outDir = URL(fileURLWithPath: (positional[1] as NSString).expandingTildeInPath, isDirectory: true)
let stem = name ?? (isVideo ? source.deletingPathExtension() : source).lastPathComponent.replacingOccurrences(of: " ", with: "-")
let folder = outDir.appendingPathComponent(stem, isDirectory: true)
let input = isVideo ? folder.appendingPathComponent("frames", isDirectory: true) : source
let usdz = folder.appendingPathComponent("\(stem).usdz")
let obj = folder.appendingPathComponent("\(stem).obj")

let started = Date()
do {
    if isVideo {
        print("Pulling \(frameCount) frames from \(source.lastPathComponent)…")
        let n = try await FrameExtractor.extract(video: source, to: input, count: frameCount) { p in
            FileHandle.standardOutput.write("\r  \(Int(p * 100))%   ".data(using: .utf8)!)
        }
        print("\n  \(n) frames written to \(input.path)")
        options.sequential = true
    }
    print("\(PhotoFolder.count(in: input)) photos · detail \(options.detail.rawValue)")
    try await ScanRunner.run(input: input, usdzURL: usdz, options: options) { event in
        switch event {
        case .stage(let s): print("\n" + s)
        case .message(let m): print("  " + m)
        case .progress(let p):
            let pct = Int(p * 100)
            FileHandle.standardOutput.write("\r  \(pct)%   ".data(using: .utf8)!)
        }
    }
    print("\nSaved \(usdz.path)")
    if options.exportOBJ {
        let s = try OBJExporter.export(usdz: usdz, to: obj, knownHeightMM: options.knownHeightMM)
        print(String(format: "Saved %@  (%.1f × %.1f × %.1f mm, %d triangles%@)", obj.path, s.sizeMM.x, s.sizeMM.y, s.sizeMM.z,
                     s.triangles, s.textureWritten ? ", with texture" : ""))
    }
    print(String(format: "Done in %.0f s", Date().timeIntervalSince(started)))
} catch {
    print("\nError: \(error.localizedDescription)")
    exit(1)
}

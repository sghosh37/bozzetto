// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// bozzetto-capture: runs Apple Object Capture on a folder of photos (or a video) and writes a USDZ.
// The Bozzetto app calls this tool on Macs; scaling and OBJ export happen in Python.
//
// bozzetto-capture <photos-folder | video.mov> <output.usdz> [options]
//   --detail preview|reduced|medium|full|raw   (default reduced)
//   --sequential                                photos taken in order (turntable)
//   --high                                      high feature sensitivity (plain products)
//   --no-mask                                   keep the background
//   --frames <n>                                frames to pull from a video (default 40)

import Foundation

let usage = """
usage: bozzetto-capture <photos-folder | video.mov> <output.usdz> [--detail reduced]
                        [--sequential] [--high] [--no-mask] [--frames 40]
"""

var args = Array(CommandLine.arguments.dropFirst())
var positional: [String] = []
var options = ScanOptions()
var frameCount = 40

while !args.isEmpty {
    let a = args.removeFirst()
    switch a {
    case "--detail":
        guard let v = args.first, let d = DetailLevel(rawValue: v) else { print(usage); exit(2) }
        options.detail = d; args.removeFirst()
    case "--frames":
        guard let v = args.first, let n = Int(v), n > 0 else { print(usage); exit(2) }
        frameCount = n; args.removeFirst()
    case "--sequential": options.sequential = true
    case "--high": options.highSensitivity = true
    case "--no-mask": options.objectMasking = false
    case "-h", "--help": print(usage); exit(0)
    default: positional.append(a)
    }
}

guard positional.count == 2 else { print(usage); exit(2) }
let source = URL(fileURLWithPath: (positional[0] as NSString).expandingTildeInPath)
let usdz = URL(fileURLWithPath: (positional[1] as NSString).expandingTildeInPath)
let isVideo = FrameExtractor.isVideo(source)
let input = isVideo
    ? usdz.deletingLastPathComponent().appendingPathComponent("frames", isDirectory: true)
    : source

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
            FileHandle.standardOutput.write("\r  \(Int(p * 100))%   ".data(using: .utf8)!)
        }
    }
    print("\nSaved \(usdz.path)")
    print(String(format: "Done in %.0f s", Date().timeIntervalSince(started)))
} catch {
    print("\nError: \(error.localizedDescription)")
    exit(1)
}

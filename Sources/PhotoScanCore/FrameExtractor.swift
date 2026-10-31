import Foundation
import AVFoundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

/// Turns a short video of the object into a folder of still photos for Object Capture.
/// Each extracted frame is a real, different viewpoint (unlike copies of one photo).
public enum FrameExtractor {
    public static let videoExtensions: Set<String> = ["mov", "mp4", "m4v"]

    public static func isVideo(_ url: URL) -> Bool { videoExtensions.contains(url.pathExtension.lowercased()) }

    /// Length of the video in seconds.
    public static func duration(of video: URL) async throws -> Double {
        let asset = AVURLAsset(url: video)
        let d = try await asset.load(.duration)
        return d.seconds.isFinite ? d.seconds : 0
    }

    /// Extracts `count` evenly spaced frames into `folder` as JPEGs.
    /// Around each point it looks at `candidates` nearby frames and keeps the sharpest,
    /// which avoids motion-blurred frames from a hand-held clip.
    /// Returns the number of frames written.
    @discardableResult
    public static func extract(video: URL,
                               to folder: URL,
                               count: Int,
                               candidates: Int = 3,
                               onProgress: @escaping @Sendable (Double) -> Void = { _ in }) async throws -> Int {
        let asset = AVURLAsset(url: video)
        let seconds = try await asset.load(.duration).seconds
        guard seconds.isFinite, seconds > 0.5 else { throw FrameError.tooShort }

        try? FileManager.default.removeItem(at: folder)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true          // keep portrait videos upright
        generator.requestedTimeToleranceBefore = CMTime(value: 1, timescale: 60)
        generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: 60)

        let n = max(1, count)
        let slot = seconds / Double(n)                           // time span each frame represents
        let c = max(1, candidates)
        var written = 0

        for i in 0..<n {
            try Task.checkCancellation()
            var best: (image: CGImage, score: Double)? = nil
            for k in 0..<c {
                // spread candidates across the middle of this slot
                let t = slot * (Double(i) + (Double(k) + 0.5) / Double(c))
                let time = CMTime(seconds: min(t, seconds - 0.01), preferredTimescale: 600)
                guard let frame = try? await generator.image(at: time).image else { continue }
                let s = sharpness(frame)
                if best == nil || s > best!.score { best = (frame, s) }
            }
            if let b = best {
                let url = folder.appendingPathComponent(String(format: "frame_%04d.jpg", i + 1))
                if writeJPEG(b.image, to: url) { written += 1 }
            }
            onProgress(Double(i + 1) / Double(n))
        }
        guard written > 0 else { throw FrameError.noFrames }
        return written
    }

    /// Simple sharpness score: average squared brightness difference between neighbouring pixels
    /// on a small greyscale copy. Blurry frames score low.
    static func sharpness(_ image: CGImage) -> Double {
        let w = 320
        let h = max(1, Int(Double(image.height) * Double(w) / Double(max(1, image.width))))
        var pixels = [UInt8](repeating: 0, count: w * h)
        let ok: Bool = pixels.withUnsafeMutableBytes { buf in
            guard let ctx = CGContext(data: buf.baseAddress, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                                      space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return false }
            ctx.interpolationQuality = .low
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard ok, w > 2, h > 2 else { return 0 }
        var sum = 0.0
        for y in 1..<(h - 1) {
            for x in 1..<(w - 1) {
                let p = Int(pixels[y * w + x])
                let lap = 4 * p - Int(pixels[y * w + x - 1]) - Int(pixels[y * w + x + 1])
                    - Int(pixels[(y - 1) * w + x]) - Int(pixels[(y + 1) * w + x])
                sum += Double(lap * lap)
            }
        }
        return sum / Double((w - 2) * (h - 2))
    }

    static func writeJPEG(_ image: CGImage, to url: URL) -> Bool {
        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { return false }
        let props = [kCGImageDestinationLossyCompressionQuality: 0.92] as CFDictionary
        CGImageDestinationAddImage(dest, image, props)
        return CGImageDestinationFinalize(dest)
    }
}

public enum FrameError: LocalizedError {
    case tooShort
    case noFrames

    public var errorDescription: String? {
        switch self {
        case .tooShort: return "The video is too short. Film at least 10–15 seconds around the object."
        case .noFrames: return "Couldn’t read any frames from the video."
        }
    }
}

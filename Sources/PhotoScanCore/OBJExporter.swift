import Foundation
import ModelIO
import simd
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

public struct MeshStats: Sendable {
    public var vertices: Int
    public var triangles: Int
    /// Width (x), height (y), depth (z) of the exported model, in mm.
    public var sizeMM: SIMD3<Double>
    /// true when the size was set from the known height you typed in
    public var scaledToKnownHeight: Bool
    public var textureWritten: Bool
}

public enum ExportError: LocalizedError {
    case noMesh
    case writeFailed(String)

    public var errorDescription: String? {
        switch self {
        case .noMesh: return "The USDZ file contains no mesh."
        case .writeFailed(let why): return "Couldn’t write the OBJ: \(why)"
        }
    }
}

/// Converts the Object Capture USDZ into a Blender-friendly OBJ:
/// millimetres, Y up, base resting on y = 0, centred on x/z, with normals, UVs and (when possible) the colour texture.
public enum OBJExporter {
    public static func export(usdz: URL, to objURL: URL, knownHeightMM: Double?) throws -> MeshStats {
        let asset = MDLAsset(url: usdz)
        asset.loadTextures()
        let meshes = asset.childObjects(of: MDLMesh.self).compactMap { $0 as? MDLMesh }
        guard !meshes.isEmpty else { throw ExportError.noMesh }

        var positions: [SIMD3<Double>] = []
        var normals: [SIMD3<Double>] = []
        var uvs: [SIMD2<Double>] = []
        var faces: [UInt32] = []
        var hasUV = true
        var baseColor: CGImage? = nil

        for mesh in meshes {
            let world = MDLTransform.globalTransform(with: mesh, atTime: 0)
            let normalMatrix = simd_float3x3(SIMD3(world.columns.0.x, world.columns.0.y, world.columns.0.z),
                                             SIMD3(world.columns.1.x, world.columns.1.y, world.columns.1.z),
                                             SIMD3(world.columns.2.x, world.columns.2.y, world.columns.2.z))
            if mesh.vertexAttributeData(forAttributeNamed: MDLVertexAttributeNormal) == nil {
                mesh.addNormals(withAttributeNamed: MDLVertexAttributeNormal, creaseThreshold: 0.5)
            }
            guard let pData = mesh.vertexAttributeData(forAttributeNamed: MDLVertexAttributePosition, as: .float3) else { continue }
            let nData = mesh.vertexAttributeData(forAttributeNamed: MDLVertexAttributeNormal, as: .float3)
            let tData = mesh.vertexAttributeData(forAttributeNamed: MDLVertexAttributeTextureCoordinate, as: .float2)
            if tData == nil { hasUV = false }

            let base = UInt32(positions.count)
            let count = mesh.vertexCount
            positions.reserveCapacity(positions.count + count)
            for i in 0..<count {
                let o = i * pData.stride
                let p = SIMD4<Float>(pData.dataStart.loadUnaligned(fromByteOffset: o, as: Float.self),
                                     pData.dataStart.loadUnaligned(fromByteOffset: o + 4, as: Float.self),
                                     pData.dataStart.loadUnaligned(fromByteOffset: o + 8, as: Float.self), 1)
                let w = world * p
                positions.append(SIMD3<Double>(Double(w.x), Double(w.y), Double(w.z)))

                if let nData {
                    let no = i * nData.stride
                    var n = SIMD3<Float>(nData.dataStart.loadUnaligned(fromByteOffset: no, as: Float.self),
                                         nData.dataStart.loadUnaligned(fromByteOffset: no + 4, as: Float.self),
                                         nData.dataStart.loadUnaligned(fromByteOffset: no + 8, as: Float.self))
                    n = simd_normalize(normalMatrix * n)
                    normals.append(SIMD3<Double>(Double(n.x), Double(n.y), Double(n.z)))
                } else {
                    normals.append(SIMD3<Double>(0, 1, 0))
                }

                if let tData {
                    let to = i * tData.stride
                    uvs.append(SIMD2<Double>(Double(tData.dataStart.loadUnaligned(fromByteOffset: to, as: Float.self)),
                                             Double(tData.dataStart.loadUnaligned(fromByteOffset: to + 4, as: Float.self))))
                } else {
                    uvs.append(SIMD2<Double>(0, 0))
                }
            }

            for case let sub as MDLSubmesh in (mesh.submeshes ?? NSMutableArray()) {
                guard sub.geometryType == .triangles else { continue }
                let buffer = sub.indexBuffer(asIndexType: .uInt32)
                let map = buffer.map()
                for k in 0..<sub.indexCount {
                    faces.append(base + map.bytes.loadUnaligned(fromByteOffset: k * 4, as: UInt32.self))
                }
                if baseColor == nil {
                    baseColor = sub.material?.property(with: .baseColor)?.textureSamplerValue?.texture?
                        .imageFromTexture()?.takeUnretainedValue()
                }
            }
        }
        guard !positions.isEmpty, !faces.isEmpty else { throw ExportError.noMesh }

        // Bounds in metres (Object Capture's unit)
        var lo = SIMD3<Double>(repeating: .infinity), hi = SIMD3<Double>(repeating: -.infinity)
        for p in positions { lo = simd_min(lo, p); hi = simd_max(hi, p) }
        let heightM = max(hi.y - lo.y, 1e-9)

        // metres -> mm, or scale so the height matches what you measured
        var scale = 1000.0
        var scaled = false
        if let h = knownHeightMM, h > 0 { scale = h / heightM; scaled = true }
        let centre = SIMD3<Double>((lo.x + hi.x) / 2, lo.y, (lo.z + hi.z) / 2)
        let size = (hi - lo) * scale

        // Texture + material (best effort; geometry is written either way)
        let stem = objURL.deletingPathExtension().lastPathComponent
        let folder = objURL.deletingLastPathComponent()
        var textureWritten = false
        if hasUV, let img = baseColor {
            let texURL = folder.appendingPathComponent("\(stem)_color.png")
            if let dest = CGImageDestinationCreateWithURL(texURL as CFURL, UTType.png.identifier as CFString, 1, nil) {
                CGImageDestinationAddImage(dest, img, nil)
                textureWritten = CGImageDestinationFinalize(dest)
            }
        }
        if textureWritten {
            let mtl = "# PhotoScan material\nnewmtl scan\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd \(stem)_color.png\n"
            try? mtl.write(to: folder.appendingPathComponent("\(stem).mtl"), atomically: true, encoding: .utf8)
        }

        // OBJ text, written in chunks so large "Raw" meshes don't use too much memory
        FileManager.default.createFile(atPath: objURL.path, contents: nil)
        guard let out = try? FileHandle(forWritingTo: objURL) else { throw ExportError.writeFailed(objURL.path) }
        defer { try? out.close() }
        var buf = String()
        buf.reserveCapacity(1 << 20)
        func emit(_ line: String) {
            buf += line
            buf += "\n"
            if buf.utf8.count > (1 << 20) { out.write(Data(buf.utf8)); buf.removeAll(keepingCapacity: true) }
        }
        func f(_ x: Double, _ d: Int) -> String { String(format: "%.\(d)f", x) }

        emit("# PhotoScan export (Apple Object Capture)")
        emit("# units: mm (1 unit = 1 mm)" + (scaled ? ", scaled to the known height you entered" : ", size from Object Capture (true scale only if the photos carried depth data)"))
        emit("# size (W x H x D): \(f(size.x, 2)) x \(f(size.y, 2)) x \(f(size.z, 2)) mm")
        emit("# vertices: \(positions.count), triangles: \(faces.count / 3)")
        emit("# Y is up; the base of the object sits at y = 0")
        if textureWritten { emit("mtllib \(stem).mtl") }
        emit("o \(stem)")
        for p in positions {
            let q = (p - centre) * scale
            emit("v \(f(q.x, 3)) \(f(q.y, 3)) \(f(q.z, 3))")
        }
        if hasUV { for t in uvs { emit("vt \(f(t.x, 5)) \(f(t.y, 5))") } }
        for n in normals { emit("vn \(f(n.x, 4)) \(f(n.y, 4)) \(f(n.z, 4))") }
        if textureWritten { emit("usemtl scan") }
        var t = 0
        while t + 2 < faces.count {
            let a = faces[t] + 1, b = faces[t + 1] + 1, c = faces[t + 2] + 1
            if hasUV { emit("f \(a)/\(a)/\(a) \(b)/\(b)/\(b) \(c)/\(c)/\(c)") }
            else { emit("f \(a)//\(a) \(b)//\(b) \(c)//\(c)") }
            t += 3
        }
        if !buf.isEmpty { out.write(Data(buf.utf8)) }

        return MeshStats(vertices: positions.count, triangles: faces.count / 3,
                         sizeMM: size, scaledToKnownHeight: scaled, textureWritten: textureWritten)
    }
}

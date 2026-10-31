// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "PhotoScan",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "PhotoScan", targets: ["PhotoScan"]),
        .executable(name: "photoscan-cli", targets: ["PhotoScanCLI"]),
    ],
    targets: [
        // Object Capture run + OBJ writer, shared by the app and the command-line tool
        .target(name: "PhotoScanCore"),
        // The Mac app (SwiftUI)
        .executableTarget(name: "PhotoScan", dependencies: ["PhotoScanCore"]),
        // Optional command-line version, for batch jobs
        .executableTarget(name: "PhotoScanCLI", dependencies: ["PhotoScanCore"]),
    ]
)

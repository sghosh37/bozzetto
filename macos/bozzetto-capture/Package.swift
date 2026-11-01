// swift-tools-version:5.9
// SPDX-License-Identifier: GPL-3.0-or-later
import PackageDescription

let package = Package(
    name: "bozzetto-capture",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "bozzetto-capture", targets: ["BozzettoCapture"])],
    targets: [.executableTarget(name: "BozzettoCapture")]
)

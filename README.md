# PhotoScan

A small Mac app that turns a folder of product photos into a 3D model, using Apple's built-in
**Object Capture** (photogrammetry). Everything runs on your Mac and nothing is uploaded. It's free.

It saves two files:

- `name.usdz`: the textured model as Object Capture made it (opens in Preview / Quick Look).
- `name.obj` (+ `.mtl` and `_color.png` when a texture can be extracted): ready for Blender, in
  **millimetres**, **Y up**, with the base resting on y = 0 and the object centred.

## Requirements

- A Mac with **Apple Silicon** (M1 or newer). Some Intel Macs with a strong AMD GPU work too; if
  yours can't, the app says so.
- **macOS 13 Ventura** or newer.
- Apple's free developer tools: either Xcode from the App Store, or just the command-line tools.

## Install (one time, about 5 minutes)

1. Open **Terminal** (Applications → Utilities).
2. If you don't have Xcode, install the command-line tools:
   ```
   xcode-select --install
   ```
3. Go to this folder (type `cd `, a space, drag the PhotoScan folder into the Terminal window, press Return), then:
   ```
   chmod +x build-app.sh
   ./build-app.sh
   ```
4. A Finder window opens on `dist`. Drag **PhotoScan.app** into **Applications**.

If the build stops with an error, copy the red error lines and send them to Claude; it's usually a one-line fix.

## Use

1. Pick the **Source**:
   - **Photo folder**: JPEG, HEIC or PNG (export RAW files to JPEG first).
   - **Video**: a MOV or MP4 that slowly circles the object (15–30 s). PhotoScan pulls out evenly spaced
     frames (default about 2 per second, adjustable), keeping the sharpest of 3 nearby frames each time,
     saves them in `<model>/frames/`, and scans them. This is the easy way to get enough viewpoints
     without taking dozens of photos.
2. **Choose…** where to save. The model goes into a new folder named after the model.
3. Pick a **Preset**:
   - **Quick shape (3–20 photos)**, the default: Reduced detail, high feature sensitivity. A rough mesh to refine in Blender.
   - **Balanced (20–50 photos)**: Medium detail.
   - **Detailed (60–80 photos)**: Full detail.
   You can still change *Detail* and the switches by hand after picking a preset.
4. Options:
   - **Photos taken in order** when you shot on a turntable, one photo after another.
   - **Plain or low-texture product** for white tubes, solid-colour bottles and the like.
   - **Remove the background**: leave on.
   - **Scale to the real height**: measure the product with a ruler or calipers and type its height.
     Without this, the size is only true to life if the photos carry depth data (iPhone HEIC).
5. **Build 3D model**. A Full model from about 70 photos usually takes a few minutes on an M-series Mac.

## Changing the defaults later

- Minimum photos: `minimumPhotos` in `Sources/PhotoScanCore/ScanRunner.swift` (now 3).
- Default detail: `detail` in `ScanOptions` (same file), and the presets in `applyPreset()` in `Sources/PhotoScan/PhotoScanApp.swift`.
- After any change, run `./build-app.sh` again.

Note: the app lets you start with 3 photos, but Apple's Object Capture decides whether it can build
from them. With very few photos it often can't; add photos until it works (10–20 is usually enough
for a rough shape).

## Shooting a video instead of photos

- Phone or camera on a gimbal/steady hand, or the product on a slowly turning turntable with the camera fixed.
- One slow full circle (15–30 s), then optionally a second circle higher up. Move slowly: blur is the enemy.
- Lock exposure and focus (on iPhone: long-press to set AE/AF lock). 4K if possible; 1080p works.
- Same lighting rules as photos: soft, even, polarised for glossy packaging.

## Shooting for good results

- 60–80 photos: two or three rings around the product (low, eye level, high) plus a few from above.
  Each photo should overlap its neighbour by about 70%.
- Turntable, 10–15° per shot, camera fixed. Keep the background plain and the product filling most of the frame.
- Everything sharp: f/8–f/11, no motion blur. Even, soft light, no harsh shadows. Don't change zoom between shots.
- **Glossy packaging:** cross-polarise (polariser on the lens, polarising gel on the lights, at 90°).
  Reflections that move between photos are the main cause of holes and bumps.
- **Clear glass or plastic:** photos alone can't capture it. Use a vanishing 3D-scanning spray, or model it in Blender.
- Plain surfaces with no texture: add a few small markers or a patterned card next to the product.

## Open in Blender

- **OBJ:** File → Import → Wavefront (.obj). Leave *Up* = Y and *Forward* = −Z. The file is in
  millimetres; Blender works in metres, so set **Scale = 0.001** in the import options (or set
  the scene unit scale to 0.001). The texture loads automatically when `_color.png` was written.
- **USDZ:** File → Import → Universal Scene Description, if your Blender version accepts .usdz.
  Use this when you want all the texture maps.
- If the texture looks scrambled on the OBJ, use the USDZ for colour and the OBJ for shape.

## Command line (optional)

`dist/photoscan-cli` does the same job for batches:

```
./dist/photoscan-cli ~/Pictures/lipstick ~/Models --detail full --height-mm 82 --sequential
./dist/photoscan-cli ~/Movies/lipstick.mov ~/Models --frames 40
```

Options: `--detail preview|reduced|medium|full|raw`, `--height-mm N`, `--sequential`, `--high`,
`--no-mask`, `--no-obj`, `--name NAME`, `--frames N` (video input).

## Files

- `Sources/PhotoScanCore/ScanRunner.swift`: runs Object Capture (`PhotogrammetrySession`).
- `Sources/PhotoScanCore/FrameExtractor.swift`: video → sharpest evenly spaced frames (JPEG).
- `Sources/PhotoScanCore/OBJExporter.swift`: USDZ → OBJ (mm, Y up, base at 0, centred, scaling, texture).
- `Sources/PhotoScan/PhotoScanApp.swift`: the app window.
- `Sources/PhotoScanCLI/main.swift`: the command-line tool.
- `build-app.sh`, `Resources/Info.plist`: build the `.app`.
- `docs/index.html`: full design and photo-capture guide (open in a browser, or publish with GitHub Pages from `/docs`).

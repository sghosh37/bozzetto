# Bozzetto

## What the name means

A **bozzetto** (Italian, pronounced *bot-SET-toh*; plural *bozzetti*) is the small, rough model a
sculptor shapes in clay or wax before the real work. The word comes from *bozza*, “rough draft”.
A bozzetto isn’t meant to be finished or exact. It fixes the overall form, proportions and pose
quickly, so the artist can judge the idea and then refine it at full size. Michelangelo and Bernini
both made them.

That is what this software makes: a quick first shape of a real object, built from a few photos,
for you to refine and finish in Blender.

## What it does

**Photos to a rough 3D shape for sculpting.** Bozzetto turns product photos, or a short video
circling the product, into a closed OBJ mesh, in millimetres, Y up, base at 0, that you refine in Blender.

It runs on **Windows, Linux and macOS** and picks a scanning engine for your photos and your computer:

| Engine | Photos | Status |
|---|---|---|
| **TripoSR**: AI shape from one photo (hidden sides guessed) | 1+ | ✅ stage 2 |
| **Turntable silhouette**: carves the outline from every angle | 6–30 on a turntable | ✅ stage 1 |
| **Apple Object Capture**: photogrammetry built into macOS | 20+ | ⏳ stage 3 (Mac) |
| **COLMAP + OpenMVS**: open-source photogrammetry | 20+ | ⏳ stage 4 |

Licence: **GPL-3.0-or-later**. Third-party parts and their licences: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Install (from source, for now)

Needs Python 3.10 or newer.

```
git clone https://github.com/sghosh37/3d-scan.git
cd 3d-scan
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -e .                 # the app and the silhouette engine
pip install -e ".[triposr]"      # optional: the TripoSR one-photo engine (PyTorch, ~1–2 GB)
```

Ready-made downloads (Windows .exe, Mac .app, Linux AppImage) come with stage 5.

## Use

**Window:** run `bozzetto`, choose a photo folder (or a video), and press **Build 3D model**.
The window shows which engine it picked and why; the Engine list lets you choose another.

**Command line:**

```
bozzetto-cli photos/lipstick out/ --height-mm 82          # automatic engine
bozzetto-cli lipstick.jpg out/ --engine triposr --height-mm 82
bozzetto-cli lipstick.mov out/ --frames 40                  # from a video
```

Options: `--engine auto|silhouette|triposr`, `--preset quick|accurate`, `--height-mm`, `--tilt` (camera
tilt, silhouette engine), `--clockwise`, `--frames`, `--glb`, `--name`, `--yes` (download without asking).

**Real size:** photos carry no scale. Measure the product’s height and enter it (`--height-mm` or
“I measured the real height”). Without it the model is scaled to 100 mm high.

**TripoSR first run:** downloads the model once (about 1.7 GB, MIT licence) from Hugging Face
into your user data folder. It runs on an NVIDIA GPU, an Apple Silicon GPU or the CPU (about a minute).

## Shooting

- **One photo (TripoSR):** the product filling most of the frame, a three-quarter view, plain background.
- **Turntable (silhouette):** 12–30 photos, one full turn in equal steps, camera fixed and tilted down
  about 20°, plain backdrop that contrasts with the product. Enter the tilt if it differs.
- **Video:** one slow 15–30 s circle; Bozzetto keeps the sharpest frame around each point in time.

The full photo guide is [`docs/capture.html`](docs/capture.html). The software design, with diagrams
of every part, is [`docs/design.html`](docs/design.html).

## Repository

```
bozzetto/
  app/          Qt window, worker threads, 3D preview
  core/         models, inputs, hardware, select (engine rules), masks, export, downloads, settings, pipeline
  engines/      base, silhouette, triposr (+ vendored tsr/, MIT), later (Apple, COLMAP: planned)
  cli.py
macos/bozzetto-capture/   Swift helper for Apple Object Capture (stage 3)
tests/          unit tests and synthetic turntable scans
docs/           capture.html, design.html, src/ (builds design.html)
```

Run the tests with `pip install -e ".[dev]"` then `pytest`.

Change the automatic engine choice in `bozzetto/core/select.py` (`RULES`), and the silhouette
engine’s detail in `bozzetto/engines/silhouette.py` (voxel resolution 160 / 224).

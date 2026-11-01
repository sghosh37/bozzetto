# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the inline SVG diagrams for docs/design.html."""
from html import escape


class D:
    def __init__(self, w, h, label, pid):
        self.w, self.h, self.label, self.pid = w, h, label, pid
        self.parts = []

    # --- primitives -------------------------------------------------------
    def rect(self, x, y, w, h, kind="box", r=10, dashed=False):
        dash = ' stroke-dasharray="5 5"' if dashed else ""
        self.parts.append(f'<rect class="d-{kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"{dash}/>')

    def text(self, x, y, t, cls="d-t", anchor="start"):
        self.parts.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{escape(t)}</text>')

    def box(self, x, y, w, h, title=None, lines=(), kind="box", mono=False, center=False, tag=None, dashed=False):
        self.rect(x, y, w, h, kind, dashed=dashed)
        ax = x + w / 2 if center else x + 14
        anchor = "middle" if center else "start"
        n = (1 if title else 0) + len(lines)
        lh = 17 if mono else 18
        inv = " d-inv" if kind == "dark" else ""
        top = y + (h - n * lh) / 2 + 13 if center else y + 24
        cy = top
        if title:
            self.text(ax, cy, title, "d-tb" + inv, anchor)
            cy += lh + (3 if lines else 0)
        for ln in lines:
            self.text(ax, cy, ln, ("d-tm" if mono else "d-ts") + inv, anchor)
            cy += lh
        if tag:
            self.text(x + w - 12, y + 20, tag, "d-tag", "end")

    def diamond(self, cx, cy, w, h, lines):
        pts = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
        self.parts.append(f'<polygon class="d-dia" points="{pts}"/>')
        y0 = cy - (len(lines) - 1) * 9 + 5
        for i, ln in enumerate(lines):
            self.text(cx, y0 + i * 18, ln, "d-tb", "middle")

    def arrow(self, pts, label=None, lx=None, ly=None, dashed=False, head=True, anchor="start", cls="d-line"):
        d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
        dash = ' stroke-dasharray="5 5"' if dashed else ""
        mk = f' marker-end="url(#{self.pid}-ah)"' if head else ""
        self.parts.append(f'<path class="{cls}" d="{d}"{dash}{mk}/>')
        if label:
            if lx is None:
                (x1, y1), (x2, y2) = pts[-2], pts[-1]
                lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 7
                anchor = "middle"
            self.text(lx, ly, label, "d-tl", anchor)

    def band(self, x, y, w, h, label):
        self.rect(x, y, w, h, "band", r=14, dashed=True)
        self.text(x + 14, y + 20, label, "d-tm")

    def svg(self, min_w=None):
        mw = f' style="min-width:{min_w}px"' if min_w else ""
        defs = (f'<defs><marker id="{self.pid}-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" class="d-head"/></marker></defs>')
        return (f'<svg viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}"{mw}>'
                + defs + "".join(self.parts) + "</svg>")


# ----------------------------------------------------------------------------
def architecture():
    d = D(1000, 560, "Layers: the Qt window, the core modules, the four engines (two built, two planned), "
                     "and the output files.", "arch")
    d.box(20, 20, 960, 70, "Desktop app · bozzetto/app (PySide6)",
          ["Input (photos or video), preset, engine + reason, real height, tilt, progress, log, 3D preview, Open in Blender."],
          kind="dark")
    d.arrow([(500, 90), (500, 128)], "Job", 512, 113)
    d.band(20, 130, 960, 150, "bozzetto/core · pure Python, no Qt  (bozzetto-cli uses the same core)")
    xs = [36, 226, 416, 606, 796]
    items = [("inputs · masks", ["photos, video frames,", "copies, cut-out, turntable"]),
             ("hardware", ["OS, NVIDIA (nvidia-smi),", "Apple GPU, RAM"]),
             ("select · pipeline", ["rules table → Choice;", "check, download, run"]),
             ("export · meshops", ["mm, Y up, base 0, clean,", "OBJ + MTL, GLB"]),
             ("downloads · settings", ["Hugging Face, SHA-256,", "settings.json"])]
    for x, (t, ls) in zip(xs, items):
        d.box(x, 160, 170, 100, t, ls, kind="key" if t.startswith("select") else "box")
    d.arrow([(500, 280), (500, 318)], "engine.run(job, progress, cancel)", 512, 303)
    d.band(20, 320, 960, 150, "bozzetto/engines · one class each, same interface")
    eng = [("silhouette.py", ["built · NumPy, OpenCV,", "scikit-image, SciPy"], "orange"),
           ("triposr.py + tsr/", ["built · PyTorch on", "CUDA, MPS or CPU"], "teal"),
           ("Apple (planned)", ["stage 3 · runs", "bozzetto-capture (Swift)"], "slate"),
           ("COLMAP (planned)", ["stage 4 · COLMAP + OpenMVS,", "downloaded programs"], "blue")]
    for i, (t, ls, k) in enumerate(eng):
        d.box(36 + i * 236, 350, 220, 100, t, ls, kind=k, dashed="planned" in t)
    d.arrow([(500, 470), (500, 498)], "RawMesh", 512, 489)
    d.box(330, 500, 340, 48, None, ["name.obj (+ .mtl, texture, .glb)"], kind="ok", center=True)
    return d.svg(760)


def modules():
    d = D(1000, 430, "Module dependencies: app and cli use core.pipeline; pipeline uses select, export and the engines; "
                     "engines use core.models, masks, inputs and downloads; core.models depends on nothing.", "mods")
    d.box(250, 20, 220, 56, "app/", ["main_window · worker · preview"], kind="dark")
    d.box(530, 20, 220, 56, "cli.py", ["bozzetto-cli"], kind="dark")
    d.box(390, 130, 220, 56, "core/pipeline.py", ["check → download → run → export"], kind="key")
    d.box(40, 240, 220, 56, "engines/", ["silhouette · triposr · later"])
    d.box(300, 240, 190, 56, "core/select.py", ["RULES → Choice"])
    d.box(510, 240, 190, 56, "core/export.py", ["+ meshops.py"])
    d.box(740, 240, 220, 56, "core/inputs.py", ["+ masks.py · hardware.py"])
    d.box(40, 340, 220, 56, "core/downloads.py", ["+ settings.py (paths)"])
    d.box(330, 360, 340, 56, "core/models.py", ["dataclasses + errors, imports nothing"], kind="ok")
    d.arrow([(360, 76), (460, 128)])
    d.arrow([(640, 76), (540, 128)])
    d.arrow([(250, 50), (150, 50), (150, 238)])
    d.arrow([(750, 50), (850, 50), (850, 238)])
    d.arrow([(420, 186), (150, 186), (150, 238)])
    d.arrow([(470, 186), (395, 238)])
    d.arrow([(530, 186), (605, 238)])
    d.arrow([(150, 296), (150, 338)])
    d.arrow([(260, 268), (298, 268)], dashed=True)
    d.arrow([(260, 368), (328, 388)])
    d.arrow([(395, 296), (430, 358)])
    d.arrow([(605, 296), (570, 358)])
    d.arrow([(850, 296), (850, 388), (672, 388)])
    return d.svg(760)


def data_model():
    d = D(1000, 780, "Data model: Job holds an InputSet and options; Hardware describes the computer; the selector "
                     "returns a Choice; engines report Status, Fit and Progress and return a RawMesh; export produces "
                     "a Result; failures raise ScanError.", "dm")
    def cls(x, y, w, name, fields, kind="box"):
        h = 34 + 17 * len(fields) + 8
        d.rect(x, y, w, h, kind)
        d.text(x + 12, y + 22, name, "d-tb")
        d.parts.append(f'<line class="d-sep" x1="{x}" y1="{y + 32}" x2="{x + w}" y2="{y + 32}"/>')
        for i, f in enumerate(fields):
            d.text(x + 12, y + 50 + i * 17, f, "d-tm")
        return h
    cls(20, 20, 300, "Job", ["inputs: InputSet", "preset: Preset  (QUICK | ACCURATE)", "engine_id: str | None  (None = auto)",
                              "height_mm: float | None", "camera_tilt_deg: float = 20", "turn_clockwise: bool = False",
                              "outputs: frozenset[\"obj\" | \"glb\"]", "out_dir: Path · name: str", "id: str"], kind="key")
    cls(350, 20, 310, "InputSet", ["kind: InputKind  (PHOTOS | VIDEO)", "source: Path", "frames: tuple[Path, ...]",
                                    "duplicates: tuple[(copy, original)]", "image_size: (width, height)",
                                    "focal_mm: float | None · focal_35mm", "turntable_score: float  (0–1)",
                                    "marker_mat: bool  (planned)"])
    cls(690, 20, 290, "Hardware", ["os: \"windows\" | \"linux\" | \"macos\"", "os_version · arch", "cpu_count · ram_gb",
                                    "nvidia: GpuInfo | None", "apple_gpu: bool  (MPS)", "object_capture: bool"])
    cls(20, 330, 300, "Choice", ["engine_id: str", "reason: str", "warnings: tuple[str]", "fallbacks: tuple[str]"], kind="key")
    cls(350, 330, 310, "Status  /  Fit", ["Status.state: READY | NEEDS_DOWNLOAD", "              | UNSUPPORTED",
                                          "Status.reason · Status.download", "DownloadSpec: title, size, licence, url",
                                          "Fit.level: GOOD | SLOW | UNSUITABLE", "Fit.reason · Fit.est_seconds"])
    cls(690, 300, 290, "Progress", ["stage: str", "fraction: float | None", "message: str | None"])
    cls(690, 420, 290, "ScanError(Exception)", ["code: ErrorCode", "user_message: str", "detail: str",
                                                 "suggest_engine: str | None", "Cancelled(ScanError)"], kind="warn")
    cls(20, 520, 300, "RawMesh", ["vertices: float32[N, 3]", "faces: int32[M, 3]", "units: \"m\" | \"mm\" | \"unit\"",
                                   "up_axis: \"y\" | \"z\"", "vertex_colors: uint8[N, 3] | None",
                                   "uvs · texture · extra_files"])
    cls(350, 560, 310, "Result", ["job_id · engine_id", "files: dict[str, Path]",
                                   "size_mm: (W, H, D)", "triangles: int · seconds: float",
                                   "scaled_to_height: bool", "log: tuple[str]"], kind="ok")
    d.arrow([(320, 60), (348, 60)], None)
    d.arrow([(170, 215), (170, 328)], "select.choose(job, hw)", 180, 275, anchor="start")
    d.arrow([(170, 440), (170, 518)], "engine.run()", 180, 482, anchor="start")
    d.arrow([(320, 620), (348, 620)], None)
    return d.svg(820)


def sequence():
    cols = [("User", 60), ("MainWindow", 200), ("JobRunner", 350), ("inputs", 490), ("select", 610),
            ("Engine", 740), ("export", 880)]
    d = D(960, 700, "Sequence of one scan: choosing the folder inspects the inputs and picks an engine; Build starts a "
                    "JobRunner on a worker thread that may download the engine, runs it with progress callbacks, "
                    "exports the mesh and returns a Result to the window.", "seq")
    for name, x in cols:
        d.box(x - 58, 14, 116, 36, None, [name], kind="dark" if name == "User" else "box", center=True)
        d.parts.append(f'<line class="d-life" x1="{x}" y1="50" x2="{x}" y2="690"/>')
    X = dict(cols)
    msgs = [
        ("User", "MainWindow", "choose folder / video", 78),
        ("MainWindow", "inputs", "inspect(path) → InputSet", 108),
        ("MainWindow", "select", "choose(job, hw) → Choice", 138),
        ("MainWindow", "User", "show engine + reason", 168, True),
        ("User", "MainWindow", "Build 3D model", 210),
        ("MainWindow", "JobRunner", "start(job) on QThread", 240),
        ("JobRunner", "Engine", "check(hw) → Status", 270),
        ("JobRunner", "MainWindow", "need download? → dialog", 300, True),
        ("JobRunner", "Engine", "run(job, progress, cancel)", 340),
        ("Engine", "JobRunner", "progress(Progress) …", 372, True),
        ("JobRunner", "MainWindow", "signal progress", 402, True),
        ("Engine", "JobRunner", "RawMesh", 440, True),
        ("JobRunner", "export", "write(mesh, job) → Result", 474),
        ("JobRunner", "MainWindow", "signal finished(Result)", 512, True),
        ("MainWindow", "User", "preview, size, Open in Blender", 542, True),
        ("User", "MainWindow", "Cancel (any time)", 590),
        ("MainWindow", "JobRunner", "cancel.set()", 620),
        ("JobRunner", "Engine", "cancel() · kill subprocess", 650),
    ]
    for m in msgs:
        a, b, label, y = m[:4]
        ret = len(m) > 4
        x1, x2 = X[a], X[b]
        d.arrow([(x1, y), (x2 + (-4 if x2 > x1 else 4), y)], label, (x1 + x2) / 2, y - 7, dashed=ret, anchor="middle")
    d.text(20, 575, "", "d-tl")
    return d.svg(820)


def states():
    d = D(1000, 390, "Window states: Empty, Inspecting, Ready, Running, Done, Failed and Cancelled; a download "
                     "dialog appears between Ready and Running when the engine is missing.", "st")
    S = {"Empty": (20, 150), "Inspecting": (190, 150), "Ready": (360, 150), "Download dialog": (560, 30),
         "Running": (560, 150), "Done": (800, 30), "Failed": (800, 150), "Cancelled": (800, 250)}
    for n, (x, y) in S.items():
        k = "ok" if n == "Done" else "warn" if n == "Failed" else "key" if n == "Running" else "box"
        d.box(x, y, 120 if n != "Download dialog" else 140, 50, None, [n], kind=k, center=True,
              dashed=n == "Download dialog")
    d.arrow([(140, 175), (188, 175)], "input", 164, 166, anchor="middle")
    d.arrow([(310, 175), (358, 175)], "ok", 334, 166, anchor="middle")
    d.arrow([(250, 200), (250, 240), (80, 240), (80, 202)], "error", 165, 256, anchor="middle")
    d.arrow([(480, 175), (558, 175)], "Build", 519, 166, anchor="middle")
    d.arrow([(420, 150), (420, 55), (558, 55)], "engine missing", 432, 46)
    d.arrow([(630, 80), (630, 148)], "Yes", 638, 120)
    d.arrow([(680, 165), (710, 165), (710, 55), (798, 55)], "Result", 718, 100)
    d.arrow([(680, 175), (798, 175)], "ScanError", 757, 166, anchor="middle")
    d.arrow([(680, 185), (710, 185), (710, 275), (798, 275)], "Cancel", 718, 235)
    d.arrow([(920, 55), (970, 55), (970, 340), (400, 340), (400, 202)], "New scan / change settings", 685, 333)
    d.arrow([(920, 175), (950, 175), (950, 320), (420, 320), (420, 202)], "Retry with … (suggest_engine)", 685, 313)
    d.arrow([(920, 275), (935, 275), (935, 360), (440, 360), (440, 202)], "Build again", 685, 353)
    return d.svg(820)


def threading():
    d = D(1000, 300, "Threads: the Qt main thread owns the window; a QThread runs JobRunner; engines that are separate "
                     "programs run as subprocesses; progress flows back as Qt signals and cancellation as a threading.Event.", "thr")
    d.box(20, 40, 250, 220, "Main thread (Qt)", ["MainWindow, dialogs, preview", "never blocks", "",
                                                  "slots: on_progress()", "       on_finished()", "       on_failed()"], kind="dark")
    d.box(370, 40, 250, 220, "Worker QThread", ["JobRunner.run()", "  downloads.ensure()", "  engine.run()", "  export.write()",
                                                 "", "cancel: threading.Event", "polled between steps"], kind="key")
    d.box(730, 40, 250, 100, "Engine subprocess", ["bozzetto-capture · colmap", "OpenMVS tools", "stdout parsed line by line"])
    d.box(730, 160, 250, 100, "In-process engine", ["silhouette (NumPy)", "TripoSR (PyTorch)", "checks cancel each step"])
    d.arrow([(270, 90), (368, 90)], "start(job)", 319, 82, anchor="middle")
    d.arrow([(368, 200), (272, 200)], "Qt signals", 319, 192, anchor="middle")
    d.arrow([(620, 80), (728, 80)], "Popen", 674, 72, anchor="middle")
    d.arrow([(728, 115), (622, 115)], "stdout lines", 674, 107, anchor="middle", dashed=True)
    d.arrow([(620, 210), (728, 210)], "direct call", 674, 202, anchor="middle")
    return d.svg(760)


def selection():
    rows = [(150, ["1–2 different", "photos?"], "TripoSR", ["one photo → closed shape"], "teal"),
            (270, ["Mac + Object Capture,", "20+ photos?"], "Apple Object Capture", ["stage 3 · skipped until built"], "slate"),
            (390, ["Turntable, 6+ photos, and ≤30", "or no GPU or Quick?"], "Turntable silhouette", ["seconds, no GPU"], "orange"),
            (510, ["20+ photos and", "an NVIDIA GPU?"], "COLMAP + OpenMVS (GPU)", ["stage 4 · skipped until built"], "blue"),
            (630, ["20+ photos?"], "COLMAP + OpenMVS (CPU)", ["stage 4 · with a time warning"], "blue"),
            (750, ["6+ photos?"], "Turntable silhouette", ["best guess, with a warning"], "orange")]
    d = D(1000, 900, "Automatic engine choice: the first matching rule whose engine can run here wins; engines not "
                     "built yet are skipped; the last resort is TripoSR on the sharpest photo.", "sel")
    d.box(110, 16, 260, 52, None, ["InputSet + Preset + Hardware"], kind="dark", center=True)
    d.arrow([(240, 68), (240, 103)])
    for i, (cy, q, eng, sub, k) in enumerate(rows):
        d.diamond(240, cy, 300, 90, q)
        d.arrow([(390, cy), (538, cy)], "yes", 400, cy - 8)
        d.box(540, cy - 32, 300, 64, eng, sub, kind=k, dashed="stage" in sub[0])
        nxt = rows[i + 1][0] - 45 if i + 1 < len(rows) else 818
        d.arrow([(240, cy + 45), (240, nxt - 2)], "no", 250, cy + 64)
    d.box(110, 820, 260, 64, "TripoSR (last resort)", ["on the sharpest photo"], kind="teal")
    d.box(860, 120, 130, 330, None, [], kind="band")
    d.text(872, 146, "Notes", "d-tb")
    for i, ln in enumerate(["Turntable =", "turntable_score", "> 0.7", "", "Your choice in", "the Engine list", "overrides all", "rules; failures", "offer the next", "engine to retry"]):
        d.text(872, 170 + i * 18, ln, "d-ts")
    return d.svg(820)


def silhouette():
    d = D(1000, 300, "Silhouette pipeline with data shapes: frames → masks → camera → carved voxels → base-wedge trim "
                     "→ mesh → RawMesh in arbitrary units, scaled by export.", "sil")
    steps = [("1 Cut out", ["≤1200 px wide", "masks: uint8[H, W]", "border colour, Otsu"]),
             ("2 Camera", ["fx from EXIF or 50°", "axis = median centre", "tilt θ, distance 1"]),
             ("3 Box", ["radius from widths", "height from rows", "160³ / 224³ voxels"]),
             ("4 Carve", ["keep voxel if inside", "every (±2 px) mask", "1 miss per 36 photos"]),
             ("5 Trim base", ["remove layers that", "grow at ≈1/tan θ", "(hidden underside)"]),
             ("6 Mesh", ["Gaussian σ 0.8,", "marching cubes,", "Taubin ×4 in export"])]
    for i, (t, ls) in enumerate(steps):
        x = 10 + i * 166
        d.box(x, 40, 146, 130, t, ls, kind="key" if i in (3, 4) else "ok" if i == 5 else "box")
        if i:
            d.arrow([(x - 20, 105), (x - 2, 105)])
    d.box(10, 200, 980, 84, "Carving, per photo i (vectorised in NumPy)", [
        "angle = ±2π·i/N;   p = K · R_cam · (R_y(angle) · voxel − C)",
        "a kept voxel whose (u, v) falls outside the dilated mask gets a miss; it is dropped after more misses than allowed"],
        kind="band")
    return d.svg(820)


def apple_protocol():
    d = D(1000, 330, "Apple engine: apple.py (stage 3) starts bozzetto-capture with --json and reads one JSON object per line: stage, "
                     "progress, message, done or error.", "apl")
    d.box(20, 30, 300, 120, "apple.py", ["Popen([cli, input, out, \"--json\",", "  \"--detail\", d, \"--no-obj\"])",
                                         "reads stdout line by line"], kind="slate", mono=True)
    d.box(680, 30, 300, 120, "bozzetto-capture (Swift)", ["PhotogrammetrySession", "writes name.usdz",
                                                         "--json → one event per line"], kind="slate")
    d.arrow([(320, 70), (678, 70)], "arguments", 499, 62, anchor="middle")
    d.arrow([(678, 120), (322, 120)], "JSON lines on stdout", 499, 112, anchor="middle", dashed=True)
    d.box(20, 180, 960, 132, "Events (stdout, one per line)", [
        '{"type": "stage",    "text": "Building the model…"}',
        '{"type": "progress", "value": 0.42}',
        '{"type": "message",  "text": "Photo #7 not used: …"}',
        '{"type": "done",     "usdz": "/…/name.usdz"}          then apple.py reads the USDZ → RawMesh',
        '{"type": "error",    "code": "NO_MODEL", "message": "…"}   → ScanError'], kind="band", mono=True)
    return d.svg(820)


def colmap():
    d = D(1000, 300, "COLMAP + OpenMVS pipeline with the share of the progress bar for each step.", "col")
    steps = [("feature_extractor", "COLMAP", "10%"), ("matcher", "COLMAP · seq./exhaustive", "15%"),
             ("mapper", "COLMAP · camera poses", "15%"), ("image_undistorter", "COLMAP", "5%"),
             ("InterfaceCOLMAP", "OpenMVS", "2%"), ("DensifyPointCloud", "OpenMVS", "33%"),
             ("ReconstructMesh", "OpenMVS", "10%"), ("TextureMesh", "OpenMVS", "10%")]
    for i, (t, sub, pct) in enumerate(steps):
        row, col = divmod(i, 4)
        x, y = 20 + col * 245, 30 + row * 130
        d.box(x, y, 215, 90, t, [sub, f"progress share {pct}"], kind="blue" if "Open" in sub else "box", mono=False)
        if col:
            d.arrow([(x - 30, y + 45), (x - 2, y + 45)])
    d.arrow([(912, 120), (912, 140), (127, 140), (127, 158)])
    d.text(20, 286, "Quick preset: --max_image_size 1600, DensifyPointCloud --resolution-level 2.  "
                     "No NVIDIA: COLMAP SiftExtraction.use_gpu 0, OpenMVS runs on CPU.", "d-ts")
    return d.svg(820)


def downloads():
    d = D(1000, 270, "Download flow: Status says what is missing; the window asks; the engine downloads into the "
                     "user data folder and records it in installed.json.", "dl")
    xs = [20, 215, 410, 605, 800]
    items = [("check()", ["NEEDS_DOWNLOAD", "+ DownloadSpec"]), ("Dialog", ["size, licence, source;", "Yes / No"]),
             ("prepare()", ["hf_hub_download (TripoSR)", "or fetch() for binaries"]),
             ("verify", ["hub checksums, or", "SHA-256 in fetch()"]),
             ("install", ["engines/triposr/", "installed.json"])]
    for x, (t, ls) in zip(xs, items):
        d.box(x, 30, 175, 90, t, ls, kind="warn" if t == "verify" else "box")
    for x in xs[1:]:
        d.arrow([(x - 20, 75), (x - 2, 75)])
    d.box(20, 150, 960, 104, "User data folder (platformdirs.user_data_dir(\"Bozzetto\") / engines)", [
        "Windows  %LOCALAPPDATA%\\Bozzetto\\engines",
        "macOS    ~/Library/Application Support/Bozzetto/engines",
        "Linux    ~/.local/share/Bozzetto/engines",
        "TripoSR: config.yaml + model.ckpt (1.7 GB, MIT) + dino-vitb16/config.json"],
        kind="band", mono=True)
    return d.svg(820)


def web():
    d = D(1000, 380, "Browser version: the page reads files or video frames, a Web Worker runs the ported core, "
                     "and the page shows the model and offers OBJ and GLB downloads.", "web")
    d.band(20, 20, 300, 340, "page · app.js")
    d.box(36, 52, 268, 74, "Input", ["drop, photos, folder, video", "settings (remembered)"])
    d.box(36, 140, 268, 74, "video.js", ["seek, sharpest of 3 per slot,", "≤ 1200 px frames"])
    d.box(36, 228, 268, 116, "Result", ["viewer.js: WebGL preview", "size, triangles, time", "Download OBJ / GLB"], kind="ok")
    d.band(360, 20, 620, 340, "worker.js · Web Worker")
    d.box(376, 52, 280, 74, "decode", ["createImageBitmap → OffscreenCanvas", "≤ 1200 px, RGBA"])
    d.box(376, 140, 280, 74, "inputs.js", ["copies (SHA-256), EXIF focal,", "turntable score"])
    d.box(376, 228, 280, 116, "pipeline.js", ["silhouette.js: cut-out, camera, carve,", "trim; volume.js: Gaussian, marching", "cubes; export.js: mm, Y up, OBJ, GLB"], kind="key")
    d.box(680, 52, 284, 292, "Same rules as the desktop", ["masks.py → masks.js, image.js", "silhouette.py → silhouette.js", "meshops.py → meshops.js", "export.py → export.js", "", "tests/test_web_parity.py runs both", "on the same synthetic photos and", "compares the models.", "", "No third-party code; nothing", "leaves the computer."], kind="band")
    d.arrow([(304, 89), (374, 89)], "files", 339, 82)
    d.arrow([(304, 177), (374, 260)], "frames", 312, 214)
    d.arrow([(516, 126), (516, 138)])
    d.arrow([(516, 214), (516, 226)])
    d.arrow([(376, 300), (306, 300)], "done", 341, 293)
    return d.svg(760)


def triposr():
    d = D(1000, 256, "TripoSR pipeline: pick the sharpest clean photo, cut out and centre it on a grey square, run "
                     "the model, extract the surface with marching cubes, turn it Y-up, colour vertices.", "tri")
    steps = [("1 Pick photo", ["sharpest of up to 12", "with a clean outline"]),
             ("2 Prepare", ["Bozzetto cut-out,", "512² grey, 85 % fill"]),
             ("3 Model", ["DINO ViT → triplane", "transformer (TSR)"]),
             ("4 Surface", ["density on 256³ / 320³", "scikit-image MC"]),
             ("5 Orient", ["Z-up → Y-up,", "facing the viewer"]),
             ("6 Colour", ["vertex colours", "→ RawMesh (unit)"])]
    for i, (t, ls) in enumerate(steps):
        x = 10 + i * 166
        d.box(x, 30, 146, 100, t, ls, kind="teal" if i in (2, 3) else "ok" if i == 5 else "box")
        if i:
            d.arrow([(x - 20, 80), (x - 2, 80)])
    d.box(10, 160, 980, 80, "Device", ["torch.cuda → \"cuda:0\" (NVIDIA)  ·  torch.backends.mps → \"mps\" (Apple Silicon, CPU fallback on)",
                                         "otherwise \"cpu\" (about a minute). The model stays loaded between runs."], kind="band")
    return d.svg(820)


ALL = {
    "architecture": architecture, "modules": modules, "datamodel": data_model, "sequence": sequence,
    "states": states, "threading": threading, "selection": selection, "silhouette": silhouette,
    "apple": apple_protocol, "triposr": triposr, "colmap": colmap, "downloads": downloads, "web": web,
}

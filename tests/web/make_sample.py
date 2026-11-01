# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Make web/sample/perfume.glb, the model on the home page, by scanning synthetic turntable photos
of a perfume bottle with the browser engine (in Node). Run from the repository root:
    python tests/web/make_sample.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from synth import render_turntable  # noqa: E402


def perfume():
    a, b, h0, h1 = 0.26, 0.14, -0.45, 0.13          # body: rounded rectangle, 0.52 × 0.58 × 0.28
    def inside(p):
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        body = ((np.abs(x / a) ** 4 + np.abs(z / b) ** 4) <= 1) & (y >= h0) & (y <= h1)
        r = np.hypot(x, z)
        neck = (r <= 0.05) & (y > h1) & (y <= h1 + 0.05)
        cap = (r <= 0.09) & (y > h1 + 0.05) & (y <= h1 + 0.2)
        dome = (np.hypot(r, y - (h1 + 0.2)) <= 0.09) & (y > h1 + 0.2)
        return body | neck | cap | dome
    return inside, np.array([-a, h0, -b]), np.array([a, h1 + 0.29, b])


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        paths = render_turntable(perfume(), t / "photos", n=36)
        entries = []
        for p in paths:
            rgba = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGBA)
            raw = p.with_suffix(".rgba")
            raw.write_bytes(rgba.tobytes())
            entries.append({"name": p.name, "file": str(p), "raw": str(raw), "width": rgba.shape[1], "height": rgba.shape[0]})
        settings = {"heightMm": 120, "tiltDeg": 20, "clockwise": False, "preset": "quick", "resolution": 110}
        (t / "m.json").write_text(json.dumps({"photos": entries, "settings": settings}))
        out = ROOT / "web/sample/perfume.glb"
        r = subprocess.run(["node", str(ROOT / "tests/web/run_core.mjs"), str(t / "m.json"), str(t / "m.obj"), str(out)],
                           capture_output=True, text=True, check=True)
        print(r.stdout.strip()[:300])
        print(out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()

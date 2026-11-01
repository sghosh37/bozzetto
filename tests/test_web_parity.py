# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""The browser engine (web/js/core, run in Node) gives the same model as the desktop silhouette engine."""
import json
import shutil
import subprocess
from pathlib import Path
from threading import Event

import cv2
import pytest

from bozzetto.core import inputs, pipeline
from bozzetto.core.models import Job

from synth import bottle, box, render_turntable

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="needs Node.js 18+ to run the browser engine")


def both(tmp_path, shape, height_mm, **kw):
    photos = tmp_path / "photos"
    paths = render_turntable(shape, photos, **kw)
    entries = []
    for p in paths:
        rgba = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGBA)
        raw = p.with_suffix(".rgba")
        raw.write_bytes(rgba.tobytes())
        entries.append({"name": p.name, "file": str(p), "raw": str(raw), "width": rgba.shape[1], "height": rgba.shape[0]})
    settings = {"heightMm": height_mm, "tiltDeg": 20, "clockwise": kw.get("clockwise", False), "preset": "quick"}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"photos": entries, "settings": settings}))
    out = subprocess.run([NODE, str(ROOT / "tests/web/run_core.mjs"), str(manifest), str(tmp_path / "web.obj")],
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr
    web = json.loads(out.stdout.strip().splitlines()[-1])

    for raw in photos.glob("*.rgba"):
        raw.unlink()
    job = Job(inputs=inputs.inspect(photos), height_mm=height_mm, out_dir=tmp_path / "out", name="m",
              turn_clockwise=kw.get("clockwise", False))
    desk, _ = pipeline.run(job, lambda p: None, Event())
    return web, desk


@pytest.mark.parametrize("clockwise", [False, True])
def test_bottle_matches_desktop(tmp_path, clockwise):
    web, desk = both(tmp_path, bottle(), 800.0, clockwise=clockwise)
    assert web["badEdges"] == 0
    for a, b in zip(web["size"], desk.size_mm):
        assert a == pytest.approx(b, rel=0.01)
    assert web["size"][0] == pytest.approx(440, rel=0.02)


def test_box_matches_desktop(tmp_path):
    web, desk = both(tmp_path, box(), 900.0)
    for a, b in zip(web["size"], desk.size_mm):
        assert a == pytest.approx(b, rel=0.01)
    assert web["score"] > 0.7

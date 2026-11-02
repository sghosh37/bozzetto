# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser TripoSR (web/js/core/tripo.js, run in Node): same photo preparation as the desktop engine,
triplane sampling identical to PyTorch's grid_sample, and the whole one-photo pipeline with stand-in
networks (the real model runs in the browser)."""
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from bozzetto.engines import triposr

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="needs Node.js 18+ to run the browser engine")
RUN = str(ROOT / "tests/web/run_tripo.mjs")


def photo(tmp_path: Path, w=800, h=600) -> Path:
    img = np.full((h, w, 3), 210, np.uint8)
    cv2.rectangle(img, (340, 120), (460, 520), (40, 60, 190), -1)     # tall red product
    cv2.circle(img, (400, 160), 30, (30, 160, 60), -1)
    p = tmp_path / "front.jpg"
    cv2.imwrite(str(p), img)
    return p


def rgba_file(p: Path):
    rgba = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGBA)
    raw = p.with_suffix(".rgba")
    raw.write_bytes(rgba.tobytes())
    return raw, rgba.shape[1], rgba.shape[0]


def node(*args):
    out = subprocess.run([NODE, RUN, *map(str, args)], capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_prepare_image_matches_desktop(tmp_path):
    p = photo(tmp_path)
    raw, w, h = rgba_file(p)
    node("prep", raw, w, h, tmp_path / "prep.f32")
    js = np.fromfile(tmp_path / "prep.f32", np.float32).reshape(3, 512, 512).transpose(1, 2, 0)
    py = triposr.prepare_image(p)
    diff = np.abs(js - py)
    assert diff.mean() < 0.002 and np.percentile(diff, 99.9) < 0.05


def grid_sample_ref(triplane, pts):
    """NumPy version of TripoSR's query: F.grid_sample(bilinear, align_corners=False, zeros) per plane."""
    planes = triplane.reshape(3, 40, 64, 64)
    out = []
    for p, (i, j) in enumerate([(0, 1), (0, 2), (1, 2)]):
        a, b = pts[:, i], pts[:, j]
        fx, fy = ((a + 1) * 64 - 1) / 2, ((b + 1) * 64 - 1) / 2
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        acc = np.zeros((len(pts), 40))
        for dx in (0, 1):
            for dy in (0, 1):
                xx, yy = x0 + dx, y0 + dy
                wgt = (1 - np.abs(fx - xx)) * (1 - np.abs(fy - yy))
                ok = (xx >= 0) & (xx < 64) & (yy >= 0) & (yy < 64)
                vals = np.zeros((len(pts), 40))
                vals[ok] = planes[p][:, yy[ok], xx[ok]].T
                acc += wgt[:, None] * vals
        out.append(acc)
    return np.concatenate(out, axis=1)


def test_triplane_sampling_matches_grid_sample(tmp_path):
    rng = np.random.default_rng(3)
    tp = rng.normal(size=3 * 40 * 64 * 64).astype(np.float32)
    pts = rng.uniform(-1.05, 1.05, size=(500, 3)).astype(np.float32)
    tp.tofile(tmp_path / "tp.f32")
    pts.tofile(tmp_path / "pts.f32")
    node("sample", tmp_path / "tp.f32", tmp_path / "pts.f32", tmp_path / "out.f32")
    js = np.fromfile(tmp_path / "out.f32", np.float32).reshape(500, 120)
    assert np.abs(js - grid_sample_ref(tp, pts)).max() < 1e-4


def run_pipeline(tmp_path, method, n_photos=1):
    paths = [photo(tmp_path)]
    for i in range(1, n_photos):
        q = tmp_path / f"view{i}.jpg"
        shutil.copy(paths[0], q)
        img = cv2.imread(str(q)); img[0, i] = (i, i, i); cv2.imwrite(str(q), img)
        paths.append(q)
    entries = []
    for p in paths:
        raw, w, h = rgba_file(p)
        entries.append({"name": p.name, "file": str(p), "raw": str(raw), "width": w, "height": h})
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"photos": entries, "settings": {"heightMm": 120, "tiltDeg": 20, "clockwise": False,
                                                              "preset": "quick", "method": method}}))
    return json.loads(node("run", m, tmp_path / "out.obj").strip().splitlines()[-1])


def test_one_photo_pipeline_orients_and_scales(tmp_path):
    r = run_pipeline(tmp_path, "auto")
    assert r["method"] == "triposr" and r["loads"] == 1 and r["badEdges"] == 0
    w, h, d = r["size"]
    # stand-in ellipsoid, TripoSR frame (Z up) semi-axes x 0.3, y 0.2, z 0.6 -> Y up: W from y, D from x
    assert h == pytest.approx(120, rel=1e-3)
    assert w == pytest.approx(40, rel=0.05) and d == pytest.approx(60, rel=0.05)
    assert r["color"] == [204, 51, 25]
    text = (tmp_path / "out.obj").read_text()
    assert "engine: triposr" in text and any(l.startswith("v ") and len(l.split()) == 7 for l in text.splitlines()[:20])


def test_one_photo_method_can_be_chosen_for_many_photos(tmp_path):
    assert run_pipeline(tmp_path, "triposr", n_photos=7)["method"] == "triposr"

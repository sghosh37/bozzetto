# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""TripoSR wrapper: photo choice, cut-out, orientation and export, with a stand-in for the neural network.

The real model needs PyTorch and the 1.7 GB weights; test_real_model runs only where both are present.
"""
import contextlib
import sys
import types
from dataclasses import replace
from pathlib import Path
from threading import Event

import cv2
import numpy as np
import pytest

from bozzetto.core import export, inputs
from bozzetto.core.models import Job, StatusState
from bozzetto.engines import triposr


def photo(tmp_path: Path) -> Path:
    img = np.full((600, 800, 3), 210, np.uint8)
    cv2.rectangle(img, (340, 120), (460, 520), (40, 60, 190), -1)     # tall red product
    p = tmp_path / "front.jpg"
    cv2.imwrite(str(p), img)
    return p


def test_prepare_image_centres_product(tmp_path):
    im = triposr.prepare_image(photo(tmp_path))
    assert im.shape == (512, 512, 3) and im.dtype == np.float32
    assert 0.0 <= im.min() and im.max() <= 1.0
    product = np.abs(im - 0.5).sum(axis=2) > 0.2
    ys, xs = np.nonzero(product)
    assert abs((xs.min() + xs.max()) / 2 - 256) < 8 and abs((ys.min() + ys.max()) / 2 - 256) < 8
    assert (ys.max() - ys.min()) / 512 == pytest.approx(0.85, abs=0.03)    # foreground ratio


class FakeModel:
    """Returns a Z-up box 1 × 2 × 3 (x, y, z) like TripoSR's own frame, with vertex colours."""
    def __call__(self, images, device):
        assert len(images) == 1 and images[0].shape == (512, 512, 3)
        return ["codes"]

    def extract_mesh(self, codes, has_vertex_color, resolution=256):
        v = np.array([[x, y, z] for x in (0, 1) for y in (0, 2) for z in (0, 3)], np.float32)
        f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                      [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int64)
        return [(v, f, np.tile([[0.8, 0.2, 0.1]], (8, 1)))]


@pytest.fixture
def fake_torch(monkeypatch):
    t = types.ModuleType("torch")
    t.no_grad = contextlib.nullcontext
    monkeypatch.setitem(sys.modules, "torch", t)
    monkeypatch.setattr(triposr.TripoSREngine, "_model", FakeModel())
    monkeypatch.setattr(triposr.TripoSREngine, "_device", "cpu")


def test_run_orients_y_up_and_exports(tmp_path, fake_torch):
    ins = inputs.inspect(photo(tmp_path))
    job = Job(inputs=ins, engine_id="triposr", height_mm=90.0, out_dir=tmp_path / "out", name="lipstick")
    mesh = triposr.TripoSREngine().run(job, lambda p: None, Event())
    ext = mesh.vertices.max(0) - mesh.vertices.min(0)
    # TripoSR's Z (height 3) must become Y
    assert ext[1] == pytest.approx(3.0) and sorted(np.round(ext, 3)) == [1.0, 2.0, 3.0]
    assert mesh.vertex_colors.shape == (8, 3) and mesh.vertex_colors[0].tolist() == [204, 51, 25]
    r = export.write(mesh, job, "triposr", 1.0)
    assert r.size_mm[1] == pytest.approx(90.0) and r.scaled_to_height
    assert "v " in Path(r.files["obj"]).read_text()


def test_check_reports_missing_parts(monkeypatch):
    monkeypatch.setattr(triposr, "missing_modules", lambda: ["torch"])
    st = triposr.TripoSREngine().check(None)
    assert st.state is StatusState.UNSUPPORTED and "pip install" in st.reason
    monkeypatch.setattr(triposr, "missing_modules", lambda: [])
    monkeypatch.setattr(triposr, "weights_present", lambda: False)
    st = triposr.TripoSREngine().check(None)
    assert st.state is StatusState.NEEDS_DOWNLOAD and st.download.size_bytes > 1e9


@pytest.mark.skipif(triposr.missing_modules() or not triposr.weights_present(),
                    reason="needs PyTorch and the downloaded TripoSR model")
def test_real_model(tmp_path):
    ins = inputs.inspect(photo(tmp_path))
    job = Job(inputs=ins, engine_id="triposr", height_mm=90.0, out_dir=tmp_path / "out", name="real")
    triposr.TripoSREngine._model = None
    mesh = triposr.TripoSREngine().run(job, lambda p: None, Event())
    assert len(mesh.faces) > 1000

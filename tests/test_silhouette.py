# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end: synthetic turntable photos -> silhouette engine -> exported OBJ with known size."""
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from bozzetto.core import inputs, meshops, pipeline
from bozzetto.core.models import Job

from synth import bottle, box, render_turntable


def scan(tmp_path, shape, height_mm, **kw):
    photos = tmp_path / "photos"
    render_turntable(shape, photos, **kw)
    ins = inputs.inspect(photos)
    assert ins.turntable_score > 0.7
    j = Job(inputs=ins, height_mm=height_mm, out_dir=tmp_path / "out", name="m")
    result, choice = pipeline.run(j, lambda p: None, Event())
    assert choice.engine_id == "silhouette"
    return result


def test_bottle_size_within_2_percent(tmp_path):
    r = scan(tmp_path, bottle(), 800.0)            # true: 440 × 800 × 440 mm
    w, h, d = r.size_mm
    assert h == pytest.approx(800, rel=1e-3)
    assert w == pytest.approx(440, rel=0.02) and d == pytest.approx(440, rel=0.02)


def test_box_size_and_known_bulge(tmp_path):
    r = scan(tmp_path, box(), 900.0)               # true: 600 × 900 × 300 mm
    w, h, d = r.size_mm
    assert w == pytest.approx(600, rel=0.05)
    # flat sides seen edge-on bulge by about length / (2 × distance): 0.6 / 3.6 ≈ 17 % here
    assert 300 <= d <= 300 * 1.22


def test_clockwise_turntable(tmp_path):
    r = scan(tmp_path, bottle(), 800.0, clockwise=True)
    assert r.size_mm[0] == pytest.approx(440, rel=0.02)


def test_mesh_is_closed(tmp_path):
    r = scan(tmp_path, bottle(), 800.0)
    text = Path(r.files["obj"]).read_text().splitlines()
    faces = [[int(t.split("//")[0]) - 1 for t in l.split()[1:]] for l in text if l.startswith("f ")]
    import numpy as np
    assert meshops.bad_edges(np.array(faces)) == 0

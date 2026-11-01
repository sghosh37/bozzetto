# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
import shutil
from dataclasses import replace
from pathlib import Path
from threading import Event

import cv2
import numpy as np
import pytest

from bozzetto.core import export, inputs, meshops, select, settings
from bozzetto.core.models import (GpuInfo, Hardware, InputKind, InputSet, Job, Preset, RawMesh, Status,
                                  StatusState)
from bozzetto.engines.base import Engine


# ---------- selector -------------------------------------------------------------------------
class FakeEngine(Engine):
    def __init__(self, id_, ok=True):
        self.id, self.name, self._ok = id_, id_, ok

    def check(self, hw):
        return Status(StatusState.READY if self._ok else StatusState.UNSUPPORTED)

    def suits(self, job, hw):
        return None

    def run(self, job, progress, cancel):
        return None


def engines(apple=False, colmap=False):
    return {"triposr": FakeEngine("triposr"), "silhouette": FakeEngine("silhouette"),
            "apple": FakeEngine("apple", apple), "colmap_openmvs": FakeEngine("colmap_openmvs", colmap)}


def job(n, tt=0.9, preset=Preset.QUICK, engine_id=None):
    frames = tuple(Path(f"/x/{i}.jpg") for i in range(n))
    return Job(inputs=InputSet(InputKind.PHOTOS, Path("/x"), frames, turntable_score=tt), preset=preset,
               engine_id=engine_id)


PC = Hardware("windows", "11", "amd64", 8, 16)
NV = replace(PC, nvidia=GpuInfo("RTX 3060", 12))
MAC = Hardware("macos", "14.5", "arm64", 8, 16, apple_gpu=True, object_capture=True)


@pytest.mark.parametrize("n,tt,hw,eng,expect", [
    (1, 0.0, PC, engines(), "triposr"),
    (2, 0.9, PC, engines(), "triposr"),
    (24, 0.9, PC, engines(), "silhouette"),
    (24, 0.9, MAC, engines(apple=True), "apple"),
    (24, 0.9, MAC, engines(apple=False), "silhouette"),          # Apple engine not built yet
    (40, 0.2, NV, engines(colmap=True), "colmap_openmvs"),
    (40, 0.2, PC, engines(colmap=False), "silhouette"),           # last resort
    (4, 0.2, PC, engines(), "triposr"),                           # too few for silhouette
])
def test_rules(n, tt, hw, eng, expect):
    assert select.choose(job(n, tt), hw, eng).engine_id == expect


def test_override_and_warnings():
    c = select.choose(job(24, engine_id="triposr"), PC, engines())
    assert c.engine_id == "triposr" and c.reason == "Chosen by you"
    assert c.fallbacks[0] == "silhouette"
    assert any("real height" in w for w in c.warnings)


# ---------- export ---------------------------------------------------------------------------
def cube(z_up=False):
    v = np.array([[x, y, z] for x in (0, 2) for y in (0, 1) for z in (0, 3)], np.float32)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                  [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int32)
    if z_up:   # store as Z-up: (x, y, z) -> (x, -z, y)
        v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)
    return RawMesh(v, f, units="unit", up_axis="z" if z_up else "y")


def test_export_scaling_axis_and_files(tmp_path):
    j = replace(job(3), height_mm=50.0, out_dir=tmp_path, name="cube", outputs=frozenset({"obj", "glb"}))
    r = export.write(cube(z_up=True), j, "test", 1.0)
    assert r.scaled_to_height
    assert r.size_mm == pytest.approx((100.0, 50.0, 150.0), rel=1e-4)    # height 1 -> 50 mm, so x2 -> 100
    text = (tmp_path / "cube" / "cube.obj").read_text()
    vs = np.array([list(map(float, l.split()[1:4])) for l in text.splitlines() if l.startswith("v ")])
    assert vs[:, 1].min() == pytest.approx(0.0, abs=1e-6)                 # base on y = 0
    assert vs[:, 0].min() == pytest.approx(-vs[:, 0].max(), abs=1e-3)     # centred on x
    glb = (tmp_path / "cube" / "cube.glb").read_bytes()
    assert glb[:4] == b"glTF"


def test_export_flips_inside_out_mesh(tmp_path):
    m = cube()
    m.faces = m.faces[:, ::-1].copy()
    j = replace(job(3), out_dir=tmp_path, name="c2")
    export.write(m, j, "test", 0.0)
    v, f, *_ = export.normalise(m, None)
    assert meshops.signed_volume(v, f) > 0


def test_meshops_largest_component():
    a = cube()
    b = cube()
    v = np.vstack([a.vertices, b.vertices + 10])
    f = np.vstack([a.faces[:10], b.faces + 8])          # first piece is smaller (10 faces vs 12)
    v2, f2, _ = meshops.largest_component(v, f)
    assert len(v2) == 8 and len(f2) == 12 and meshops.bad_edges(f2) == 0
    assert v2[:, 0].min() >= 10                          # the second (bigger) piece was kept


# ---------- inputs ---------------------------------------------------------------------------
def test_duplicates_and_video(tmp_path):
    img = np.full((120, 160, 3), 200, np.uint8)
    cv2.circle(img, (80, 60), 30, (30, 40, 180), -1)
    for i in range(3):
        cv2.imwrite(str(tmp_path / f"a{i}.png"), np.roll(img, i * 5, axis=1))
    shutil.copy(tmp_path / "a0.png", tmp_path / "a0_copy.png")
    ins = inputs.inspect(tmp_path)
    assert ins.unique_count == 3 and len(ins.duplicates) == 1

    vid = tmp_path / "clip.mp4"
    w = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for i in range(30):
        w.write(np.roll(img, i, axis=1))
    w.release()
    vins = inputs.inspect(vid, frames_dir=tmp_path / "frames", video_frames=8)
    assert vins.kind is InputKind.VIDEO and vins.unique_count == 8


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", lambda: tmp_path)
    s = settings.Settings(height_mm=82.0)
    s.extra = {"future_key": 1}
    settings.save(s)
    s2 = settings.load()
    assert s2.height_mm == 82.0 and s2.extra == {"future_key": 1}

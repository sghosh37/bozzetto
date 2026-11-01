# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turntable silhouette engine ("visual hull").

Keeps only the space that lies inside the product's outline in every photo. Plain turntable model:
the camera is fixed, tilted down by `camera_tilt_deg`, and the product turns by equal steps about a
vertical axis. Scale is arbitrary (distance to the axis = 1); export scales to the real height.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from threading import Event

import cv2
import numpy as np
from scipy import ndimage
from skimage import measure

from ..core.inputs import read_image
from ..core.masks import cut_out
from ..core.models import (Cancelled, ErrorCode, Fit, FitLevel, Hardware, Job, Preset, Progress, ProgressFn,
                           RawMesh, ScanError, Status, StatusState)
from .base import Engine

WORK_WIDTH = 1200          # photos are reduced to this width for cut-out and carving
DEFAULT_HFOV_DEG = 50.0    # used when EXIF has no focal length


@dataclass(frozen=True)
class Camera:
    fx: float
    fy: float
    cx: float
    cy: float
    tilt: float           # radians, camera looking down
    distance: float = 1.0

    def rotation(self) -> np.ndarray:
        s, c = math.sin(self.tilt), math.cos(self.tilt)
        right = np.array([1.0, 0.0, 0.0])
        down = np.array([0.0, -c, s])
        fwd = np.array([0.0, -s, -c])
        return np.stack([right, down, fwd])

    def centre(self) -> np.ndarray:
        return np.array([0.0, self.distance * math.sin(self.tilt), self.distance * math.cos(self.tilt)])

    def project(self, pts: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """World points (N,3) of the object turned by `angle` about +Y -> pixel u, v and depth."""
        ca, sa = math.cos(angle), math.sin(angle)
        ry = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
        p = pts @ ry.T
        pc = (p - self.centre()) @ self.rotation().T
        z = pc[:, 2]
        zs = np.where(z > 1e-6, z, 1e-6)
        return self.fx * pc[:, 0] / zs + self.cx, self.fy * pc[:, 1] / zs + self.cy, z

    def ray_y_at_axis_plane(self, v: float) -> float:
        """World height where the camera ray through image row v (centre column) meets the plane x-y."""
        d_cam = np.array([0.0, (v - self.cy) / self.fy, 1.0])
        d = self.rotation().T @ d_cam
        c = self.centre()
        t = -c[2] / d[2] if abs(d[2]) > 1e-9 else 0.0
        return float(c[1] + t * d[1])


def focal_px(width: int, focal_mm, is_35mm: bool) -> float:
    if focal_mm and is_35mm:
        return focal_mm / 36.0 * width
    if focal_mm and focal_mm > 0:
        # actual focal without sensor size: assume an APS-C-like 23.5 mm wide sensor
        return focal_mm / 23.5 * width
    return (width / 2) / math.tan(math.radians(DEFAULT_HFOV_DEG / 2))


def trim_base_wedge(occ: np.ndarray, voxel: float, tilt: float) -> int:
    """Remove the wedge the carving leaves under the base.

    The camera looks down at `tilt`, so it never sees under the product: below the base the carved
    shape shrinks inward by about 1/tan(tilt) per unit of depth. Going up from the bottom, layers whose
    footprint is still growing at (most of) that rate are removed. Returns the number of layers removed.
    """
    if tilt <= math.radians(2):
        return 0
    area = occ.sum(axis=(0, 2))
    filled = np.where(area > 0)[0]
    if len(filled) < 6:
        return 0
    r = np.sqrt(area / math.pi) * voxel           # equivalent radius per layer
    wedge_slope = 1.0 / math.tan(tilt)            # radius change per unit height inside the wedge
    k = 2
    lo = filled[0]
    limit = lo + int(len(filled) * 0.3)           # never trim more than 30 % of the height
    j = lo
    while j + k <= limit:
        slope = (r[j + k] - r[j]) / (k * voxel)
        if slope < 0.45 * wedge_slope:
            break
        j += 1
    if j > lo:
        occ[:, :j, :] = 0
    return int(j - lo)


class SilhouetteEngine(Engine):
    id = "silhouette"
    name = "Turntable silhouette"
    min_photos = 6
    smooth_iterations = 4

    def check(self, hw: Hardware) -> Status:
        return Status(StatusState.READY)

    def suits(self, job: Job, hw: Hardware) -> Fit:
        n = job.inputs.unique_count
        if n < self.min_photos:
            return Fit(FitLevel.UNSUITABLE, f"needs at least {self.min_photos} photos")
        if job.inputs.turntable_score < 0.7:
            return Fit(FitLevel.SLOW, "photos don’t look like a turntable shoot", 10)
        return Fit(FitLevel.GOOD, "turntable photos", max(3.0, n * 0.4))

    def run(self, job: Job, progress: ProgressFn, cancel: Event) -> RawMesh:
        frames = list(job.inputs.frames)
        n = len(frames)
        if n < self.min_photos:
            raise ScanError(ErrorCode.TOO_FEW_PHOTOS,
                            f"The silhouette engine needs at least {self.min_photos} photos all the way round.",
                            suggest_engine="triposr")

        # 1-2: load and cut out
        masks, bad = [], []
        for i, p in enumerate(frames):
            if cancel.is_set():
                raise Cancelled()
            img = read_image(p, max_width=WORK_WIDTH)
            co = cut_out(img)
            if not co.ok:
                bad.append(p.name)
            masks.append(co.mask)
            progress(Progress("Cutting out the product", 0.4 * (i + 1) / n))
        if len(bad) > n // 4:
            raise ScanError(ErrorCode.NO_OUTLINE,
                            f"Couldn’t separate the product from the background in {len(bad)} of {n} photos. "
                            "Use a plain backdrop that contrasts with the product.",
                            detail=", ".join(bad[:10]), suggest_engine="triposr")
        if bad:
            progress(Progress("Cutting out the product", None, f"Outline unclear in {len(bad)} photo(s): {', '.join(bad[:5])}"))
        h, w = masks[0].shape
        if any(m.shape != (h, w) for m in masks):
            raise ScanError(ErrorCode.NO_OUTLINE, "The photos are not all the same size, so they can’t be from one turntable shoot.")

        # 3: camera
        f = focal_px(w, job.inputs.focal_mm, job.inputs.focal_35mm) * (w / job.inputs.image_size[0]
                                                                        if job.inputs.image_size[0] else 1.0)
        xs = []
        tops, bottoms, half_widths = [], [], []
        for m in masks:
            cols = np.where(m.max(axis=0) > 0)[0]
            rows = np.where(m.max(axis=1) > 0)[0]
            if len(cols) == 0:
                continue
            xs.append((cols[0] + cols[-1]) / 2)
            tops.append(rows[0])
            bottoms.append(rows[-1])
        u_axis = float(np.median(xs))
        for m in masks:
            cols = np.where(m.max(axis=0) > 0)[0]
            if len(cols):
                half_widths.append(max(u_axis - cols[0], cols[-1] - u_axis))
        cam = Camera(fx=f, fy=f, cx=u_axis, cy=h / 2.0, tilt=math.radians(job.camera_tilt_deg))
        radius = float(np.max(half_widths)) / f * cam.distance * 1.25
        y_top = cam.ray_y_at_axis_plane(float(np.min(tops)))
        y_bot = cam.ray_y_at_axis_plane(float(np.max(bottoms)))
        lo = np.array([-radius, min(y_top, y_bot) - 0.35 * radius, -radius])
        hi = np.array([radius, max(y_top, y_bot) + 0.35 * radius, radius])

        # 4: carve
        res = 224 if job.preset is Preset.ACCURATE else 160
        voxel = float((hi - lo).max() / res)
        dims = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 2)
        grid = np.stack(np.meshgrid(*[lo[k] + (np.arange(dims[k]) + 0.5) * voxel for k in range(3)],
                                    indexing="ij"), axis=-1).reshape(-1, 3).astype(np.float32)
        idx = np.arange(len(grid))
        misses = np.zeros(len(grid), np.int16)
        allowed = n // 36                    # with many photos, tolerate one bad outline
        step = (-1 if job.turn_clockwise else 1) * 2 * math.pi / n
        tol = max(1, int(round(w * 0.002)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1))
        for i, m in enumerate(masks):
            if cancel.is_set():
                raise Cancelled()
            mm = cv2.dilate(m, kernel) > 0
            u, v, z = cam.project(grid[idx], i * step)
            ui, vi = np.round(u).astype(np.int64), np.round(v).astype(np.int64)
            inside = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h) & (z > 0)
            hit = np.zeros(len(idx), bool)
            hit[inside] = mm[vi[inside], ui[inside]]
            misses[idx[~hit]] += 1
            keep = misses[idx] <= allowed
            idx = idx[keep]
            progress(Progress("Carving the shape", 0.4 + 0.45 * (i + 1) / n))
            if len(idx) == 0:
                break
        if len(idx) < 50:
            raise ScanError(ErrorCode.NO_MODEL,
                            "Nothing was left after carving. The turntable direction, camera tilt or photo order may be wrong.",
                            suggest_engine="triposr")
        occ = np.zeros(int(np.prod(dims)), np.float32)
        occ[idx] = 1.0
        occ = occ.reshape(dims)
        cut = trim_base_wedge(occ, voxel, cam.tilt)
        if cut:
            progress(Progress("Carving the shape", 0.86, f"Trimmed {cut} voxel layers of hidden-underside wedge"))

        # 5: mesh
        progress(Progress("Building the mesh", 0.9))
        occ = np.pad(occ, 1)
        occ = ndimage.gaussian_filter(occ, 0.8)
        verts, faces, _, _ = measure.marching_cubes(occ, level=0.5, spacing=(voxel, voxel, voxel))
        verts = verts + (lo - voxel)
        progress(Progress("Building the mesh", 1.0, f"Carved {dims[0]}×{dims[1]}×{dims[2]} voxels, "
                                                     f"kept {len(idx):,}; {len(faces):,} triangles"))
        return RawMesh(vertices=verts.astype(np.float32), faces=faces.astype(np.int32), units="unit", up_axis="y")

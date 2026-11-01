# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render synthetic turntable photos of shapes with known size (uses OpenCV's own projection)."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np


def box(half=(0.30, 0.45, 0.15)):
    hx, hy, hz = half
    return (lambda p: (np.abs(p[:, 0]) <= hx) & (np.abs(p[:, 1]) <= hy) & (np.abs(p[:, 2]) <= hz),
            np.array([-hx, -hy, -hz]), np.array([hx, hy, hz]))


def bottle(r=0.22, h=0.6, neck_r=0.08, neck_h=0.2, y0=-0.45):
    def inside(p):
        rr = np.hypot(p[:, 0], p[:, 2])
        body = (rr <= r) & (p[:, 1] >= y0) & (p[:, 1] <= y0 + h)
        neck = (rr <= neck_r) & (p[:, 1] > y0 + h) & (p[:, 1] <= y0 + h + neck_h)
        return body | neck
    return inside, np.array([-r, y0, -r]), np.array([r, y0 + h + neck_h, r])


def solid_points(inside, lo, hi, step=0.006):
    axes = [np.arange(lo[k], hi[k] + step / 2, step) for k in range(3)]
    g = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    return g[inside(g)]


def render_turntable(shape, out: Path, n=24, tilt_deg=20.0, distance=1.8, size=(1200, 900),
                     hfov_deg=50.0, clockwise=False, seed=0) -> list[Path]:
    inside, lo, hi = shape
    pts = solid_points(inside, lo, hi)
    w, h = size
    f = (w / 2) / math.tan(math.radians(hfov_deg / 2))
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], np.float64)
    t = math.radians(tilt_deg)
    eye = np.array([0, distance * math.sin(t), distance * math.cos(t)])
    z = -eye / np.linalg.norm(eye)
    x = np.cross(z, [0, 1, 0]); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])
    rvec, _ = cv2.Rodrigues(R)
    tvec = -R @ eye
    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        a = (-1 if clockwise else 1) * 2 * math.pi * i / n
        ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
        p = pts @ ry.T
        uv, _ = cv2.projectPoints(p, rvec, tvec, K, None)
        uv = np.round(uv.reshape(-1, 2)).astype(int)
        ok = (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        mask = np.zeros((h, w), np.uint8)
        mask[uv[ok, 1], uv[ok, 0]] = 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        mask = np.zeros_like(mask)
        cv2.drawContours(mask, cnts, -1, 255, cv2.FILLED)
        img = np.full((h, w, 3), 205, np.float32)
        rows = np.linspace(0.6, 1.0, h)[:, None]
        product = np.stack([40 * rows, 60 * rows, 190 * rows], -1) * np.ones((1, w, 1))
        img[mask > 0] = product[mask > 0]
        img = np.clip(img + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8)
        filled = img
        path = out / f"IMG_{i + 1:04d}.jpg"
        cv2.imwrite(str(path), filled, [cv2.IMWRITE_JPEG_QUALITY, 92])
        paths.append(path)
    return paths

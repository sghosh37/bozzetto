# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate the product from a plain background ("cut-out").

Assumes a fairly even backdrop: the colour along the photo's border is taken as the background,
and every pixel is scored by how far its colour is from it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class CutOut:
    mask: np.ndarray          # uint8 (H, W), 255 = product
    area: float               # fraction of the image covered by the product
    border_touch: float       # fraction of the image border the product touches
    bbox: tuple[int, int, int, int]   # x, y, w, h
    background_lab: tuple[float, float, float]

    @property
    def ok(self) -> bool:
        return 0.005 < self.area < 0.9 and self.border_touch < 0.35


def border_pixels(img: np.ndarray, frac: float = 0.03) -> np.ndarray:
    h, w = img.shape[:2]
    b = max(2, int(round(min(h, w) * frac)))
    parts = [img[:b].reshape(-1, img.shape[2]), img[-b:].reshape(-1, img.shape[2]),
             img[:, :b].reshape(-1, img.shape[2]), img[:, -b:].reshape(-1, img.shape[2])]
    return np.concatenate(parts, axis=0)


def cut_out(img_bgr: np.ndarray, dilate_px: int = 0) -> CutOut:
    """Return the product mask for one photo (BGR, uint8)."""
    h, w = img_bgr.shape[:2]
    blur = cv2.GaussianBlur(img_bgr, (5, 5), 0)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = border_pixels(lab)
    bg = np.median(border, axis=0)
    # distance from the background colour (lightness counts half, so soft shadows matter less)
    diff = lab - bg
    dist = np.sqrt(0.25 * diff[..., 0] ** 2 + diff[..., 1] ** 2 + diff[..., 2] ** 2)
    border_dist = np.sqrt(0.25 * (border[:, 0] - bg[0]) ** 2 + (border[:, 1] - bg[1]) ** 2 + (border[:, 2] - bg[2]) ** 2)
    noise = float(np.percentile(border_dist, 99)) + 4.0
    d8 = np.clip(dist / max(dist.max(), 1e-6) * 255, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = max(noise, otsu / 255.0 * dist.max() * 0.6)
    mask = (dist > thr).astype(np.uint8) * 255

    k = max(3, int(round(min(h, w) * 0.006)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # keep the largest blob
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return CutOut(np.zeros((h, w), np.uint8), 0.0, 0.0, (0, 0, 0, 0), tuple(float(x) for x in bg))
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = np.where(labels == biggest, 255, 0).astype(np.uint8)

    # fill holes: redraw the outer outline filled
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    mask = np.zeros_like(mask)
    cv2.drawContours(mask, contours, -1, 255, thickness=cv2.FILLED)

    if dilate_px > 0:
        dk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
        mask = cv2.dilate(mask, dk)

    x, y, bw, bh = cv2.boundingRect(mask)
    edge = np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]])
    return CutOut(mask=mask, area=float((mask > 0).mean()), border_touch=float((edge > 0).mean()),
                  bbox=(x, y, bw, bh), background_lab=tuple(float(v) for v in bg))

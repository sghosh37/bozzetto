# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""A light 3D preview: flat-shaded triangles drawn with QPainter. Drag to turn, scroll to zoom."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

MAX_FACES = 60000


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    vs, cs, fs = [], [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                vs.append([float(x) for x in parts[1:4]])
                if len(parts) >= 7:
                    cs.append([float(x) for x in parts[4:7]])
            elif line.startswith("f "):
                fs.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
    v = np.array(vs, np.float32)
    c = np.array(cs, np.float32) if len(cs) == len(vs) and cs else None
    return v, np.array(fs, np.int32), c


class MeshPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.v = self.f = self.c = None
        self.yaw, self.pitch, self.zoom = math.radians(-30), math.radians(15), 1.0
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def set_mesh(self, v: np.ndarray, f: np.ndarray, c: np.ndarray | None = None):
        if len(f) > MAX_FACES:     # thin out very dense meshes for display only
            keep = np.random.default_rng(0).choice(len(f), MAX_FACES, replace=False)
            f = f[np.sort(keep)]
        centre = (v.max(axis=0) + v.min(axis=0)) / 2
        self.v = (v - centre) / max(float(np.ptp(v, axis=0).max()), 1e-6)
        self.f, self.c = f, c
        self.update()

    def load(self, path: Path):
        self.set_mesh(*load_obj(path))

    def mousePressEvent(self, e):
        self._drag = e.position()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            d = e.position() - self._drag
            self.yaw += d.x() * 0.01
            self.pitch = max(-1.4, min(1.4, self.pitch + d.y() * 0.01))
            self._drag = e.position()
            self.update()

    def wheelEvent(self, e):
        self.zoom = max(0.3, min(4.0, self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1B1F25"))
        if self.v is None or len(self.f) == 0:
            p.setPen(QColor("#9AA3AD"))
            p.drawText(self.rect(), Qt.AlignCenter, "The model will appear here")
            return
        cy, sy, cp, sp = math.cos(self.yaw), math.sin(self.yaw), math.cos(self.pitch), math.sin(self.pitch)
        ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        v = self.v @ (rx @ ry).T
        tri = v[self.f]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        front = n[:, 2] > 0
        tri, n = tri[front], n[front]
        idx = np.nonzero(front)[0]
        order = np.argsort(tri[:, :, 2].mean(axis=1))          # far to near
        light = np.array([0.35, 0.5, 0.8]) / np.linalg.norm([0.35, 0.5, 0.8])
        shade = np.clip(0.25 + 0.75 * (n @ light), 0.15, 1.0)
        s = min(self.width(), self.height()) * 0.8 * self.zoom
        ox, oy = self.width() / 2, self.height() / 2
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)
        base = np.array([0.85, 0.80, 0.74])
        for k in order:
            t = tri[k]
            if self.c is not None:
                col = self.c[self.f[idx[k]]].mean(axis=0)
            else:
                col = base
            r, g, b = (np.clip(col * shade[k], 0, 1) * 255).astype(int)
            p.setBrush(QColor(int(r), int(g), int(b)))
            p.drawPolygon(QPolygonF([QPointF(ox + x * s, oy - y * s) for x, y, _ in t]))
        p.end()

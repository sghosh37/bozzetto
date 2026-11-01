# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small mesh helpers on plain NumPy arrays (no mesh library needed)."""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components


def _adjacency(n_vertices: int, faces: np.ndarray) -> sparse.csr_matrix:
    f = faces.astype(np.int64)
    i = np.concatenate([f[:, 0], f[:, 1], f[:, 2], f[:, 1], f[:, 2], f[:, 0]])
    j = np.concatenate([f[:, 1], f[:, 2], f[:, 0], f[:, 0], f[:, 1], f[:, 2]])
    a = sparse.coo_matrix((np.ones(len(i), np.float32), (i, j)), shape=(n_vertices, n_vertices)).tocsr()
    a.data[:] = 1.0
    return a


def remove_degenerate(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    f = faces
    ok = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    v = vertices
    area = np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1)
    return faces[ok & (area > 1e-12)]


def largest_component(vertices: np.ndarray, faces: np.ndarray, colors=None):
    """Keep only the biggest connected piece (by face count); re-index vertices."""
    if len(faces) == 0:
        return vertices, faces, colors
    n, labels = connected_components(_adjacency(len(vertices), faces), directed=False)
    if n > 1:
        face_label = labels[faces[:, 0]]
        best = np.bincount(face_label).argmax()
        faces = faces[face_label == best]
    used = np.unique(faces)
    remap = -np.ones(len(vertices), np.int64)
    remap[used] = np.arange(len(used))
    return (vertices[used], remap[faces].astype(np.int32),
            None if colors is None else colors[used])


def taubin(vertices: np.ndarray, faces: np.ndarray, iterations: int = 6,
           lam: float = 0.5, mu: float = -0.53) -> np.ndarray:
    """Taubin smoothing: removes voxel steps and noise without shrinking the shape."""
    if iterations <= 0 or len(faces) == 0:
        return vertices
    a = _adjacency(len(vertices), faces)
    deg = np.asarray(a.sum(axis=1)).ravel()
    deg[deg == 0] = 1
    inv = sparse.diags(1.0 / deg)
    w = inv @ a
    v = vertices.astype(np.float64)
    for _ in range(iterations):
        v = v + lam * (w @ v - v)
        v = v + mu * (w @ v - v)
    return v.astype(np.float32)


def signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    v = vertices.astype(np.float64)
    return float(np.einsum("ij,ij->i", v[faces[:, 0]], np.cross(v[faces[:, 1]], v[faces[:, 2]])).sum() / 6.0)


def orient_outward(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Flip all faces if the closed mesh is inside-out (negative volume)."""
    return faces[:, ::-1].copy() if signed_volume(vertices, faces) < 0 else faces


def vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v = vertices.astype(np.float64)
    fn = np.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]])   # area-weighted
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return (n / ln).astype(np.float32)


def bad_edges(faces: np.ndarray) -> int:
    """Edges not shared by exactly two faces (0 = closed, manifold)."""
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts != 2).sum())

# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Normalise any engine's mesh and write it: millimetres, Y up, base on y = 0, centred on x/z."""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path
from typing import Optional

import numpy as np

from . import meshops
from .models import ErrorCode, Job, RawMesh, Result, ScanError

DEFAULT_HEIGHT_MM = 100.0   # used when the engine's scale is arbitrary and no height was given


def normalise(mesh: RawMesh, height_mm: Optional[float], smooth: int = 0):
    """Return (vertices_mm, faces, colors, uvs, scaled_to_height)."""
    v = mesh.vertices.astype(np.float64)
    f = mesh.faces.astype(np.int64)
    if len(v) == 0 or len(f) == 0:
        raise ScanError(ErrorCode.NO_MODEL, "The engine produced an empty mesh.")
    colors, uvs = mesh.vertex_colors, mesh.uvs

    # 1 axis: Z up -> Y up (rotate -90° about X): (x, y, z) -> (x, z, -y)
    if mesh.up_axis == "z":
        v = np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)

    # 2 clean (UVs are kept only when the mesh needs no re-indexing)
    f = meshops.remove_degenerate(v, f)
    v2, f2, c2 = meshops.largest_component(v, f, colors)
    if len(v2) != len(v):
        uvs = None
    v, f, colors = v2, f2, c2
    f = meshops.orient_outward(v, f)
    if smooth:
        v = meshops.taubin(v, f, smooth).astype(np.float64)

    # 3 units
    height = float(v[:, 1].max() - v[:, 1].min())
    if height <= 0:
        raise ScanError(ErrorCode.NO_MODEL, "The engine produced a flat mesh.")
    if height_mm and height_mm > 0:
        scale, scaled = height_mm / height, True
    elif mesh.units == "m":
        scale, scaled = 1000.0, False
    elif mesh.units == "mm":
        scale, scaled = 1.0, False
    else:
        scale, scaled = DEFAULT_HEIGHT_MM / height, False

    # 4 place
    centre = np.array([(v[:, 0].max() + v[:, 0].min()) / 2, v[:, 1].min(), (v[:, 2].max() + v[:, 2].min()) / 2])
    v = (v - centre) * scale
    return v.astype(np.float32), f.astype(np.int32), colors, uvs, scaled


def write_obj(path: Path, v: np.ndarray, f: np.ndarray, normals: np.ndarray, colors=None, uvs=None,
              mtl_name: Optional[str] = None, header: tuple[str, ...] = ()) -> None:
    lines = [f"# {h}" for h in header]
    if mtl_name:
        lines.append(f"mtllib {mtl_name}.mtl")
    lines.append(f"o {path.stem}")
    out = ["\n".join(lines), "\n"]
    if colors is not None:
        c = colors.astype(np.float32) / 255.0
        data = np.hstack([v, c])
        out.append("\n".join("v %.3f %.3f %.3f %.4f %.4f %.4f" % tuple(r) for r in data))
    else:
        out.append("\n".join("v %.3f %.3f %.3f" % tuple(r) for r in v))
    out.append("\n")
    if uvs is not None:
        out.append("\n".join("vt %.5f %.5f" % tuple(r) for r in uvs))
        out.append("\n")
    out.append("\n".join("vn %.4f %.4f %.4f" % tuple(r) for r in normals))
    out.append("\n")
    if mtl_name:
        out.append("usemtl scan\n")
    ff = f + 1
    if uvs is not None:
        out.append("\n".join(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}" for a, b, c in ff))
    else:
        out.append("\n".join(f"f {a}//{a} {b}//{b} {c}//{c}" for a, b, c in ff))
    out.append("\n")
    path.write_text("".join(out), encoding="utf-8")


def write_glb(path: Path, v: np.ndarray, f: np.ndarray, normals: np.ndarray, colors=None) -> None:
    """Minimal binary glTF 2.0 (positions in metres, as glTF expects)."""
    pos = (v / 1000.0).astype(np.float32)
    nrm = normals.astype(np.float32)
    idx = f.astype(np.uint32).ravel()
    blobs = [pos.tobytes(), nrm.tobytes()]
    if colors is not None:
        blobs.append((colors.astype(np.float32) / 255.0).astype(np.float32).tobytes())
    blobs.append(idx.tobytes())
    views, offset = [], 0
    for i, b in enumerate(blobs):
        target = 34963 if i == len(blobs) - 1 else 34962
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(b), "target": target})
        offset += len(b) + (-len(b)) % 4
    attrs = {"POSITION": 0, "NORMAL": 1}
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
         "min": pos.min(axis=0).tolist(), "max": pos.max(axis=0).tolist()},
        {"bufferView": 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
    ]
    if colors is not None:
        attrs["COLOR_0"] = 2
        accessors.append({"bufferView": 2, "componentType": 5126, "count": len(pos), "type": "VEC3"})
    accessors.append({"bufferView": len(blobs) - 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
    gltf = {"asset": {"version": "2.0", "generator": "Bozzetto"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": attrs, "indices": len(accessors) - 1}]}],
            "buffers": [{"byteLength": offset}], "bufferViews": views, "accessors": accessors}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binary = b"".join(b + b"\0" * ((-len(b)) % 4) for b in blobs)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def write(mesh: RawMesh, job: Job, engine_id: str, seconds: float, log: tuple[str, ...] = (),
          smooth: int = 0) -> Result:
    v, f, colors, uvs, scaled = normalise(mesh, job.height_mm, smooth)
    normals = meshops.vertex_normals(v, f)
    folder = job.folder
    folder.mkdir(parents=True, exist_ok=True)
    size = tuple(float(x) for x in (v.max(axis=0) - v.min(axis=0)))
    files: dict[str, Path] = {}

    mtl_name = None
    if mesh.texture is not None and uvs is not None and Path(mesh.texture).exists():
        tex = folder / f"{job.name}_color{Path(mesh.texture).suffix}"
        shutil.copyfile(mesh.texture, tex)
        mtl_name = job.name
        (folder / f"{job.name}.mtl").write_text(
            f"# Bozzetto material\nnewmtl scan\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd {tex.name}\n",
            encoding="utf-8")
        files["mtl"] = folder / f"{job.name}.mtl"
        files["texture"] = tex
    else:
        uvs = None

    if "obj" in job.outputs:
        size_note = ("scaled to the real height you entered" if scaled else
                     "true scale from the engine" if mesh.units in ("m", "mm") else
                     f"no real height given: scaled to {DEFAULT_HEIGHT_MM:.0f} mm high")
        header = ("Bozzetto export", f"engine: {engine_id}", f"units: mm (1 unit = 1 mm), {size_note}",
                  "size (W x H x D): %.2f x %.2f x %.2f mm" % size,
                  f"vertices: {len(v)}, triangles: {len(f)}", "Y is up; the base of the object sits at y = 0")
        p = folder / f"{job.name}.obj"
        write_obj(p, v, f, normals, colors, uvs, mtl_name, header)
        files["obj"] = p
    if "glb" in job.outputs:
        p = folder / f"{job.name}.glb"
        write_glb(p, v, f, normals, colors)
        files["glb"] = p
    for extra in mesh.extra_files:
        if Path(extra).exists():
            dst = folder / Path(extra).name
            if Path(extra).resolve() != dst.resolve():
                shutil.copyfile(extra, dst)
            files[Path(extra).suffix.lstrip(".")] = dst
    return Result(job_id=job.id, engine_id=engine_id, files=files, size_mm=size, triangles=int(len(f)),
                  seconds=seconds, scaled_to_height=scaled, log=log)

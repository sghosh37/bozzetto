# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""TripoSR engine: one photo -> a closed, plausible 3D shape (the hidden side is guessed).

Uses the vendored TripoSR inference code (MIT) in ./tsr and the official weights from Hugging Face
(stabilityai/TripoSR, MIT), downloaded once into the user's data folder.
"""
from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path
from threading import Event, Lock
from typing import Optional

import cv2
import numpy as np

from ..core import downloads
from ..core.inputs import read_image, sharpness
from ..core.masks import cut_out
from ..core.models import (Cancelled, DownloadSpec, ErrorCode, Fit, FitLevel, Hardware, Job, Preset, Progress,
                           ProgressFn, RawMesh, ScanError, Status, StatusState)
from .base import Engine

MODEL_REPO = "stabilityai/TripoSR"
TOKENIZER_REPO = "facebook/dino-vitb16"
MODEL_FILES = ("config.yaml", "model.ckpt")
REQUIRED_MODULES = ("torch", "transformers", "omegaconf", "einops", "huggingface_hub")
INSTALL_HINT = 'pip install "bozzetto[triposr]"'


def model_dir() -> Path:
    return downloads.engines_dir() / "triposr"


def missing_modules() -> list[str]:
    return [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]


def weights_present() -> bool:
    d = model_dir()
    return all((d / f).exists() for f in MODEL_FILES) and (d / "dino-vitb16" / "config.json").exists()


def pick_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda:0"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def best_photo(frames) -> Path:
    """The sharpest photo whose product outline is clean (checks up to 12 evenly spaced photos)."""
    if len(frames) == 1:
        return frames[0]
    picks = [frames[int(i)] for i in np.linspace(0, len(frames) - 1, min(12, len(frames)))]
    scored = []
    for p in picks:
        img = read_image(p, max_width=800)
        co = cut_out(img)
        scored.append((co.ok, sharpness(img), p))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def prepare_image(path: Path, size: int = 512, fg_ratio: float = 0.85) -> np.ndarray:
    """Cut the product out, centre it on a square grey canvas (TripoSR's expected input), RGB float 0..1."""
    img = read_image(path, max_width=1600)
    co = cut_out(img)
    if not co.ok:
        raise ScanError(ErrorCode.NO_OUTLINE,
                        f"Couldn’t separate the product from the background in {path.name}. "
                        "Use a plain backdrop that contrasts with the product.")
    x, y, w, h = co.bbox
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    alpha = cv2.GaussianBlur(co.mask, (3, 3), 0).astype(np.float32)[..., None] / 255.0
    crop_rgb, crop_a = rgb[y:y + h, x:x + w], alpha[y:y + h, x:x + w]
    side = int(math.ceil(max(w, h) / fg_ratio))
    canvas = np.full((side, side, 3), 0.5, np.float32)
    a_canvas = np.zeros((side, side, 1), np.float32)
    oy, ox = (side - h) // 2, (side - w) // 2
    canvas[oy:oy + h, ox:ox + w] = crop_rgb
    a_canvas[oy:oy + h, ox:ox + w] = crop_a
    out = canvas * a_canvas + 0.5 * (1 - a_canvas)
    return cv2.resize(out, (size, size), interpolation=cv2.INTER_AREA)


class TripoSREngine(Engine):
    id = "triposr"
    name = "TripoSR (one photo)"
    min_photos = 1
    smooth_iterations = 0

    _model = None
    _device: Optional[str] = None
    _lock = Lock()

    def check(self, hw: Hardware) -> Status:
        missing = missing_modules()
        if missing:
            return Status(StatusState.UNSUPPORTED,
                          f"TripoSR support isn’t installed (missing {', '.join(missing)}). Run: {INSTALL_HINT}")
        if not weights_present():
            return Status(StatusState.NEEDS_DOWNLOAD, "model not downloaded yet",
                          DownloadSpec(title="TripoSR model", size_bytes=1_680_000_000, licence="MIT",
                                       source_url="https://huggingface.co/stabilityai/TripoSR"))
        return Status(StatusState.READY)

    def suits(self, job: Job, hw: Hardware) -> Fit:
        gpu = hw.nvidia is not None or hw.apple_gpu
        secs = 10 if gpu else 90
        if job.inputs.unique_count > 2:
            return Fit(FitLevel.GOOD, "uses the sharpest single photo; hidden sides are guessed", secs)
        return Fit(FitLevel.GOOD, "builds from one photo; hidden sides are guessed", secs)

    def prepare(self, progress: ProgressFn, cancel: Event) -> None:
        d = model_dir()
        d.mkdir(parents=True, exist_ok=True)
        steps = [(MODEL_REPO, "config.yaml", d), (TOKENIZER_REPO, "config.json", d / "dino-vitb16"),
                 (MODEL_REPO, "model.ckpt", d)]
        for i, (repo, name, target) in enumerate(steps):
            progress(Progress("Downloading the TripoSR model", i / len(steps), f"Downloading {name} from {repo}"))
            downloads.hf_download(repo, name, target, cancel=cancel)
        downloads.mark_installed("triposr", {"repo": MODEL_REPO, "files": list(MODEL_FILES), "licence": "MIT"})
        progress(Progress("Downloading the TripoSR model", 1.0, "TripoSR model ready"))

    def _load(self, progress: ProgressFn):
        with TripoSREngine._lock:
            if TripoSREngine._model is not None:
                return TripoSREngine._model, TripoSREngine._device
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            from omegaconf import OmegaConf
            import torch
            from .tsr.system import TSR
            progress(Progress("Loading the TripoSR model", 0.05))
            d = model_dir()
            cfg = OmegaConf.load(d / "config.yaml")
            cfg.image_tokenizer.pretrained_model_name_or_path = str(d / "dino-vitb16")
            OmegaConf.resolve(cfg)
            model = TSR(cfg)
            state = torch.load(d / "model.ckpt", map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            device = pick_device()
            model.renderer.set_chunk_size(8192 if device != "cpu" else 4096)
            model.to(device)
            model.eval()
            TripoSREngine._model, TripoSREngine._device = model, device
            return model, device

    def run(self, job: Job, progress: ProgressFn, cancel: Event) -> RawMesh:
        import torch
        photo = best_photo(list(job.inputs.frames))
        progress(Progress("Preparing the photo", 0.02, f"Using {photo.name}"))
        image = prepare_image(photo)
        if cancel.is_set():
            raise Cancelled()
        model, device = self._load(progress)
        progress(Progress("Reading the shape from the photo", 0.15, f"Running on {device}"))
        with torch.no_grad():
            scene_codes = model([image], device=device)
        if cancel.is_set():
            raise Cancelled()
        resolution = 320 if job.preset is Preset.ACCURATE else 256
        progress(Progress("Building the mesh", 0.55, f"Marching cubes at {resolution}³"))
        v, f, colors = model.extract_mesh(scene_codes, True, resolution=resolution)[0]
        if len(f) == 0:
            raise ScanError(ErrorCode.NO_MODEL, "TripoSR couldn’t find a shape in this photo.")
        # TripoSR's frame -> Y up, facing the viewer (same as TripoSR's own viewer orientation)
        rx = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float64)     # -90° about X
        ry = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], np.float64)     # +90° about Y
        v = (v.astype(np.float64) @ rx.T) @ ry.T
        vc = None if colors is None else np.clip(colors * 255, 0, 255).astype(np.uint8)
        progress(Progress("Building the mesh", 0.95, f"{len(f):,} triangles"))
        return RawMesh(vertices=v.astype(np.float32), faces=f.astype(np.int32), units="unit", up_axis="y",
                       vertex_colors=vc)

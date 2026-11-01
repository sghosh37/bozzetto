# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared data types and errors. This module imports nothing from the rest of Bozzetto."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional

import numpy as np


class InputKind(enum.Enum):
    PHOTOS = "photos"
    VIDEO = "video"


class Preset(enum.Enum):
    QUICK = "quick"        # rough shape, as fast as possible
    ACCURATE = "accurate"  # more detail, slower engines allowed


@dataclass(frozen=True)
class InputSet:
    kind: InputKind
    source: Path                       # the folder or the video file the user chose
    frames: tuple[Path, ...]           # usable, unique image files, in order
    duplicates: tuple[tuple[Path, Path], ...] = ()   # (copy, original)
    image_size: tuple[int, int] = (0, 0)             # (width, height) of the first frame
    focal_mm: Optional[float] = None                  # from EXIF, 35 mm equivalent when known
    focal_35mm: bool = False                          # True when focal_mm is a 35 mm-equivalent value
    turntable_score: float = 0.0                      # 0..1, how much this looks like a turntable shoot
    marker_mat: bool = False                          # printed marker mat found (planned)

    @property
    def unique_count(self) -> int:
        return len(self.frames)


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_gb: float


@dataclass(frozen=True)
class Hardware:
    os: Literal["windows", "linux", "macos"]
    os_version: str
    arch: str
    cpu_count: int
    ram_gb: float
    nvidia: Optional[GpuInfo] = None
    apple_gpu: bool = False            # Apple Silicon GPU usable by PyTorch (MPS)
    object_capture: bool = False       # macOS 12+ on Apple Silicon (helper built separately)

    @property
    def gpu_note(self) -> str:
        if self.nvidia:
            return self.nvidia.name
        if self.apple_gpu:
            return "Apple GPU"
        return "no GPU"


@dataclass(frozen=True)
class Job:
    inputs: InputSet
    preset: Preset = Preset.QUICK
    engine_id: Optional[str] = None            # None = choose automatically
    height_mm: Optional[float] = None          # real height of the object
    camera_tilt_deg: float = 20.0              # silhouette engine, plain turntable
    turn_clockwise: bool = False               # silhouette engine: turntable direction seen from above
    outputs: frozenset[str] = frozenset({"obj"})   # "obj", "glb"
    out_dir: Path = Path.home() / "Bozzetto"
    name: str = "scan"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def folder(self) -> Path:
        return self.out_dir / self.name

    @property
    def work_dir(self) -> Path:
        return self.folder / ".work"


@dataclass(frozen=True)
class Choice:
    engine_id: str
    reason: str
    warnings: tuple[str, ...] = ()
    fallbacks: tuple[str, ...] = ()


class StatusState(enum.Enum):
    READY = "ready"
    NEEDS_DOWNLOAD = "needs_download"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class DownloadSpec:
    title: str              # "TripoSR model"
    size_bytes: int         # approximate, for the dialog
    licence: str
    source_url: str


@dataclass(frozen=True)
class Status:
    state: StatusState
    reason: str = ""
    download: Optional[DownloadSpec] = None


class FitLevel(enum.Enum):
    GOOD = "good"
    SLOW = "slow"
    UNSUITABLE = "unsuitable"


@dataclass(frozen=True)
class Fit:
    level: FitLevel
    reason: str = ""
    est_seconds: Optional[float] = None


@dataclass(frozen=True)
class Progress:
    stage: str
    fraction: Optional[float] = None    # 0..1 within the whole job, None = unknown
    message: Optional[str] = None       # a line for the log


ProgressFn = Callable[[Progress], None]


@dataclass
class RawMesh:
    vertices: np.ndarray                         # float32 (N, 3)
    faces: np.ndarray                            # int32 (M, 3), counter-clockwise = outward
    units: Literal["m", "mm", "unit"] = "unit"   # "unit" = arbitrary scale
    up_axis: Literal["y", "z"] = "y"
    vertex_colors: Optional[np.ndarray] = None   # uint8 (N, 3)
    uvs: Optional[np.ndarray] = None             # float32 (N, 2)
    texture: Optional[Path] = None
    extra_files: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class Result:
    job_id: str
    engine_id: str
    files: dict
    size_mm: tuple[float, float, float]
    triangles: int
    seconds: float
    scaled_to_height: bool
    log: tuple[str, ...] = ()


class ErrorCode(enum.Enum):
    NO_INPUT = "NO_INPUT"
    TOO_FEW_PHOTOS = "TOO_FEW_PHOTOS"
    COPIES_ONLY = "COPIES_ONLY"
    NO_OUTLINE = "NO_OUTLINE"
    NO_MODEL = "NO_MODEL"
    UNSUPPORTED = "UNSUPPORTED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    ENGINE_CRASHED = "ENGINE_CRASHED"
    CANCELLED = "CANCELLED"


class ScanError(Exception):
    def __init__(self, code: ErrorCode, user_message: str, detail: str = "", suggest_engine: Optional[str] = None):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.detail = detail
        self.suggest_engine = suggest_engine

    def __str__(self) -> str:
        return self.user_message


class Cancelled(ScanError):
    def __init__(self):
        super().__init__(ErrorCode.CANCELLED, "Cancelled.")

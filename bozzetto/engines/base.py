# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""The interface every scanning engine implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Event
from typing import ClassVar

from ..core.models import Fit, Hardware, Job, ProgressFn, RawMesh, Status


class Engine(ABC):
    id: ClassVar[str]           # "silhouette", "triposr", "apple", "colmap_openmvs"
    name: ClassVar[str]         # shown in the window
    min_photos: ClassVar[int] = 1
    smooth_iterations: ClassVar[int] = 0   # extra Taubin smoothing applied by export

    @abstractmethod
    def check(self, hw: Hardware) -> Status:
        """Can it run on this computer? READY, NEEDS_DOWNLOAD (+ what) or UNSUPPORTED (+ why)."""

    @abstractmethod
    def suits(self, job: Job, hw: Hardware) -> Fit:
        """How well does it fit this input? GOOD / SLOW / UNSUITABLE, with a reason and rough time."""

    @abstractmethod
    def run(self, job: Job, progress: ProgressFn, cancel: Event) -> RawMesh:
        """Build the mesh. Raise ScanError (or Cancelled) on failure."""

    def prepare(self, progress: ProgressFn, cancel: Event) -> None:
        """Download whatever check() said is missing. Default: nothing to do."""

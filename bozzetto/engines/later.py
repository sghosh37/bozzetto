# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engines planned for later stages. They report UNSUPPORTED so the selector skips them."""
from __future__ import annotations

from threading import Event

from ..core.models import (ErrorCode, Fit, FitLevel, Hardware, Job, ProgressFn, RawMesh, ScanError, Status,
                           StatusState)
from .base import Engine


class _Planned(Engine):
    stage = ""

    def check(self, hw: Hardware) -> Status:
        return Status(StatusState.UNSUPPORTED, f"coming in {self.stage}")

    def suits(self, job: Job, hw: Hardware) -> Fit:
        return Fit(FitLevel.UNSUITABLE, f"coming in {self.stage}")

    def run(self, job: Job, progress: ProgressFn, cancel: Event) -> RawMesh:
        raise ScanError(ErrorCode.UNSUPPORTED, f"{self.name} is not built yet ({self.stage}).")


class AppleEngine(_Planned):
    id = "apple"
    name = "Apple Object Capture"
    min_photos = 10
    stage = "stage 3 (Mac only)"


class ColmapOpenMVSEngine(_Planned):
    id = "colmap_openmvs"
    name = "COLMAP + OpenMVS"
    min_photos = 20
    stage = "stage 4"

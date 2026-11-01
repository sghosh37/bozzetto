# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine registry. To add an engine: write a class implementing base.Engine and list it here."""
from __future__ import annotations

from .base import Engine
from .later import AppleEngine, ColmapOpenMVSEngine
from .silhouette import SilhouetteEngine
from .triposr import TripoSREngine

REGISTRY: dict[str, type[Engine]] = {e.id: e for e in
                                     (TripoSREngine, SilhouetteEngine, AppleEngine, ColmapOpenMVSEngine)}


def available() -> dict[str, Engine]:
    """One instance of every engine, keyed by id (order = dropdown order)."""
    return {k: cls() for k, cls in REGISTRY.items()}

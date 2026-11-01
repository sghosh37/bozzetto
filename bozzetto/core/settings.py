# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Remember the user's choices between runs (settings.json in the user config folder)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

import platformdirs

APP = "Bozzetto"


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP, appauthor=False))


def data_dir() -> Path:
    """Where downloaded engines and models live."""
    return Path(platformdirs.user_data_dir(APP, appauthor=False))


@dataclass
class Settings:
    version: int = 1
    last_input_dir: Optional[str] = None
    out_dir: str = str(Path.home() / "Bozzetto")
    preset: str = "quick"
    engine: str = "auto"
    height_mm: Optional[float] = None
    camera_tilt_deg: float = 20.0
    turn_clockwise: bool = False
    outputs: list = field(default_factory=lambda: ["obj"])
    video_frames: int = 40
    blender_path: Optional[str] = None
    extra: dict = field(default_factory=dict)      # unknown keys from newer versions are kept here


def path() -> Path:
    return config_dir() / "settings.json"


def load() -> Settings:
    try:
        raw = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    s = Settings(**{k: v for k, v in raw.items() if k in known and k != "extra"})
    s.extra = {k: v for k, v in raw.items() if k not in known}
    return s


def save(s: Settings) -> None:
    data = asdict(s)
    extra = data.pop("extra", {}) or {}
    data.update(extra)
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)

# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic engine choice.

The rules are a table, checked top to bottom; the first rule whose engine can run here and whose
condition is true wins. Edit RULES to change the defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .models import Choice, Hardware, Job, Preset, StatusState

TURNTABLE = 0.7   # turntable_score above this counts as a turntable shoot


@dataclass(frozen=True)
class Rule:
    engine: str
    when: Callable[[Job, Hardware], bool]
    reason: str           # formatted with facts(): {n}, {gpu}


def _turntable(j: Job) -> bool:
    return j.inputs.turntable_score > TURNTABLE


RULES: list[Rule] = [
    Rule("triposr", lambda j, h: j.inputs.unique_count <= 2,
         "{n} photo(s): only TripoSR can build a shape from so few"),
    Rule("apple", lambda j, h: h.object_capture and j.inputs.unique_count >= 20,
         "Mac with Object Capture and {n} photos"),
    Rule("silhouette", lambda j, h: _turntable(j) and j.inputs.unique_count >= 6
         and (j.inputs.unique_count <= 30 or h.nvidia is None or j.preset is Preset.QUICK),
         "{n} turntable photos, {gpu}: builds in seconds"),
    Rule("colmap_openmvs", lambda j, h: j.inputs.unique_count >= 20 and h.nvidia is not None,
         "{n} photos and an NVIDIA GPU ({gpu})"),
    Rule("colmap_openmvs", lambda j, h: j.inputs.unique_count >= 20,
         "{n} photos, no NVIDIA GPU: this may take a long time"),
    # last resort: always possible
    Rule("silhouette", lambda j, h: j.inputs.unique_count >= 6,
         "{n} photos; best guess (not detected as a turntable shoot)"),
    Rule("triposr", lambda j, h: True,
         "{n} photos: using the sharpest one for a one-photo shape"),
]


def facts(job: Job, hw: Hardware) -> dict:
    return {"n": job.inputs.unique_count, "gpu": hw.gpu_note}


def warnings_for(job: Job, hw: Hardware, engine_id: str) -> tuple[str, ...]:
    w = []
    if job.inputs.duplicates:
        w.append(f"{len(job.inputs.duplicates)} exact copies ignored (copies add no new viewpoint).")
    if engine_id in ("triposr", "silhouette") and not job.height_mm:
        w.append("Enter the real height in mm for a true-to-size model.")
    if engine_id == "silhouette" and not _turntable(job):
        w.append("These photos don’t look like a turntable shoot; the shape may be rough.")
    return tuple(w)


def choose(job: Job, hw: Hardware, engines: dict) -> Choice:
    """engines: id -> Engine instance (from bozzetto.engines.available())."""
    if job.engine_id and job.engine_id != "auto":
        auto = choose(replace(job, engine_id=None), hw, engines)
        fallbacks = tuple(e for e in (auto.engine_id, *auto.fallbacks) if e != job.engine_id)
        return Choice(job.engine_id, "Chosen by you", warnings_for(job, hw, job.engine_id), fallbacks)
    runnable = [r for r in RULES if r.engine in engines
                and engines[r.engine].check(hw).state is not StatusState.UNSUPPORTED]
    for r in runnable:
        if r.when(job, hw):
            fallbacks = tuple(dict.fromkeys(x.engine for x in runnable if x.engine != r.engine))
            return Choice(r.engine, r.reason.format(**facts(job, hw)), warnings_for(job, hw, r.engine), fallbacks)
    # nothing matched (cannot happen while the last rule is unconditional)
    first = next(iter(engines))
    return Choice(first, "Default engine", warnings_for(job, hw, first), ())

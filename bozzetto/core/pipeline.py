# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run one job: choose the engine, make sure it is downloaded, run it, export. Used by the window and the CLI."""
from __future__ import annotations

import shutil
import time
from dataclasses import replace
from threading import Event
from typing import Callable, Optional

from . import export
from .hardware import detect
from .models import (Cancelled, Choice, ErrorCode, Job, Progress, ProgressFn, Result, ScanError, StatusState)
from .select import choose

# Called before a download; return False to cancel. Receives the engine and its Status.
ConfirmDownload = Callable[[object, object], bool]


def run(job: Job, progress: ProgressFn, cancel: Optional[Event] = None,
        confirm_download: Optional[ConfirmDownload] = None, engines: Optional[dict] = None) -> tuple[Result, Choice]:
    from ..engines import available
    cancel = cancel or Event()
    engines = engines or available()
    hw = detect()
    choice = choose(job, hw, engines)
    engine = engines.get(choice.engine_id)
    if engine is None:
        raise ScanError(ErrorCode.UNSUPPORTED, f"Unknown engine “{choice.engine_id}”.")
    log: list[str] = [f"Engine: {engine.name} ({choice.reason})", *choice.warnings]
    for line in log:
        progress(Progress("Starting", 0.0, line))

    status = engine.check(hw)
    if status.state is StatusState.UNSUPPORTED:
        raise ScanError(ErrorCode.UNSUPPORTED, f"{engine.name} can’t run on this computer: {status.reason}.",
                        suggest_engine=choice.fallbacks[0] if choice.fallbacks else None)
    if status.state is StatusState.NEEDS_DOWNLOAD:
        if confirm_download and not confirm_download(engine, status):
            raise Cancelled()
        engine.prepare(progress, cancel)

    if job.inputs.unique_count < engine.min_photos:
        raise ScanError(ErrorCode.TOO_FEW_PHOTOS,
                        f"{engine.name} needs at least {engine.min_photos} different photos; this set has "
                        f"{job.inputs.unique_count}.", suggest_engine=choice.fallbacks[0] if choice.fallbacks else None)

    job.work_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        mesh = engine.run(job, progress, cancel)
        if cancel.is_set():
            raise Cancelled()
        progress(Progress("Saving", 0.97))
        result = export.write(mesh, job, engine.id, time.monotonic() - started, tuple(log),
                              smooth=getattr(engine, "smooth_iterations", 0))
    except ScanError as e:
        if e.suggest_engine is None and choice.fallbacks and e.code is not ErrorCode.CANCELLED:
            e.suggest_engine = choice.fallbacks[0]
        raise
    except Exception as e:  # unexpected crash inside an engine
        raise ScanError(ErrorCode.ENGINE_CRASHED, f"{engine.name} stopped unexpectedly: {e}",
                        detail=repr(e), suggest_engine=choice.fallbacks[0] if choice.fallbacks else None) from e
    shutil.rmtree(job.work_dir, ignore_errors=True)     # kept only when something failed
    progress(Progress("Done", 1.0))
    return result, choice


def with_engine(job: Job, engine_id: str) -> Job:
    return replace(job, engine_id=engine_id)

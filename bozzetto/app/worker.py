# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Background work for the window: inspecting the input and running a job, off the main thread."""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal

from ..core import inputs, pipeline
from ..core.models import ErrorCode, Job, Progress, ScanError


class _Base(QObject):
    progress = Signal(object)    # Progress
    failed = Signal(object)      # ScanError
    done = Signal(object)        # result

    def __init__(self):
        super().__init__()
        self.cancel = Event()
        self._last = 0.0

    def _emit_progress(self, p: Progress):
        now = time.monotonic()
        if p.message or now - self._last > 0.1 or (p.fraction or 0) >= 1:   # at most 10 updates a second
            self._last = now
            self.progress.emit(p)

    def _fail(self, e: BaseException):
        if isinstance(e, ScanError):
            self.failed.emit(e)
        else:
            self.failed.emit(ScanError(ErrorCode.ENGINE_CRASHED, f"Something went wrong: {e}",
                                       detail=traceback.format_exc()))


class InspectWorker(_Base):
    def __init__(self, path: Path, video_frames: int):
        super().__init__()
        self.path, self.video_frames = path, video_frames

    def run(self):
        try:
            ins = inputs.inspect(self.path, video_frames=self.video_frames,
                                 progress=lambda f: self._emit_progress(Progress("Reading the video", f)),
                                 cancel=self.cancel)
            self.done.emit(ins)
        except BaseException as e:   # noqa: BLE001 - report everything to the window
            self._fail(e)


class JobWorker(_Base):
    def __init__(self, job: Job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            result, choice = pipeline.run(self.job, self._emit_progress, self.cancel,
                                          confirm_download=lambda engine, status: True)
            self.done.emit((result, choice))
        except BaseException as e:   # noqa: BLE001
            self._fail(e)


def start(worker: _Base, parent: QObject) -> QThread:
    """Run worker.run() on a new QThread; the thread cleans itself up."""
    thread = QThread(parent)
    thread.worker = worker            # keep the worker alive as long as its thread
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread

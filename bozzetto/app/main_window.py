# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bozzetto window. All work runs on worker threads; this file only shows state and collects settings."""
from __future__ import annotations

import enum
import glob
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import settings as settings_mod
from ..core.hardware import describe, detect
from ..core.inputs import VIDEO_EXTS
from ..core.models import InputKind, InputSet, Job, Preset, Progress, ScanError, StatusState
from ..core.select import choose
from ..engines import available
from . import worker
from .preview import MeshPreview


class UiState(enum.Enum):
    EMPTY = "empty"
    INSPECTING = "inspecting"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


def find_blender(configured: Optional[str]) -> Optional[str]:
    if configured and Path(configured).exists():
        return configured
    exe = shutil.which("blender")
    if exe:
        return exe
    candidates = []
    if sys.platform == "win32":
        candidates = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    elif sys.platform == "darwin":
        candidates = ["/Applications/Blender.app/Contents/MacOS/Blender"]
    return next((c for c in candidates if Path(c).exists()), None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bozzetto")
        self.resize(1180, 780)
        self.hw = detect()
        self.engines = available()
        self.settings = settings_mod.load()
        self.inputs: Optional[InputSet] = None
        self.input_path: Optional[Path] = None
        self.current: Optional[worker._Base] = None
        self.last_result = None
        self.retry_engine: Optional[str] = None
        self._build_ui()
        self._load_settings()
        self.set_state(UiState.EMPTY)

    # ---------- layout ----------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        top = QHBoxLayout()
        title = QLabel("<b style='font-size:16px'>Bozzetto</b>&nbsp;&nbsp;<span style='color:#5B6470'>photos to a rough 3D shape</span>")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(QLabel(f"<span style='color:#5B6470'>{describe(self.hw)}</span>"))
        outer.addLayout(top)

        body = QHBoxLayout()
        outer.addLayout(body, 1)

        # left: input / result
        left = QVBoxLayout()
        body.addLayout(left, 3)
        self.stack = QStackedWidget()
        left.addWidget(self.stack, 1)

        inp = QGroupBox("Input")
        il = QVBoxLayout(inp)
        row = QHBoxLayout()
        self.src_photos = QRadioButton("Photos")
        self.src_video = QRadioButton("Video")
        self.src_photos.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.src_photos)
        grp.addButton(self.src_video)
        row.addWidget(self.src_photos)
        row.addWidget(self.src_video)
        row.addStretch(1)
        self.choose_btn = QPushButton("Choose folder…")
        self.choose_btn.clicked.connect(self.choose_input)
        self.src_photos.toggled.connect(lambda on: self.choose_btn.setText("Choose folder…" if on else "Choose video…"))
        row.addWidget(self.choose_btn)
        il.addLayout(row)
        self.path_label = QLabel("Choose a folder of photos, one photo, or a short video that circles the object.")
        self.path_label.setWordWrap(True)
        il.addWidget(self.path_label)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setIconSize(QSize(96, 96))
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setMovement(QListWidget.Static)
        il.addWidget(self.thumbs, 1)
        self.checks = QLabel("")
        self.checks.setWordWrap(True)
        il.addWidget(self.checks)
        self.stack.addWidget(inp)

        res = QGroupBox("Result")
        rl = QVBoxLayout(res)
        self.preview = MeshPreview()
        rl.addWidget(self.preview, 1)
        self.stack.addWidget(res)

        logbox = QGroupBox("Log")
        ll = QVBoxLayout(logbox)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setFixedHeight(130)
        ll.addWidget(self.log)
        left.addWidget(logbox)

        # right: settings and actions
        right = QVBoxLayout()
        body.addLayout(right, 2)
        sbox = QGroupBox("Settings")
        form = QFormLayout(sbox)
        self.preset = QComboBox()
        self.preset.addItem("Quick shape", Preset.QUICK)
        self.preset.addItem("Accurate", Preset.ACCURATE)
        self.preset.currentIndexChanged.connect(self.update_choice)
        form.addRow("Preset", self.preset)
        self.engine = QComboBox()
        self.engine.currentIndexChanged.connect(self.update_choice)
        form.addRow("Engine", self.engine)
        self.reason = QLabel("")
        self.reason.setWordWrap(True)
        self.reason.setStyleSheet("color:#5B6470")
        form.addRow("", self.reason)
        self.height_known = QCheckBox("I measured the real height")
        self.height = QDoubleSpinBox()
        self.height.setRange(1, 5000)
        self.height.setDecimals(1)
        self.height.setSuffix(" mm")
        self.height.setValue(100)
        self.height.setEnabled(False)
        self.height_known.toggled.connect(self.height.setEnabled)
        self.height_known.toggled.connect(self.update_choice)
        hrow = QHBoxLayout()
        hrow.addWidget(self.height_known)
        hrow.addWidget(self.height)
        form.addRow("Size", hrow)
        self.tilt = QSpinBox()
        self.tilt.setRange(0, 80)
        self.tilt.setSuffix("° looking down")
        form.addRow("Camera tilt", self.tilt)
        self.clockwise = QCheckBox("Turntable turned clockwise (seen from above)")
        form.addRow("", self.clockwise)
        self.frames = QSpinBox()
        self.frames.setRange(8, 200)
        self.frames.setSuffix(" frames")
        form.addRow("From a video", self.frames)
        orow = QHBoxLayout()
        self.out_obj = QCheckBox("OBJ")
        self.out_obj.setChecked(True)
        self.out_glb = QCheckBox("GLB")
        orow.addWidget(self.out_obj)
        orow.addWidget(self.out_glb)
        orow.addStretch(1)
        form.addRow("Save as", orow)
        drow = QHBoxLayout()
        self.out_dir = QLabel("")
        self.out_dir.setWordWrap(True)
        change = QPushButton("Change…")
        change.clicked.connect(self.choose_out_dir)
        drow.addWidget(self.out_dir, 1)
        drow.addWidget(change)
        form.addRow("Save to", drow)
        right.addWidget(sbox)

        self.build_btn = QPushButton("Build 3D model")
        self.build_btn.setMinimumHeight(44)
        self.build_btn.setStyleSheet("QPushButton{background:#B45309;color:white;font-weight:600;border-radius:8px}"
                                     "QPushButton:disabled{background:#C9CED6;color:#6B7380}")
        self.build_btn.clicked.connect(self.build)
        right.addWidget(self.build_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        right.addWidget(self.cancel_btn)
        self.stage = QLabel("")
        right.addWidget(self.stage)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        right.addWidget(self.bar)

        self.result_box = QGroupBox("Model")
        rgrid = QGridLayout(self.result_box)
        self.result_text = QLabel("")
        self.result_text.setWordWrap(True)
        rgrid.addWidget(self.result_text, 0, 0, 1, 2)
        self.open_blender = QPushButton("Open in Blender")
        self.open_blender.clicked.connect(self.open_in_blender)
        self.show_folder = QPushButton("Show in folder")
        self.show_folder.clicked.connect(self.show_in_folder)
        rgrid.addWidget(self.open_blender, 1, 0)
        rgrid.addWidget(self.show_folder, 1, 1)
        self.new_scan = QPushButton("New scan")
        self.new_scan.clicked.connect(lambda: self.set_state(UiState.READY if self.inputs else UiState.EMPTY))
        rgrid.addWidget(self.new_scan, 2, 0)
        self.retry_btn = QPushButton("Retry with …")
        self.retry_btn.clicked.connect(self.retry)
        rgrid.addWidget(self.retry_btn, 2, 1)
        right.addWidget(self.result_box)
        right.addStretch(1)
        right.addWidget(QLabel(f"<span style='color:#8A929C'>Bozzetto {__version__} · GPL-3.0-or-later</span>"))

        self.setCentralWidget(root)
        self._fill_engines()

    def _fill_engines(self):
        self.engine.blockSignals(True)
        self.engine.clear()
        self.engine.addItem("Automatic", "auto")
        for eid, e in self.engines.items():
            st = e.check(self.hw)
            note = {StatusState.READY: "",
                    StatusState.NEEDS_DOWNLOAD: f" (downloads {st.download.size_bytes / 1e9:.1f} GB on first use)"
                    if st.download else " (downloads on first use)",
                    StatusState.UNSUPPORTED: f" ({st.reason})"}[st.state]
            self.engine.addItem(e.name + note, eid)
            if st.state is StatusState.UNSUPPORTED:
                item = self.engine.model().item(self.engine.count() - 1)
                item.setEnabled(False)
        self.engine.blockSignals(False)

    # ---------- settings ---------------------------------------------------------------------
    def _load_settings(self):
        s = self.settings
        self.preset.setCurrentIndex(0 if s.preset == "quick" else 1)
        i = self.engine.findData(s.engine)
        self.engine.setCurrentIndex(max(0, i))
        if s.height_mm:
            self.height.setValue(s.height_mm)
        self.tilt.setValue(int(s.camera_tilt_deg))
        self.clockwise.setChecked(s.turn_clockwise)
        self.frames.setValue(s.video_frames)
        self.out_glb.setChecked("glb" in s.outputs)
        self.out_obj.setChecked("obj" in s.outputs)
        self.out_dir.setText(s.out_dir)

    def _save_settings(self):
        s = self.settings
        s.preset = self.preset.currentData().value
        s.engine = self.engine.currentData()
        s.height_mm = self.height.value() if self.height_known.isChecked() else s.height_mm
        s.camera_tilt_deg = float(self.tilt.value())
        s.turn_clockwise = self.clockwise.isChecked()
        s.video_frames = self.frames.value()
        s.outputs = [x for x, cb in (("obj", self.out_obj), ("glb", self.out_glb)) if cb.isChecked()] or ["obj"]
        s.out_dir = self.out_dir.text()
        try:
            settings_mod.save(s)
        except OSError:
            pass

    # ---------- state machine ----------------------------------------------------------------
    def set_state(self, state: UiState):
        self.state = state
        busy = state in (UiState.INSPECTING, UiState.RUNNING)
        self.build_btn.setVisible(not busy)
        self.cancel_btn.setVisible(busy)
        self.build_btn.setEnabled(state in (UiState.READY, UiState.DONE, UiState.FAILED, UiState.CANCELLED)
                                  and self.inputs is not None)
        self.choose_btn.setEnabled(not busy)
        for w in (self.preset, self.engine, self.height_known, self.tilt, self.clockwise, self.frames,
                  self.out_obj, self.out_glb):
            w.setEnabled(not busy)
        self.height.setEnabled(not busy and self.height_known.isChecked())
        self.result_box.setVisible(state in (UiState.DONE, UiState.FAILED))
        self.open_blender.setVisible(state is UiState.DONE)
        self.show_folder.setVisible(state is UiState.DONE)
        self.retry_btn.setVisible(state is UiState.FAILED and self.retry_engine is not None)
        self.stack.setCurrentIndex(1 if state is UiState.DONE else 0)
        if state in (UiState.EMPTY, UiState.READY):
            self.bar.setValue(0)
            self.stage.setText("")

    # ---------- input -------------------------------------------------------------------------
    def choose_input(self):
        start = self.settings.last_input_dir or str(Path.home())
        if self.src_photos.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Choose the folder with your photos", start)
        else:
            exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
            path, _ = QFileDialog.getOpenFileName(self, "Choose a video that circles the object", start,
                                                  f"Videos ({exts})")
        if not path:
            return
        self.input_path = Path(path)
        self.settings.last_input_dir = str(self.input_path.parent if self.input_path.is_file() else self.input_path)
        self.path_label.setText(str(self.input_path))
        self.thumbs.clear()
        self.checks.setText("")
        self.inputs = None
        self.write(f"Reading {self.input_path.name}…")
        self.set_state(UiState.INSPECTING)
        w = worker.InspectWorker(self.input_path, self.frames.value())
        w.progress.connect(self.on_progress)
        w.done.connect(self.on_inspected)
        w.failed.connect(self.on_failed)
        self.current = w
        worker.start(w, self)

    def on_inspected(self, ins: InputSet):
        self.inputs = ins
        self.current = None
        for p in ins.frames[:48]:
            pm = QPixmap(str(p))
            item = QListWidgetItem(QIcon(pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)), "")
            item.setToolTip(p.name)
            self.thumbs.addItem(item)
        chips = [f"{ins.unique_count} {'frames' if ins.kind is InputKind.VIDEO else 'photos'}"]
        chips.append("Turntable shoot" if ins.turntable_score > 0.7 else "Not a turntable shoot")
        chips.append(f"{len(ins.duplicates)} copies ignored" if ins.duplicates else "No copies")
        if ins.focal_mm:
            chips.append(f"Focal length {ins.focal_mm:.0f} mm{' (35 mm eq.)' if ins.focal_35mm else ''}")
        self.checks.setText("  ·  ".join(chips))
        self.write(f"{ins.unique_count} usable image(s); turntable score {ins.turntable_score:.2f}")
        self.set_state(UiState.READY)
        self.update_choice()

    # ---------- engine choice -------------------------------------------------------------------
    def make_job(self, engine_id: Optional[str] = None) -> Job:
        eid = engine_id or self.engine.currentData()
        name = (self.input_path.stem if self.input_path and self.input_path.is_file()
                else self.input_path.name if self.input_path else "scan").replace(" ", "-")
        outs = frozenset(x for x, cb in (("obj", self.out_obj), ("glb", self.out_glb)) if cb.isChecked()) or {"obj"}
        return Job(inputs=self.inputs, preset=self.preset.currentData(), engine_id=None if eid == "auto" else eid,
                   height_mm=self.height.value() if self.height_known.isChecked() else None,
                   camera_tilt_deg=float(self.tilt.value()), turn_clockwise=self.clockwise.isChecked(),
                   outputs=frozenset(outs), out_dir=Path(self.out_dir.text()), name=name)

    def update_choice(self):
        if not self.inputs:
            self.reason.setText("")
            return
        c = choose(self.make_job(), self.hw, self.engines)
        eng = self.engines[c.engine_id]
        fit = eng.suits(self.make_job(), self.hw)
        text = f"<b>{eng.name}</b>: {c.reason}"
        if fit and fit.est_seconds:
            text += f" · about {fit.est_seconds:.0f} s"
        for w in c.warnings:
            text += f"<br><span style='color:#7A3A00'>{w}</span>"
        self.reason.setText(text)

    # ---------- running ----------------------------------------------------------------------
    def build(self, engine_id: Optional[str] = None):
        if not self.inputs:
            return
        job = self.make_job(engine_id if isinstance(engine_id, str) else None)
        c = choose(job, self.hw, self.engines)
        eng = self.engines[c.engine_id]
        st = eng.check(self.hw)
        if st.state is StatusState.UNSUPPORTED:
            QMessageBox.warning(self, "Bozzetto", f"{eng.name} can’t run here: {st.reason}")
            return
        if st.state is StatusState.NEEDS_DOWNLOAD and st.download:
            d = st.download
            ok = QMessageBox.question(
                self, f"Download {d.title}?",
                f"{eng.name} needs to download {d.title} once (about {d.size_bytes / 1e9:.1f} GB).\n\n"
                f"Licence: {d.licence}\nSource: {d.source_url}\n\nIt is stored for later runs. Download now?")
            if ok != QMessageBox.Yes:
                return
        self._save_settings()
        self.retry_engine = None
        self.log.clear()
        self.write(f"Building with {eng.name}…")
        self.set_state(UiState.RUNNING)
        self.bar.setValue(0)
        w = worker.JobWorker(replace(job, engine_id=c.engine_id))
        w.progress.connect(self.on_progress)
        w.done.connect(self.on_done)
        w.failed.connect(self.on_failed)
        self.current = w
        worker.start(w, self)

    def cancel(self):
        if self.current:
            self.current.cancel.set()
            self.stage.setText("Cancelling…")

    def on_progress(self, p: Progress):
        self.stage.setText(p.stage)
        if p.fraction is not None:
            self.bar.setValue(int(p.fraction * 1000))
        if p.message:
            self.write(p.message)

    def on_done(self, payload):
        result, choice = payload
        self.current = None
        self.last_result = result
        w, h, d = result.size_mm
        files = ", ".join(Path(p).name for p in result.files.values())
        size_note = "" if result.scaled_to_height else "<br><span style='color:#7A3A00'>Size is not real-world: tick “I measured the real height” and build again.</span>"
        self.result_text.setText(f"<b>Model ready</b><br>{w:.1f} × {h:.1f} × {d:.1f} mm (W × H × D)<br>"
                                 f"{result.triangles:,} triangles · {result.seconds:.1f} s · {self.engines[result.engine_id].name}"
                                 f"<br>Saved {files}{size_note}")
        self.write(f"Saved {files} in {result.files.get('obj', next(iter(result.files.values()))).parent}")
        if "obj" in result.files:
            self.preview.load(result.files["obj"])
        self.bar.setValue(1000)
        self.stage.setText("Done")
        self.set_state(UiState.DONE)

    def on_failed(self, e: ScanError):
        self.current = None
        cancelled = e.code.value == "CANCELLED"
        self.write(e.user_message)
        if e.detail and not cancelled:
            self.write(f"  details: {e.detail.strip().splitlines()[-1][:300]}")
        if self.state is UiState.INSPECTING:
            self.inputs = None
            self.set_state(UiState.EMPTY)
            if not cancelled:
                QMessageBox.warning(self, "Bozzetto", e.user_message)
            return
        self.retry_engine = e.suggest_engine if not cancelled else None
        if self.retry_engine:
            self.retry_btn.setText(f"Retry with {self.engines[self.retry_engine].name}")
        self.result_text.setText(f"<b>{'Cancelled' if cancelled else 'Couldn’t build the model'}</b><br>{e.user_message}")
        self.stage.setText("Cancelled" if cancelled else "Failed")
        self.set_state(UiState.CANCELLED if cancelled else UiState.FAILED)
        if cancelled:
            self.result_box.setVisible(False)

    def retry(self):
        if self.retry_engine:
            i = self.engine.findData(self.retry_engine)
            if i >= 0:
                self.engine.setCurrentIndex(i)
            self.build(self.retry_engine)

    # ---------- results ----------------------------------------------------------------------
    def show_in_folder(self):
        if self.last_result:
            folder = next(iter(self.last_result.files.values())).parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_in_blender(self):
        if not self.last_result or "obj" not in self.last_result.files:
            return
        exe = find_blender(self.settings.blender_path)
        if not exe:
            QMessageBox.information(self, "Bozzetto", "Blender wasn’t found. Install it from blender.org, or open "
                                                      "the OBJ yourself: File → Import → Wavefront (.obj), Scale 0.001.")
            return
        obj = str(self.last_result.files["obj"])
        script = ("import bpy; bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(); "
                  f"bpy.ops.wm.obj_import(filepath={obj!r}, global_scale=0.001)")
        subprocess.Popen([exe, "--python-expr", script])

    def choose_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose where to save models", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def write(self, line: str):
        self.log.appendPlainText(line)

    def closeEvent(self, e):
        self._save_settings()
        if self.current:
            self.current.cancel.set()
        super().closeEvent(e)


def main() -> int:
    if platform.system() == "Darwin":
        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Bozzetto")
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

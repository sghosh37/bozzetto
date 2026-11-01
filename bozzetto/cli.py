# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""bozzetto-cli: the same pipeline as the window, from a terminal."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from threading import Event

from . import __version__
from .core import inputs, pipeline
from .core.hardware import describe, detect
from .core.models import Job, Preset, Progress, ScanError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bozzetto-cli",
                                 description="Turn photos or a video into a rough 3D shape (OBJ) for sculpting.")
    ap.add_argument("input", type=Path, help="a folder of photos, one photo, or a video (MOV/MP4)")
    ap.add_argument("out_dir", type=Path, help="folder to save into (a subfolder named after the model is made)")
    ap.add_argument("--engine", default="auto",
                    help="auto (default), silhouette, triposr, apple, colmap_openmvs")
    ap.add_argument("--preset", choices=["quick", "accurate"], default="quick")
    ap.add_argument("--height-mm", type=float, help="real height of the object, for true size")
    ap.add_argument("--tilt", type=float, default=20.0, help="camera tilt in degrees (silhouette engine)")
    ap.add_argument("--clockwise", action="store_true", help="turntable turned clockwise seen from above")
    ap.add_argument("--frames", type=int, default=40, help="frames to take from a video")
    ap.add_argument("--glb", action="store_true", help="also write a GLB file")
    ap.add_argument("--name", help="model name (default: input name)")
    ap.add_argument("--yes", action="store_true", help="download engines without asking")
    ap.add_argument("--version", action="version", version=f"Bozzetto {__version__}")
    a = ap.parse_args(argv)

    print(f"Bozzetto {__version__} · {describe(detect())}")
    last = {"stage": None}

    def progress(p: Progress):
        if p.message:
            print(f"\r  {p.message}" + " " * 10)
        if p.stage != last["stage"]:
            print(f"\n{p.stage}…")
            last["stage"] = p.stage
        if p.fraction is not None:
            sys.stdout.write(f"\r  {int(p.fraction * 100):3d}%")
            sys.stdout.flush()

    def confirm(engine, status) -> bool:
        if a.yes:
            return True
        spec = status.download
        size = f"{spec.size_bytes / 1e9:.1f} GB" if spec else "some files"
        ans = input(f"\n{engine.name} needs to download {spec.title if spec else 'files'} ({size}, "
                    f"{spec.licence if spec else ''}). Download now? [y/N] ")
        return ans.strip().lower() in ("y", "yes")

    try:
        print("Reading the input…")
        ins = inputs.inspect(a.input, video_frames=a.frames)
        print(f"  {ins.unique_count} usable photo(s)" + (f", {len(ins.duplicates)} copies ignored" if ins.duplicates else "")
              + f", turntable score {ins.turntable_score:.2f}")
        name = a.name or (a.input.stem if a.input.is_file() else a.input.name).replace(" ", "-")
        job = Job(inputs=ins, preset=Preset(a.preset), engine_id=None if a.engine == "auto" else a.engine,
                  height_mm=a.height_mm, camera_tilt_deg=a.tilt, turn_clockwise=a.clockwise,
                  outputs=frozenset({"obj", "glb"} if a.glb else {"obj"}), out_dir=a.out_dir, name=name)
        result, choice = pipeline.run(job, progress, Event(), confirm)
    except ScanError as e:
        print(f"\n\nError: {e.user_message}")
        if e.detail:
            print(f"  ({e.detail})")
        if e.suggest_engine:
            print(f"  Try: --engine {e.suggest_engine}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    w, h, d = result.size_mm
    print(f"\n\nSaved {result.files.get('obj') or next(iter(result.files.values()))}")
    print(f"  {w:.1f} × {h:.1f} × {d:.1f} mm (W × H × D) · {result.triangles:,} triangles · "
          f"{result.seconds:.1f} s · engine {result.engine_id}"
          + ("" if result.scaled_to_height else "  (enter --height-mm for true size)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

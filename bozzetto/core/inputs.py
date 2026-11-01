# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a photo folder or a video into an InputSet: frames, copies, EXIF focal length, turntable score."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .masks import cut_out
from .models import ErrorCode, InputKind, InputSet, ScanError

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def is_video(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXTS


def list_photos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_EXTS
                  and not p.name.startswith("."))


def read_image(path: Path, max_width: Optional[int] = None) -> np.ndarray:
    """Read any supported photo as BGR uint8 (HEIC via pillow-heif when installed)."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        from PIL import Image
        try:
            import pillow_heif  # noqa: F401
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
        with Image.open(path) as im:
            img = cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    if max_width and img.shape[1] > max_width:
        s = max_width / img.shape[1]
        img = cv2.resize(img, (max_width, int(round(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
    return img


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(paths: list[Path]) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """Split into unique files and (copy, original) pairs, by exact content."""
    seen: dict[str, Path] = {}
    unique, dups = [], []
    for p in paths:
        key = file_hash(p)
        if key in seen:
            dups.append((p, seen[key]))
        else:
            seen[key] = p
            unique.append(p)
    return unique, dups


def exif_focal(path: Path) -> tuple[Optional[float], bool]:
    """(focal length in mm, is_35mm_equivalent) from EXIF, or (None, False)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            exif = im.getexif()
            sub = exif.get_ifd(0x8769)
            f35 = sub.get(0xA405)
            if f35:
                return float(f35), True
            f = sub.get(0x920A)
            if f:
                return float(f), False
    except Exception:
        pass
    return None, False


def sharpness(img: np.ndarray) -> float:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if g.shape[1] > 320:
        g = cv2.resize(g, (320, int(g.shape[0] * 320 / g.shape[1])), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def extract_frames(video: Path, out_dir: Path, count: int = 40, candidates: int = 3,
                   progress=None, cancel=None) -> list[Path]:
    """Evenly spaced frames; around each point keep the sharpest of `candidates` nearby frames."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ScanError(ErrorCode.NO_INPUT, f"Couldn’t open the video {video.name}.")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 2:
        cap.release()
        raise ScanError(ErrorCode.NO_INPUT, "The video is too short. Film a slow 15–30 s circle around the object.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):
        old.unlink()
    n = max(1, min(count, total))
    slot = total / n
    written: list[Path] = []
    for i in range(n):
        if cancel is not None and cancel.is_set():
            break
        best, best_s = None, -1.0
        for k in range(candidates):
            idx = int(min(total - 1, slot * (i + (k + 0.5) / candidates)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            s = sharpness(frame)
            if s > best_s:
                best, best_s = frame, s
        if best is not None:
            p = out_dir / f"frame_{i + 1:04d}.jpg"
            cv2.imwrite(str(p), best, [cv2.IMWRITE_JPEG_QUALITY, 92])
            written.append(p)
        if progress:
            progress((i + 1) / n)
    cap.release()
    if not written:
        raise ScanError(ErrorCode.NO_INPUT, "Couldn’t read any frames from the video.")
    return written


def turntable_score(frames: list[Path], sample: int = 12) -> float:
    """0..1: same size, same backdrop colour, outline centred similarly, similar outline height."""
    if len(frames) < 3:
        return 0.0
    picks = [frames[int(i)] for i in np.linspace(0, len(frames) - 1, min(sample, len(frames)))]
    sizes, bgs, cxs, heights = set(), [], [], []
    for p in picks:
        img = read_image(p, max_width=400)
        sizes.add(img.shape[:2])
        co = cut_out(img)
        if not co.ok:
            return 0.0
        x, y, w, h = co.bbox
        bgs.append(co.background_lab)
        cxs.append((x + w / 2) / img.shape[1])
        heights.append(h / img.shape[0])
    s_size = 1.0 if len(sizes) == 1 else 0.0
    bg_spread = float(np.max(np.std(np.array(bgs), axis=0)))
    s_bg = float(np.clip(1 - bg_spread / 12.0, 0, 1))
    s_cx = float(np.clip(1 - np.std(cxs) / 0.08, 0, 1))
    s_h = float(np.clip(1 - np.std(heights) / max(np.mean(heights), 1e-6) / 0.15, 0, 1))
    return round(0.25 * s_size + 0.25 * s_bg + 0.25 * s_cx + 0.25 * s_h, 3)


def inspect(path: Path, frames_dir: Optional[Path] = None, video_frames: int = 40,
            progress=None, cancel=None) -> InputSet:
    """Build an InputSet from a photo folder, a single photo, or a video file."""
    path = Path(path)
    if is_video(path):
        if frames_dir is None:
            import platformdirs
            frames_dir = Path(platformdirs.user_cache_dir("Bozzetto")) / "frames" / file_hash(path)[:16]
        frames = extract_frames(path, frames_dir, video_frames, progress=progress, cancel=cancel)
        kind, dups = InputKind.VIDEO, []
    elif path.is_dir():
        photos = list_photos(path)
        if not photos:
            raise ScanError(ErrorCode.NO_INPUT, "That folder has no JPEG, HEIC or PNG photos.")
        frames, dups = find_duplicates(photos)
        kind = InputKind.PHOTOS
    elif path.is_file() and path.suffix.lower() in PHOTO_EXTS:
        frames, dups, kind = [path], [], InputKind.PHOTOS
    else:
        raise ScanError(ErrorCode.NO_INPUT, f"{path.name} isn’t a photo folder, a photo or a video.")

    first = read_image(frames[0])
    focal, is35 = exif_focal(frames[0])
    return InputSet(kind=kind, source=path, frames=tuple(frames), duplicates=tuple(dups),
                    image_size=(first.shape[1], first.shape[0]), focal_mm=focal, focal_35mm=is35,
                    turntable_score=turntable_score(frames))

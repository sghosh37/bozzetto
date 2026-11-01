# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch engine files on first use, verify them and keep them in the user's data folder."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from .models import Cancelled, ErrorCode, ScanError
from .settings import data_dir


def engines_dir() -> Path:
    d = data_dir() / "engines"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _installed_path() -> Path:
    return engines_dir() / "installed.json"


def installed() -> dict:
    try:
        return json.loads(_installed_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mark_installed(name: str, info: dict) -> None:
    data = installed()
    data[name] = info
    _installed_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch(url: str, dest: Path, sha256: Optional[str] = None,
          progress: Optional[Callable[[int, int], None]] = None, cancel: Optional[Event] = None) -> Path:
    """Download url to dest via a resumable .part file; verify SHA-256 when given."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "Bozzetto", **({"Range": f"bytes={start}-"} if start else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if start and r.status != 206:
                start = 0
            total = start + int(r.headers.get("Content-Length") or 0)
            with open(part, "ab" if start else "wb") as fh:
                done = start
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except Cancelled:
        raise
    except Exception as e:  # network errors
        raise ScanError(ErrorCode.DOWNLOAD_FAILED, f"Couldn’t download {dest.name}: {e}", detail=url) from e
    if sha256:
        h = hashlib.sha256()
        with open(part, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha256.lower():
            part.unlink(missing_ok=True)
            raise ScanError(ErrorCode.CHECKSUM_MISMATCH,
                            f"The downloaded file {dest.name} was damaged and has been deleted. Please try again.")
    os.replace(part, dest)
    return dest


def hf_download(repo_id: str, filename: str, target_dir: Path,
                progress: Optional[Callable[[int, int], None]] = None, cancel: Optional[Event] = None) -> Path:
    """Download one file from a Hugging Face repository into target_dir (resumable, verified by the hub)."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise ScanError(ErrorCode.UNSUPPORTED, "TripoSR support isn’t installed. Run: pip install \"bozzetto[triposr]\"") from e
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    try:
        return Path(hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(target_dir)))
    except Exception as e:
        raise ScanError(ErrorCode.DOWNLOAD_FAILED, f"Couldn’t download {filename} from Hugging Face: {e}",
                        detail=f"{repo_id}/{filename}") from e

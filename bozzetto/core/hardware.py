# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Describe this computer once at start-up."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache

from .models import GpuInfo, Hardware


def _ram_gb() -> float:
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (ValueError, OSError):
        pass
    if platform.system() == "Windows":
        import ctypes

        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMSTAT()
        st.dwLength = ctypes.sizeof(MEMSTAT)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return st.ullTotalPhys / 1024 ** 3
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            return int(out.stdout.strip()) / 1024 ** 3
        except Exception:
            pass
    return 0.0


def nvidia_info() -> GpuInfo | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10)
        line = out.stdout.strip().splitlines()[0]
        name, mem = [s.strip() for s in line.split(",")]
        return GpuInfo(name=name, memory_gb=round(float(mem) / 1024, 1))
    except Exception:
        return None


@lru_cache(maxsize=1)
def detect() -> Hardware:
    system = platform.system()
    os_name = {"Windows": "windows", "Darwin": "macos"}.get(system, "linux")
    arch = platform.machine().lower()
    if os_name == "macos":
        version = platform.mac_ver()[0] or platform.release()
    else:
        version = platform.release()
    apple_silicon = os_name == "macos" and arch in ("arm64", "aarch64")
    try:
        major = int(version.split(".")[0]) if os_name == "macos" else 0
    except ValueError:
        major = 0
    return Hardware(os=os_name, os_version=version, arch=arch, cpu_count=os.cpu_count() or 1,
                    ram_gb=round(_ram_gb(), 1), nvidia=nvidia_info(), apple_gpu=apple_silicon,
                    object_capture=apple_silicon and major >= 12)


def describe(hw: Hardware) -> str:
    os_label = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}[hw.os]
    gpu = hw.nvidia.name if hw.nvidia else ("Apple GPU" if hw.apple_gpu else "no NVIDIA GPU")
    return f"{os_label} {hw.os_version} · {gpu} · {hw.ram_gb:.0f} GB"

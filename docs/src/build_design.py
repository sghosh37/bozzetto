# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build docs/design.html from design_template.html, filling {{name}} with the SVG diagrams.

    python docs/src/build_design.py
"""
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
from diagrams import ALL  # noqa: E402

page = (here / "design_template.html").read_text(encoding="utf-8")
for key, fn in ALL.items():
    page = page.replace("{{" + key + "}}", fn())
left = re.findall(r"\{\{\w+\}\}", page)
if left:
    raise SystemExit(f"unfilled diagrams: {left}")
(here.parent / "design.html").write_text(page, encoding="utf-8")
print("wrote", here.parent / "design.html")

# Bozzetto: photos to a rough 3D shape for sculpting
# Copyright (C) 2026 Suman Ghosh
# SPDX-License-Identifier: GPL-3.0-or-later
"""python -m bozzetto opens the window; with arguments it runs the command-line tool."""
import sys

if len(sys.argv) > 1:
    from .cli import main
    sys.exit(main())
else:
    from .app.main_window import main
    sys.exit(main())

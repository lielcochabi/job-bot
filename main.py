#!/usr/bin/env python3
"""CLI entry point — run: python main.py [command]"""
from __future__ import annotations

import sys
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1255 encoding errors)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_bot.cli import main

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the same checks as .github/workflows/ci.yml locally (WP-9)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    steps = [
        [sys.executable, "-m", "pytest", "pae/tests", "-q", "--tb=short"],
        [sys.executable, str(root / "tools" / "magic_number_grep.py")],
    ]
    for cmd in steps:
        print("+", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=root)
        if proc.returncode != 0:
            return proc.returncode
    print("ci_local: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

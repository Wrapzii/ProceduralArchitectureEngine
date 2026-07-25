#!/usr/bin/env python3
"""Export validated M1 box-house manifest to Saved/exports/m1_manifest.json.

Thin compatibility wrapper around :mod:`tools.export_manifest`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.export_manifest import main as export_main  # noqa: E402


def main() -> int:
    return export_main(["--milestone", "m1"])


if __name__ == "__main__":
    raise SystemExit(main())

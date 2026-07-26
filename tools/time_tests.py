#!/usr/bin/env python3
"""Time each unit-test file separately so slow ones are obvious.

    python tools/time_tests.py [--top N] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    files = sorted((ROOT / "pae" / "tests" / "unit").glob("test_*.py"))
    rows = []
    for i, f in enumerate(files, 1):
        rel = f.relative_to(ROOT).as_posix()
        t = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", rel, "-q", "--no-header",
                 "-p", "no:cacheprovider"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
            dt = time.perf_counter() - t
            status = "ok" if proc.returncode == 0 else f"FAIL({proc.returncode})"
        except subprocess.TimeoutExpired:
            dt = args.timeout
            status = "TIMEOUT"
        rows.append((dt, rel, status))
        print(f"[{i:3d}/{len(files)}] {dt:7.1f}s  {status:10s} {rel}", flush=True)

    rows.sort(reverse=True)
    print("\n===== slowest =====")
    for dt, rel, status in rows[: args.top]:
        print(f"  {dt:7.1f}s  {status:10s} {rel}")
    print(f"\ntotal: {sum(r[0] for r in rows):.1f}s across {len(rows)} files")
    bad = [r for r in rows if r[2] != "ok"]
    if bad:
        print(f"\n===== not passing ({len(bad)}) =====")
        for dt, rel, status in bad:
            print(f"  {status:10s} {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

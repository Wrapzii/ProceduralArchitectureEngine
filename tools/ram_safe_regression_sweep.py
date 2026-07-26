#!/usr/bin/env python3
"""RAM-safe whole-suite regression sweep — one pytest process per file.

Usage:
    python tools/ram_safe_regression_sweep.py
    python tools/ram_safe_regression_sweep.py --include-deferred
    python tools/ram_safe_regression_sweep.py --only test_assemble.py

Never runs xdist, ci_local, or multi-file pytest invocations.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = ROOT / "pae" / "tests"
REPORT_PATH = ROOT / "Saved" / "exports" / "regression_sweep_report.json"

# Run last (or skip unless --include-deferred). Known RAM-heavy / slow paths.
DEFERRED_HEAVY = {
    "test_fortress_compound.py",
    "test_random_specs.py",
    "test_golden_scaffold.py",
    "test_arch_arcade_gallery.py",
    "test_blender_build.py",
}

# Per-file timeout seconds (deferred get longer budget).
DEFAULT_TIMEOUT_S = 180
DEFERRED_TIMEOUT_S = 600
MEMORY_LIMIT_MB = 4096  # kill child if RSS exceeds this (when psutil available)


def _try_import_psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except ImportError:
        return None


def discover_test_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("unit/test_*.py", "integration/test_*.py", "property/test_*.py", "golden/test_*.py"):
        files.extend(sorted(TESTS_ROOT.glob(pattern)))
    return files


def partition_files(files: list[Path], include_deferred: bool) -> tuple[list[Path], list[Path]]:
    primary: list[Path] = []
    deferred: list[Path] = []
    for f in files:
        if f.name in DEFERRED_HEAVY:
            deferred.append(f)
        else:
            primary.append(f)
    if include_deferred:
        return primary, deferred
    return primary, deferred


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def run_one_file(
    test_file: Path,
    *,
    timeout_s: int,
    psutil,
) -> dict:
    rel = _rel(test_file)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        rel,
        "-q",
        "-p",
        "no:cacheprovider",
        "--tb=line",
    ]
    t0 = time.monotonic()
    peak_rss_mb = 0.0
    status = "error"
    passed = 0
    failed = 0
    skipped = 0
    detail = ""

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines: list[str] = []
        while True:
            if proc.poll() is not None:
                # drain remainder
                rest = proc.stdout.read() if proc.stdout else ""
                if rest:
                    output_lines.append(rest)
                break
            if psutil is not None:
                try:
                    p = psutil.Process(proc.pid)
                    rss = p.memory_info().rss / (1024 * 1024)
                    peak_rss_mb = max(peak_rss_mb, rss)
                    if rss > MEMORY_LIMIT_MB:
                        proc.kill()
                        proc.wait()
                        elapsed = time.monotonic() - t0
                        return {
                            "file": rel,
                            "status": "skipped_for_memory",
                            "passed": 0,
                            "failed": 0,
                            "skipped": 0,
                            "duration_s": round(elapsed, 2),
                            "peak_rss_mb": round(peak_rss_mb, 1),
                            "detail": f"Killed: RSS {rss:.0f}MB > {MEMORY_LIMIT_MB}MB",
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            elapsed = time.monotonic() - t0
            if elapsed > timeout_s:
                proc.kill()
                proc.wait()
                return {
                    "file": rel,
                    "status": "error",
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "duration_s": round(elapsed, 2),
                    "peak_rss_mb": round(peak_rss_mb, 1),
                    "detail": f"Timeout after {timeout_s}s",
                }
            time.sleep(0.25)

        elapsed = time.monotonic() - t0
        output = "".join(output_lines)
        rc = proc.returncode or 0

        # pytest -q summary line e.g. "12 passed in 1.23s" or "2 failed, 10 passed in 3.4s"
        m_passed = re.search(r"(\d+) passed", output)
        m_failed = re.search(r"(\d+) failed", output)
        m_skipped = re.search(r"(\d+) skipped", output)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_skipped:
            skipped = int(m_skipped.group(1))

        if rc == 0:
            status = "passed"
        elif failed > 0 or "FAILED" in output:
            status = "failed"
        else:
            status = "error"

        # last non-empty lines for detail on failure
        if status != "passed":
            tail = [ln.strip() for ln in output.strip().splitlines() if ln.strip()][-8:]
            detail = "\n".join(tail)

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        return {
            "file": rel,
            "status": "error",
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration_s": round(elapsed, 2),
            "peak_rss_mb": round(peak_rss_mb, 1),
            "detail": str(exc),
        }

    return {
        "file": rel,
        "status": status,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_s": round(elapsed, 2),
        "peak_rss_mb": round(peak_rss_mb, 1),
        "detail": detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAM-safe per-file pytest sweep")
    parser.add_argument("--include-deferred", action="store_true", help="Run heavy/deferred files last")
    parser.add_argument("--only", metavar="NAME", help="Run a single test file (basename or path)")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Output JSON path")
    args = parser.parse_args()

    psutil = _try_import_psutil()
    all_files = discover_test_files()
    if args.only:
        needle = args.only.replace("\\", "/")
        matched = [f for f in all_files if needle in f.as_posix() or f.name == needle]
        if not matched:
            print(f"No test file matching {args.only!r}", file=sys.stderr)
            return 2
        run_queue = matched
        deferred_not_run: list[str] = []
    else:
        primary, deferred = partition_files(all_files, include_deferred=args.include_deferred)
        run_queue = primary + (deferred if args.include_deferred else [])
        deferred_not_run = [_rel(f) for f in deferred] if not args.include_deferred else []

    results: list[dict] = []
    skipped_memory: list[str] = []

    print(f"ram_safe_regression_sweep: {len(run_queue)} file(s) queued", flush=True)
    for i, test_file in enumerate(run_queue, 1):
        rel = _rel(test_file)
        timeout = DEFERRED_TIMEOUT_S if test_file.name in DEFERRED_HEAVY else DEFAULT_TIMEOUT_S
        print(f"[{i}/{len(run_queue)}] {rel} ...", flush=True)
        row = run_one_file(test_file, timeout_s=timeout, psutil=psutil)
        results.append(row)
        if row["status"] == "skipped_for_memory":
            skipped_memory.append(rel)
        mark = row["status"].upper()
        print(f"    -> {mark} ({row['duration_s']}s, peak_rss={row.get('peak_rss_mb', 0)}MB)", flush=True)
        if row["status"] in ("failed", "error") and row.get("detail"):
            for ln in row["detail"].splitlines()[:3]:
                print(f"       {ln}", flush=True)

    totals = {
        "files_run": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "skipped_for_memory": len(skipped_memory),
        "deferred_not_run": len(deferred_not_run),
        "tests_passed": sum(r["passed"] for r in results),
        "tests_failed": sum(r["failed"] for r in results),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ram_safe": True,
        "single_process_per_file": True,
        "include_deferred": bool(args.include_deferred),
        "totals": totals,
        "skipped_for_memory": skipped_memory,
        "deferred_not_run": deferred_not_run,
        "files": results,
    }

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out}", flush=True)
    print(
        f"Totals: run={totals['files_run']} passed={totals['passed']} "
        f"failed={totals['failed']} error={totals['error']} "
        f"skipped_memory={totals['skipped_for_memory']} deferred_not_run={totals['deferred_not_run']}",
        flush=True,
    )
    return 1 if totals["failed"] or totals["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

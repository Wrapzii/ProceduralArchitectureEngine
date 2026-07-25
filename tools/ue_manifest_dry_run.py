#!/usr/bin/env python3
"""Deterministic UE manifest dry-run consumer (M6).

Simulates the Unreal spawn-ready checks without an editor: schema, required fields,
placement ``loc_cm`` / ``yaw``, asset references, and validation gate.

Usage::

    python tools/ue_manifest_dry_run.py [path_to_manifest.json]
    python tools/ue_manifest_dry_run.py --milestone m3

Default manifest: ``Saved/exports/m1_manifest.json`` (auto-exported when missing).
``--milestone`` resolves to ``Saved/exports/{milestone}_manifest.json`` and
auto-exports via :mod:`tools.export_manifest` when that file is absent.
Report: ``Saved/exports/m6_dry_run_report.json`` (exit 0 when ``ok``, else 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from numbers import Real
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.export.manifest import SCHEMA  # noqa: E402

from tools.export_manifest import MILESTONE_SPECS  # noqa: E402

DEFAULT_MANIFEST_PATH = ROOT / "Saved" / "exports" / "m1_manifest.json"
DEFAULT_REPORT_PATH = ROOT / "Saved" / "exports" / "m6_dry_run_report.json"

REQUIRED_TOP_LEVEL = (
    "schema",
    "module_cm",
    "storey_cm",
    "origin_convention",
    "contract",
    "assets",
    "placements",
    "validation",
)

REQUIRED_CONTRACT_KEYS = ("module_cm", "storey_cm", "wall_t_cm", "floor_t_cm")

REQUIRED_PLACEMENT_KEYS = ("asset_id", "piece_id", "loc_cm", "yaw", "cell", "level")

VALID_YAWS = frozenset({0, 90, 180, 270})

JsonDict = Dict[str, Any]


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _valid_yaw(value: Any) -> bool:
    if not _is_number(value):
        return False
    as_int = int(value)
    return float(as_int) == float(value) and as_int in VALID_YAWS


def _valid_loc_cm(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    return all(_is_number(v) for v in value)


def _asset_ids(assets: Any) -> set[str]:
    if not isinstance(assets, list):
        return set()
    ids: set[str] = set()
    for row in assets:
        if isinstance(row, Mapping) and isinstance(row.get("id"), str):
            ids.add(row["id"])
    return ids


def dry_run_manifest(manifest: Mapping[str, Any]) -> JsonDict:
    """Run spawn-readiness checks on an in-memory manifest dict."""
    failures: List[str] = []

    def fail(msg: str) -> None:
        failures.append(msg)

    if not isinstance(manifest, Mapping):
        fail("manifest root must be a JSON object")
        return {
            "ok": False,
            "placement_count": 0,
            "asset_count": 0,
            "failures": failures,
        }

    for key in REQUIRED_TOP_LEVEL:
        if key not in manifest:
            fail(f"missing required field: {key}")

    schema = manifest.get("schema")
    if schema != SCHEMA:
        fail(f"schema must be {SCHEMA!r}, got {schema!r}")

    origin = manifest.get("origin_convention")
    if origin != "min_corner":
        fail(f"origin_convention must be 'min_corner', got {origin!r}")

    contract = manifest.get("contract")
    if not isinstance(contract, Mapping):
        fail("contract must be an object")
    else:
        for key in REQUIRED_CONTRACT_KEYS:
            if key not in contract:
                fail(f"contract missing required key: {key}")
            elif not _is_number(contract[key]):
                fail(f"contract.{key} must be numeric")

    assets = manifest.get("assets")
    asset_count = 0
    known_assets: set[str] = set()
    if not isinstance(assets, list):
        fail("assets must be an array")
    else:
        asset_count = len(assets)
        known_assets = _asset_ids(assets)
        if asset_count == 0:
            fail("assets must not be empty")

    placements = manifest.get("placements")
    placement_count = 0
    if not isinstance(placements, list):
        fail("placements must be an array")
    else:
        placement_count = len(placements)
        if placement_count == 0:
            fail("placements must not be empty")
        for idx, row in enumerate(placements):
            prefix = f"placements[{idx}]"
            if not isinstance(row, Mapping):
                fail(f"{prefix} must be an object")
                continue
            for key in REQUIRED_PLACEMENT_KEYS:
                if key not in row:
                    fail(f"{prefix} missing required field: {key}")
            asset_id = row.get("asset_id")
            if isinstance(asset_id, str):
                if asset_id not in known_assets:
                    fail(f"{prefix} asset_id {asset_id!r} not in assets[]")
            else:
                fail(f"{prefix} asset_id must be a string")
            if not _valid_loc_cm(row.get("loc_cm")):
                fail(f"{prefix} loc_cm must be three numeric values")
            if not _valid_yaw(row.get("yaw")):
                yaw_val = row.get("yaw")
                fail(
                    f"{prefix} yaw must be one of {sorted(VALID_YAWS)}, got {yaw_val!r}"
                )

    validation = manifest.get("validation")
    if not isinstance(validation, Mapping):
        fail("validation must be an object")
    else:
        if validation.get("ok") is not True:
            fail("validation.ok must be true")
        critical_count = validation.get("critical_count")
        if critical_count != 0:
            fail(f"validation.critical_count must be 0, got {critical_count!r}")

    return {
        "ok": len(failures) == 0,
        "placement_count": placement_count,
        "asset_count": asset_count,
        "failures": failures,
    }


def load_manifest(path: Path) -> JsonDict:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"manifest root must be a JSON object: {path}")
    return data


def ensure_manifest_exists(path: Path) -> None:
    """Auto-export a known milestone manifest when *path* is missing."""
    if path.is_file():
        return
    from tools.export_manifest import (
        milestone_from_manifest_path,
        run_export,
    )

    milestone = milestone_from_manifest_path(path)
    if milestone is None and path.resolve() == DEFAULT_MANIFEST_PATH.resolve():
        milestone = "m1"
    if milestone is None:
        raise FileNotFoundError(f"manifest not found: {path}")

    rc, _data, report = run_export(milestone, out_path=path)
    if rc != 0 or not path.is_file():
        detail = "; ".join(f.message for f in report.critical[:3])
        raise RuntimeError(
            f"failed to export {milestone} manifest to {path}"
            + (f" ({detail})" if detail else "")
        )


def write_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_dry_run(
    manifest_path: Path,
    *,
    report_path: Path = DEFAULT_REPORT_PATH,
    auto_export: bool = True,
) -> JsonDict:
    """Load (optionally export), validate, and write the dry-run report."""
    if auto_export:
        ensure_manifest_exists(manifest_path)
    elif not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    manifest = load_manifest(manifest_path)
    report = dry_run_manifest(manifest)
    write_report(report, report_path)
    return report


def resolve_manifest_path(
    manifest_arg: Optional[str],
    milestone: Optional[str],
) -> Path:
    """Resolve CLI manifest path from positional arg and/or ``--milestone``."""
    from tools.export_manifest import VALID_MILESTONES, manifest_out_path

    if milestone is not None:
        if milestone not in VALID_MILESTONES:
            choices = ", ".join(sorted(VALID_MILESTONES))
            raise ValueError(f"unknown milestone {milestone!r}; expected one of: {choices}")
        if manifest_arg is not None:
            raise ValueError("pass either a manifest path or --milestone, not both")
        return manifest_out_path(milestone)

    raw = manifest_arg if manifest_arg is not None else str(DEFAULT_MANIFEST_PATH)
    manifest_path = Path(raw)
    if not manifest_path.is_absolute():
        manifest_path = (ROOT / manifest_path).resolve()
    return manifest_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="UE manifest dry-run consumer — spawn-readiness without Unreal Editor.",
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        default=None,
        help=f"path to manifest JSON (default: {DEFAULT_MANIFEST_PATH.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--milestone",
        "-m",
        default=None,
        choices=sorted(MILESTONE_SPECS),
        help="milestone label → Saved/exports/{milestone}_manifest.json",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help=f"dry-run report output (default: {DEFAULT_REPORT_PATH.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--no-auto-export",
        action="store_true",
        help="do not auto-export when the manifest path is missing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        manifest_path = resolve_manifest_path(args.manifest, args.milestone)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = (ROOT / report_path).resolve()

    try:
        report = run_dry_run(
            manifest_path,
            report_path=report_path,
            auto_export=not args.no_auto_export,
        )
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError, ValueError) as exc:
        report = {
            "ok": False,
            "placement_count": 0,
            "asset_count": 0,
            "failures": [str(exc)],
        }
        write_report(report, report_path)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Wrote {report_path}")
    print(
        f"  ok={report['ok']} placements={report['placement_count']} "
        f"assets={report['asset_count']}"
    )
    if report["failures"]:
        for line in report["failures"]:
            print(f"  FAIL: {line}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

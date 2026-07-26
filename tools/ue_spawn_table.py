#!/usr/bin/env python3
"""Emit a UE-ready spawn table from a validated PAE manifest (M6 handoff).

Transforms ``placements[]`` into a flat table of ``asset_id``, ``loc_cm``,
``yaw``, and ``piece_id`` — no grid math required in Unreal.

Usage::

    python tools/ue_spawn_table.py --milestone m1
    # → Saved/exports/m1_spawn_table.json
    python tools/ue_spawn_table.py --milestone m1 --csv
    # → Saved/exports/m1_spawn_table.json + m1_spawn_table.csv

Refuses when ``validation.ok`` is false or the manifest fails dry-run checks.
Auto-exports the milestone manifest via :mod:`tools.export_manifest` when missing.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.export_manifest import (  # noqa: E402
    VALID_MILESTONES,
    manifest_out_path,
)
from pae.export.spawn_groups import group_rows_by_asset_id  # noqa: E402
from tools.ue_manifest_dry_run import (  # noqa: E402
    ensure_manifest_exists,
    load_manifest,
)

SPAWN_TABLE_SCHEMA = "pae.spawn_table/2"
SPAWN_TABLE_SCHEMA_V1 = "pae.spawn_table/1"
SUPPORTED_SPAWN_TABLE_SCHEMAS = frozenset({SPAWN_TABLE_SCHEMA, SPAWN_TABLE_SCHEMA_V1})

JsonDict = Dict[str, Any]

REQUIRED_ROW_KEYS = ("asset_id", "loc_cm", "yaw", "piece_id")


def spawn_table_out_path(milestone: str, root: Path = ROOT) -> Path:
    """Default on-disk path for a milestone spawn table."""
    return root / "Saved" / "exports" / f"{milestone}_spawn_table.json"


def spawn_table_csv_path(milestone: str, root: Path = ROOT) -> Path:
    """Default CSV path alongside the JSON spawn table."""
    return root / "Saved" / "exports" / f"{milestone}_spawn_table.csv"


def _normalize_loc_cm(value: Any) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("loc_cm must be a list of three numbers")
    return [float(value[0]), float(value[1]), float(value[2])]


def manifest_to_spawn_rows(manifest: Mapping[str, Any]) -> List[JsonDict]:
    """Extract ISM-ready rows from a manifest ``placements[]`` array."""
    placements = manifest.get("placements")
    if not isinstance(placements, list):
        raise ValueError("manifest placements must be an array")
    if not placements:
        raise ValueError("manifest placements must not be empty")

    rows: List[JsonDict] = []
    for idx, placement in enumerate(placements):
        prefix = f"placements[{idx}]"
        if not isinstance(placement, Mapping):
            raise ValueError(f"{prefix} must be an object")
        for key in REQUIRED_ROW_KEYS:
            if key not in placement:
                raise ValueError(f"{prefix} missing required field: {key}")
        asset_id = placement["asset_id"]
        piece_id = placement["piece_id"]
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError(f"{prefix} asset_id must be a non-empty string")
        if not isinstance(piece_id, str) or not piece_id:
            raise ValueError(f"{prefix} piece_id must be a non-empty string")
        yaw = placement["yaw"]
        if int(yaw) != float(yaw):
            raise ValueError(f"{prefix} yaw must be an integer degree value")
        rows.append(
            {
                "asset_id": asset_id,
                "loc_cm": _normalize_loc_cm(placement["loc_cm"]),
                "yaw": int(yaw),
                "piece_id": piece_id,
            }
        )
    return rows


def build_spawn_table(
    manifest: Mapping[str, Any],
    *,
    milestone: str,
    source_manifest: Union[str, Path],
) -> JsonDict:
    """Build the spawn-table document from an in-memory manifest."""
    validation = manifest.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("manifest validation must be an object")
    if validation.get("ok") is not True:
        raise ValueError("validation.ok must be true — spawn table refused")

    rows = manifest_to_spawn_rows(manifest)
    ism_groups = group_rows_by_asset_id(rows)
    return {
        "schema": SPAWN_TABLE_SCHEMA,
        "milestone": milestone,
        "source_manifest": str(source_manifest).replace("\\", "/"),
        "row_count": len(rows),
        "ism_group_count": len(ism_groups),
        "rows": rows,
        "ism_groups": ism_groups,
    }


def write_spawn_table(table: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(table), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_spawn_table_csv(table: Mapping[str, Any], path: Path) -> None:
    rows = table.get("rows")
    if not isinstance(rows, list):
        raise ValueError("spawn table rows must be an array")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ("asset_id", "loc_cm_x", "loc_cm_y", "loc_cm_z", "yaw", "piece_id")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            loc = row.get("loc_cm", [0, 0, 0])
            writer.writerow(
                {
                    "asset_id": row.get("asset_id", ""),
                    "loc_cm_x": loc[0],
                    "loc_cm_y": loc[1],
                    "loc_cm_z": loc[2],
                    "yaw": row.get("yaw", 0),
                    "piece_id": row.get("piece_id", ""),
                }
            )


def run_spawn_table(
    milestone: str,
    *,
    out_path: Optional[Path] = None,
    csv_path: Optional[Path] = None,
    write_csv: bool = False,
    auto_export: bool = True,
    root: Path = ROOT,
) -> JsonDict:
    """Load (optionally export) manifest, gate on validation, write spawn table."""
    if milestone not in VALID_MILESTONES:
        choices = ", ".join(sorted(VALID_MILESTONES))
        raise ValueError(f"unknown milestone {milestone!r}; expected one of: {choices}")

    manifest_path = manifest_out_path(milestone, root=root)
    if auto_export:
        ensure_manifest_exists(manifest_path)
    elif not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    manifest = load_manifest(manifest_path)

    from tools.ue_manifest_dry_run import dry_run_manifest

    dry = dry_run_manifest(manifest)
    if not dry["ok"]:
        detail = "; ".join(dry["failures"][:3])
        raise ValueError(
            "manifest failed dry-run — spawn table refused"
            + (f" ({detail})" if detail else "")
        )

    table = build_spawn_table(
        manifest,
        milestone=milestone,
        source_manifest=manifest_path.relative_to(root).as_posix(),
    )

    json_out = out_path or spawn_table_out_path(milestone, root=root)
    write_spawn_table(table, json_out)

    if write_csv:
        csv_out = csv_path or spawn_table_csv_path(milestone, root=root)
        write_spawn_table_csv(table, csv_out)

    return table


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit UE ISM spawn table from a validated PAE manifest.",
    )
    parser.add_argument(
        "--milestone",
        "-m",
        default="m1",
        choices=sorted(VALID_MILESTONES),
        help="milestone label (default: m1)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="override JSON output (default: Saved/exports/{milestone}_spawn_table.json)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="also write Saved/exports/{milestone}_spawn_table.csv",
    )
    parser.add_argument(
        "--csv-out",
        default=None,
        help="override CSV output path (implies --csv)",
    )
    parser.add_argument(
        "--no-auto-export",
        action="store_true",
        help="do not auto-export manifest when missing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    milestone = args.milestone
    out_path = Path(args.out) if args.out else spawn_table_out_path(milestone)
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()

    write_csv = args.csv or args.csv_out is not None
    csv_path: Optional[Path] = None
    if args.csv_out:
        csv_path = Path(args.csv_out)
        if not csv_path.is_absolute():
            csv_path = (ROOT / csv_path).resolve()

    try:
        table = run_spawn_table(
            milestone,
            out_path=out_path,
            csv_path=csv_path,
            write_csv=write_csv,
            auto_export=not args.no_auto_export,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Wrote {out_path}")
    print(f"  milestone={milestone} schema={table['schema']} rows={table['row_count']}")
    if write_csv:
        csv_written = csv_path or spawn_table_csv_path(milestone)
        print(f"Wrote {csv_written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Emit a UE asset bind table from a validated PAE manifest or spawn table.

Maps ``asset_id`` values to suggested Unreal soft object paths under
``/Game/RE/PAE/...`` so the RE project can wire static meshes without
recomputing placement.

Usage::

    python tools/ue_asset_bind_table.py --milestone m1
    # → Saved/exports/m1_asset_bind.json

Refuses when ``validation.ok`` is false or the manifest fails dry-run checks.
Auto-exports the milestone manifest when missing (same as spawn table).
"""

from __future__ import annotations

import argparse
import json
import re
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
from tools.ue_manifest_dry_run import (  # noqa: E402
    ensure_manifest_exists,
    load_manifest,
)
from tools.ue_spawn_table import (  # noqa: E402
    SPAWN_TABLE_SCHEMA,
    spawn_table_out_path,
)

ASSET_BIND_SCHEMA = "pae.asset_bind/1"
DEFAULT_COLLISION_PROFILE = "BlockAll"
CONTENT_ROOT = "/Game/RE/PAE"

JsonDict = Dict[str, Any]


def asset_bind_out_path(milestone: str, root: Path = ROOT) -> Path:
    """Default on-disk path for a milestone asset bind table."""
    return root / "Saved" / "exports" / f"{milestone}_asset_bind.json"


def _milestone_content_segment(milestone: str) -> str:
    """Folder segment for UE content paths (``m4_l`` → ``M4_L``)."""
    return milestone.upper()


def _asset_id_to_sm_name(asset_id: str) -> str:
    """Convert PAE asset_id to a static-mesh asset name."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", asset_id.strip())
    if not safe:
        raise ValueError("asset_id must be a non-empty string")
    return f"SM_{safe}"


def suggested_content_path(asset_id: str, milestone: str) -> str:
    """Suggested UE soft object path for *asset_id* at *milestone*."""
    segment = _milestone_content_segment(milestone)
    sm_name = _asset_id_to_sm_name(asset_id)
    return f"{CONTENT_ROOT}/{segment}/{sm_name}.{sm_name}"


def _collision_profile_for(asset_id: str, manifest: Mapping[str, Any]) -> str:
    collision = manifest.get("collision")
    if isinstance(collision, list):
        for row in collision:
            if not isinstance(row, Mapping):
                continue
            if row.get("asset_id") == asset_id:
                preset = row.get("ue_collision_preset")
                if isinstance(preset, str) and preset:
                    return preset
                profile = row.get("profile")
                if isinstance(profile, str) and profile:
                    return profile
    return DEFAULT_COLLISION_PROFILE


def collect_asset_ids_from_manifest(manifest: Mapping[str, Any]) -> List[str]:
    """Unique asset ids from ``assets[]``, falling back to ``placements[]``."""
    seen: MutableMapping[str, None] = {}
    assets = manifest.get("assets")
    if isinstance(assets, list):
        for entry in assets:
            if not isinstance(entry, Mapping):
                continue
            asset_id = entry.get("id")
            if isinstance(asset_id, str) and asset_id:
                seen[asset_id] = None
    if not seen:
        placements = manifest.get("placements")
        if not isinstance(placements, list):
            raise ValueError("manifest must include assets[] or placements[]")
        for placement in placements:
            if not isinstance(placement, Mapping):
                continue
            asset_id = placement.get("asset_id")
            if isinstance(asset_id, str) and asset_id:
                seen[asset_id] = None
    if not seen:
        raise ValueError("manifest has no asset ids to bind")
    return sorted(seen)


def collect_asset_ids_from_spawn_table(table: Mapping[str, Any]) -> List[str]:
    """Unique asset ids from spawn-table ``rows[]``."""
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("spawn table rows must be a non-empty array")
    seen: MutableMapping[str, None] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        asset_id = row.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            seen[asset_id] = None
    if not seen:
        raise ValueError("spawn table has no asset ids to bind")
    return sorted(seen)


def manifest_to_bindings(
    manifest: Mapping[str, Any],
    *,
    milestone: str,
) -> List[JsonDict]:
    """Build bind rows for every unique asset in *manifest*."""
    bindings: List[JsonDict] = []
    for asset_id in collect_asset_ids_from_manifest(manifest):
        path = suggested_content_path(asset_id, milestone)
        bindings.append(
            {
                "asset_id": asset_id,
                "suggested_content_path": path,
                "lod0": path,
                "collision_profile": _collision_profile_for(asset_id, manifest),
            }
        )
    return bindings


def spawn_table_to_bindings(
    table: Mapping[str, Any],
    *,
    milestone: str,
    manifest: Optional[Mapping[str, Any]] = None,
) -> List[JsonDict]:
    """Build bind rows from spawn-table asset ids (collision from manifest when given)."""
    manifest = manifest or {}
    bindings: List[JsonDict] = []
    for asset_id in collect_asset_ids_from_spawn_table(table):
        path = suggested_content_path(asset_id, milestone)
        bindings.append(
            {
                "asset_id": asset_id,
                "suggested_content_path": path,
                "lod0": path,
                "collision_profile": _collision_profile_for(asset_id, manifest),
            }
        )
    return bindings


def build_asset_bind_table(
    manifest: Mapping[str, Any],
    *,
    milestone: str,
    source_manifest: Union[str, Path],
    source_spawn_table: Optional[Union[str, Path]] = None,
    spawn_table: Optional[Mapping[str, Any]] = None,
) -> JsonDict:
    """Build the asset-bind document from manifest and/or spawn table."""
    validation = manifest.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("manifest validation must be an object")
    if validation.get("ok") is not True:
        raise ValueError("validation.ok must be true — asset bind table refused")

    if spawn_table is not None:
        bindings = spawn_table_to_bindings(
            spawn_table,
            milestone=milestone,
            manifest=manifest,
        )
    else:
        bindings = manifest_to_bindings(manifest, milestone=milestone)

    doc: JsonDict = {
        "schema": ASSET_BIND_SCHEMA,
        "milestone": milestone,
        "source_manifest": str(source_manifest).replace("\\", "/"),
        "bind_count": len(bindings),
        "bindings": bindings,
    }
    if source_spawn_table is not None:
        doc["source_spawn_table"] = str(source_spawn_table).replace("\\", "/")
    return doc


def write_asset_bind_table(table: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(table), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_spawn_table(path: Path) -> JsonDict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"spawn table must be a JSON object: {path}")
    if data.get("schema") != SPAWN_TABLE_SCHEMA:
        raise ValueError(
            f"unsupported spawn table schema: {data.get('schema')!r}; "
            f"expected {SPAWN_TABLE_SCHEMA!r}"
        )
    return data


def run_asset_bind_table(
    milestone: str,
    *,
    out_path: Optional[Path] = None,
    spawn_table_path: Optional[Path] = None,
    auto_export: bool = True,
    root: Path = ROOT,
) -> JsonDict:
    """Load manifest (and optional spawn table), gate, write asset bind JSON."""
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
            "manifest failed dry-run — asset bind table refused"
            + (f" ({detail})" if detail else "")
        )

    spawn_table: Optional[JsonDict] = None
    spawn_source: Optional[Path] = None
    if spawn_table_path is not None:
        if not spawn_table_path.is_file():
            raise FileNotFoundError(f"spawn table not found: {spawn_table_path}")
        spawn_table = _load_spawn_table(spawn_table_path)
        spawn_source = spawn_table_path
    else:
        default_spawn = spawn_table_out_path(milestone, root=root)
        if default_spawn.is_file():
            spawn_table = _load_spawn_table(default_spawn)
            spawn_source = default_spawn.relative_to(root)

    table = build_asset_bind_table(
        manifest,
        milestone=milestone,
        source_manifest=manifest_path.relative_to(root).as_posix(),
        source_spawn_table=spawn_source,
        spawn_table=spawn_table,
    )

    json_out = out_path or asset_bind_out_path(milestone, root=root)
    write_asset_bind_table(table, json_out)
    return table


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit UE asset bind table (asset_id → content path stubs).",
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
        help="override JSON output (default: Saved/exports/{milestone}_asset_bind.json)",
    )
    parser.add_argument(
        "--spawn-table",
        default=None,
        help="optional spawn table JSON (default: use Saved/exports/{milestone}_spawn_table.json when present)",
    )
    parser.add_argument(
        "--no-auto-export",
        action="store_true",
        help="do not auto-export manifest when missing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    milestone = args.milestone
    out_path = Path(args.out) if args.out else asset_bind_out_path(milestone)
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()

    spawn_table_path: Optional[Path] = None
    if args.spawn_table:
        spawn_table_path = Path(args.spawn_table)
        if not spawn_table_path.is_absolute():
            spawn_table_path = (ROOT / spawn_table_path).resolve()

    try:
        table = run_asset_bind_table(
            milestone,
            out_path=out_path,
            spawn_table_path=spawn_table_path,
            auto_export=not args.no_auto_export,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Wrote {out_path}")
    print(
        f"  milestone={milestone} schema={table['schema']} "
        f"bindings={table['bind_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

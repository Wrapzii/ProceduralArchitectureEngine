"""UE manifest export (§8.2) — schema ``pae.manifest/1``.

Dims always come from ``pae.contract`` (never hard-coded). Export refuses when
validation reports critical defects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, placement_origin_cm
from pae.export.gate import ExportRefused, ensure_exportable
from pae.report import Failure, Report

SCHEMA = "pae.manifest/1"
ORIGIN_CONVENTION = "min_corner"

PathLike = Union[str, Path]


def _failure_dict(f: Failure) -> Dict[str, Any]:
    return {
        "check": f.check,
        "message": f.message,
        "world_xyz": list(f.world_xyz) if f.world_xyz is not None else None,
        "piece_id": f.piece_id,
        "critical": f.critical,
    }


def _validation_block(report: Report) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    for f in report.failures:
        bucket = checks.setdefault(
            f.check,
            {"ok": True, "failures": []},
        )
        bucket["failures"].append(_failure_dict(f))
        if f.critical:
            bucket["ok"] = False
    return {
        "ok": report.ok,
        "critical_count": len(report.critical),
        "warning_count": len(report.warnings),
        "checks": checks,
    }


def placement_loc_cm(p: SolidPlacement) -> Tuple[float, float, float]:
    """World origin (min corner) for a placement — contract dims only."""
    return placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)


def build_manifest(
    assembly: Assembly,
    report: Report,
    *,
    assets: Optional[Sequence[Mapping[str, Any]]] = None,
    asset_fbx: Optional[Mapping[str, str]] = None,
    collision: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build an in-memory ``pae.manifest/1`` dict (does not write disk)."""
    fbx_map = dict(asset_fbx or {})
    if assets is None:
        seen: Dict[str, None] = {}
        asset_rows: List[Dict[str, Any]] = []
        for p in assembly.placements:
            if p.asset_id in seen:
                continue
            seen[p.asset_id] = None
            asset_rows.append(
                {
                    "id": p.asset_id,
                    "fbx": fbx_map.get(p.asset_id, ""),
                    "lod": {},
                }
            )
    else:
        asset_rows = [dict(a) for a in assets]

    placements: List[Dict[str, Any]] = []
    for p in assembly.placements:
        lx, ly, lz = placement_loc_cm(p)
        placements.append(
            {
                "asset_id": p.asset_id,
                "piece_id": p.piece_id,
                "loc_cm": [lx, ly, lz],
                "yaw": p.yaw,
                "cell": [p.cell[0], p.cell[1]],
                "level": p.level,
            }
        )

    return {
        "schema": SCHEMA,
        "module_cm": MODULE_CM,
        "storey_cm": STOREY_CM,
        "origin_convention": ORIGIN_CONVENTION,
        "assets": asset_rows,
        "placements": placements,
        "collision": list(collision) if collision is not None else [],
        "validation": _validation_block(report),
    }


def export_manifest(
    assembly: Assembly,
    path: PathLike,
    *,
    report: Optional[Report] = None,
    assets: Optional[Sequence[Mapping[str, Any]]] = None,
    asset_fbx: Optional[Mapping[str, str]] = None,
    collision: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Report]:
    """Validate, then write manifest JSON. Raises :class:`ExportRefused` on fail.

    On refusal nothing is written to *path*.
    """
    out = Path(path)
    report = ensure_exportable(assembly, report)
    data = build_manifest(
        assembly,
        report,
        assets=assets,
        asset_fbx=asset_fbx,
        collision=collision,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data, report


__all__ = [
    "SCHEMA",
    "ORIGIN_CONVENTION",
    "ExportRefused",
    "build_manifest",
    "export_manifest",
    "placement_loc_cm",
]

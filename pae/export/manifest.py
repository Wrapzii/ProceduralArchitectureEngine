"""UE manifest export (§8.2) — schema ``pae.manifest/1``.

Dims always come from ``pae.contract`` (never hard-coded). Export refuses when
validation reports critical defects.

UE consumes this file with **zero placement logic** — spawn instanced actors at
``loc_cm`` + ``yaw`` only. See ``Docs/UE_MANIFEST_CONSUMER.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from pae.assembly_types import Assembly, SolidPlacement
from pae.anchors import anchor_kind_from_tags, anchor_loc_cm
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    placement_origin_cm,
)
from pae.export.gate import ExportRefused, ensure_exportable
from pae.report import Failure, Report

SCHEMA = "pae.manifest/1"
ORIGIN_CONVENTION = "min_corner"
LOD_LEVEL_KEYS = ("0", "1", "2")

PathLike = Union[str, Path]


def contract_block() -> Dict[str, float]:
    """Contract dimensions embedded in every manifest (single source: ``pae.contract``)."""
    return {
        "module_cm": MODULE_CM,
        "storey_cm": STOREY_CM,
        "wall_t_cm": WALL_T_CM,
        "floor_t_cm": FLOOR_T_CM,
    }


def lod_placeholder() -> Dict[str, str]:
    """Per-asset LOD slot map — empty paths until UE binds static meshes."""
    return {key: "" for key in LOD_LEVEL_KEYS}


def collision_stub(asset_id: str) -> Dict[str, Any]:
    """Collision placeholder for one asset — UE consumer fills mesh / preset."""
    if asset_id.startswith("light_anchor"):
        # Position-only markers — UE spawns lights; no mesh collision.
        return {
            "asset_id": asset_id,
            "profile": "none",
            "ue_collision_preset": "NoCollision",
            "simple_bounds": "none",
            "note": "light_anchor marker — spawn UE light at loc_cm; no collision",
        }
    return {
        "asset_id": asset_id,
        "profile": "mesh_complex",
        "ue_collision_preset": "BlockAll",
        "simple_bounds": "measured_from_mesh",
        "note": "stub — assign SM collision in UE; PAE does not export physics meshes",
    }


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
        "failures": [_failure_dict(f) for f in report.failures],
        "checks": checks,
    }


def _default_assets(
    assembly: Assembly,
    fbx_map: Mapping[str, str],
) -> List[Dict[str, Any]]:
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
                "lod": lod_placeholder(),
            }
        )
    asset_rows.sort(key=lambda row: row["id"])
    return asset_rows


def _default_collision(assembly: Assembly) -> List[Dict[str, Any]]:
    seen: Dict[str, None] = {}
    stubs: List[Dict[str, Any]] = []
    for p in assembly.placements:
        if p.asset_id in seen:
            continue
        seen[p.asset_id] = None
        stubs.append(collision_stub(p.asset_id))
    stubs.sort(key=lambda row: row["asset_id"])
    return stubs


def placement_loc_cm(p: SolidPlacement) -> Tuple[float, float, float]:
    """World origin (min corner) for a placement — contract dims only."""
    return placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)


def _light_anchors_block(assembly: Assembly) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in assembly.placements:
        if p.kind != "light_anchor":
            continue
        kind_hint = anchor_kind_from_tags(p.tags) or "unknown"
        lx, ly, lz = anchor_loc_cm(p)
        rows.append(
            {
                "piece_id": p.piece_id,
                "asset_id": p.asset_id,
                "loc_cm": [lx, ly, lz],
                "yaw": p.yaw,
                "anchor_kind": kind_hint,
                "level": p.level,
                "intensity_hint": "medium",
            }
        )
    rows.sort(key=lambda row: row["piece_id"])
    return rows


def build_manifest(
    assembly: Assembly,
    report: Report,
    *,
    assets: Optional[Sequence[Mapping[str, Any]]] = None,
    asset_fbx: Optional[Mapping[str, str]] = None,
    collision: Optional[Sequence[Mapping[str, Any]]] = None,
    terrain_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an in-memory ``pae.manifest/1`` dict (does not write disk)."""
    fbx_map = dict(asset_fbx or {})
    if assets is None:
        asset_rows = _default_assets(assembly, fbx_map)
    else:
        asset_rows = [dict(a) for a in assets]

    if collision is None:
        collision_rows = _default_collision(assembly)
    else:
        collision_rows = [dict(c) for c in collision]

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

    contract = contract_block()
    manifest: Dict[str, Any] = {
        "schema": SCHEMA,
        "module_cm": contract["module_cm"],
        "storey_cm": contract["storey_cm"],
        "origin_convention": ORIGIN_CONVENTION,
        "contract": contract,
        "assets": asset_rows,
        "placements": placements,
        "light_anchors": _light_anchors_block(assembly),
        "collision": collision_rows,
        "validation": _validation_block(report),
    }
    if terrain_mode is not None:
        manifest["terrain_bind"] = {"mode": terrain_mode, "source": "heightmap"}
    return manifest


def export_manifest(
    assembly: Assembly,
    path: PathLike,
    *,
    report: Optional[Report] = None,
    assets: Optional[Sequence[Mapping[str, Any]]] = None,
    asset_fbx: Optional[Mapping[str, str]] = None,
    collision: Optional[Sequence[Mapping[str, Any]]] = None,
    terrain_mode: Optional[str] = None,
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
        terrain_mode=terrain_mode,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data, report


__all__ = [
    "SCHEMA",
    "ORIGIN_CONVENTION",
    "LOD_LEVEL_KEYS",
    "ExportRefused",
    "build_manifest",
    "collision_stub",
    "contract_block",
    "export_manifest",
    "lod_placeholder",
    "placement_loc_cm",
]

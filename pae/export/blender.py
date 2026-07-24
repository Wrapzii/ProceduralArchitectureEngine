"""Blender ``.blend`` export with linked duplicates (§8.1) — WP-6.

Pure planning works without ``bpy`` (unit tests). Real Blender I/O is behind an
import guard.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pae.assembly_types import Assembly
from pae.export.gate import ExportRefused, ensure_exportable
from pae.export.manifest import placement_loc_cm
from pae.report import Report

PathLike = Union[str, Path]


@dataclass(frozen=True)
class LinkedInstance:
    """One linked-duplicate instance to spawn from a shared mesh datablock."""

    piece_id: str
    asset_id: str
    collection: str
    loc_cm: Tuple[float, float, float]
    yaw: int
    level: int


@dataclass
class LinkedDuplicatePlan:
    """Collections-per-storey + instance list + PAE_meta payload."""

    collections: List[str] = field(default_factory=list)
    instances: List[LinkedInstance] = field(default_factory=list)
    assets_unique: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class BlenderRequired(RuntimeError):
    """Raised when a binary ``.blend`` write is requested without ``bpy``."""


def _has_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def plan_linked_duplicates(
    assembly: Assembly,
    report: Report,
    *,
    spec_hash: Optional[str] = None,
) -> LinkedDuplicatePlan:
    """Build a linked-duplicate plan (no Blender required)."""
    levels = sorted({p.level for p in assembly.placements})
    collections = [f"PAE_L{level}" for level in levels]
    # System buckets (optional grouping)
    for kind in ("wall", "floor", "ground", "roof", "stair", "prop"):
        if any(p.kind == kind for p in assembly.placements):
            collections.append(f"PAE_{kind}")

    seen_assets: Dict[str, None] = {}
    assets_unique: List[str] = []
    instances: List[LinkedInstance] = []
    for p in assembly.placements:
        if p.asset_id not in seen_assets:
            seen_assets[p.asset_id] = None
            assets_unique.append(p.asset_id)
        instances.append(
            LinkedInstance(
                piece_id=p.piece_id,
                asset_id=p.asset_id,
                collection=f"PAE_L{p.level}",
                loc_cm=placement_loc_cm(p),
                yaw=p.yaw,
                level=p.level,
            )
        )

    meta: Dict[str, Any] = {
        "PAE_meta": {
            "spec_hash": spec_hash,
            "validation_ok": report.ok,
            "critical_count": len(report.critical),
            "warning_count": len(report.warnings),
            "placement_count": len(assembly.placements),
        }
    }
    return LinkedDuplicatePlan(
        collections=collections,
        instances=instances,
        assets_unique=assets_unique,
        meta=meta,
    )


def write_plan_json(plan: LinkedDuplicatePlan, path: PathLike) -> Path:
    """Serialize a linked-duplicate plan for headless / CI use."""
    out = Path(path)

    def _default(o: Any) -> Any:
        if isinstance(o, tuple):
            return list(o)
        raise TypeError(type(o))

    payload = {
        "format": "pae.blend_linked_plan/1",
        "collections": plan.collections,
        "assets_unique": plan.assets_unique,
        "instances": [asdict(i) for i in plan.instances],
        "meta": plan.meta,
        "note": "Linked-duplicate plan — binary .blend requires Blender (bpy).",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return out


def _export_blend_with_bpy(
    assembly: Assembly,
    plan: LinkedDuplicatePlan,
    path: Path,
) -> Path:
    """Real Blender path — guarded; creates empty scene + writes .blend stub.

    Full linked-duplicate mesh library loading is left for the add-on operator;
    this proves the bpy branch is reachable when Blender hosts the module.
    """
    import bpy

    # Clear default scene content carefully (Blender 3+/4+).
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for col_name in plan.collections:
        if col_name not in bpy.data.collections:
            bpy.data.collections.new(col_name)
            bpy.context.scene.collection.children.link(bpy.data.collections[col_name])

    # Store PAE_meta on the scene.
    scene = bpy.context.scene
    scene["PAE_meta"] = json.dumps(plan.meta.get("PAE_meta", {}))

    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path.resolve()))
    return path


def export_blend(
    assembly: Assembly,
    path: PathLike,
    *,
    report: Optional[Report] = None,
    spec_hash: Optional[str] = None,
    plan_path: Optional[PathLike] = None,
    allow_plan_without_blender: bool = True,
) -> Tuple[LinkedDuplicatePlan, Report, Dict[str, Any]]:
    """Plan (+ optionally write) a linked-duplicate Blender export.

    Always validates first. On :class:`ExportRefused` nothing is written.

    Without ``bpy``, writes a ``.blend.plan.json`` (or *plan_path*) and does
    **not** create a binary ``.blend``.
    """
    out = Path(path)
    report = ensure_exportable(assembly, report)
    plan = plan_linked_duplicates(assembly, report, spec_hash=spec_hash)

    meta: Dict[str, Any] = {
        "blender_available": _has_bpy(),
        "instance_count": len(plan.instances),
    }

    if _has_bpy():
        written = _export_blend_with_bpy(assembly, plan, out)
        meta["blend"] = str(written)
        # Also keep a plan sidecar for tooling.
        sidecar = Path(plan_path) if plan_path else out.with_suffix(".blend.plan.json")
        write_plan_json(plan, sidecar)
        meta["plan"] = str(sidecar)
        return plan, report, meta

    if not allow_plan_without_blender:
        raise BlenderRequired(
            "binary .blend export requires Blender (bpy); plan fallback disabled"
        )

    sidecar = Path(plan_path) if plan_path else out.with_suffix(".blend.plan.json")
    if out.suffix.lower() == ".blend" and out.exists():
        # Never leave a stale binary when we refuse to write one.
        out.unlink()
    write_plan_json(plan, sidecar)
    meta["blend"] = None
    meta["plan"] = str(sidecar)
    meta["note"] = "Blender unavailable — wrote linked-duplicate plan; refused .blend."
    return plan, report, meta


__all__ = [
    "BlenderRequired",
    "ExportRefused",
    "LinkedDuplicatePlan",
    "LinkedInstance",
    "export_blend",
    "plan_linked_duplicates",
    "write_plan_json",
]

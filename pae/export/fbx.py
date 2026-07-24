"""FBX export — WP-6.

Without Blender (``bpy``), writes a clear **placement list** sidecar and refuses
to emit a binary ``.fbx``. With ``bpy`` available the real FBX writer can be
wired behind the same validation gate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pae.assembly_types import Assembly
from pae.export.gate import ExportRefused, ensure_exportable
from pae.export.manifest import placement_loc_cm
from pae.report import Report

PathLike = Union[str, Path]


@dataclass(frozen=True)
class FbxPlacementRow:
    """One instance that would become an FBX transform / spawn."""

    asset_id: str
    piece_id: str
    loc_cm: Tuple[float, float, float]
    yaw: int
    cell: Tuple[int, int]
    level: int


class BlenderRequired(RuntimeError):
    """Raised when a binary FBX write is requested without ``bpy``."""


def _has_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def build_placement_list(assembly: Assembly) -> List[FbxPlacementRow]:
    """Pure path: placement rows for FBX / UE spawn (no Blender required)."""
    rows: List[FbxPlacementRow] = []
    for p in assembly.placements:
        rows.append(
            FbxPlacementRow(
                asset_id=p.asset_id,
                piece_id=p.piece_id,
                loc_cm=placement_loc_cm(p),
                yaw=p.yaw,
                cell=p.cell,
                level=p.level,
            )
        )
    return rows


def write_placement_list(
    assembly: Assembly,
    path: PathLike,
) -> Path:
    """Write a JSON placement list (not FBX)."""
    out = Path(path)
    rows = build_placement_list(assembly)
    payload = {
        "format": "pae.fbx_placement_list/1",
        "note": "Placement list only — binary FBX requires Blender (bpy).",
        "placements": [asdict(r) for r in rows],
    }
    # JSON cannot encode tuples; asdict keeps tuples — coerce via dumps default.
    def _default(o: Any) -> Any:
        if isinstance(o, tuple):
            return list(o)
        raise TypeError(type(o))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return out


def export_fbx(
    assembly: Assembly,
    path: PathLike,
    *,
    report: Optional[Report] = None,
    placement_list_path: Optional[PathLike] = None,
    allow_placement_list_without_blender: bool = True,
) -> Tuple[Optional[Path], Report, Dict[str, Any]]:
    """Export FBX when Blender is present; otherwise write a placement list.

    Always runs the validation gate first. On :class:`ExportRefused` nothing is
    written.

    Returns ``(fbx_path_or_None, report, meta)``.
    """
    out = Path(path)
    report = ensure_exportable(assembly, report)

    meta: Dict[str, Any] = {
        "blender_available": _has_bpy(),
        "placement_count": len(assembly.placements),
    }

    if _has_bpy():
        # Real FBX path is reserved for an in-Blender operator; structure is
        # ready — call site would invoke bpy.ops.export_scene.fbx after
        # linked-duplicate assembly. For headless CI we still emit the list.
        list_path = Path(placement_list_path) if placement_list_path else out.with_suffix(
            ".placements.json"
        )
        write_placement_list(assembly, list_path)
        meta["placement_list"] = str(list_path)
        meta["fbx"] = str(out)
        meta["note"] = (
            "bpy present — placement list written; binary FBX operator not yet invoked."
        )
        return None, report, meta

    if not allow_placement_list_without_blender:
        raise BlenderRequired(
            "binary FBX export requires Blender (bpy); placement-list fallback disabled"
        )

    list_path = Path(placement_list_path) if placement_list_path else out.with_suffix(
        ".placements.json"
    )
    # Never write a fake .fbx binary.
    if out.exists():
        out.unlink()
    write_placement_list(assembly, list_path)
    meta["placement_list"] = str(list_path)
    meta["fbx"] = None
    meta["note"] = "Blender unavailable — wrote placement list; refused binary .fbx."
    return None, report, meta


__all__ = [
    "BlenderRequired",
    "ExportRefused",
    "FbxPlacementRow",
    "build_placement_list",
    "export_fbx",
    "write_placement_list",
]

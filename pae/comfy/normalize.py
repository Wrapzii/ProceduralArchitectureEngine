"""Pure-Python normalisation for Comfy GLB metadata (§9.2).

No Blender / ComfyUI required. Real mesh ops (decimate, UV) are optional
Blender hooks; this module records the contract transforms from measured AABB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from pae.assets.import_ import (
    MeasuredAABB,
    min_corner_origin_offset,
    normalize_to_min_corner,
)
from pae.contract import MODULE_CM


# LOD triangle budget (not a grid dimension).
DEFAULT_LOD_TRI_BUDGET = 12_000


@dataclass(frozen=True)
class GlbMetadata:
    """Fake / real GLB sidecar for pure-Python tests and offline ingest.

    Declared sizes are never trusted — *measured* is authoritative.
    """

    path: str
    measured: MeasuredAABB
    # Optional prompt scale hint in metres (converted for notes only).
    prompt_height_m: Optional[float] = None
    forward_axis: str = "+Y"
    up_axis: str = "+Z"
    texture_path: Optional[str] = None
    tri_count: Optional[int] = None


@dataclass(frozen=True)
class NormalizeResult:
    """Result of the normalise stage (§9.2)."""

    origin_offset_cm: Tuple[float, float, float]
    size_cm: Tuple[float, float, float]
    min_corner: Tuple[float, float, float]
    max_corner: Tuple[float, float, float]
    forward_axis: str
    up_axis: str
    lod_tri_budget: int
    needs_uv: bool
    notes: Tuple[str, ...] = field(default_factory=tuple)


def _cm_from_metres(metres: float) -> float:
    return metres * 100.0


def normalize_measured(
    measured: MeasuredAABB,
    *,
    forward_axis: str = "+Y",
    up_axis: str = "+Z",
    prompt_height_m: Optional[float] = None,
    tri_count: Optional[int] = None,
    lod_tri_budget: int = DEFAULT_LOD_TRI_BUDGET,
) -> NormalizeResult:
    """Apply §9.2 contract: origin → min corner, record +Y forward, LOD budget."""
    notes: list[str] = []
    offset = min_corner_origin_offset(measured.min_corner)
    new_min, new_max = normalize_to_min_corner(measured.min_corner, measured.max_corner)
    size = (
        new_max[0] - new_min[0],
        new_max[1] - new_min[1],
        new_max[2] - new_min[2],
    )

    if forward_axis.upper() != "+Y":
        notes.append(
            f"reorient to +Y forward required (metadata forward_axis={forward_axis})"
        )
    else:
        notes.append("oriented +Y forward")

    if prompt_height_m is not None:
        hint_cm = _cm_from_metres(prompt_height_m)
        delta = abs(size[2] - hint_cm)
        # Soft note only — never trust prompt over measure.
        if delta > MODULE_CM * 0.25:
            notes.append(
                f"prompt height hint {_cm_from_metres(prompt_height_m):.1f} cm "
                f"differs from measured Z {size[2]:.1f} cm — measured wins"
            )
        else:
            notes.append("prompt height hint within loose tolerance of measured Z")

    needs_uv = True  # assume absent until Blender hook proves otherwise
    if tri_count is not None and tri_count > lod_tri_budget:
        notes.append(
            f"tri_count {tri_count} exceeds LOD budget {lod_tri_budget} — decimate required"
        )

    notes.append(f"origin shifted by {offset}")

    return NormalizeResult(
        origin_offset_cm=offset,
        size_cm=size,
        min_corner=new_min,
        max_corner=new_max,
        forward_axis="+Y",
        up_axis=up_axis if up_axis.upper() == "+Z" else "+Z",
        lod_tri_budget=lod_tri_budget,
        needs_uv=needs_uv,
        notes=tuple(notes),
    )


def normalize_glb_metadata(
    meta: GlbMetadata,
    *,
    lod_tri_budget: int = DEFAULT_LOD_TRI_BUDGET,
) -> NormalizeResult:
    """Normalise from GlbMetadata (tests / offline — no Comfy or Blender)."""
    return normalize_measured(
        meta.measured,
        forward_axis=meta.forward_axis,
        up_axis=meta.up_axis,
        prompt_height_m=meta.prompt_height_m,
        tri_count=meta.tri_count,
        lod_tri_budget=lod_tri_budget,
    )

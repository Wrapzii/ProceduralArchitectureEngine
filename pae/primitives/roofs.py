"""Pitched roof bay **with gable infill**.

Prior failure mode: walls stopped at the eaves and nothing filled the gable
triangle → 8 m holes. This piece includes the triangular infill in its AABB.
"""

from __future__ import annotations

from typing import Optional

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

# Default pitch rise/run from gothic_academy style (not a grid dimension).
DEFAULT_ROOF_PITCH = 1.05


def roof_rise_cm(pitch: float = DEFAULT_ROOF_PITCH, span_cm: float = MODULE_CM) -> float:
    """Rise for a gable spanning ``span_cm`` (ridge at mid-span)."""
    return pitch * (span_cm * 0.5)


def roof_pitched_gable(
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
) -> PrimitiveDescriptor:
    """One-module bay: depth X, run Y, gable faces on ±Y with solid infill."""
    rise = roof_rise_cm(pitch, MODULE_CM)
    # Height includes deck thickness sitting on the eaves line.
    height = rise + FLOOR_T_CM
    tag = frozenset({module_tag(), "roof"})
    sockets = (
        SocketDesc(
            name="eave_x0",
            pos_cm=(0.0, MODULE_CM * 0.5, 0.0),
            normal=(-1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_x1",
            pos_cm=(MODULE_CM, MODULE_CM * 0.5, 0.0),
            normal=(1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="gable_y0",
            pos_cm=(MODULE_CM * 0.5, 0.0, rise * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="roof_gable",
            tags=tag,
        ),
        SocketDesc(
            name="gable_y1",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM, rise * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="roof_gable",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_pitched_gable",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=height / STOREY_CM,  # informational only
        size_cm=(MODULE_CM, MODULE_CM, height),
        sockets=sockets,
        tags=frozenset({"roof", "pitched", "gable", module_tag()}),
        origin="min_corner",
        notes=(
            f"Pitch={pitch}: rise={rise:.1f} cm over half-span. "
            "Gable triangles are part of this piece (no open gable hole)."
        ),
    )


def all_roofs() -> tuple:
    return (roof_pitched_gable(),)


def build_roof_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Prism proxy of the roof AABB; gable planes implied by the solid.

    A dedicated gable-fan mesh can replace this proxy without changing the
    descriptor footprint.
    """
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    return bpy_util.box_mesh(name or desc.id, desc.size_cm, origin_at_min_corner=True)

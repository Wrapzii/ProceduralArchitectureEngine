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


def roof_flat_span_size_cm(modules_x: int, modules_y: int) -> tuple[float, float, float]:
    """Axis-aligned flat roof slab spanning *modules_x* × *modules_y* bays."""
    if modules_x < 1 or modules_y < 1:
        raise ValueError(f"roof span must be ≥ 1×1 modules, got {modules_x}×{modules_y}")
    return (modules_x * MODULE_CM, modules_y * MODULE_CM, FLOOR_T_CM)


def roof_flat() -> PrimitiveDescriptor:
    """One-module flat roof deck (assemble scales XY via ``roof_flat_span_size_cm``)."""
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
            name="eave_y0",
            pos_cm=(MODULE_CM * 0.5, 0.0, 0.0),
            normal=(0.0, -1.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_y1",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM, 0.0),
            normal=(0.0, 1.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_flat",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=roof_flat_span_size_cm(1, 1),
        sockets=sockets,
        tags=frozenset({"roof", "flat", module_tag()}),
        origin="min_corner",
        notes="Deck thickness FLOOR_T; place top at level_z + STOREY (§6 flat roof).",
    )


def all_roofs() -> tuple:
    return (roof_pitched_gable(), roof_flat())


def build_roof_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Prism proxy of the roof AABB; gable planes implied by the solid.

    A dedicated gable-fan mesh can replace this proxy without changing the
    descriptor footprint.
    """
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    return bpy_util.box_mesh(name or desc.id, desc.size_cm, origin_at_min_corner=True)

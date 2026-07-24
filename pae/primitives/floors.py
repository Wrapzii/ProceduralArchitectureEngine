"""Floor slabs — solid and with stair/light-well hole."""

from __future__ import annotations

from typing import Optional

from pae.contract import FLOOR_T_CM, MODULE_CM
from pae.primitives.types import (
    ApertureDesc,
    PrimitiveDescriptor,
    SocketDesc,
    module_tag,
)

# Hole occupies the centre half-module (stair VOID cell).
_HOLE_FRAC = 0.5


def _edge_sockets() -> tuple:
    tag = frozenset({module_tag(), "floor"})
    mid = MODULE_CM * 0.5
    t = FLOOR_T_CM
    return (
        SocketDesc("edge_x0", (0.0, mid, t), (-1.0, 0.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_x1", (MODULE_CM, mid, t), (1.0, 0.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_y0", (mid, 0.0, t), (0.0, -1.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_y1", (mid, MODULE_CM, t), (0.0, 1.0, 0.0), "floor_edge", tag),
    )


def floor_slab() -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id="floor",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=_edge_sockets(),
        tags=frozenset({"floor", "slab", module_tag()}),
        origin="min_corner",
        notes="Place at level_z − FLOOR_T so top lands on the storey (§2.4).",
    )


def floor_with_hole() -> PrimitiveDescriptor:
    hole = MODULE_CM * _HOLE_FRAC
    margin = (MODULE_CM - hole) * 0.5
    pad_z = FLOOR_T_CM * 0.25
    return PrimitiveDescriptor(
        id="floor_hole",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=_edge_sockets(),
        tags=frozenset({"floor", "hole", "stairwell", module_tag()}),
        origin="min_corner",
        aperture=ApertureDesc(
            kind="hole",
            min_cm=(margin, margin, -pad_z),
            max_cm=(margin + hole, margin + hole, FLOOR_T_CM + pad_z),
        ),
        notes="Centre hole for VOID / stair top clearance.",
    )


def all_floors() -> tuple:
    return (floor_slab(), floor_with_hole())


def build_floor_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    core = bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)
    if desc.aperture is None:
        return core
    ap = desc.aperture
    cutter_size = (
        ap.max_cm[0] - ap.min_cm[0],
        ap.max_cm[1] - ap.min_cm[1],
        ap.max_cm[2] - ap.min_cm[2],
    )
    cutter = bpy_util.box_mesh(
        f"{obj_name}_cut",
        cutter_size,
        origin_at_min_corner=True,
        location=ap.min_cm,
    )
    bpy_util.apply_boolean_difference(core, cutter)
    return core

"""Stairs — straight run (2 modules × 1 storey) and spiral quarter."""

from __future__ import annotations

from typing import Optional

from pae.contract import MODULE_CM, STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

_SPIRAL_RISE_STOREYS = 0.25  # STOREY/4 per quarter (§5.3)


def stair_straight() -> PrimitiveDescriptor:
    """Spans exactly 2 modules, rises exactly 1 storey."""
    sx = 2.0 * MODULE_CM
    sy = MODULE_CM
    sz = STOREY_CM
    tag = frozenset({module_tag(), "stair"})
    sockets = (
        SocketDesc(
            name="bottom",
            pos_cm=(0.0, sy * 0.5, 0.0),
            normal=(-1.0, 0.0, 0.0),
            type="stair_bottom",
            tags=tag,
        ),
        SocketDesc(
            name="top",
            pos_cm=(sx, sy * 0.5, sz),
            normal=(1.0, 0.0, 0.0),
            type="stair_top",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="stair_straight",
        kind="stair",
        footprint_modules=(2, 1),
        height_storeys=1.0,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=frozenset({"stair", "straight", module_tag()}),
        origin="min_corner",
        notes="Run along +X; top requires VOID cell above.",
    )


def stair_spiral_quarter() -> PrimitiveDescriptor:
    """One 90° spiral quarter — four stack to one storey (§5.3).

    Authored about the circle centre (``rotates_about_center``).
    """
    rise = STOREY_CM * _SPIRAL_RISE_STOREYS
    # AABB of first-quadrant wedge with outer radius = MODULE: (MODULE, MODULE, rise)
    # but origin at centre → min at (0,0,0) for +X+Y quadrant outer box is not
    # centred; use centred convention: extents MODULE×MODULE with min (−0? ).
    # Spec: centred pieces — origin is rotation centre. Quarter lives in +X+Y,
    # so aabb_min = (0, 0, 0), size = (MODULE, MODULE, rise). Footprint 1×1.
    tag = frozenset({module_tag(), "stair", "spiral"})
    sockets = (
        SocketDesc(
            name="bottom",
            pos_cm=(MODULE_CM * 0.5, 0.0, 0.0),
            normal=(0.0, -1.0, 0.0),
            type="stair_bottom",
            tags=tag,
        ),
        SocketDesc(
            name="top",
            pos_cm=(0.0, MODULE_CM * 0.5, rise),
            normal=(-1.0, 0.0, 0.0),
            type="stair_top",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="stair_spiral_quarter",
        kind="stair",
        footprint_modules=(1, 1),
        height_storeys=_SPIRAL_RISE_STOREYS,
        size_cm=(MODULE_CM, MODULE_CM, rise),
        sockets=sockets,
        tags=frozenset({"stair", "spiral", "quarter", module_tag()}),
        origin="center",
        rotates_about_center=True,
        # First-quadrant sector relative to centre: min at (0,0,0).
        aabb_min_cm=(0.0, 0.0, 0.0),
        notes="Four quarters per storey; place all at the same cell centre.",
    )


def all_stairs() -> tuple:
    return (stair_straight(), stair_spiral_quarter())


def build_stair_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Simple solid proxy AABB; tread detailing is a later polish pass."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    if desc.rotates_about_center:
        # Spiral quarter: annular sector proxy (inner radius half of outer).
        outer = MODULE_CM
        inner = MODULE_CM * 0.35
        z0, z1 = 0.0, desc.size_cm[2]
        verts, faces = bpy_util.annulus_quarter_verts(outer, inner, z0, z1)
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj)
        return obj
    return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)

"""Tower kit — arc quarter, crown, junction, and cap.

Arc quarters are authored about the circle centre. Four quarters share one cell
(``rotates_about_center``); do **not** offset them to four cells (§2.2).
"""

from __future__ import annotations

from typing import Optional

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import ApertureDesc, PrimitiveDescriptor, SocketDesc, module_tag

# Outer radius = one MODULE so a full tower diameter is 2 modules.
_CROWN_H_FRAC = 0.20  # of STOREY
_CAP_H_FRAC = 0.85  # of STOREY — steep cone
_JUNCTION_H_FRAC = 0.06  # of STOREY — corbel / string ring under the crown
# Helical drum window: centred in the quarter, above floor, below plate.
_ARC_WINDOW_W_FRAC = 0.28  # of MODULE (tangential run of the opening AABB)
_ARC_WINDOW_H_FRAC = 0.36  # of STOREY
_ARC_WINDOW_SILL_FRAC = 0.28  # of STOREY


def tower_arc_quarter() -> PrimitiveDescriptor:
    outer = MODULE_CM
    # AABB of first-quadrant annulus: (0,0,0) → (outer, outer, STOREY)
    tag = frozenset({module_tag(), "tower", "arc"})
    sockets = (
        SocketDesc(
            name="radial_a",
            pos_cm=(outer, 0.0, STOREY_CM * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
        SocketDesc(
            name="radial_b",
            pos_cm=(0.0, outer, STOREY_CM * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="tower_arc_quarter",
        kind="tower_arc",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(outer, outer, STOREY_CM),
        sockets=sockets,
        tags=frozenset({"tower", "arc", "quarter", module_tag()}),
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(0.0, 0.0, 0.0),
        notes=f"Inner radius = MODULE − WALL_T ({MODULE_CM - WALL_T_CM:.1f} cm).",
    )


def tower_arc_quarter_window() -> PrimitiveDescriptor:
    """Arc quarter with a rectangular aperture for helical / perimeter glazing.

    Same footprint as ``tower_arc_quarter`` so assemble can swap a quarter without
    shifting the drum. Mesh punch is optional (descriptor aperture is the contract).
    """
    base = tower_arc_quarter()
    outer = MODULE_CM
    # Opening AABB in the first-quadrant shell: mid-angle band through the wall.
    run0 = outer * (0.5 - _ARC_WINDOW_W_FRAC * 0.5)
    run1 = outer * (0.5 + _ARC_WINDOW_W_FRAC * 0.5)
    z0 = STOREY_CM * _ARC_WINDOW_SILL_FRAC
    z1 = z0 + STOREY_CM * _ARC_WINDOW_H_FRAC
    inner = MODULE_CM - WALL_T_CM
    return PrimitiveDescriptor(
        id="tower_arc_quarter_window",
        kind="tower_arc",
        footprint_modules=base.footprint_modules,
        height_storeys=base.height_storeys,
        size_cm=base.size_cm,
        sockets=base.sockets,
        tags=frozenset({"tower", "arc", "quarter", "window", module_tag()}),
        origin=base.origin,
        rotates_about_center=True,
        aabb_min_cm=base.aabb_min_cm,
        aperture=ApertureDesc(
            kind="window",
            min_cm=(inner, run0, z0),
            max_cm=(outer, run1, z1),
        ),
        notes="Windowed drum quarter — aperture for helical stair lighting (Phase 0.6 / 4.7).",
    )


def tower_junction() -> PrimitiveDescriptor:
    """Thin annular corbel ring — defined joint between drum top and crown/cap."""
    diam = 2.0 * MODULE_CM
    h = STOREY_CM * _JUNCTION_H_FRAC
    tag = frozenset({module_tag(), "tower", "junction"})
    sockets = (
        SocketDesc(
            name="bottom",
            pos_cm=(0.0, 0.0, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="tower_join",
            tags=tag,
        ),
        SocketDesc(
            name="top",
            pos_cm=(0.0, 0.0, h),
            normal=(0.0, 0.0, 1.0),
            type="tower_join",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="tower_junction",
        # Same measure family as crown (centred 2×MODULE annulus).
        kind="tower_crown",
        footprint_modules=(2, 2),
        height_storeys=_JUNCTION_H_FRAC,
        size_cm=(diam, diam, h),
        sockets=sockets,
        tags=frozenset({"tower", "junction", "corbel", module_tag()}),
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
        notes="Roof junction stub: drum → junction → crown → cap.",
    )


def tower_crown() -> PrimitiveDescriptor:
    """Full annular crown (assembled as one centred piece, diameter 2 modules)."""
    diam = 2.0 * MODULE_CM
    h = STOREY_CM * _CROWN_H_FRAC
    tag = frozenset({module_tag(), "tower", "crown"})
    sockets = (
        SocketDesc(
            name="bottom",
            pos_cm=(0.0, 0.0, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="tower_join",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="tower_crown",
        kind="tower_crown",
        footprint_modules=(2, 2),
        height_storeys=_CROWN_H_FRAC,
        size_cm=(diam, diam, h),
        sockets=sockets,
        tags=frozenset({"tower", "crown", module_tag()}),
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
        notes="Battlemented ring; sits on assembled drum.",
    )


def tower_cap() -> PrimitiveDescriptor:
    """Steep conical cap — footprint diameter 2 modules, centred."""
    diam = 2.0 * MODULE_CM
    h = STOREY_CM * _CAP_H_FRAC
    tag = frozenset({module_tag(), "tower", "cap"})
    sockets = (
        SocketDesc(
            name="bottom",
            pos_cm=(0.0, 0.0, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="tower_join",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="tower_cap",
        kind="tower_cap",
        footprint_modules=(2, 2),
        height_storeys=_CAP_H_FRAC,
        size_cm=(diam, diam, h),
        sockets=sockets,
        tags=frozenset({"tower", "cap", "cone", module_tag()}),
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
        notes="Cone steeple; style may swap to shallower pitch later.",
    )


def all_towers() -> tuple:
    return (
        tower_arc_quarter(),
        tower_arc_quarter_window(),
        tower_junction(),
        tower_crown(),
        tower_cap(),
    )


def build_tower_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    if desc.id in ("tower_arc_quarter", "tower_arc_quarter_window"):
        verts, faces = bpy_util.annulus_quarter_verts(
            outer,
            inner,
            0.0,
            STOREY_CM,
            segments_full=bpy_util.TOWER_ARC_SEGMENTS_FULL,
            cap_horizontal=False,
        )
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj, angle_deg=40.0)
        return obj
    if desc.id == "tower_junction":
        h = desc.size_cm[2]
        verts, faces = bpy_util.annulus_ring_verts(
            outer,
            inner,
            0.0,
            h,
            segments_full=bpy_util.TOWER_ARC_SEGMENTS_FULL,
        )
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj, angle_deg=40.0)
        return obj
    if desc.id == "tower_crown":
        h = desc.size_cm[2]
        verts, faces = bpy_util.annulus_battlement_ring_verts(
            outer,
            inner,
            0.0,
            h,
            segments_full=bpy_util.TOWER_ARC_SEGMENTS_FULL,
        )
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj, angle_deg=40.0)
        return obj
    if desc.id == "tower_cap":
        h = desc.size_cm[2]
        verts, faces = bpy_util.cone_verts(
            outer,
            0.0,
            h,
            segments_full=bpy_util.TOWER_ARC_SEGMENTS_FULL,
        )
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj, angle_deg=40.0)
        return obj
    raise ValueError(f"unknown tower primitive: {desc.id!r}")

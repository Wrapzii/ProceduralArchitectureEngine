"""Wall kit pieces — plain / window / arrowslit / door / arcade.

Wall occupies the low-X strip of its cell: size ``(WALL_T, MODULE, STOREY)``.
Arcade arch is cut **into** the module so the outer footprint still fills one bay.
"""

from __future__ import annotations

from typing import Optional

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import (
    ApertureDesc,
    PrimitiveDescriptor,
    SocketDesc,
    module_tag,
)

# Relative aperture layout (fractions of MODULE / STOREY — no raw contract literals).
_WINDOW_W = 0.35
_WINDOW_H = 0.40
_WINDOW_SILL = 0.28
_DOOR_W = 0.40
_DOOR_H = 0.72
_SLIT_W = 0.05
_SLIT_H = 0.45
_SLIT_SILL = 0.30
_ARCH_JAMB = 0.15  # fraction of MODULE each side
_ARCH_SPRING = 0.18  # fraction of STOREY — arch starts above plinth band


def _wall_sockets() -> tuple:
    tag = frozenset({module_tag(), "wall"})
    # Long axis = Y. Ends face −Y / +Y.
    return (
        SocketDesc(
            name="end_a",
            pos_cm=(WALL_T_CM * 0.5, 0.0, STOREY_CM * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(WALL_T_CM * 0.5, MODULE_CM, STOREY_CM * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
        SocketDesc(
            name="face_out",
            pos_cm=(0.0, MODULE_CM * 0.5, STOREY_CM * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_face",
            tags=tag,
        ),
    )


def _base_wall(
    piece_id: str,
    *,
    tags: frozenset,
    aperture: Optional[ApertureDesc] = None,
    notes: str = "",
) -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id=piece_id,
        kind="wall",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        sockets=_wall_sockets(),
        tags=tags,
        origin="min_corner",
        rotates_about_center=False,
        aabb_min_cm=(0.0, 0.0, 0.0),
        aperture=aperture,
        notes=notes,
    )


def wall_plain() -> PrimitiveDescriptor:
    return _base_wall(
        "wall_plain",
        tags=frozenset({"wall", "plain", "exterior", module_tag()}),
        notes="Solid bay wall, low-X strip.",
    )


def wall_window() -> PrimitiveDescriptor:
    cx = WALL_T_CM * 0.5
    # Opening punches through thickness; Y/Z centred in bay.
    half_w = MODULE_CM * _WINDOW_W * 0.5
    y0 = MODULE_CM * 0.5 - half_w
    y1 = MODULE_CM * 0.5 + half_w
    z0 = STOREY_CM * _WINDOW_SILL
    z1 = z0 + STOREY_CM * _WINDOW_H
    # Cutter slightly oversized in X so boolean clears both faces.
    pad = WALL_T_CM * 0.1
    return _base_wall(
        "wall_window",
        tags=frozenset({"wall", "window", "exterior", module_tag()}),
        aperture=ApertureDesc(
            kind="window",
            min_cm=(-pad, y0, z0),
            max_cm=(WALL_T_CM + pad, y1, z1),
        ),
        notes="Window opening; sill above floor.",
    )


def wall_arrowslit() -> PrimitiveDescriptor:
    half_w = MODULE_CM * _SLIT_W * 0.5
    y0 = MODULE_CM * 0.5 - half_w
    y1 = MODULE_CM * 0.5 + half_w
    z0 = STOREY_CM * _SLIT_SILL
    z1 = z0 + STOREY_CM * _SLIT_H
    pad = WALL_T_CM * 0.1
    return _base_wall(
        "wall_arrowslit",
        tags=frozenset({"wall", "arrowslit", "defensive", "exterior", module_tag()}),
        aperture=ApertureDesc(
            kind="arrowslit",
            min_cm=(-pad, y0, z0),
            max_cm=(WALL_T_CM + pad, y1, z1),
        ),
        notes="Narrow vertical slit.",
    )


def wall_door() -> PrimitiveDescriptor:
    half_w = MODULE_CM * _DOOR_W * 0.5
    y0 = MODULE_CM * 0.5 - half_w
    y1 = MODULE_CM * 0.5 + half_w
    z0 = 0.0
    z1 = STOREY_CM * _DOOR_H
    pad = WALL_T_CM * 0.1
    return _base_wall(
        "wall_door",
        tags=frozenset({"wall", "door", "exterior", module_tag()}),
        aperture=ApertureDesc(
            kind="door",
            min_cm=(-pad, y0, z0),
            max_cm=(WALL_T_CM + pad, y1, z1),
        ),
        notes="Door reaches floor (z=0).",
    )


def wall_arcade() -> PrimitiveDescriptor:
    """Arcade bay: arch cut **into** the module — outer size still one bay."""
    jamb = MODULE_CM * _ARCH_JAMB
    y0 = jamb
    y1 = MODULE_CM - jamb
    z0 = STOREY_CM * _ARCH_SPRING
    # Arch rises to near storey top, leaving a lintel band.
    z1 = STOREY_CM * 0.92
    pad = WALL_T_CM * 0.1
    return _base_wall(
        "wall_arcade",
        tags=frozenset({"wall", "arcade", "arch", "exterior", module_tag()}),
        aperture=ApertureDesc(
            kind="arch",
            min_cm=(-pad, y0, z0),
            max_cm=(WALL_T_CM + pad, y1, z1),
        ),
        notes="Rounded arch boolean into core before any decorative bands.",
    )


def all_walls() -> tuple:
    return (
        wall_plain(),
        wall_window(),
        wall_arrowslit(),
        wall_door(),
        wall_arcade(),
    )


def build_wall_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Optional bpy builder: core box, then aperture boolean (if any)."""
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
    if ap.kind == "arch":
        # Approximate arch: keep rectangular cutter for descriptor parity;
        # a true radial arch can replace the cutter top in a later polish pass.
        pass
    bpy_util.apply_boolean_difference(core, cutter)
    return core

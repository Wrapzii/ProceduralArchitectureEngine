"""Battlement / crenellation run — sits on a wall bay."""

from __future__ import annotations

from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

_BATTLEMENT_H_FRAC = 0.22  # of STOREY
_MERLON_COUNT = 4  # per bay run
_CRENEL_FRAC = 0.42  # merlon height / total battlement height


def battlement() -> PrimitiveDescriptor:
    h = STOREY_CM * _BATTLEMENT_H_FRAC
    tag = frozenset({module_tag(), "battlement"})
    sockets = (
        SocketDesc(
            name="end_a",
            pos_cm=(WALL_T_CM * 0.5, 0.0, h * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(WALL_T_CM * 0.5, MODULE_CM, h * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="wall_end",
            tags=tag,
        ),
        SocketDesc(
            name="bottom",
            pos_cm=(WALL_T_CM * 0.5, MODULE_CM * 0.5, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="battlement_base",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="battlement",
        kind="battlement",
        footprint_modules=(1, 1),
        height_storeys=_BATTLEMENT_H_FRAC,
        size_cm=(WALL_T_CM, MODULE_CM, h),
        sockets=sockets,
        tags=frozenset({"battlement", "defensive", "exterior", module_tag()}),
        origin="min_corner",
        notes="Crenellated parapet strip; merlon cutouts optional in bpy polish.",
    )


def all_battlements() -> tuple:
    return (battlement(),)


def _battlement_parts(desc: PrimitiveDescriptor) -> List[BoxPart]:
    """Parapet walk with alternating merlons along the run (Y axis)."""
    t, run, h = desc.size_cm
    walk_h = h * (1.0 - _CRENEL_FRAC)
    merlon_h = h - walk_h
    merlon_w = run / (_MERLON_COUNT * 2 - 1)
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (t, run, walk_h)),
    ]
    for i in range(_MERLON_COUNT):
        y0 = i * merlon_w * 2.0
        parts.append(((0.0, y0, walk_h), (t, merlon_w, merlon_h)))
    return parts


def build_battlement_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    parts = _battlement_parts(desc)
    return bpy_util.build_mesh_from_box_parts(
        name or desc.id, parts, origin_at_min_corner=True
    )

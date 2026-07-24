"""Battlement / crenellation run — sits on a wall bay."""

from __future__ import annotations

from typing import Optional

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

_BATTLEMENT_H_FRAC = 0.22  # of STOREY


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


def build_battlement_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    return bpy_util.box_mesh(name or desc.id, desc.size_cm, origin_at_min_corner=True)

"""Ground plinth / foundation slab (§2.5)."""

from __future__ import annotations

from typing import Optional

from pae.contract import FLOOR_T_CM, MODULE_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag


def ground_plinth() -> PrimitiveDescriptor:
    tag = frozenset({module_tag(), "plinth"})
    sockets = (
        SocketDesc(
            name="top",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM * 0.5, FLOOR_T_CM),
            normal=(0.0, 0.0, 1.0),
            type="plinth_top",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="ground_plinth",
        kind="plinth",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=sockets,
        tags=frozenset({"plinth", "ground", "foundation", module_tag()}),
        origin="min_corner",
        notes=(
            "Assemble places origin at ground_plinth_z_cm() (−2×FLOOR_T) so the "
            "slab top lands at z = −FLOOR_T, flush under the level-0 floor (§2.5)."
        ),
    )


def all_plinths() -> tuple:
    return (ground_plinth(),)


def build_plinth_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    return bpy_util.box_mesh(name or desc.id, desc.size_cm, origin_at_min_corner=True)

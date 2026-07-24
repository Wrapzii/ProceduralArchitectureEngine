"""Socket auto-proposal (§4.2–4.3) — WP-2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from pae.assets.db import Socket
from pae.contract import FLOOR_T_CM, MODULE_CM, WALL_T_CM


@dataclass(frozen=True)
class GeometryDescriptor:
    """Measured AABB + kind — Blender-optional pure-Python input."""

    size_cm: Tuple[float, float, float]
    kind: str
    rotates_about_center: bool = False


def _module_tag() -> set[str]:
    return {f"module_{int(MODULE_CM)}"}


def _wall_end_sockets(sx: float, sy: float, sz: float) -> List[Socket]:
    """Ends on faces perpendicular to the long horizontal axis."""
    tags = _module_tag()
    mid_z = sz * 0.5
    if sx >= sy:
        return [
            Socket(
                name="end_a",
                pos_cm=(0.0, sy * 0.5, mid_z),
                normal=(-1.0, 0.0, 0.0),
                type="wall_end",
                tags=set(tags),
            ),
            Socket(
                name="end_b",
                pos_cm=(sx, sy * 0.5, mid_z),
                normal=(1.0, 0.0, 0.0),
                type="wall_end",
                tags=set(tags),
            ),
        ]
    return [
        Socket(
            name="end_a",
            pos_cm=(sx * 0.5, 0.0, mid_z),
            normal=(0.0, -1.0, 0.0),
            type="wall_end",
            tags=set(tags),
        ),
        Socket(
            name="end_b",
            pos_cm=(sx * 0.5, sy, mid_z),
            normal=(0.0, 1.0, 0.0),
            type="wall_end",
            tags=set(tags),
        ),
    ]


def _floor_edge_sockets(sx: float, sy: float, sz: float) -> List[Socket]:
    tags = _module_tag()
    z = FLOOR_T_CM * 0.5 if abs(sz - FLOOR_T_CM) <= 6.0 else sz * 0.5
    return [
        Socket("edge_west", (0.0, sy * 0.5, z), (-1.0, 0.0, 0.0), "floor_edge", set(tags)),
        Socket("edge_east", (sx, sy * 0.5, z), (1.0, 0.0, 0.0), "floor_edge", set(tags)),
        Socket("edge_south", (sx * 0.5, 0.0, z), (0.0, -1.0, 0.0), "floor_edge", set(tags)),
        Socket("edge_north", (sx * 0.5, sy, z), (0.0, 1.0, 0.0), "floor_edge", set(tags)),
    ]


def _stair_sockets(sx: float, sy: float, sz: float) -> List[Socket]:
    tags = _module_tag()
    return [
        Socket(
            name="bottom",
            pos_cm=(sx * 0.5, sy * 0.5, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="stair_bottom",
            tags=set(tags),
        ),
        Socket(
            name="top",
            pos_cm=(sx * 0.5, sy * 0.5, sz),
            normal=(0.0, 0.0, 1.0),
            type="stair_top",
            tags=set(tags),
        ),
    ]


def _tower_arc_sockets(sx: float, sy: float, sz: float) -> List[Socket]:
    """Centred arc piece — sockets relative to rotation centre at bbox centre."""
    tags = _module_tag() | {"tower", "curved"}
    cx, cy = sx * 0.5, sy * 0.5
    return [
        Socket(
            name="arc_start",
            pos_cm=(0.0, cy, sz * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_end",
            tags=set(tags),
        ),
        Socket(
            name="arc_end",
            pos_cm=(cx, sy, sz * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="wall_end",
            tags=set(tags),
        ),
    ]


def _roof_eave_sockets(sx: float, sy: float, sz: float) -> List[Socket]:
    tags = _module_tag()
    return [
        Socket(
            name="eave_south",
            pos_cm=(sx * 0.5, 0.0, 0.0),
            normal=(0.0, -1.0, 0.0),
            type="roof_eave",
            tags=set(tags),
        ),
        Socket(
            name="eave_north",
            pos_cm=(sx * 0.5, sy, 0.0),
            normal=(0.0, 1.0, 0.0),
            type="roof_eave",
            tags=set(tags),
        ),
    ]


def propose_sockets(descriptor: GeometryDescriptor) -> List[Socket]:
    """Auto-propose sockets from measured geometry (§4.3 step 3)."""
    sx, sy, sz = descriptor.size_cm
    kind = descriptor.kind.lower()

    if kind == "wall":
        sockets = _wall_end_sockets(sx, sy, sz)
    elif kind == "floor":
        sockets = _floor_edge_sockets(sx, sy, sz)
    elif kind == "stair":
        sockets = _stair_sockets(sx, sy, sz)
    elif kind == "tower_arc":
        sockets = _tower_arc_sockets(sx, sy, sz)
    elif kind == "roof":
        sockets = _roof_eave_sockets(sx, sy, sz)
    else:
        sockets = []

    if descriptor.rotates_about_center and kind == "tower_arc":
        cx, cy = sx * 0.5, sy * 0.5
        centred: List[Socket] = []
        for sock in sockets:
            px, py, pz = sock.pos_cm
            centred.append(
                Socket(
                    name=sock.name,
                    pos_cm=(px - cx, py - cy, pz),
                    normal=sock.normal,
                    type=sock.type,
                    tags=set(sock.tags),
                )
            )
        return centred

    return sockets


def sockets_compatible(a: Socket, b: Socket, normal_tol: float = 0.05) -> bool:
    """§4.2 compatibility: same type, tag overlap, anti-parallel normals."""
    if a.type != b.type:
        return False
    if not (a.tags & b.tags):
        return False
    ax, ay, az = a.normal
    bx, by, bz = b.normal
    dot = ax * bx + ay * by + az * bz
    return dot <= -(1.0 - normal_tol)

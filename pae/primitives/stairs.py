"""Stairs — school / academy circulation kit.

Styles
------
* ``stair_straight`` — 2×1 module full-storey run (corridor / hall)
* ``stair_half`` — 1×1 half-storey flight (composes switchbacks)
* ``stair_landing`` — 1×1 mid-landing pad
* ``stair_switchback`` — 2×2 U / dog-leg (classic school stairwell)
* ``stair_wide`` — 2×2 double-width monumental straight run
* ``stair_spiral_quarter`` — 90° helical quarter (4 → one storey)
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

Vec3 = Tuple[float, float, float]
Face = Tuple[int, ...]

_SPIRAL_RISE_STOREYS = 0.25  # STOREY/4 per quarter (§5.3)
_STRAIGHT_STAIR_STEPS = 20
_HALF_STAIR_STEPS = 10
_SWITCHBACK_FLIGHT_STEPS = 10
_WIDE_STAIR_STEPS = 16
_SPIRAL_STEPS_PER_QUARTER = 6
_SPIRAL_INNER_RADIUS_FRAC = 0.35


def spiral_inner_radius_cm(outer_radius_cm: float) -> float:
    """Inner edge of the authored helical tread for a requested outer radius."""
    return float(outer_radius_cm) * _SPIRAL_INNER_RADIUS_FRAC


def straight_stair_step_count() -> int:
    """Number of treads on a full straight run (one storey rise)."""
    return _STRAIGHT_STAIR_STEPS


def _box_verts_faces(
    ox: float, oy: float, oz: float, sx: float, sy: float, sz: float
) -> Tuple[List[Vec3], List[Face]]:
    verts: List[Vec3] = [
        (ox, oy, oz),
        (ox + sx, oy, oz),
        (ox + sx, oy + sy, oz),
        (ox, oy + sy, oz),
        (ox, oy, oz + sz),
        (ox + sx, oy, oz + sz),
        (ox + sx, oy + sy, oz + sz),
        (ox, oy + sy, oz + sz),
    ]
    faces: List[Face] = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return verts, faces


def _merge_verts_faces(
    parts: Sequence[Tuple[List[Vec3], List[Face]]],
) -> Tuple[List[Vec3], List[Face]]:
    verts: List[Vec3] = []
    faces: List[Face] = []
    for part_verts, part_faces in parts:
        base = len(verts)
        verts.extend(part_verts)
        faces.extend(tuple(i + base for i in f) for f in part_faces)
    return verts, faces


def straight_stair_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    *,
    steps: Optional[int] = None,
    along: str = "x",
) -> Tuple[List[Vec3], List[Face]]:
    """Stacked tread + riser geometry — import-safe (no bpy).

    ``along='x'`` rises in +X; ``along='y'`` rises in +Y; ``along='-y'`` rises
    while travelling −Y (second flight of a switchback).
    """
    n = steps if steps is not None else _STRAIGHT_STAIR_STEPS
    if n < 1:
        raise ValueError("steps must be >= 1")
    if along not in ("x", "y", "-y"):
        raise ValueError(f"unsupported along={along!r}")

    run = sx if along == "x" else sy
    width = sy if along == "x" else sx
    tread_d = run / n
    riser_h = sz / n
    riser_t = max(tread_d * 0.18, 4.0)
    tread_t = max(riser_h * 0.22, 5.0)
    nose = tread_d * 0.12
    # Closed STRINGS carrying the flight. Treads and risers alone gave a ladder of
    # floating steps with nothing beneath it — user: "there are no supports under the
    # stairs, it just looks like there's floating steps." A string is a raked beam down
    # each side; built here as a stepped stack because the kit is box geometry, which
    # gives the right silhouette and a closed soffit line from the side.
    string_t = max(width * 0.09, 6.0)
    parts: List[Tuple[List[Vec3], List[Face]]] = []

    # Closed SOFFIT / undercarriage between the stringers — without this the flight
    # reads as a hollow inverted-U tunnel when viewed end-on (fancy manor section).
    core_w = max(width - 2.0 * string_t, width * 0.5)
    core_y0 = (width - core_w) * 0.5
    for i in range(n):
        z_top = max((i + 1) * riser_h - tread_t, riser_h * 0.35)
        if along == "x":
            parts.append(
                _box_verts_faces(i * tread_d, core_y0, 0.0, tread_d, core_w, z_top)
            )
        elif along == "y":
            parts.append(
                _box_verts_faces(core_y0, i * tread_d, 0.0, core_w, tread_d, z_top)
            )
        else:  # -y
            parts.append(
                _box_verts_faces(
                    core_y0, run - (i + 1) * tread_d, 0.0, core_w, tread_d, z_top
                )
            )

    for i in range(n):
        z0 = i * riser_h
        top = z0 + riser_h
        for near in (0.0, width - string_t):
            if along == "x":
                parts.append(
                    _box_verts_faces(i * tread_d, near, 0.0, tread_d, string_t, top)
                )
            elif along == "y":
                parts.append(
                    _box_verts_faces(near, i * tread_d, 0.0, string_t, tread_d, top)
                )
            else:  # -y
                parts.append(
                    _box_verts_faces(
                        near, run - (i + 1) * tread_d, 0.0, string_t, tread_d, top
                    )
                )

    for i in range(n):
        z0 = i * riser_h
        if along == "x":
            x0 = i * tread_d
            parts.append(_box_verts_faces(x0, 0.0, z0, riser_t, width, riser_h))
            parts.append(
                _box_verts_faces(
                    x0 - nose,
                    0.0,
                    z0 + riser_h - tread_t,
                    tread_d + nose,
                    width,
                    tread_t,
                )
            )
        elif along == "y":
            y0 = i * tread_d
            parts.append(_box_verts_faces(0.0, y0, z0, width, riser_t, riser_h))
            parts.append(
                _box_verts_faces(
                    0.0,
                    y0 - nose,
                    z0 + riser_h - tread_t,
                    width,
                    tread_d + nose,
                    tread_t,
                )
            )
        else:  # -y : start at y=run, step toward y=0
            y0 = run - i * tread_d
            parts.append(
                _box_verts_faces(0.0, y0 - riser_t, z0, width, riser_t, riser_h)
            )
            parts.append(
                _box_verts_faces(
                    0.0,
                    y0 - tread_d,
                    z0 + riser_h - tread_t,
                    width,
                    tread_d + nose,
                    tread_t,
                )
            )
    return _merge_verts_faces(parts)


def switchback_stair_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    *,
    steps_per_flight: Optional[int] = None,
) -> Tuple[List[Vec3], List[Face]]:
    """U / dog-leg: up one side, mid landing, up the other (school stairwell)."""
    n = steps_per_flight if steps_per_flight is not None else _SWITCHBACK_FLIGHT_STEPS
    half_z = sz * 0.5
    half_x = sx * 0.5
    half_y = sy * 0.5
    land_t = max(FLOOR_T_CM, half_z * 0.08)

    f1_v, f1_f = straight_stair_verts_faces(
        half_x, half_y, half_z, steps=n, along="y"
    )
    f1_shift = [(v[0] + half_x, v[1], v[2]) for v in f1_v]

    land_v, land_f = _box_verts_faces(
        0.0, half_y, half_z - land_t, sx, half_y, land_t
    )

    f2_local_v, f2_local_f = straight_stair_verts_faces(
        half_x, half_y, half_z, steps=n, along="-y"
    )
    f2_shift = [(v[0], v[1] + half_y, v[2] + half_z) for v in f2_local_v]

    return _merge_verts_faces(
        [
            (f1_shift, f1_f),
            (land_v, land_f),
            (f2_shift, f2_local_f),
        ]
    )


def helical_quarter_step_verts_faces(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    steps: Optional[int] = None,
) -> Tuple[List[Vec3], List[Face]]:
    """True helical wedge steps for one 90° spiral quarter (import-safe)."""
    n = steps if steps is not None else _SPIRAL_STEPS_PER_QUARTER
    if n < 1:
        raise ValueError("steps must be >= 1")
    if outer_r <= inner_r:
        raise ValueError("outer_r must exceed inner_r")
    a0 = 0.0
    a1 = math.pi * 0.5
    dz = (z1 - z0) / n
    da = (a1 - a0) / n
    tread_t = max(dz * 0.28, 4.0)
    parts: List[Tuple[List[Vec3], List[Face]]] = []

    def _wedge(theta0: float, theta1: float, zb: float, zt: float) -> None:
        b0 = (inner_r * math.cos(theta0), inner_r * math.sin(theta0), zb)
        b1 = (outer_r * math.cos(theta0), outer_r * math.sin(theta0), zb)
        b2 = (outer_r * math.cos(theta1), outer_r * math.sin(theta1), zb)
        b3 = (inner_r * math.cos(theta1), inner_r * math.sin(theta1), zb)
        t0 = (inner_r * math.cos(theta0), inner_r * math.sin(theta0), zt)
        t1 = (outer_r * math.cos(theta0), outer_r * math.sin(theta0), zt)
        t2 = (outer_r * math.cos(theta1), outer_r * math.sin(theta1), zt)
        t3 = (inner_r * math.cos(theta1), inner_r * math.sin(theta1), zt)
        verts = [b0, b1, b2, b3, t0, t1, t2, t3]
        faces = [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 4, 0),
        ]
        parts.append((verts, faces))

    for i in range(n):
        th0 = a0 + i * da
        th1 = a0 + (i + 1) * da
        zb = z0 + i * dz
        # Last tread reaches the quarter top so stacked quarters meet cleanly.
        zt = z1 if i == n - 1 else zb + tread_t
        if i == 0:
            _wedge(th0, th1, z0, zt)
        else:
            prev_zt = z0 + (i - 1) * dz + tread_t
            if i == n - 1:
                prev_zt = z0 + (i - 1) * dz + tread_t
            if zb > prev_zt + 1e-6:
                _wedge(th0, th1, prev_zt, zb)
            _wedge(th0, th1, zb, zt)
    return _merge_verts_faces(parts)


def _stair_tag(*extra: str) -> frozenset:
    return frozenset({module_tag(), "stair", *extra})


def stair_straight() -> PrimitiveDescriptor:
    """Spans exactly 2 modules, rises exactly 1 storey."""
    sx = 2.0 * MODULE_CM
    sy = MODULE_CM
    sz = STOREY_CM
    tag = _stair_tag("straight")
    sockets = (
        SocketDesc("bottom", (0.0, sy * 0.5, 0.0), (-1.0, 0.0, 0.0), "stair_bottom", tag),
        SocketDesc("top", (sx, sy * 0.5, sz), (1.0, 0.0, 0.0), "stair_top", tag),
    )
    return PrimitiveDescriptor(
        id="stair_straight",
        kind="stair",
        footprint_modules=(2, 1),
        height_storeys=1.0,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=tag,
        origin="min_corner",
        notes="Run along +X; top requires VOID cell above.",
    )


def stair_half() -> PrimitiveDescriptor:
    """One-module half-storey flight — building block for switchbacks."""
    sx = MODULE_CM
    sy = MODULE_CM
    sz = STOREY_CM * 0.5
    tag = _stair_tag("half")
    sockets = (
        SocketDesc("bottom", (0.0, sy * 0.5, 0.0), (-1.0, 0.0, 0.0), "stair_bottom", tag),
        SocketDesc("top", (sx, sy * 0.5, sz), (1.0, 0.0, 0.0), "stair_top", tag),
    )
    return PrimitiveDescriptor(
        id="stair_half",
        kind="stair",
        footprint_modules=(1, 1),
        height_storeys=0.5,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=tag,
        origin="min_corner",
        notes="Half rise / one bay — pair with stair_landing for dog-legs.",
    )


def stair_landing() -> PrimitiveDescriptor:
    """Mid-landing pad (1 module) for switchback / L compositions."""
    sx = MODULE_CM
    sy = MODULE_CM
    sz = FLOOR_T_CM * 1.5
    tag = _stair_tag("landing")
    mid = MODULE_CM * 0.5
    sockets = (
        SocketDesc("edge_x0", (0.0, mid, sz), (-1.0, 0.0, 0.0), "stair_landing", tag),
        SocketDesc("edge_x1", (sx, mid, sz), (1.0, 0.0, 0.0), "stair_landing", tag),
        SocketDesc("edge_y0", (mid, 0.0, sz), (0.0, -1.0, 0.0), "stair_landing", tag),
        SocketDesc("edge_y1", (mid, sy, sz), (0.0, 1.0, 0.0), "stair_landing", tag),
    )
    return PrimitiveDescriptor(
        id="stair_landing",
        kind="stair",
        footprint_modules=(1, 1),
        height_storeys=sz / STOREY_CM,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=tag,
        origin="min_corner",
        notes="Walkable mid-landing; place at half-storey Z.",
    )


def stair_switchback() -> PrimitiveDescriptor:
    """2×2 U / dog-leg — primary school / academy stairwell piece."""
    sx = 2.0 * MODULE_CM
    sy = 2.0 * MODULE_CM
    sz = STOREY_CM
    tag = _stair_tag("switchback")
    sockets = (
        SocketDesc(
            "bottom",
            (sx * 0.75, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            "stair_bottom",
            tag,
        ),
        SocketDesc(
            "top",
            (sx * 0.25, sy * 0.5, sz),
            (0.0, -1.0, 0.0),
            "stair_top",
            tag,
        ),
    )
    return PrimitiveDescriptor(
        id="stair_switchback",
        kind="stair",
        footprint_modules=(2, 2),
        height_storeys=1.0,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=tag,
        origin="min_corner",
        notes="Dog-leg: east flight up, north landing, west flight up. VOID 2×2 above.",
    )


def stair_wide() -> PrimitiveDescriptor:
    """Double-width monumental straight run (2×2 footprint)."""
    sx = 2.0 * MODULE_CM
    sy = 2.0 * MODULE_CM
    sz = STOREY_CM
    tag = _stair_tag("wide")
    sockets = (
        SocketDesc("bottom", (0.0, sy * 0.5, 0.0), (-1.0, 0.0, 0.0), "stair_bottom", tag),
        SocketDesc("top", (sx, sy * 0.5, sz), (1.0, 0.0, 0.0), "stair_top", tag),
    )
    return PrimitiveDescriptor(
        id="stair_wide",
        kind="stair",
        footprint_modules=(2, 2),
        height_storeys=1.0,
        size_cm=(sx, sy, sz),
        sockets=sockets,
        tags=tag,
        origin="min_corner",
        notes="Grand hall / entrance stair — twice corridor width.",
    )


def stair_spiral_quarter() -> PrimitiveDescriptor:
    """One 90° helical quarter — four stack to one storey (§5.3)."""
    rise = STOREY_CM * _SPIRAL_RISE_STOREYS
    tag = _stair_tag("spiral", "quarter")
    sockets = (
        SocketDesc(
            "bottom",
            (MODULE_CM, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            "stair_bottom",
            tag,
        ),
        SocketDesc(
            "top",
            (0.0, MODULE_CM, rise),
            (-1.0, 0.0, 0.0),
            "stair_top",
            tag,
        ),
    )
    return PrimitiveDescriptor(
        id="stair_spiral_quarter",
        kind="stair",
        footprint_modules=(2, 2),
        height_storeys=_SPIRAL_RISE_STOREYS,
        # The mesh is a quarter of a circle with outer radius MODULE, so its
        # centred AABB is two modules wide. The previous one-module declaration
        # made every collision/hole/landing query half the visible Blender size.
        size_cm=(2.0 * MODULE_CM, 2.0 * MODULE_CM, rise),
        sockets=sockets,
        tags=tag,
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
        notes="Helical wedge steps; four quarters per storey at same cell centre.",
    )


def all_stairs() -> tuple:
    return (
        stair_straight(),
        stair_half(),
        stair_landing(),
        stair_switchback(),
        stair_wide(),
        stair_spiral_quarter(),
    )


def build_stair_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Author stair meshes for every kit style."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    sx, sy, sz = desc.size_cm

    if desc.id == "stair_landing":
        return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)

    if desc.id == "stair_switchback":
        verts, faces = switchback_stair_verts_faces(sx, sy, sz)
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)

    if desc.id == "stair_wide":
        verts, faces = straight_stair_verts_faces(
            sx, sy, sz, steps=_WIDE_STAIR_STEPS, along="x"
        )
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)

    if desc.id == "stair_half":
        verts, faces = straight_stair_verts_faces(
            sx, sy, sz, steps=_HALF_STAIR_STEPS, along="x"
        )
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)

    if desc.rotates_about_center or desc.id == "stair_spiral_quarter":
        outer = MODULE_CM
        inner = spiral_inner_radius_cm(outer)
        verts, faces = helical_quarter_step_verts_faces(
            outer, inner, 0.0, desc.size_cm[2]
        )
        obj = bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
        bpy_util.smooth_shade_curved_faces(obj)
        return obj

    verts, faces = straight_stair_verts_faces(sx, sy, sz)
    return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)

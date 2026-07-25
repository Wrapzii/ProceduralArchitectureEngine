"""PAE grid contract — single source of truth for dimensions and placement offsets.

Nothing else may hard-code MODULE / STOREY / WALL_T / FLOOR_T values.
See Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md §2.
"""

from __future__ import annotations

from typing import Tuple

# --- §2 core dimensions (centimetres) ---
MODULE_CM = 400.0
STOREY_CM = 350.0
WALL_T_CM = 60.0
FLOOR_T_CM = 30.0
# Visible eave beyond wall outer face (§6) — fraction of wall thickness, not a bare module.
EAVE_OVERHANG_CM = WALL_T_CM * 0.5

# Validation / fit tolerances
TOL_CM = 6.0
MAX_STRETCH = 0.06  # 6 % long-axis stretch ceiling (§4.4)
CHEST_HEIGHT_CM = 120.0  # enclosure flood (§7.5)
VERTICAL_SUPPORT_TOL_CM = 35.0  # floater probe (§7.2)

Yaw = int  # 0 | 90 | 180 | 270


def cell_to_world_cm(
    cell_x: int,
    cell_y: int,
    level: int,
    off_x: float = 0.0,
    off_y: float = 0.0,
    off_z: float = 0.0,
) -> Tuple[float, float, float]:
    """Integer cell + local offset → world centimetres."""
    return (
        cell_x * MODULE_CM + off_x,
        cell_y * MODULE_CM + off_y,
        level * STOREY_CM + off_z,
    )


def rotation_offset_cm(
    yaw: Yaw,
    footprint_sx_cm: float,
    footprint_sy_cm: float,
    *,
    rotates_about_center: bool = False,
) -> Tuple[float, float]:
    """Compensate min-corner origin so yaw keeps the piece in its intended cell (§2.2).

    Curved / centred pieces take no offset.
    """
    if rotates_about_center:
        return (0.0, 0.0)
    sx, sy = footprint_sx_cm, footprint_sy_cm
    if yaw == 0:
        return (0.0, 0.0)
    if yaw == 90:
        return (sy, 0.0)
    if yaw == 180:
        return (sx, sy)
    if yaw == 270:
        return (0.0, sx)
    raise ValueError(f"yaw must be 0/90/180/270, got {yaw}")


def wall_run_cell(face: str, x0: int, y0: int, x1: int, y1: int) -> Tuple[int, int, Yaw]:
    """Boundary-line wall placement (§2.3). Returns (cell_x, cell_y, yaw).

    East/north runs sit on x1+1 / y1+1 — NOT on x1/y1.
    """
    face = face.lower()
    if face == "west":
        return (x0, y0, 0)  # caller spans Y; cell_x fixed
    if face == "east":
        return (x1 + 1, y0, 180)
    if face == "south":
        return (x0, y0, 270)
    if face == "north":
        return (x0, y1 + 1, 90)
    raise ValueError(f"unknown wall face: {face}")


def floor_placement_z_cm(level: int) -> float:
    """World Z for a floor slab origin so its top lands on the storey (§2.4)."""
    level_z = level * STOREY_CM
    return level_z - FLOOR_T_CM


def ground_plinth_z_cm() -> float:
    """Ground / plinth slab origin so its top is at z = -FLOOR_T (§2.5).

    Slab thickness is ``FLOOR_T_CM``, so the min-corner origin sits one slab
    below that top contact plane (floor bottom at level 0).
    """
    return -2.0 * FLOOR_T_CM


def rotate_local_xy(
    lx: float,
    ly: float,
    yaw: Yaw,
    footprint_sx_cm: float,
    footprint_sy_cm: float,
) -> Tuple[float, float]:
    """Rotate a local XY point about the min-corner origin (pure yaw).

    Compensating cell offset is applied separately via ``rotation_offset_cm`` /
    ``offset_cm`` on the placement origin — do **not** bake it in here or east
    walls land a full ``WALL_T`` too far out and corners fail to meet.
    """
    del footprint_sx_cm, footprint_sy_cm
    if yaw == 0:
        return (lx, ly)
    if yaw == 90:
        return (-ly, lx)
    if yaw == 180:
        return (-lx, -ly)
    if yaw == 270:
        return (ly, -lx)
    raise ValueError(f"yaw must be 0/90/180/270, got {yaw}")


def placement_origin_cm(
    cell_x: int,
    cell_y: int,
    level: int,
    offset_cm: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """World origin (min corner) for a placement before yaw footprint swap."""
    ox, oy, oz = offset_cm
    return cell_to_world_cm(cell_x, cell_y, level, ox, oy, oz)


def placement_world_aabb(
    cell_x: int,
    cell_y: int,
    level: int,
    yaw: Yaw,
    size_cm: Tuple[float, float, float],
    offset_cm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    rotates_about_center: bool = False,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Axis-aligned world bounds for a placed solid (min_corner convention)."""
    sx, sy, sz = size_cm
    wx, wy, wz = placement_origin_cm(cell_x, cell_y, level, offset_cm)

    if rotates_about_center:
        hx, hy = sx * 0.5, sy * 0.5
        return (
            (wx - hx, wy - hy, wz),
            (wx + hx, wy + hy, wz + sz),
        )

    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for lx in (0.0, sx):
        for ly in (0.0, sy):
            for lz in (0.0, sz):
                rx, ry = rotate_local_xy(lx, ly, yaw, sx, sy)
                xs.append(wx + rx)
                ys.append(wy + ry)
                zs.append(wz + lz)

    return (
        (min(xs), min(ys), min(zs)),
        (max(xs), max(ys), max(zs)),
    )


def aabb_overlap(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
    tol: float = TOL_CM,
) -> bool:
    """True when AABBs overlap by more than *tol* on every axis (§7.4)."""
    for amin, amax, bmin, bmax in zip(a_min, a_max, b_min, b_max):
        depth = min(amax, bmax) - max(amin, bmin)
        if depth <= tol:
            return False
    return True


def aabb_intersects(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
    tol: float = TOL_CM,
) -> bool:
    """True when AABBs touch or overlap (within *tol*)."""
    for amin, amax, bmin, bmax in zip(a_min, a_max, b_min, b_max):
        if min(amax, bmax) - max(amin, bmin) < -tol:
            return False
    return True

"""PAE grid contract — single source of truth for dimensions and placement offsets.

Nothing else may hard-code MODULE / STOREY / WALL_T / FLOOR_T values.
See Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md §2.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

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

# Monumental gate / arch clear opening — at least one full storey (§BUILDING_HEIGHT_FLEX).
GATE_CLEAR_MIN_STOREYS = 1.0
# Conservative lower bound on gate profile ``height_frac`` (kit profiles are ≥ this).
# Used to size the wall leaf so clear opening can reach ``GATE_CLEAR_MIN_STOREYS``.
GATE_OPENING_HEIGHT_FRAC_MIN = 0.88

# Tower drum rim apertures (@TOWER_ENTRY_CLIMB_FIX) — fractions of MODULE / STOREY.
DRUM_WINDOW_CHORD_FRAC = 0.36  # narrow vertical lancet chord on curved masonry
DRUM_WINDOW_HEIGHT_FRAC = 0.58  # perimeter lancet height per storey
DRUM_WINDOW_HELICAL_HEIGHT_FRAC = 0.52  # stair-light lancet below next tread
DRUM_WINDOW_SILL_FRAC = 0.18  # sill above storey datum
TOWER_ENTRY_DOOR_CHORD_FRAC = 0.42  # attach-face passage width
TOWER_ENTRY_DOOR_HEIGHT_FRAC = 0.82  # clear leaf height under storey plate

Yaw = int  # 0 | 90 | 180 | 270


def drum_window_chord_cm(*, module_cm: float = MODULE_CM) -> float:
    """Tangential run of a drum-rim window overlay at the outer shell."""
    return module_cm * DRUM_WINDOW_CHORD_FRAC


def drum_window_height_cm(
    *, storey_cm: float = STOREY_CM, helical: bool = False
) -> float:
    """Vertical extent of a drum window overlay on one slot."""
    frac = (
        DRUM_WINDOW_HELICAL_HEIGHT_FRAC if helical else DRUM_WINDOW_HEIGHT_FRAC
    )
    return storey_cm * frac


def tower_entry_door_chord_cm(*, module_cm: float = MODULE_CM) -> float:
    """Walkable chord for a hall↔drum ``tower_entry`` on the attach face."""
    return module_cm * TOWER_ENTRY_DOOR_CHORD_FRAC


def tower_entry_door_height_cm(*, storey_cm: float = STOREY_CM) -> float:
    """Passage leaf height for ``tower_entry`` under the storey slab."""
    return storey_cm * TOWER_ENTRY_DOOR_HEIGHT_FRAC - FLOOR_T_CM


def height_cm_from_storeys(
    storeys: float, *, storey_cm: float = STOREY_CM
) -> float:
    """Convert storey count (int or float) → centimetres via ``STOREY_CM``."""
    if storeys < 0:
        raise ValueError(f"storeys must be >= 0, got {storeys}")
    return float(storeys) * float(storey_cm)


def storeys_from_height_cm(
    height_cm: float, *, storey_cm: float = STOREY_CM
) -> float:
    """Convert centimetres → storey count (float)."""
    if storey_cm <= 0:
        raise ValueError(f"storey_cm must be > 0, got {storey_cm}")
    return float(height_cm) / float(storey_cm)


def resolve_height_cm(
    *,
    storeys: Optional[float] = None,
    height_cm: Optional[float] = None,
    storey_cm: float = STOREY_CM,
) -> float:
    """Resolve a declared height to centimetres.

    Prefer ``storeys`` when both are given (JSON / BuildingSpec path). ``height_cm``
    is the Python/measured override — BuildingSpec JSON still forbids ``*_cm`` keys.
    """
    if storeys is not None:
        return height_cm_from_storeys(storeys, storey_cm=storey_cm)
    if height_cm is not None:
        if height_cm < 0:
            raise ValueError(f"height_cm must be >= 0, got {height_cm}")
        return float(height_cm)
    raise ValueError("height requires storeys or height_cm")


def resolve_height_storeys(
    *,
    storeys: Optional[float] = None,
    height_cm: Optional[float] = None,
    storey_cm: float = STOREY_CM,
) -> float:
    """Resolve a declared height to storeys (float). Prefer ``storeys``."""
    return storeys_from_height_cm(
        resolve_height_cm(storeys=storeys, height_cm=height_cm, storey_cm=storey_cm),
        storey_cm=storey_cm,
    )


def gate_clear_min_cm(*, storey_cm: float = STOREY_CM) -> float:
    """Minimum clear opening height for monumental gate/arch leaves."""
    return height_cm_from_storeys(GATE_CLEAR_MIN_STOREYS, storey_cm=storey_cm)


def gate_span_min_storeys() -> float:
    """Minimum wall leaf height (storeys) so a gate can clear one storey."""
    return GATE_CLEAR_MIN_STOREYS / GATE_OPENING_HEIGHT_FRAC_MIN


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
        storey_datum_z_cm(level) + off_z,
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


def cumulative_height_units_below(
    level: int,
    height_units: Optional[Sequence[float]] = None,
) -> float:
    """Sum of per-level ``height_units`` strictly below ``level``.

    When ``height_units`` is omitted, each level is 1 unit (legacy uniform grid).
    Levels beyond the declared list also count as 1 unit each.
    """
    if level <= 0:
        return 0.0
    if not height_units:
        return float(level)
    total = 0.0
    for i in range(level):
        if i < len(height_units):
            total += float(height_units[i])
        else:
            total += 1.0
    return total


def storey_datum_z_cm(
    level: int,
    *,
    datum_offset_cm: float = 0.0,
    height_units: Optional[Sequence[float]] = None,
    storey_cm: float = STOREY_CM,
) -> float:
    """World Z of storey ``level`` datum (floor / ceiling reference plane).

    Master Plan Stage B: ``level z = sum(height_units below) * storey_cm``,
    not a blind ``level * STOREY_CM``. Omitting ``height_units`` preserves the
    legacy uniform grid (each level = 1 unit).

    Per-volume offsets (Roadmap T-111) add ``datum_offset_cm`` above that datum.
    """
    units = cumulative_height_units_below(level, height_units)
    return units * storey_cm + datum_offset_cm


def floor_placement_z_cm(
    level: int,
    *,
    datum_offset_cm: float = 0.0,
    height_units: Optional[Sequence[float]] = None,
    storey_cm: float = STOREY_CM,
) -> float:
    """World Z for a floor slab origin so its top lands on the storey (§2.4)."""
    return (
        storey_datum_z_cm(
            level,
            datum_offset_cm=datum_offset_cm,
            height_units=height_units,
            storey_cm=storey_cm,
        )
        - FLOOR_T_CM
    )


# --- Per-volume storey datum tags (Roadmap 10.6 / T-111) --------------------

VOLUME_TAG_PREFIX = "volume:"
DATUM_OFFSET_TAG_PREFIX = "datum_offset_cm:"


def volume_id_from_tags(tags: Iterable[str]) -> Optional[str]:
    """Bare volume id from ``volume:<name>`` tag, if present."""
    for t in tags:
        if t.startswith(VOLUME_TAG_PREFIX):
            return t[len(VOLUME_TAG_PREFIX) :]
    return None


def datum_offset_cm_from_tags(tags: Iterable[str]) -> Optional[float]:
    """Per-volume datum offset (cm above uniform grid) from ``datum_offset_cm:<n>``."""
    for t in tags:
        if not t.startswith(DATUM_OFFSET_TAG_PREFIX):
            continue
        try:
            return float(t[len(DATUM_OFFSET_TAG_PREFIX) :])
        except ValueError:
            return None
    return None


def placement_volume_offset_z_cm(
    *,
    level: int,
    kind: str,
    datum_offset_cm: float,
) -> float:
    """Expected ``offset_cm[2]`` when the cell grid still uses uniform ``storey_datum_z_cm(level)``.

    World Z origin is ``storey_datum_z_cm(level) + offset_cm[2]``. A volume whose datum
    sits ``datum_offset_cm`` above the uniform grid must bake that delta into ``offset_cm[2]``
    until assemble routes ``cell_to_world`` through per-volume datums.
    """
    if kind in ("floor", "ground"):
        return datum_offset_cm - FLOOR_T_CM
    if kind in ("stair", "wall", "plinth", "hole"):
        return datum_offset_cm
    return datum_offset_cm


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


@lru_cache(maxsize=1 << 16)
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
    """Axis-aligned world bounds for a placed solid (min_corner convention).

    Memoized: validation asks for the same placement's bounds hundreds of times
    per run (interpenetration, headroom and support each rescan every pair), and
    the result depends only on these arguments.
    """
    sx, sy, sz = size_cm
    wx, wy, wz = placement_origin_cm(cell_x, cell_y, level, offset_cm)

    if rotates_about_center:
        hx, hy = sx * 0.5, sy * 0.5
        return (
            (wx - hx, wy - hy, wz),
            (wx + hx, wy + hy, wz + sz),
        )

    # Yaw never tilts the piece, so Z needs no rotation and the four base corners
    # bound XY on their own.
    xs: list[float] = []
    ys: list[float] = []
    for lx in (0.0, sx):
        for ly in (0.0, sy):
            rx, ry = rotate_local_xy(lx, ly, yaw, sx, sy)
            xs.append(wx + rx)
            ys.append(wy + ry)

    lo_z, hi_z = (wz, wz + sz) if sz >= 0.0 else (wz + sz, wz)
    return (
        (min(xs), min(ys), lo_z),
        (max(xs), max(ys), hi_z),
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

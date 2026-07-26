"""Continuous facade shell — solid exterior panels with grammar-cut openings.

Builds a CITY&BEYOND-style box shell from :class:`pae.facade_grammar.FacadeParams`
without per-cell modular exterior wall kits. Interior partition grids are never
emitted as outer skin; only a stair well and optional inset corridor wall live
inside the footprint.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    rotation_offset_cm,
)
from pae.facade_grammar import (
    FacadeParams,
    params_to_spec,
    params_to_style_overrides,
    party_wall_faces,
    resolve_wealth,
)
from pae.primitives.roofs import (
    DEFAULT_ROOF_PITCH,
    roof_eave_offset_cm,
    roof_eave_overhang_per_side,
    roof_flat_span_size_cm,
    roof_gable_end_offset_cm,
    roof_gable_end_size_cm,
    roof_rise_cm,
)
from pae.report import Report
from pae.shared_ids import resolve_shared
from pae.spec import BuildingSpec

# Shell mesh ids — Blender builds axis-aligned boxes from placement ``size_cm``.
SHELL_WALL_ASSET = "shell_wall_solid"
SHELL_OPENING_CUTTER_ASSET = "shell_opening_cutter"
SHELL_FLOOR_ASSET = "shell_floor_slab"
SHELL_ROOF_ASSET = "shell_roof_slope"
SHELL_INTERIOR_WALL_ASSET = "shell_wall_interior"

# Opening cutter padding — pierces both wall skins for boolean / panel punch.
_CUTTER_PAD_X_FRAC = 0.25
_CUTTER_PAD_YZ_CM = 0.5
SHELL_DOOR_ASSET = "shell_door"
SHELL_WINDOW_MUNTIN_ASSET = "shell_window_muntin"
SHELL_CHIMNEY_ASSET = "shell_chimney_stub"

_SHELL_TAG = frozenset({"facade_shell"})
_EXTERIOR_TAG = frozenset({"facade_shell", "exterior"})
_INTERIOR_TAG = frozenset({"facade_shell", "interior"})

_FACE_YAW = {"west": 0, "east": 180, "south": 270, "north": 90}

# Georgian aperture fractions of a bay / storey (not full modular wall kits).
_WINDOW_W_FRAC = 0.55
_WINDOW_H_FRAC = 0.58
_WINDOW_SILL_FRAC = 0.22  # of STOREY — sill height above floor
_DOOR_W_FRAC = 0.42
_DOOR_H_FRAC = 0.78
_PLINTH_FRAC = 0.16
_CORNICE_FRAC = 0.10
_FRAME_T_FRAC = 0.08  # of WALL_T — thin sash/door leaf in the opening
_MUNTIN_T_FRAC = 0.045  # of WALL_T — thin Georgian cross bars
_CHIMNEY_W_FRAC = 0.18  # of MODULE — roof stub footprint
_CHIMNEY_H_FRAC = 0.42  # of STOREY — short stack above ridge


def is_shell_placement(p: SolidPlacement) -> bool:
    """True when Blender should mesh this placement as a sized shell box."""
    aid = getattr(p, "asset_id", "") or ""
    if aid.startswith("shell_"):
        return True
    return "facade_shell" in getattr(p, "tags", frozenset())


def _next_id(counters: Dict[str, int], prefix: str) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    n = counters[prefix]
    return prefix if n == 1 else f"{prefix}_{n}"


def _wall_offset_cm(face: str, yaw: int, size_cm: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """East/north tuck thickness inward (matches assemble ``_boundary_wall_offset_cm``)."""
    sx, sy, _ = size_cm
    ox, oy = rotation_offset_cm(yaw, sx, sy, rotates_about_center=False)
    face = face.lower()
    if face == "east":
        ox -= WALL_T_CM
    elif face == "north":
        oy -= WALL_T_CM
    return (ox, oy, 0.0)


def _footprint_cm(bays_x: int, bays_y: int) -> Tuple[float, float]:
    return bays_x * MODULE_CM, bays_y * MODULE_CM


def _stair_anchor_and_cells(
    stair_id: str, bays_x: int, bays_y: int
) -> Tuple[Tuple[int, int], int, List[Tuple[int, int]]]:
    """Pick an interior stair anchor and occupied cells (inside footprint)."""
    if stair_id == "stair_switchback" and bays_x >= 4 and bays_y >= 3:
        ax, ay = max(1, bays_x - 3), 1
        cells = [(ax + i, ay + j) for i in range(2) for j in range(2)]
        return (ax, ay), 0, cells
    # stair_straight — 2×1 run along +X, tucked against north interior.
    ax = max(0, min(1, bays_x - 2))
    ay = max(1, bays_y - 2)
    cells = [(ax, ay), (ax + 1, ay)]
    return (ax, ay), 0, cells


def _place_shell_box(
    *,
    piece_prefix: str,
    asset_id: str,
    face: str,
    level: int,
    cell: Tuple[int, int],
    size_cm: Tuple[float, float, float],
    offset_extra: Tuple[float, float, float],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
    kind: str = "wall",
) -> None:
    yaw = _FACE_YAW[face]
    base = _wall_offset_cm(face, yaw, size_cm)
    offset = (
        base[0] + offset_extra[0],
        base[1] + offset_extra[1],
        base[2] + offset_extra[2],
    )
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, piece_prefix),
            asset_id=asset_id,
            kind=kind,
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=size_cm,
            tags=tags,
        )
    )


def _face_run_and_origin(
    face: str, bays_x: int, bays_y: int, width_cm: float, depth_cm: float
) -> Tuple[float, int, Tuple[int, int]]:
    """Return (run_cm, bay_count, origin_cell) for a facade face."""
    if face in ("west", "east"):
        return depth_cm, bays_y, ((0, 0) if face == "west" else (bays_x, 0))
    return width_cm, bays_x, ((0, 0) if face == "south" else (0, bays_y))


def _opening_spec(
    *,
    face: str,
    bay: int,
    level: int,
    door_bay: int,
    bay_count: int,
) -> Optional[Tuple[str, float, float, float]]:
    """Return (kind, width_cm, height_cm, sill_z_cm) or None if solid pier bay."""
    if face == "south" and level == 0 and bay == door_bay:
        w = MODULE_CM * _DOOR_W_FRAC
        h = STOREY_CM * _DOOR_H_FRAC
        return ("door", w, h, 0.0)
    # Skip a second opening in the door bay on ground south.
    if face == "south" and level == 0 and bay == door_bay:
        return None
    w = MODULE_CM * _WINDOW_W_FRAC
    h = STOREY_CM * _WINDOW_H_FRAC
    sill = STOREY_CM * _WINDOW_SILL_FRAC
    return ("window", w, h, sill)


def _place_window_muntins(
    *,
    face: str,
    level: int,
    origin: Tuple[int, int],
    open_center: float,
    open_y0: float,
    open_w: float,
    open_h: float,
    sill_z: float,
    frame_t: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
) -> None:
    """Cheap Georgian cross — one vertical + one horizontal bar in the sash."""
    muntin_t = max(2.5, WALL_T_CM * _MUNTIN_T_FRAC)
    inset_w = open_w * 0.88
    inset_h = open_h * 0.88
    depth = max(2.5, frame_t * 0.55)
    base_x = (WALL_T_CM - depth) * 0.5
    y_inset = open_y0 + open_w * 0.06
    z_inset = sill_z + open_h * 0.06
    _place_shell_box(
        piece_prefix=f"shell_muntin_v_{face}_L{level}",
        asset_id=SHELL_WINDOW_MUNTIN_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(depth, muntin_t, inset_h),
        offset_extra=(base_x, open_center - muntin_t * 0.5, z_inset),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"muntin", "window"}),
        kind="prop",
    )
    _place_shell_box(
        piece_prefix=f"shell_muntin_h_{face}_L{level}",
        asset_id=SHELL_WINDOW_MUNTIN_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(depth, inset_w, muntin_t),
        offset_extra=(base_x, y_inset, sill_z + open_h * 0.5 - muntin_t * 0.5),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"muntin", "window"}),
        kind="prop",
    )


def _place_glazed_face(
    *,
    face: str,
    level: int,
    bays_x: int,
    bays_y: int,
    width_cm: float,
    depth_cm: float,
    door_bay: int,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Continuous cream facade with real opening gaps (no modular wall-window kits)."""
    run_cm, bay_count, origin = _face_run_and_origin(
        face, bays_x, bays_y, width_cm, depth_cm
    )
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}"})
    plinth_h = STOREY_CM * _PLINTH_FRAC
    cornice_h = STOREY_CM * _CORNICE_FRAC
    frame_t = max(4.0, WALL_T_CM * _FRAME_T_FRAC)

    # Continuous plinth + cornice bands (reads as one building, not cells).
    _place_shell_box(
        piece_prefix=f"shell_plinth_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(WALL_T_CM, run_cm, plinth_h),
        offset_extra=(0.0, 0.0, 0.0),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"plinth"}),
    )
    _place_shell_box(
        piece_prefix=f"shell_cornice_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(WALL_T_CM, run_cm, cornice_h),
        offset_extra=(0.0, 0.0, STOREY_CM - cornice_h),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"cornice"}),
    )

    # Walk the run in bay modules; solid piers + punched openings.
    cursor = 0.0
    for bay in range(bay_count):
        bay_start = bay * MODULE_CM
        bay_end = bay_start + MODULE_CM
        opening = _opening_spec(
            face=face, bay=bay, level=level, door_bay=door_bay, bay_count=bay_count
        )
        # Along-face axis is local +Y after yaw (size.y = run).
        # offset_extra.y shifts the piece along the face from the face origin.
        if opening is None:
            # Should not happen; treat as solid bay fill between plinth/cornice.
            mid_h = STOREY_CM - plinth_h - cornice_h
            _place_shell_box(
                piece_prefix=f"shell_fill_{face}_L{level}_B{bay}",
                asset_id=SHELL_WALL_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(WALL_T_CM, MODULE_CM, mid_h),
                offset_extra=(0.0, bay_start, plinth_h),
                placements=placements,
                counters=counters,
                tags=tags,
            )
            cursor = bay_end
            continue

        kind, open_w, open_h, sill_z = opening
        # Keep opening inside the mid band.
        sill_z = max(plinth_h, sill_z)
        head_z = min(STOREY_CM - cornice_h, sill_z + open_h)
        open_h = max(40.0, head_z - sill_z)
        open_center = bay_start + MODULE_CM * 0.5
        open_y0 = open_center - open_w * 0.5
        open_y1 = open_center + open_w * 0.5

        # Left pier (from previous cursor / bay start to opening).
        left_w = open_y0 - bay_start
        if left_w > 2.0:
            mid_h = STOREY_CM - plinth_h - cornice_h
            _place_shell_box(
                piece_prefix=f"shell_pier_L_{face}_L{level}_B{bay}",
                asset_id=SHELL_WALL_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(WALL_T_CM, left_w, mid_h),
                offset_extra=(0.0, bay_start, plinth_h),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"pier"}),
            )
        # Right pier
        right_w = bay_end - open_y1
        if right_w > 2.0:
            mid_h = STOREY_CM - plinth_h - cornice_h
            _place_shell_box(
                piece_prefix=f"shell_pier_R_{face}_L{level}_B{bay}",
                asset_id=SHELL_WALL_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(WALL_T_CM, right_w, mid_h),
                offset_extra=(0.0, open_y1, plinth_h),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"pier"}),
            )
        # Spandrel under opening (if sill above plinth)
        under_h = sill_z - plinth_h
        if under_h > 2.0:
            _place_shell_box(
                piece_prefix=f"shell_spandrel_{face}_L{level}_B{bay}",
                asset_id=SHELL_WALL_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(WALL_T_CM, open_w, under_h),
                offset_extra=(0.0, open_y0, plinth_h),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"spandrel"}),
            )
        # Lintel over opening (if head below cornice)
        over_h = (STOREY_CM - cornice_h) - (sill_z + open_h)
        if over_h > 2.0:
            _place_shell_box(
                piece_prefix=f"shell_lintel_{face}_L{level}_B{bay}",
                asset_id=SHELL_WALL_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(WALL_T_CM, open_w, over_h),
                offset_extra=(0.0, open_y0, sill_z + open_h),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"lintel"}),
            )

        # Thin opening fill: cream is NOT used — dark sash frame box (visual glass hole).
        if kind == "window":
            _place_shell_box(
                piece_prefix=f"shell_sash_{face}_L{level}_B{bay}",
                asset_id="shell_window_frame",
                face=face,
                level=level,
                cell=origin,
                size_cm=(frame_t, open_w * 0.92, open_h * 0.92),
                offset_extra=(
                    (WALL_T_CM - frame_t) * 0.5,
                    open_y0 + open_w * 0.04,
                    sill_z + open_h * 0.04,
                ),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"window", "opening"}),
                kind="prop",
            )
            _place_window_muntins(
                face=face,
                level=level,
                origin=origin,
                open_center=open_center,
                open_y0=open_y0,
                open_w=open_w,
                open_h=open_h,
                sill_z=sill_z,
                frame_t=frame_t,
                placements=placements,
                counters=counters,
                tags=tags,
            )
        else:
            # Door: thin shell slab inset in the opening (no modular kit z-fight).
            door_t = max(4.0, frame_t)
            _place_shell_box(
                piece_prefix=f"shell_door_{face}_L{level}",
                asset_id=SHELL_DOOR_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(door_t, open_w * 0.94, open_h * 0.98),
                offset_extra=(
                    (WALL_T_CM - door_t) * 0.5,
                    open_y0 + open_w * 0.03,
                    0.0,
                ),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"door", "opening"}),
                kind="prop",
            )
        cursor = bay_end


def _place_continuous_wall(
    *,
    face: str,
    level: int,
    run_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    bays_x: int,
    bays_y: int,
    blind: bool,
) -> None:
    """Party / blind face — plinth + cornice bands match glazed faces for one cream read."""
    if face == "west":
        cell = (0, 0)
    elif face == "east":
        cell = (bays_x, 0)
    elif face == "south":
        cell = (0, 0)
    else:
        cell = (0, bays_y)
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}"})
    if blind:
        tags = tags | frozenset({"party_wall", "blind"})
    plinth_h = STOREY_CM * _PLINTH_FRAC
    cornice_h = STOREY_CM * _CORNICE_FRAC
    mid_h = STOREY_CM - plinth_h - cornice_h
    _place_shell_box(
        piece_prefix=f"shell_plinth_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=cell,
        size_cm=(WALL_T_CM, run_cm, plinth_h),
        offset_extra=(0.0, 0.0, 0.0),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"plinth"}),
    )
    _place_shell_box(
        piece_prefix=f"shell_cornice_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=cell,
        size_cm=(WALL_T_CM, run_cm, cornice_h),
        offset_extra=(0.0, 0.0, STOREY_CM - cornice_h),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"cornice"}),
    )
    _place_shell_box(
        piece_prefix=f"shell_wall_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=cell,
        size_cm=(WALL_T_CM, run_cm, mid_h),
        offset_extra=(0.0, 0.0, plinth_h),
        placements=placements,
        counters=counters,
        tags=tags,
    )


def _place_floor_slab(
    *,
    level: int,
    width_cm: float,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_L{level}"),
            asset_id=SHELL_FLOOR_ASSET,
            kind="floor",
            cell=(0, 0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(width_cm, depth_cm, FLOOR_T_CM),
            tags=_SHELL_TAG | frozenset({"spanning_floor"}),
        )
    )


def _place_stair_hole(
    *,
    level: int,
    hole_cells: Sequence[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    if not hole_cells:
        return
    xs = [c[0] for c in hole_cells]
    ys = [c[1] for c in hole_cells]
    hx, hy = min(xs), min(ys)
    hw = max(xs) - hx + 1
    hh = max(ys) - hy + 1
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_hole_L{level}"),
            asset_id="floor_hole",
            kind="hole",
            cell=(hx, hy),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(hw * MODULE_CM, hh * MODULE_CM, FLOOR_T_CM),
            tags=_SHELL_TAG,
        )
    )


def _place_spanning_floor_deck(
    *,
    level: int,
    width_cm: float,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Upper-storey deck using catalog ``floor`` id so Blender punches holes."""
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_deck_L{level}"),
            asset_id="floor",
            kind="floor",
            cell=(0, 0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(width_cm, depth_cm, FLOOR_T_CM),
            tags=_SHELL_TAG | frozenset({"spanning_floor"}),
        )
    )


def _place_stair(
    *,
    stair_id: str,
    anchor: Tuple[int, int],
    yaw: int,
    level: int,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    from pae.primitives.catalog import catalog_by_id

    cat = catalog_by_id()
    desc = cat.get(stair_id)
    if desc is None:
        return
    sx, sy, sz = desc.size_cm
    ox, oy = rotation_offset_cm(yaw, sx, sy, rotates_about_center=desc.rotates_about_center)
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_stair_L{level}"),
            asset_id=stair_id,
            kind="stair",
            cell=anchor,
            level=level,
            yaw=yaw,
            offset_cm=(ox, oy, 0.0),
            size_cm=desc.size_cm,
            rotates_about_center=desc.rotates_about_center,
            tags=_INTERIOR_TAG | frozenset({"stair"}),
        )
    )


def _place_interior_corridor_wall(
    *,
    level: int,
    inset_cell_x: int,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Single partition inset from the west party line — fully inside the shell."""
    run_cm = depth_cm - 2.0 * WALL_T_CM
    if run_cm < MODULE_CM * 0.5:
        return
    size_cm = (WALL_T_CM, run_cm, STOREY_CM)
    yaw = 0
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_corridor_L{level}"),
            asset_id=SHELL_INTERIOR_WALL_ASSET,
            kind="wall",
            cell=(inset_cell_x, 0),
            level=level,
            yaw=yaw,
            offset_cm=(WALL_T_CM, WALL_T_CM, 0.0),
            size_cm=size_cm,
            tags=_INTERIOR_TAG | frozenset({"partition", "face_west"}),
        )
    )


def _place_pitched_roof(
    *,
    level: int,
    bays_x: int,
    bays_y: int,
    pitch: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    rx0, ry0, rx1, ry1 = 0, 0, bays_x - 1, bays_y - 1
    roof_spans = [(rx0, ry0, rx1, ry1)]
    west, east, south, north = roof_eave_overhang_per_side(
        rx0, ry0, rx1, ry1, roof_spans
    )
    eave_ox, eave_oy, _ = roof_eave_offset_cm(overhang_west=west, overhang_south=south)
    modules_x = bays_x
    modules_y = bays_y
    ridge_along_x = modules_x >= modules_y
    span_x = modules_x * MODULE_CM
    span_y = modules_y * MODULE_CM
    ridge_modules = max(1, min(modules_x, modules_y))
    full_rise = roof_rise_cm(pitch, ridge_modules * MODULE_CM)
    gable_height = full_rise + FLOOR_T_CM
    deck_x = span_x + west + east
    deck_y = span_y + south + north
    roof_z = STOREY_CM

    if ridge_along_x:
        for x in (rx0, rx1):
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_roof_gable"),
                    asset_id="roof_gable_infill",
                    kind="roof",
                    cell=(x, ry0),
                    level=level,
                    yaw=0,
                    offset_cm=(
                        *roof_gable_end_offset_cm(
                            ridge_along_x=True, is_low_end=(x == rx0)
                        )[:2],
                        roof_z,
                    ),
                    size_cm=roof_gable_end_size_cm(
                        ridge_along_x=True,
                        span_x_cm=span_x,
                        span_y_cm=span_y,
                        gable_height=gable_height,
                    ),
                    tags=_SHELL_TAG,
                )
            )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope"),
                asset_id="roof_pitched_slope",
                kind="roof",
                cell=(rx0, ry0),
                level=level,
                yaw=0,
                offset_cm=(eave_ox, eave_oy, roof_z),
                size_cm=(deck_x, deck_y, gable_height),
                tags=_SHELL_TAG,
            )
        )
    else:
        for y in (ry0, ry1):
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_roof_gable"),
                    asset_id="roof_gable_infill",
                    kind="roof",
                    cell=(rx0, y),
                    level=level,
                    yaw=0,
                    offset_cm=(
                        *roof_gable_end_offset_cm(
                            ridge_along_x=False, is_low_end=(y == ry0)
                        )[:2],
                        roof_z,
                    ),
                    size_cm=roof_gable_end_size_cm(
                        ridge_along_x=False,
                        span_x_cm=span_x,
                        span_y_cm=span_y,
                        gable_height=gable_height,
                    ),
                    tags=_SHELL_TAG,
                )
            )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope"),
                asset_id="roof_pitched_slope",
                kind="roof",
                cell=(rx0, ry0),
                level=level,
                yaw=0,
                offset_cm=(eave_ox, eave_oy, roof_z),
                size_cm=(deck_x, deck_y, gable_height),
                tags=_SHELL_TAG,
            )
        )


def _place_chimney_stubs(
    *,
    level: int,
    bays_x: int,
    bays_y: int,
    width_cm: float,
    depth_cm: float,
    style_overrides: dict,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Short masonry stacks on the roof deck — shell boxes, not catalog trim."""
    if not style_overrides.get("shell", {}).get("chimney_stub", False):
        return
    w = MODULE_CM * _CHIMNEY_W_FRAC
    h = STOREY_CM * _CHIMNEY_H_FRAC
    roof_z = STOREY_CM
    tags = _SHELL_TAG | frozenset({"chimney", "roofline"})
    ridge_along_x = bays_x >= bays_y
    if ridge_along_x:
        anchors = [
            (MODULE_CM * 1.1, depth_cm * 0.32),
            (width_cm - MODULE_CM * 1.6, depth_cm * 0.38),
        ]
    else:
        anchors = [
            (width_cm * 0.58, MODULE_CM * 0.9),
            (width_cm * 0.42, depth_cm - MODULE_CM * 1.4),
        ]
    if min(bays_x, bays_y) < 3:
        anchors = anchors[:1]
    for ax, ay in anchors[:2]:
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_chimney"),
                asset_id=SHELL_CHIMNEY_ASSET,
                kind="prop",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(ax, ay, roof_z),
                size_cm=(w, w, h),
                tags=tags,
            )
        )


def _glazed_faces(blind: FrozenSet[str]) -> Tuple[str, ...]:
    """Every non-party face gets punched openings (terrace end walls included)."""
    return tuple(f for f in ("south", "north", "east", "west") if f not in blind)


def build_shell_assembly(
    params: FacadeParams,
    spec: Optional[BuildingSpec] = None,
) -> Tuple[Assembly, Report]:
    """Build a continuous shell :class:`Assembly` from facade sliders."""
    spec = spec or params_to_spec(params)
    bays_x = spec.footprint.bays_x
    bays_y = spec.footprint.bays_y
    storeys = spec.storeys
    wealth = resolve_wealth(params.wealth)
    blind = party_wall_faces(params.row_context)
    style_overrides = params_to_style_overrides(params)
    pitch = float(getattr(spec.roof, "pitch", DEFAULT_ROOF_PITCH) or DEFAULT_ROOF_PITCH)

    width_cm, depth_cm = _footprint_cm(bays_x, bays_y)
    stair_id = resolve_shared("stair", wealth, "main")
    # Prefer straight stair inside shell unless footprint is large enough.
    if stair_id == "stair_switchback" and min(bays_x, bays_y) < 3:
        stair_id = "stair_straight"
    anchor, stair_yaw, stair_cells = _stair_anchor_and_cells(stair_id, bays_x, bays_y)
    door_bay = max(0, min(bays_x - 1, bays_x // 2))
    glazed = _glazed_faces(blind)

    placements: List[SolidPlacement] = []
    counters: Dict[str, int] = {}

    for level in range(storeys):
        if level == 0:
            _place_floor_slab(
                level=level,
                width_cm=width_cm,
                depth_cm=depth_cm,
                placements=placements,
                counters=counters,
            )
        else:
            _place_spanning_floor_deck(
                level=level,
                width_cm=width_cm,
                depth_cm=depth_cm,
                placements=placements,
                counters=counters,
            )
            _place_stair_hole(
                level=level,
                hole_cells=stair_cells,
                placements=placements,
                counters=counters,
            )

        for face in ("west", "east", "south", "north"):
            run_cm = depth_cm if face in ("west", "east") else width_cm
            if face in blind:
                _place_continuous_wall(
                    face=face,
                    level=level,
                    run_cm=run_cm,
                    placements=placements,
                    counters=counters,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    blind=True,
                )
            elif face in glazed:
                _place_glazed_face(
                    face=face,
                    level=level,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    width_cm=width_cm,
                    depth_cm=depth_cm,
                    door_bay=door_bay,
                    placements=placements,
                    counters=counters,
                )
            else:
                _place_continuous_wall(
                    face=face,
                    level=level,
                    run_cm=run_cm,
                    placements=placements,
                    counters=counters,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    blind=False,
                )

        # One inset interior partition only (never an exterior cell grid).
        if bays_x >= 3 and level == 0:
            inset_x = 1 if "west" in blind else min(2, max(1, bays_x - 2))
            _place_interior_corridor_wall(
                level=level,
                inset_cell_x=inset_x,
                depth_cm=depth_cm,
                placements=placements,
                counters=counters,
            )

    for level in range(storeys - 1):
        _place_stair(
            stair_id=stair_id,
            anchor=anchor,
            yaw=stair_yaw,
            level=level,
            placements=placements,
            counters=counters,
        )

    _place_pitched_roof(
        level=storeys - 1,
        bays_x=bays_x,
        bays_y=bays_y,
        pitch=pitch,
        placements=placements,
        counters=counters,
    )
    _place_chimney_stubs(
        level=storeys - 1,
        bays_x=bays_x,
        bays_y=bays_y,
        width_cm=width_cm,
        depth_cm=depth_cm,
        style_overrides=style_overrides,
        placements=placements,
        counters=counters,
    )

    assembly = Assembly(
        placements=placements,
        storeys=storeys,
        building_class=spec.building_class,
        stair_kind=stair_id.replace("stair_", ""),
    )
    return assembly, Report.from_failures([])


def count_exterior_shell_walls(assembly: Assembly) -> int:
    """Count continuous exterior shell wall panels (cream shell boxes on faces)."""
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET and "exterior" in p.tags
    )


def count_modular_window_kits(assembly: Assembly) -> int:
    """Legacy modular wall-window kits must not appear on the shell facade."""
    kit_ids = {
        "wall_window",
        "wall_window_cross",
        "wall_window_mullioned",
        "wall_window_plain",
        "wall_door",
        "wall_door_double",
        "wall_door_plain",
        "wall_door_gothic",
    }
    return sum(1 for p in assembly.placements if p.asset_id in kit_ids)


def count_shell_doors(assembly: Assembly, face: str = "south") -> int:
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_DOOR_ASSET and f"face_{face}" in p.tags
    )


def count_chimney_stubs(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if p.asset_id == SHELL_CHIMNEY_ASSET)


def count_muntin_placements(assembly: Assembly) -> int:
    return sum(
        1 for p in assembly.placements if p.asset_id == SHELL_WINDOW_MUNTIN_ASSET
    )


def count_window_placements(assembly: Assembly, face: str) -> int:
    return sum(
        1
        for p in assembly.placements
        if "window" in p.tags and f"face_{face}" in p.tags
    )


__all__ = [
    "SHELL_CHIMNEY_ASSET",
    "SHELL_DOOR_ASSET",
    "SHELL_FLOOR_ASSET",
    "SHELL_INTERIOR_WALL_ASSET",
    "SHELL_ROOF_ASSET",
    "SHELL_WALL_ASSET",
    "SHELL_WINDOW_MUNTIN_ASSET",
    "build_shell_assembly",
    "count_chimney_stubs",
    "count_exterior_shell_walls",
    "count_modular_window_kits",
    "count_muntin_placements",
    "count_shell_doors",
    "count_window_placements",
    "is_shell_placement",
]

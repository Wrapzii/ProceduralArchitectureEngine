"""Stair occupancy helpers — spiral helix stacks + landing clearance.

Spiral quarters are one helical unit (same tower anchor, complementary yaws,
Z-stacked). Their shared ``covered_cells`` are co-occupancy by design, not a clash.

``stair_landing_clear`` (CRITICAL, fail-closed): no solid wall without door/aperture
may occupy or block landing cells at the top OR bottom of a linear stair flight.
Uses ``covered_cells`` of the stair + landing pads (Handbook 5.1) — never ``p.cell`` alone.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, FLOOR_T_CM, WALL_T_CM, placement_world_aabb
from pae.existence import is_door_or_gate_asset
from pae.report import Failure

SPIRAL_QUARTER_ASSET = "stair_spiral_quarter"
SPIRAL_COMPLEMENTARY_YAWS = frozenset({0, 90, 180, 270})

# Fail-closed slug — not demotable to warning; no suppress tags.
CHECK_STAIR_LANDING_CLEAR = "stair_landing_clear"
CHECK_STAIR_LANDING_STRIP_SCOPE = "stair_landing_strip_scope"
# Legacy alias kept for older test greps during transition.
CHECK_STAIR_LANDING_CLEARANCE = "stair_landing_clearance"

# Landing autofix may only touch cells within this many bays along the stair run axis.
STRIP_AXIS_BUFFER = 1

Cell = Tuple[int, int]

_YAW_TO_FACE = {0: "west", 180: "east", 270: "south", 90: "north"}
_FACE_DELTA = {
    "north": (0, 1),
    "south": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
}


def _yaw_norm(yaw: Union[float, int]) -> int:
    return int(yaw) % 360


def is_spiral_quarter_helix_stack(placements: Sequence[SolidPlacement]) -> bool:
    """True when *placements* are one helical stair stack, not competing stairs.

    Correct model (assemble + primitives notes): four ``stair_spiral_quarter`` at
    yaw 0/90/180/270 share the tower anchor cell and stack in Z. Drum offset can
    make ``covered_cells`` span two bays — still one unit. Allowed when:

    - every piece is ``stair_spiral_quarter``
    - all share the same ``p.cell`` (tower anchor)
    - yaws are distinct and ⊆ {0, 90, 180, 270}
    """
    if len(placements) < 2:
        return False
    if any(p.asset_id != SPIRAL_QUARTER_ASSET for p in placements):
        return False
    anchors = {p.cell for p in placements}
    if len(anchors) != 1:
        return False
    yaws = [_yaw_norm(p.yaw) for p in placements]
    if len(yaws) != len(set(yaws)):
        return False
    return set(yaws) <= SPIRAL_COMPLEMENTARY_YAWS


def spiral_cooccupancy_allowed(occupants: Sequence[SolidPlacement]) -> bool:
    """Cell hosts >1 stair but co-occupancy is the helical stack (not a clash)."""
    return is_spiral_quarter_helix_stack(occupants)


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _placement_aabb(
    p: SolidPlacement,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _is_solid_blocker_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = (p.asset_id or "").lower()
    if is_door_or_gate_asset(aid):
        return False
    if "window" in aid or "arcade" in aid or "arrowslit" in aid:
        return False
    if "opening" in aid or "arch" in aid:
        return False
    return True


def _stair_axis_ends(
    cells: Sequence[Cell],
) -> Optional[Tuple[int, int, int, Cell, Cell]]:
    """Return (axis, other, lo, hi_cell_fn extras) — axis 0=x / 1=y, lo, hi, cross."""
    if len(cells) < 1:
        return None
    xs = {c[0] for c in cells}
    ys = {c[1] for c in cells}
    if len(xs) >= len(ys):
        axis, other = 0, 1
    else:
        axis, other = 1, 0
    lo = min(c[axis] for c in cells)
    hi = max(c[axis] for c in cells)
    cross = sorted({c[other] for c in cells})[0]
    return axis, other, lo, hi, cross


def _cell_at(axis: int, cross: int, v: int) -> Cell:
    return (v, cross) if axis == 0 else (cross, v)


def _face_from_yaw(yaw: int) -> Optional[str]:
    return _YAW_TO_FACE.get(_yaw_norm(yaw))


def _wall_blocks_step(
    wall: SolidPlacement, from_cell: Cell, to_cell: Cell
) -> bool:
    """True when *wall* sits on the shared edge between from_cell and to_cell."""
    face = _face_from_yaw(wall.yaw)
    if face is None:
        return False
    dx, dy = _FACE_DELTA[face]
    cells = covered_cells_safe(wall)
    # Wall on from_cell facing toward to_cell.
    if from_cell in cells:
        if (from_cell[0] + dx, from_cell[1] + dy) == to_cell:
            return True
    # Wall on to_cell facing toward from_cell.
    if to_cell in cells:
        if (to_cell[0] + dx, to_cell[1] + dy) == from_cell:
            return True
    return False


def covered_cells_safe(p: SolidPlacement) -> Set[Cell]:
    from pae.trim import covered_cells

    return set(covered_cells(p))


def landing_strip_zone(
    st: SolidPlacement, pad: Cell, from_c: Cell, to_c: Cell
) -> Set[Cell]:
    """Cells the landing autofix may touch — pad, stair ends, ±buffer along run axis.

    Never spans a full MODULE perpendicular to the run or through the building depth.
    Wide/switchback wells include every cross-bay the stair ``covered_cells`` occupy.
    """
    stair_cells = sorted(covered_cells_safe(st))
    ends = _stair_axis_ends(stair_cells)
    if ends is None:
        return {pad, from_c, to_c}
    axis, other, _lo, _hi, _cross = ends
    cross_vals = sorted({c[other] for c in stair_cells})
    zone: Set[Cell] = set()
    for anchor in (pad, from_c, to_c):
        zone.add(anchor)
        av = anchor[axis]
        for delta in range(-STRIP_AXIS_BUFFER, STRIP_AXIS_BUFFER + 1):
            for cv in cross_vals:
                zone.add(_cell_at(axis, cv, av + delta))
    return zone


def _landing_wall_blocks(
    w: SolidPlacement,
    pad: Cell,
    from_c: Cell,
    to_c: Cell,
    in_floor: bool,
) -> bool:
    """True when *w* is a landing blocker (same rules as ``stair_landing_clear``)."""
    if not _is_solid_blocker_wall(w):
        return False
    w_cells = covered_cells_safe(w)
    on_pad = pad in w_cells
    blocks_interior = in_floor and _wall_blocks_step(w, from_c, to_c)
    return blocks_interior or (on_pad and not in_floor)


def _ascent_delta_from_yaw(yaw: Union[float, int]) -> Optional[Tuple[int, int]]:
    """Grid step from bottom→top along the flight (matches assemble yaw faces)."""
    face = _face_from_yaw(_yaw_norm(yaw))
    if face is None:
        return None
    return _FACE_DELTA[face]


def landing_cells_for_stair(st: SolidPlacement) -> List[Tuple[str, Cell, int, Cell, Cell]]:
    """Landing probes: (name, landing_cell, level, from_cell, to_cell).

    Uses ``covered_cells`` of the stair (Rule 5.1). Pads follow **yaw ascent**,
    not geometric min/max alone — a yaw-270 flight exits toward south even when
    its covered cells extend north to the exterior wall.
    """
    cells = sorted(covered_cells_safe(st))
    if not cells:
        return []
    ends = _stair_axis_ends(cells)
    if ends is None:
        return []
    axis, _other, lo, hi, cross = ends
    geo_lo = _cell_at(axis, cross, lo)
    geo_hi = _cell_at(axis, cross, hi)
    delta = _ascent_delta_from_yaw(st.yaw)
    # Default (unknown / non-cardinal yaw): historic geometric lo→hi ascent.
    if delta is None:
        bottom_end, top_end = geo_lo, geo_hi
    else:
        d_axis = delta[axis]
        if d_axis > 0:
            bottom_end, top_end = geo_lo, geo_hi
        elif d_axis < 0:
            bottom_end, top_end = geo_hi, geo_lo
        else:
            # Ascent perpendicular to long covered axis (wide/switchback odd poses).
            bottom_end, top_end = geo_lo, geo_hi
    bdx = bottom_end[0] - top_end[0]
    bdy = bottom_end[1] - top_end[1]
    # Unit step from top toward bottom along the run (then invert for top pad).
    if abs(bdx) + abs(bdy) == 0:
        return []
    step = (
        0 if bdx == 0 else (1 if bdx > 0 else -1),
        0 if bdy == 0 else (1 if bdy > 0 else -1),
    )
    # bottom_pad = one bay past bottom_end away from top; top_pad past top away from bottom.
    bottom_pad = (bottom_end[0] + step[0], bottom_end[1] + step[1])
    top_pad = (top_end[0] - step[0], top_end[1] - step[1])
    return [
        ("bottom", bottom_pad, st.level, bottom_pad, bottom_end),
        ("top", top_pad, st.level + 1, top_end, top_pad),
    ]


def check_stair_landing_clearance(assembly: Assembly) -> List[Failure]:
    """CRITICAL: solid walls must not block stair landings (top or bottom).

    A wall blocks when it has no door/gate/window/arcade aperture and either:
      * occupies a landing pad with no floor (true solid masonry), or
      * sits on the shared edge between the stair end and the landing pad
        (the 1–2 walls-on-landing regression).

    Spiral quarters skipped — helix exit is ``stair_exit_clearance`` / floor holes.
    Severity is always CRITICAL — no warning demotion, no suppress tags.
    """
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    if not stairs:
        return []

    floors_by_level: Dict[int, Set[Cell]] = {}
    walls_by_level: Dict[int, List[SolidPlacement]] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            floors_by_level.setdefault(p.level, set()).update(covered_cells_safe(p))
        elif p.kind == "wall":
            walls_by_level.setdefault(p.level, []).append(p)

    failures: List[Failure] = []
    seen: Set[Tuple[str, str]] = set()  # (stair_id, wall_id) dedupe

    for st in stairs:
        if st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        for name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            walls = walls_by_level.get(level, [])
            floors = floors_by_level.get(level, set())
            in_floor = pad in floors

            for w in walls:
                if not _landing_wall_blocks(w, pad, from_c, to_c, in_floor):
                    continue
                key = (st.piece_id, w.piece_id)
                if key in seen:
                    continue
                seen.add(key)
                bb_min, bb_max = _placement_aabb(st)
                failures.append(
                    Failure(
                        check=CHECK_STAIR_LANDING_CLEAR,
                        message=(
                            f"stair {st.piece_id} ({st.asset_id}) blocked at its "
                            f"{name} landing — solid wall {w.piece_id} "
                            f"({w.asset_id}) on cell {pad} level {level} "
                            f"has no door/aperture"
                        ),
                        world_xyz=_centre(bb_min, bb_max),
                        piece_id=w.piece_id,
                        critical=True,
                    )
                )
    return failures


def check_stair_landing_strip_scope(assembly: Assembly) -> List[Failure]:
    """CRITICAL: landing blockers outside the strip zone must not be auto-stripped.

    Fires when a solid wall blocks a landing but ``covered_cells`` extend beyond the
    landing pad + stair ends + ``STRIP_AXIS_BUFFER`` along the run axis. The autofix
    refuses to remove such walls (fail-closed) so enclosure masonry two+ bays away survives.
    """
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    if not stairs:
        return []

    floors_by_level: Dict[int, Set[Cell]] = {}
    walls_by_level: Dict[int, List[SolidPlacement]] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            floors_by_level.setdefault(p.level, set()).update(covered_cells_safe(p))
        elif p.kind == "wall":
            walls_by_level.setdefault(p.level, []).append(p)

    failures: List[Failure] = []
    seen: Set[Tuple[str, str]] = set()

    for st in stairs:
        if st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        for name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            zone = landing_strip_zone(st, pad, from_c, to_c)
            in_floor = pad in floors_by_level.get(level, set())
            for w in walls_by_level.get(level, []):
                if not _landing_wall_blocks(w, pad, from_c, to_c, in_floor):
                    continue
                w_cells = covered_cells_safe(w)
                outside = w_cells - zone
                if not outside:
                    continue
                key = (st.piece_id, w.piece_id)
                if key in seen:
                    continue
                seen.add(key)
                bb_min, bb_max = _placement_aabb(st)
                failures.append(
                    Failure(
                        check=CHECK_STAIR_LANDING_STRIP_SCOPE,
                        message=(
                            f"stair {st.piece_id} {name} landing blocker {w.piece_id} "
                            f"spans outside strip zone — cells {sorted(outside)} "
                            f"are >{STRIP_AXIS_BUFFER} bay(s) from pad {pad}; "
                            f"autofix must not strip through the building"
                        ),
                        world_xyz=_centre(bb_min, bb_max),
                        piece_id=w.piece_id,
                        critical=True,
                    )
                )
    return failures


def measure_stair_landing_strip(assembly: Assembly) -> Dict[str, int]:
    """Count landing strip candidates vs stair footprint (fortress diagnostics)."""
    floors_by_level: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            floors_by_level.setdefault(p.level, set()).update(covered_cells_safe(p))

    stair_cells = 0
    candidates = 0
    in_zone = 0
    overscoped = 0

    for st in assembly.placements:
        if st.kind != "stair" or st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        stair_cells += len(covered_cells_safe(st))
        for _name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            zone = landing_strip_zone(st, pad, from_c, to_c)
            in_floor = pad in floors_by_level.get(level, set())
            for w in assembly.placements:
                if w.level != level or not _landing_wall_blocks(
                    w, pad, from_c, to_c, in_floor
                ):
                    continue
                candidates += 1
                w_cells = covered_cells_safe(w)
                if w_cells <= zone:
                    in_zone += 1
                else:
                    overscoped += 1
    return {
        "stair_covered_cells": stair_cells,
        "strip_candidates": candidates,
        "strip_in_zone": in_zone,
        "strip_overscoped": overscoped,
    }


def repair_stair_landing_walls(assembly: Assembly) -> Assembly:
    """Autofix: strip landing-blocking solid walls confined to the landing strip zone.

    Only removes walls whose ``covered_cells`` lie entirely inside
    ``landing_strip_zone`` (pad + stair ends + ``STRIP_AXIS_BUFFER`` along the run
    axis). Long perimeter runs that block a landing but span outside the zone are
    left intact — ``stair_landing_strip_scope`` / ``stair_landing_clear`` fail closed.
    """
    floors_by_level: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            floors_by_level.setdefault(p.level, set()).update(covered_cells_safe(p))

    # Prefer open bay (strip) over wall_door — converting a perimeter face to a
    # door creates aperture_reachability failures (opens onto nothing). Interior
    # party-wall pairs: strip BOTH duplicate skins.
    remove_ids: Set[str] = set()
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    for st in stairs:
        if st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        for _name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            zone = landing_strip_zone(st, pad, from_c, to_c)
            in_floor = pad in floors_by_level.get(level, set())
            for w in assembly.placements:
                if w.level != level:
                    continue
                if not _landing_wall_blocks(w, pad, from_c, to_c, in_floor):
                    continue
                if covered_cells_safe(w) <= zone:
                    remove_ids.add(w.piece_id)

    if not remove_ids:
        return assembly

    new_placements = [
        p for p in assembly.placements if p.piece_id not in remove_ids
    ]
    kept_aps = [
        ap for ap in assembly.apertures if ap.wall_piece_id not in remove_ids
    ]

    return Assembly(
        placements=new_placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=kept_aps,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def make_stair_landing_solid_wall_defect() -> Assembly:
    """Minimal poisoned assembly: straight stair bottom ends in wall-without-floor.

    Handbook §6 can-fire guard — must not rely on milestone false positives.
    """
    stair = SolidPlacement(
        piece_id="poison_stair",
        asset_id="stair_straight",
        kind="stair",
        cell=(5, 5),
        level=0,
        yaw=90,
        offset_cm=(MODULE_CM, 0.0, 0.0),
        size_cm=(MODULE_CM * 2.0, MODULE_CM, STOREY_CM),
        rotates_about_center=False,
        tags=frozenset({"stair"}),
    )
    # South of the run (yaw 90 → along +Y): cell (5, 4) is wall only — no floor.
    wall = SolidPlacement(
        piece_id="poison_wall",
        asset_id="wall_plain",
        kind="wall",
        cell=(5, 4),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, WALL_T_CM, STOREY_CM),
        tags=frozenset({"wall"}),
    )
    return Assembly(placements=[stair, wall], storeys=1)


def make_stair_landing_top_wall_block_defect() -> Assembly:
    """1–2 solid walls on the TOP landing blocking exit onto the floor.

    Matches the user Blender regression: walls on the upper landing pad / exit edge.
    Uses assemble-like north/south boundary offsets so ``covered_cells`` land on
    the stair-end / pad cells (Rule 5.1).
    """
    from pae.contract import rotation_offset_cm

    stair = SolidPlacement(
        piece_id="poison_stair_top",
        asset_id="stair_straight",
        kind="stair",
        cell=(2, 2),
        level=0,
        yaw=90,
        offset_cm=(MODULE_CM, 0.0, 0.0),
        size_cm=(MODULE_CM * 2.0, MODULE_CM, STOREY_CM),
        rotates_about_center=False,
        tags=frozenset({"stair"}),
    )
    # Stair covered cells ≈ (2,2)+(2,3). Top pad (2,4) on level 1 has floor.
    floor = SolidPlacement(
        piece_id="poison_landing_floor",
        asset_id="floor",
        kind="floor",
        cell=(2, 4),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    # Also floor the stair top end so both sides of the exit edge are walkable.
    floor_end = SolidPlacement(
        piece_id="poison_stair_top_floor",
        asset_id="floor",
        kind="floor",
        cell=(2, 3),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    size = (WALL_T_CM, MODULE_CM, STOREY_CM)
    # North wall on boundary cell (2,4) tucked inward — covers (2,3), faces +Y.
    # Same pattern as assemble north perimeter (blocks (2,3)→(2,4)).
    ox_n, oy_n = rotation_offset_cm(90, size[0], size[1])
    wall_a = SolidPlacement(
        piece_id="poison_landing_wall_a",
        asset_id="wall_plain",
        kind="wall",
        cell=(2, 4),
        level=1,
        yaw=90,
        offset_cm=(ox_n, oy_n - WALL_T_CM, 0.0),
        size_cm=size,
        tags=frozenset({"wall"}),
    )
    # Second solid on the pad facing back (south) — duplicate blocker skin.
    ox_s, oy_s = rotation_offset_cm(270, size[0], size[1])
    wall_b = SolidPlacement(
        piece_id="poison_landing_wall_b",
        asset_id="wall_plain",
        kind="wall",
        cell=(2, 4),
        level=1,
        yaw=270,
        offset_cm=(ox_s, oy_s, 0.0),
        size_cm=size,
        tags=frozenset({"wall"}),
    )
    return Assembly(
        placements=[stair, floor, floor_end, wall_a, wall_b], storeys=2
    )


def make_stair_landing_through_wall_defect() -> Assembly:
    """Perimeter wall run blocks the landing but spans outside the strip zone.

    Autofix must NOT strip the full run (would punch a hole through the building).
    """
    from pae.contract import rotation_offset_cm

    base = make_stair_landing_top_wall_block_defect()
    stair = next(p for p in base.placements if p.kind == "stair")
    size = (WALL_T_CM, MODULE_CM * 5.0, STOREY_CM)
    ox, oy = rotation_offset_cm(90, size[0], size[1])
    wall_run = SolidPlacement(
        piece_id="poison_through_wall",
        asset_id="wall_plain",
        kind="wall",
        cell=(0, 4),
        level=1,
        yaw=90,
        offset_cm=(ox, oy - WALL_T_CM, 0.0),
        size_cm=size,
        tags=frozenset({"wall"}),
    )
    placements = [
        p
        for p in base.placements
        if p.piece_id not in ("poison_landing_wall_a", "poison_landing_wall_b")
    ]
    placements.append(wall_run)
    return Assembly(placements=placements, storeys=2)


def make_stair_landing_distant_wall_defect() -> Assembly:
    """Enclosure wall ≥2 bays from the landing pad must survive landing repair."""
    base = make_stair_landing_top_wall_block_defect()
    wall_far = SolidPlacement(
        piece_id="poison_distant_wall",
        asset_id="wall_plain",
        kind="wall",
        cell=(2, 6),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"wall"}),
    )
    return Assembly(
        placements=list(base.placements) + [wall_far], storeys=2
    )


# --- P0 circulation integrity (stair exit / flight / landing) ----------------

CHECK_STAIR_EXIT_INTO_WALL = "stair_exit_into_wall"
CHECK_STAIR_FLIGHT_DIRECTION = "stair_flight_direction_incoherent"
CHECK_STAIR_UNREACHABLE_LANDING = "stair_unreachable_landing"
CHECK_FLOOR_ISLAND = "floor_island"

_FLIGHT_ASSETS = frozenset({"stair_straight", "stair_switchback", "stair_wide"})
_ATRIUM_TAGS = frozenset({"atrium", "designed_atrium", "light_well"})


def _interior_floor_cells(assembly: Assembly) -> Dict[int, Set[Cell]]:
    """Habitable deck cells per level (Rule 5.1 covered_cells; no holes/balconies)."""
    out: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "floor" or "hole" in p.asset_id:
            continue
        tags = set(getattr(p, "tags", ()) or ())
        if tags & frozenset({"balcony", "balcony_deck"}) or "balcony" in p.asset_id:
            continue
        out.setdefault(p.level, set()).update(covered_cells_safe(p))
    return out


def _built_plan_cells(assembly: Assembly, level: int) -> Set[Cell]:
    """Cells that exist in the floor-plan layer (or floor decks as fallback)."""
    layer = assembly.floor_plan.get(level) if assembly.floor_plan else None
    if layer is not None:
        ox, oy = layer.origin_cell
        cells: Set[Cell] = set()
        for ly in range(layer.height):
            for lx in range(layer.width):
                cells.add((ox + lx, oy + ly))
        return cells
    return _interior_floor_cells(assembly).get(level, set())


def check_stair_exit_into_wall(assembly: Assembly) -> List[Failure]:
    """CRITICAL: top of a linear flight must not walk into an exterior/solid wall.

    Catches the manor regression: offset pad flush to the north envelope so the
    yaw-aware top landing sits outside the footprint or behind perimeter masonry.
    Uses covered_cells + yaw ascent (Rule 5.1) — never ``p.cell`` alone.
    """
    floors = _interior_floor_cells(assembly)
    walls_by_level: Dict[int, List[SolidPlacement]] = {}
    for p in assembly.placements:
        if p.kind == "wall":
            walls_by_level.setdefault(p.level, []).append(p)

    failures: List[Failure] = []
    for st in assembly.placements:
        if st.kind != "stair" or st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        if st.asset_id not in _FLIGHT_ASSETS:
            continue
        for name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            if name != "top":
                continue
            built = _built_plan_cells(assembly, level)
            pad_outside = pad not in built
            in_floor = pad in floors.get(level, set())
            blocked = False
            blocker_id = None
            for w in walls_by_level.get(level, []):
                if not _is_solid_blocker_wall(w):
                    continue
                if _wall_blocks_step(w, from_c, to_c) or pad in covered_cells_safe(w):
                    blocked = True
                    blocker_id = w.piece_id
                    break
            # Fail when exit pad is outside the footprint, or a solid wall seals
            # the step onto a non-floored pad (flush exterior).
            if not pad_outside and not (blocked and not in_floor):
                continue
            bb_min, bb_max = _placement_aabb(st)
            failures.append(
                Failure(
                    check=CHECK_STAIR_EXIT_INTO_WALL,
                    message=(
                        f"stair {st.piece_id} ({st.asset_id}) exits into wall/void at "
                        f"top landing pad {pad} level {level} "
                        f"(from {from_c}; blocker={blocker_id or 'outside_footprint'})"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=st.piece_id,
                    critical=True,
                )
            )
    return failures


def check_stair_unreachable_landing(assembly: Assembly) -> List[Failure]:
    """CRITICAL: top landing pad must have walkable floor (or designed atrium tag)."""
    floors = _interior_floor_cells(assembly)
    stair_walkable: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "stair":
            continue
        stair_walkable.setdefault(p.level, set()).update(
            covered_cells_safe(p)
        )
    atrium = any(
        _ATRIUM_TAGS & set(getattr(p, "tags", ()) or ())
        for p in assembly.placements
    )
    failures: List[Failure] = []
    for st in assembly.placements:
        if st.kind != "stair" or st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        if st.asset_id not in _FLIGHT_ASSETS:
            continue
        for name, pad, level, from_c, _to_c in landing_cells_for_stair(st):
            if name != "top":
                continue
            if (
                pad in floors.get(level, set())
                or pad in stair_walkable.get(level, set())
            ):
                continue
            # Stair top storey may be roof-only — still need a deck cell at the pad
            # unless the whole building declares an atrium/light well.
            if atrium:
                continue
            built = _built_plan_cells(assembly, level)
            if pad not in built and level >= assembly.storeys:
                continue
            bb_min, bb_max = _placement_aabb(st)
            failures.append(
                Failure(
                    check=CHECK_STAIR_UNREACHABLE_LANDING,
                    message=(
                        f"stair {st.piece_id} top landing {pad} level {level} has no "
                        f"walkable floor (exit cell {from_c}) — unreachable landing"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=st.piece_id,
                    critical=True,
                )
            )
    return failures


def _flight_ends(st: SolidPlacement) -> Optional[Tuple[Cell, Cell]]:
    """(bottom_end, top_end) cells along yaw ascent."""
    probes = landing_cells_for_stair(st)
    if len(probes) < 2:
        return None
    _bn, _bp, _bl, bottom_pad, bottom_end = probes[0]
    _tn, _tp, _tl, top_end, top_pad = probes[1]
    return bottom_end, top_end


def _cells_adjacent(a: Cell, b: Cell) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1


def _neighbors4(c: Cell) -> List[Cell]:
    x, y = c
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _floor_links_stair_ends(
    lo_top: Cell, hi_bot: Cell, floors: Set[Cell]
) -> bool:
    """True when a floor-connected landing path joins lower exit to upper entry."""
    if lo_top == hi_bot or _cells_adjacent(lo_top, hi_bot):
        return True
    starts = {c for c in _neighbors4(lo_top) if c in floors}
    if lo_top in floors:
        starts.add(lo_top)
    goals = {c for c in _neighbors4(hi_bot) if c in floors}
    if hi_bot in floors:
        goals.add(hi_bot)
    if not starts or not goals:
        return False
    if starts & goals:
        return True
    remaining = set(floors)
    for s in list(starts):
        if s not in remaining and s not in floors:
            continue
        stack = [s]
        seen = {s}
        while stack:
            cur = stack.pop()
            if cur in goals:
                return True
            for n in _neighbors4(cur):
                if n in remaining and n not in seen:
                    seen.add(n)
                    stack.append(n)
    return False


def check_stair_flight_direction_incoherent(assembly: Assembly) -> List[Failure]:
    """CRITICAL: stacked opposite-facing flights need a switchback landing link.

    A 180° yaw flip with laterally offset pads is only legal when the lower
    flight's top end reaches the upper flight's bottom end via adjacent cells or
    a walkable **floor** landing path. Opposite-facing traps fail closed.
    """
    floors = _interior_floor_cells(assembly)
    by_level: Dict[int, List[SolidPlacement]] = {}
    for p in assembly.placements:
        if p.kind != "stair" or p.asset_id not in _FLIGHT_ASSETS:
            continue
        by_level.setdefault(p.level, []).append(p)

    failures: List[Failure] = []
    seen: Set[Tuple[str, str]] = set()
    for level, lower_list in sorted(by_level.items()):
        upper_list = by_level.get(level + 1)
        if not upper_list:
            continue
        landing_floors = floors.get(level + 1, set())
        for lo in lower_list:
            lo_ends = _flight_ends(lo)
            if lo_ends is None:
                continue
            _lo_bot, lo_top = lo_ends
            for hi in upper_list:
                key = (lo.piece_id, hi.piece_id)
                if key in seen:
                    continue
                yaw_delta = abs(_yaw_norm(lo.yaw) - _yaw_norm(hi.yaw)) % 360
                if yaw_delta not in (180,):
                    continue
                hi_ends = _flight_ends(hi)
                if hi_ends is None:
                    continue
                hi_bot, _hi_top = hi_ends
                if _floor_links_stair_ends(lo_top, hi_bot, landing_floors):
                    continue
                seen.add(key)
                bb_min, bb_max = _placement_aabb(hi)
                failures.append(
                    Failure(
                        check=CHECK_STAIR_FLIGHT_DIRECTION,
                        message=(
                            f"stair {hi.piece_id} yaw {hi.yaw} opposite "
                            f"{lo.piece_id} yaw {lo.yaw} without switchback landing "
                            f"(lower exit {lo_top} vs upper entry {hi_bot})"
                        ),
                        world_xyz=_centre(bb_min, bb_max),
                        piece_id=hi.piece_id,
                        critical=True,
                    )
                )
    return failures


def check_floor_islands(assembly: Assembly) -> List[Failure]:
    """CRITICAL: each storey must have one connected habitable floor region.

    Accidental stair VOID slots that bisect the deck into two islands fail.
    Designed atriums opt out via tags ``atrium`` / ``designed_atrium`` / ``light_well``.

    PARTITIONED BY BUILDING. A site holds several buildings, and on a nine-building town
    this reported "storey 1 has 9 disconnected habitable floor islands" — one per house,
    which is exactly what a street IS. Deck connectivity is a WITHIN-building property.
    Same trap the ``freestanding`` check hit; see Handbook §11d.
    """
    markers = sorted(
        {
            t
            for p in assembly.placements
            for t in (getattr(p, "tags", ()) or ())
            if isinstance(t, str) and t.startswith("building:")
        }
    )
    if len(markers) > 1:
        from dataclasses import replace as _replace

        out: List[Failure] = []
        for marker in markers:
            subset = [
                p for p in assembly.placements if marker in (getattr(p, "tags", ()) or ())
            ]
            if len(subset) < 2:
                continue
            try:
                one = _replace(assembly, placements=subset)
            except Exception:
                continue
            out.extend(check_floor_islands(one))
        return out

    if any(
        _ATRIUM_TAGS & set(getattr(p, "tags", ()) or ())
        for p in assembly.placements
    ):
        return []

    floors = _interior_floor_cells(assembly)
    # A tower-room annulus is a separate vertical circulation structure, not a
    # disconnected island of the host building. Keep it visible to landing and
    # reachability checks, but remove it from this one host-deck graph.
    tower_room_cells: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if "tower_room_floor" not in set(getattr(p, "tags", ()) or ()):
            continue
        tower_room_cells.setdefault(p.level, set()).update(
            covered_cells_safe(p)
        )
    floors = {
        level: set(cells) - tower_room_cells.get(level, set())
        for level, cells in floors.items()
    }
    # Stair covered cells are walkable circulation — bridge islands across wells.
    stair_cells: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "stair":
            continue
        stair_cells.setdefault(p.level, set()).update(covered_cells_safe(p))
        # Emergence onto the storey above through the well.
        stair_cells.setdefault(p.level + 1, set()).update(covered_cells_safe(p))

    failures: List[Failure] = []
    for level, cells in sorted(floors.items()):
        if level < 1 or len(cells) < 2:
            continue
        walkable = set(cells) | stair_cells.get(level, set())
        # Flood-fill islands on floor cells only (stair bridges count as adjacency).
        remaining = set(cells)
        islands: List[Set[Cell]] = []
        while remaining:
            start = remaining.pop()
            comp = {start}
            stack = [start]
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    n = (nx, ny)
                    if n in remaining:
                        remaining.remove(n)
                        comp.add(n)
                        stack.append(n)
                    elif n in walkable and n not in cells:
                        # Step onto stair/void bridge then back to floor.
                        for n2x, n2y in (
                            (nx + 1, ny),
                            (nx - 1, ny),
                            (nx, ny + 1),
                            (nx, ny - 1),
                        ):
                            n2 = (n2x, n2y)
                            if n2 in remaining:
                                remaining.remove(n2)
                                comp.add(n2)
                                stack.append(n2)
            islands.append(comp)
        if len(islands) <= 1:
            continue
        # Ignore tiny debris (<2 cells) — balcony scraps / rounding.
        big = [isl for isl in islands if len(isl) >= 2]
        if len(big) <= 1:
            continue
        cx = sum(c[0] for c in cells) / len(cells)
        cy = sum(c[1] for c in cells) / len(cells)
        failures.append(
            Failure(
                check=CHECK_FLOOR_ISLAND,
                message=(
                    f"storey {level} has {len(big)} disconnected habitable floor "
                    f"islands (sizes {[len(i) for i in big]}) — accidental void slot"
                ),
                world_xyz=(cx * MODULE_CM, cy * MODULE_CM, float(level * STOREY_CM)),
                piece_id=None,
                critical=True,
            )
        )
    return failures


def make_stair_exit_into_wall_defect() -> Assembly:
    """Poison: L0 straight flight flush to north exterior — top pad outside / walled."""
    from pae.contract import rotation_offset_cm
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    _, _, base, _ = run_through_assemble(m2_two_storey_stair_spec())
    keep = [p for p in base.placements if p.kind != "stair"]
    sx, sy, sz = (2 * MODULE_CM, MODULE_CM, STOREY_CM)
    yaw = 90
    ox, oy = rotation_offset_cm(yaw, sx, sy, rotates_about_center=False)
    # Covered (1,2),(1,3) → top pad (1,4) outside footprint.
    stair = SolidPlacement(
        piece_id="poison_flush_stair",
        asset_id="stair_straight",
        kind="stair",
        cell=(1, 2),
        level=0,
        yaw=yaw,
        offset_cm=(ox, oy, 0.0),
        size_cm=(sx, sy, sz),
        tags=frozenset({"straight", "stair"}),
    )
    wall = SolidPlacement(
        piece_id="poison_north_wall",
        asset_id="wall_plain",
        kind="wall",
        cell=(1, 4),
        level=1,
        yaw=90,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, WALL_T_CM, STOREY_CM),
        tags=frozenset({"exterior", "wall"}),
    )
    return Assembly(
        placements=keep + [stair, wall],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        storeys=base.storeys,
    )


def make_stair_flight_direction_defect() -> Assembly:
    """Poison: opposite-facing offset flights with no landing link (user screenshot)."""
    from pae.contract import rotation_offset_cm

    sx, sy, sz = (2 * MODULE_CM, MODULE_CM, STOREY_CM)
    ox0, oy0 = rotation_offset_cm(90, sx, sy, rotates_about_center=False)
    ox1, oy1 = rotation_offset_cm(270, sx, sy, rotates_about_center=False)
    # L0 climbs north into (2,1); L1 climbs south from (2,3) — no floor bridge.
    lo = SolidPlacement(
        piece_id="poison_lo",
        asset_id="stair_straight",
        kind="stair",
        cell=(2, 0),
        level=0,
        yaw=90,
        offset_cm=(ox0, oy0, 0.0),
        size_cm=(sx, sy, sz),
        tags=frozenset({"straight", "stair"}),
    )
    hi = SolidPlacement(
        piece_id="poison_hi",
        asset_id="stair_straight",
        kind="stair",
        cell=(2, 2),
        level=1,
        yaw=270,
        offset_cm=(ox1, oy1, 0.0),
        size_cm=(sx, sy, sz),
        tags=frozenset({"straight", "stair"}),
    )
    # Tiny disconnected floor scraps — not a landing path between exits.
    floor_a = SolidPlacement(
        piece_id="poison_floor_a",
        asset_id="floor",
        kind="floor",
        cell=(0, 0),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    floor_b = SolidPlacement(
        piece_id="poison_floor_b",
        asset_id="floor",
        kind="floor",
        cell=(5, 3),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    return Assembly(
        placements=[lo, hi, floor_a, floor_b],
        storeys=3,
    )


def make_floor_island_defect() -> Assembly:
    """Poison: L1 deck split into two islands by a full-depth void slot."""
    from pae.pipeline import run_through_assemble
    from pae.spec import BuildingSpec, CirculationSpec, FootprintSpec, RoofSpec

    spec = BuildingSpec(
        name="poison_floor_slot",
        style="manor",
        footprint=FootprintSpec(kind="rect", bays_x=6, bays_y=4),
        storeys=2,
        storey_use=["hall", "hall"],
        roof=RoofSpec(kind="flat", pitch=0.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        seed=2,
    )
    _, _, base, _ = run_through_assemble(spec)
    # Strip L1 floors in the middle column so left/right islands remain.
    survivors = []
    for p in base.placements:
        if p.level == 1 and p.kind == "floor" and "hole" not in p.asset_id:
            cells = covered_cells_safe(p)
            if any(c[0] in (2, 3) for c in cells):
                # Drop middle decks / shrink — keep only non-middle cells via skip.
                continue
        survivors.append(p)
    # Explicit left + right islands
    left = SolidPlacement(
        piece_id="island_left",
        asset_id="floor",
        kind="floor",
        cell=(0, 0),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(2 * MODULE_CM, 4 * MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    right = SolidPlacement(
        piece_id="island_right",
        asset_id="floor",
        kind="floor",
        cell=(4, 0),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(2 * MODULE_CM, 4 * MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    return Assembly(
        placements=survivors + [left, right],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        storeys=2,
    )


__all__ = [
    "CHECK_STAIR_LANDING_CLEAR",
    "CHECK_STAIR_LANDING_STRIP_SCOPE",
    "CHECK_STAIR_LANDING_CLEARANCE",
    "CHECK_STAIR_EXIT_INTO_WALL",
    "CHECK_STAIR_FLIGHT_DIRECTION",
    "CHECK_STAIR_UNREACHABLE_LANDING",
    "CHECK_FLOOR_ISLAND",
    "SPIRAL_QUARTER_ASSET",
    "STRIP_AXIS_BUFFER",
    "check_stair_landing_clearance",
    "check_stair_exit_into_wall",
    "check_stair_flight_direction_incoherent",
    "check_stair_unreachable_landing",
    "check_floor_islands",
    "make_stair_exit_into_wall_defect",
    "make_stair_flight_direction_defect",
    "make_floor_island_defect",
    "check_stair_landing_clearance",
    "check_stair_landing_strip_scope",
    "is_spiral_quarter_helix_stack",
    "landing_cells_for_stair",
    "landing_strip_zone",
    "make_stair_landing_distant_wall_defect",
    "make_stair_landing_solid_wall_defect",
    "make_stair_landing_through_wall_defect",
    "make_stair_landing_top_wall_block_defect",
    "measure_stair_landing_strip",
    "repair_stair_landing_walls",
    "spiral_cooccupancy_allowed",
]

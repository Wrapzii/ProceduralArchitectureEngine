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


def landing_cells_for_stair(st: SolidPlacement) -> List[Tuple[str, Cell, int, Cell, Cell]]:
    """Landing probes: (name, landing_cell, level, from_cell, to_cell).

    Uses ``covered_cells`` of the stair (Rule 5.1). Bottom pad is one bay before
    the low end on the stair level; top pad is one bay past the high end on level+1.
    """
    cells = sorted(covered_cells_safe(st))
    if not cells:
        return []
    ends = _stair_axis_ends(cells)
    if ends is None:
        return []
    axis, _other, lo, hi, cross = ends
    bottom_end = _cell_at(axis, cross, lo)
    top_end = _cell_at(axis, cross, hi)
    bottom_pad = _cell_at(axis, cross, lo - 1)
    top_pad = _cell_at(axis, cross, hi + 1)
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


__all__ = [
    "CHECK_STAIR_LANDING_CLEAR",
    "CHECK_STAIR_LANDING_STRIP_SCOPE",
    "CHECK_STAIR_LANDING_CLEARANCE",
    "SPIRAL_QUARTER_ASSET",
    "STRIP_AXIS_BUFFER",
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

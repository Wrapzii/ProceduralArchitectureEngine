"""Stair occupancy helpers — spiral helix stacks + landing clearance.

Spiral quarters are one helical unit (same tower anchor, complementary yaws,
Z-stacked). Their shared ``covered_cells`` are co-occupancy by design, not a clash.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple, Union

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM, placement_world_aabb
from pae.report import Failure

SPIRAL_QUARTER_ASSET = "stair_spiral_quarter"
SPIRAL_COMPLEMENTARY_YAWS = frozenset({0, 90, 180, 270})

Cell = Tuple[int, int]


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


def check_stair_landing_clearance(assembly: Assembly) -> List[Failure]:
    """A stair must not dead-end into solid (wall without floor) at either end.

    WHY: ``stair_exit_clearance`` only checks the void ABOVE a flight. This check
    covers the two ends.

    FALSE POSITIVES (D-18 triage):
    - Perimeter bays carry BOTH wall and floor — the wall sits on the outer face;
      treating any wall-tagged neighbor as solid masonry flags every stairwell that
      abuts an enclosure wall (m2/m3/m8/school).
    - ``stair_spiral_quarter``: drum-offset ``covered_cells`` are not a linear run;
      axis-extension into the body bay is meaningless. Helix exit is
      ``stair_exit_clearance`` / floor holes. Skip spiral quarters here.
    - Switchback/wide wells: enclosure walls on one axis are normal when the well
      opens onto floor on another side; wall+floor at the axis end is not a dead-end.

    Rule (Handbook 5.1): beyond each end of a linear stair footprint, the target
    cell is blocked only when it has a wall and **no** floor (true solid).
    Wall+floor = walkable perimeter bay.
    """
    from pae.trim import covered_cells

    stairs = [p for p in assembly.placements if p.kind == "stair"]
    if not stairs:
        return []

    walls_by_level: Dict[int, Set[Cell]] = {}
    floors_by_level: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind == "wall":
            walls_by_level.setdefault(p.level, set()).update(covered_cells(p))
        elif p.kind == "floor" and "hole" not in p.asset_id:
            floors_by_level.setdefault(p.level, set()).update(covered_cells(p))

    failures: List[Failure] = []
    for st in stairs:
        # Helix has no linear run ends — skip (see module docstring).
        if st.asset_id == SPIRAL_QUARTER_ASSET:
            continue
        cells = sorted(covered_cells(st))
        if len(cells) < 2:
            continue
        xs = {c[0] for c in cells}
        ys = {c[1] for c in cells}
        if len(xs) >= len(ys):
            axis, other = 0, 1
        else:
            axis, other = 1, 0
        lo = min(c[axis] for c in cells)
        hi = max(c[axis] for c in cells)
        cross = sorted({c[other] for c in cells})[0]

        def cell_at(v: int) -> Cell:
            return (v, cross) if axis == 0 else (cross, v)

        ends = (
            ("bottom", cell_at(lo - 1), st.level),
            ("top", cell_at(hi + 1), st.level + 1),
        )
        for name, target, level in ends:
            in_wall = target in walls_by_level.get(level, set())
            in_floor = target in floors_by_level.get(level, set())
            # Wall + floor = perimeter bay (walkable). Solid = wall without floor.
            blocked = in_wall and not in_floor
            if not blocked:
                continue
            bb_min, bb_max = _placement_aabb(st)
            failures.append(
                Failure(
                    check="stair_landing_clearance",
                    message=(
                        f"stair {st.piece_id} ({st.asset_id}) runs into a wall at its "
                        f"{name} end - cell {target} on level {level} is solid"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=st.piece_id,
                    # Warning until remaining true positives are triaged (D-18).
                    critical=False,
                )
            )
    return failures


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

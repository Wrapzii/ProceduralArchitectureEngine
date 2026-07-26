"""Multi-storey stair wells: no orphan opening beside the flights, one shaft.

Regression for the "every 3+ storey building has a hole next to the stairs and the
flights look randomly placed" defect. The plan reserves a whole well (e.g. 2x4) but a
flight only occupies 1x2, so upper decks used to punch the ENTIRE reserved well.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

import pytest

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM
from pae.pipeline import run_through_assemble
from pae.plan import CellRole
from pae.spec import m2_two_storey_stair_spec
from pae.sketch import sketch_to_spec
from pae.stair_occupancy import (
    CHECK_STAIR_SHAFT_CONTINUITY,
    CHECK_STAIR_WELL_HOLE_SCOPE,
    check_stair_shaft_continuity,
    check_stair_well_hole_scope,
)
from pae.trim import covered_cells
from pae.validate import validate

SKETCH_3 = """
########
########
########
####S###
########
"""

SKETCH_4 = """
#########
#########
#########
####S####
#########
"""


def _build(sketch: str, storeys: int, style: str = "townhouse"):
    spec = sketch_to_spec(
        sketch, name=f"well_{storeys}", style=style, storeys=storeys, seed=7
    )
    _massing, _plan, assembly, report = run_through_assemble(spec)
    assert assembly is not None, [f.check for f in report.critical][:6]
    return assembly


def _stair_cells_by_level(assembly: Assembly) -> Dict[int, Set[Tuple[int, int]]]:
    out: Dict[int, Set[Tuple[int, int]]] = {}
    for p in assembly.placements:
        if p.kind == "stair":
            out.setdefault(p.level, set()).update(covered_cells(p))
    return out


def _orphan_hole_cells(assembly: Assembly) -> List[Tuple[int, Tuple[int, int]]]:
    stair_cells = _stair_cells_by_level(assembly)
    orphans: List[Tuple[int, Tuple[int, int]]] = []
    for p in assembly.placements:
        if p.kind != "floor" or "hole" not in p.asset_id:
            continue
        cells = covered_cells(p)
        served = stair_cells.get(p.level, set()) | stair_cells.get(p.level - 1, set())
        if not (cells & served):
            continue  # genuine void, not a stair well
        for c in sorted(cells - served):
            orphans.append((p.level, c))
    return orphans


@pytest.mark.parametrize(
    "sketch,storeys,style",
    [
        (SKETCH_3, 3, "townhouse"),
        (SKETCH_3, 3, "keep"),
        (SKETCH_4, 4, "townhouse"),
        (SKETCH_4, 5, "manor"),
    ],
)
def test_no_orphan_hole_beside_stairs(sketch, storeys, style):
    assembly = _build(sketch, storeys, style)
    assert _orphan_hole_cells(assembly) == []
    assert check_stair_well_hole_scope(assembly) == []


@pytest.mark.parametrize("storeys", [3, 4])
def test_flights_form_one_shaft(storeys):
    sketch = SKETCH_3 if storeys == 3 else SKETCH_4
    assembly = _build(sketch, storeys)
    assert check_stair_shaft_continuity(assembly) == []


@pytest.mark.parametrize("storeys", [3, 4])
def test_reserved_well_cells_are_floored_not_void(storeys):
    """Well cells no flight uses must be walkable landing deck."""
    sketch = SKETCH_3 if storeys == 3 else SKETCH_4
    assembly = _build(sketch, storeys)
    stair_cells = _stair_cells_by_level(assembly)

    floors: Dict[int, Set[Tuple[int, int]]] = {}
    holes: Dict[int, Set[Tuple[int, int]]] = {}
    for p in assembly.placements:
        if p.kind != "floor":
            continue
        bucket = holes if "hole" in p.asset_id else floors
        bucket.setdefault(p.level, set()).update(covered_cells(p))

    # For every level above ground, a cell that is neither a flight footprint nor
    # served head-room must not be a bare gap: it is floor.
    for level in range(1, storeys):
        served = stair_cells.get(level, set()) | stair_cells.get(level - 1, set())
        for c in holes.get(level, set()) - served:
            assert c in floors.get(level, set()), (
                f"level {level} cell {c} is an unserved opening with no floor"
            )


def test_check_flags_synthetic_over_punched_well():
    """The check must FAIL on the old pattern (hole spanning the whole 2x4 well)."""
    stair = SolidPlacement(
        piece_id="stair_L0",
        asset_id="stair_straight",
        kind="stair",
        cell=(4, 1),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM * 2, 350.0),
        tags=frozenset({"building:lot_a"}),
    )
    over_punched = SolidPlacement(
        piece_id="floor_hole_L1",
        asset_id="floor_hole",
        kind="floor",
        cell=(4, 1),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        # 2 bays wide x 4 long = the whole reserved well, not the 1x2 flight.
        size_cm=(MODULE_CM * 2, MODULE_CM * 4, FLOOR_T_CM),
        tags=frozenset({"building:lot_a"}),
    )
    fails = check_stair_well_hole_scope(
        Assembly(placements=[stair, over_punched])
    )
    assert fails, "over-punched stair well must be CRITICAL"
    assert all(f.critical for f in fails)
    assert fails[0].check == CHECK_STAIR_WELL_HOLE_SCOPE


def test_check_flags_scattered_flights():
    """Detached upper flight must be CRITICAL (the 'random placement' symptom)."""
    lower = SolidPlacement(
        piece_id="stair_L0",
        asset_id="stair_straight",
        kind="stair",
        cell=(1, 1),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM * 2, 350.0),
        tags=frozenset({"building:lot_a"}),
    )
    upper = SolidPlacement(
        piece_id="stair_L1",
        asset_id="stair_straight",
        kind="stair",
        cell=(8, 7),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM * 2, 350.0),
        tags=frozenset({"building:lot_a"}),
    )
    fails = check_stair_shaft_continuity(Assembly(placements=[lower, upper]))
    assert fails, "detached flights must be CRITICAL"
    assert fails[0].check == CHECK_STAIR_SHAFT_CONTINUITY


def test_separate_buildings_are_not_compared():
    """Two lots on one site each have their own shaft — not a continuity failure."""
    a = SolidPlacement(
        piece_id="a_stair_L0",
        asset_id="stair_straight",
        kind="stair",
        cell=(1, 1),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM * 2, 350.0),
        tags=frozenset({"building:lot_a"}),
    )
    b = SolidPlacement(
        piece_id="b_stair_L1",
        asset_id="stair_straight",
        kind="stair",
        cell=(30, 30),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM * 2, 350.0),
        tags=frozenset({"building:lot_b"}),
    )
    assert check_stair_shaft_continuity(Assembly(placements=[a, b])) == []


_INTERIOR_FLOOR_ROLES = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
        CellRole.SERVICE,
    }
)


def _solid_floor_cells(assembly: Assembly) -> Dict[int, Set[Tuple[int, int]]]:
    out: Dict[int, Set[Tuple[int, int]]] = {}
    for p in assembly.placements:
        if p.kind != "floor" or "hole" in p.asset_id:
            continue
        out.setdefault(p.level, set()).update(covered_cells(p))
    return out


def _missing_adjacent_interior_floor(
    assembly: Assembly, plan
) -> List[Tuple[int, Tuple[int, int]]]:
    """Interior neighbours of a straight flight that have no solid floor slab."""
    floors = _solid_floor_cells(assembly)
    missing: List[Tuple[int, Tuple[int, int]]] = []
    for st in assembly.placements:
        if st.kind != "stair" or st.asset_id != "stair_straight":
            continue
        level = st.level
        if level + 1 >= len(plan.storeys):
            continue
        upper = level + 1
        grid = plan.storeys[upper]
        for cx, cy in covered_cells(st):
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                role = grid.get(nx, ny)
                if role not in _INTERIOR_FLOOR_ROLES:
                    continue
                if (nx, ny) in floors.get(upper, set()):
                    continue
                missing.append((upper, (nx, ny)))
    return missing


@pytest.mark.parametrize("storeys", [3, 4])
def test_adjacent_interior_cells_have_solid_upper_floor_sketch(storeys):
    sketch = SKETCH_3 if storeys == 3 else SKETCH_4
    _, plan, assembly, _ = run_through_assemble(
        sketch_to_spec(
            sketch,
            name=f"well_{storeys}",
            style="townhouse",
            storeys=storeys,
            seed=7,
        )
    )
    missing = _missing_adjacent_interior_floor(assembly, plan)
    assert missing == [], f"missing solid floor beside stair: {missing}"


def test_adjacent_interior_cells_have_solid_upper_floor_m2():
    _, plan, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    missing = _missing_adjacent_interior_floor(assembly, plan)
    assert missing == [], f"missing solid floor beside stair: {missing}"


def test_adjacent_interior_cells_have_solid_upper_floor_manor():
    sketch = "\n".join(["######", "######", "##S###", "######"])
    spec = sketch_to_spec(sketch, name="manor_well", style="manor", storeys=3, seed=7)
    _, plan, assembly, _ = run_through_assemble(spec)
    missing = _missing_adjacent_interior_floor(assembly, plan)
    assert missing == [], f"missing solid floor beside stair: {missing}"


@pytest.mark.parametrize("storeys", [3, 4])
def test_full_validate_reports_no_stair_well_criticals(storeys):
    sketch = SKETCH_3 if storeys == 3 else SKETCH_4
    assembly = _build(sketch, storeys)
    _checked, report = validate(assembly)
    bad = [
        f.check
        for f in report.critical
        if f.check in (CHECK_STAIR_WELL_HOLE_SCOPE, CHECK_STAIR_SHAFT_CONTINUITY)
    ]
    assert bad == []

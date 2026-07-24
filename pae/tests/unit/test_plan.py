"""Unit tests — floor plan + circulation (§5.2–5.3)."""

from __future__ import annotations

from pae.plan import CellRole, plan
from pae.solver import solve
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    m1_box_house_spec,
)


def test_m1_plan_cells():
    spec = m1_box_house_spec()
    massing, mreport = solve(spec)
    assert mreport.ok is True
    fp, preport = plan(massing)
    assert preport.ok is True
    assert fp is not None
    assert len(fp.storeys) == 1
    grid = fp.storeys[0]
    interiorish = [
        c
        for c, r in grid.cells.items()
        if r in (CellRole.INTERIOR, CellRole.WALL_LINE, CellRole.DOOR, CellRole.STAIR)
    ]
    # 4×3 footprint = 12 cells
    assert len(interiorish) == 12
    assert len(fp.door_cells) == 1
    assert len(fp.window_cells) == 2
    assert fp.ground_slab is True
    assert grid.get(*fp.door_cells[0]) == CellRole.DOOR


def test_stair_graph_two_storey():
    spec = BuildingSpec(
        name="two_up",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "dormitory"],
        roof=RoofSpec(kind="flat"),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=1, windows_ground=2),
        seed=2,
        ground_slab=True,
    )
    massing, mreport = solve(spec)
    assert mreport.ok is True
    assert massing is not None
    assert len(massing.stair_cells) >= 2  # straight run spans 2 modules

    fp, preport = plan(massing)
    assert preport.ok is True, [f.message for f in preport.failures]
    assert fp is not None
    assert len(fp.storeys) == 2

    # Ground has STAIR cells; level above has VOID over them.
    ground = fp.storeys[0]
    upper = fp.storeys[1]
    stair_on_ground = [
        c for c, r in ground.cells.items() if r == CellRole.STAIR
    ]
    assert len(stair_on_ground) >= 1
    for c in stair_on_ground:
        assert upper.get(*c) == CellRole.VOID

    # Circulation: every upper node reachable from ground.
    ground_nodes = [n for n in fp.circulation.nodes if n[0] == 0]
    assert ground_nodes
    reachable = set()
    for g in ground_nodes:
        reachable |= fp.circulation.connected_from(g)
    upper_nodes = [n for n in fp.circulation.nodes if n[0] == 1]
    assert upper_nodes
    for node in upper_nodes:
        assert node in reachable


def test_plan_rejects_when_stair_missing_on_tiny_footprint():
    # 1×1 footprint cannot host a 2-module straight stair.
    spec = BuildingSpec(
        name="tiny",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=1, bays_y=1),
        storeys=2,
        storey_use=["a", "b"],
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
    )
    massing, mreport = solve(spec)
    # Solver should fail: cannot place stair for upper storey.
    assert mreport.ok is False
    assert any(f.check == "stair_serves_upper" for f in mreport.failures)

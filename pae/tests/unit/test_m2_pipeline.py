"""Milestone 2 — two storeys, straight stair, floor hole, reachability."""

from __future__ import annotations

from pae.assemble import assemble
from pae.contract import MODULE_CM, STOREY_CM, placement_world_aabb
from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble
from pae.solver import solve
from pae.spec import (
    load_spec,
    load_style,
    m1_box_house_spec,
    m2_two_storey_stair_dict,
    m2_two_storey_stair_spec,
)
from pae.validate import validate


def _m2_assembly():
    spec = m2_two_storey_stair_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly, floor_plan, massing


def test_m2_factory_fields():
    spec = m2_two_storey_stair_spec()
    assert spec.name == "m2_two_storey_stair"
    assert spec.storeys == 2
    assert spec.footprint.bays_x == 4
    assert spec.footprint.bays_y == 3
    assert spec.circulation.stair_kind == "straight"


def test_m2_factory_dict_round_trip():
    spec, report = load_spec(m2_two_storey_stair_dict())
    assert report.ok is True
    assert spec is not None
    assert spec.storeys == 2


def test_m2_plan_stair_void_and_graph():
    _, floor_plan, massing = _m2_assembly()
    assert len(massing.stair_cells) == 2
    ground = floor_plan.storeys[0]
    upper = floor_plan.storeys[1]
    stair_cells = [c for c, r in ground.cells.items() if r == CellRole.STAIR]
    assert len(stair_cells) == 2
    for cell in stair_cells:
        assert upper.get(*cell) == CellRole.VOID
    reachable = set()
    for g in [n for n in floor_plan.circulation.nodes if n[0] == 0]:
        reachable |= floor_plan.circulation.connected_from(g)
    for node in [n for n in floor_plan.circulation.nodes if n[0] == 1]:
        assert node in reachable


def test_m2_assemble_stair_and_floor_hole():
    assembly, floor_plan, _ = _m2_assembly()
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    holes = [p for p in assembly.placements if p.asset_id == "floor_hole"]
    assert len(stairs) == 1
    assert stairs[0].asset_id == "stair_straight"
    assert stairs[0].level == 0
    # The void bays are OPEN — asserted on cells, not on how many rectangles the
    # emitter needed to cover them (a 1x2 well is one placement, not two).
    from pae.trim import covered_cells

    hole_cells: set = set()
    for p in holes:
        hole_cells |= covered_cells(p)
    void_cells = {
        c for c, r in floor_plan.storeys[1].cells.items() if r == CellRole.VOID
    }
    assert hole_cells == void_cells
    upper_solids = {
        p.cell
        for p in assembly.placements
        if p.level == 1 and p.kind == "floor" and p.asset_id == "floor"
    }
    # Spanning deck at origin (walls carry the span); holes punch the void bays.
    assert upper_solids == {(0, 0)}
    deck = next(
        p
        for p in assembly.placements
        if p.level == 1 and p.asset_id == "floor"
    )
    assert deck.size_cm[0] > MODULE_CM
    assert deck.size_cm[1] > MODULE_CM


def test_m2_east_north_boundary_unchanged():
    """Regression — §2.3 east/north wall cells must stay on x1+1 / y1+1."""
    assembly, _, _ = _m2_assembly()
    east_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 180}
    north_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 90}
    assert east_cells == {(4, 0), (4, 1), (4, 2)}
    assert north_cells == {(0, 3), (1, 3), (2, 3), (3, 3)}
    assert (3, 0) not in east_cells
    assert (0, 2) not in north_cells


def test_m2_stair_spans_two_modules():
    assembly, _, _ = _m2_assembly()
    stair = next(p for p in assembly.placements if p.kind == "stair")
    bb_min, bb_max = placement_world_aabb(
        stair.cell[0],
        stair.cell[1],
        stair.level,
        stair.yaw,
        stair.size_cm,
        stair.offset_cm,
        rotates_about_center=stair.rotates_about_center,
    )
    assert abs(bb_max[2] - STOREY_CM) < 1.0
    assert abs((bb_max[1] - bb_min[1]) - 2 * MODULE_CM) < 1.0


def test_m2_validate_passes_end_to_end():
    spec = m2_two_storey_stair_spec()
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True, [f.message for f in report.critical]
    assert report.critical == []


def test_m1_still_passes_after_m2_changes():
    """M1 must not regress when M2 assembly rules land."""
    spec = m1_box_house_spec()
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []

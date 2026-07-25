"""Milestone 4 — L / U / courtyard plans (§11 M4)."""

from __future__ import annotations

from pae.assemble import assemble
from pae.contract import MODULE_CM, placement_world_aabb
from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble
from pae.solver import solve
from pae.spec import (
    load_spec,
    load_style,
    m1_box_house_spec,
    m4_courtyard_dict,
    m4_courtyard_spec,
    m4_l_plan_dict,
    m4_l_plan_spec,
    m4_u_plan_dict,
    m4_u_plan_spec,
)
from pae.validate import validate


def _assembly_from_spec(spec):
    massing, mreport = solve(spec)
    assert mreport.ok is True, [f.message for f in mreport.failures]
    assert massing is not None
    floor_plan, preport = plan(massing)
    assert preport.ok is True, [f.message for f in preport.failures]
    assert floor_plan is not None
    style, _ = load_style(spec.style)
    assembly, areport = assemble(floor_plan, None, style)
    assert areport.ok is True, [f.message for f in areport.failures]
    return assembly, floor_plan, massing


def test_m4_factory_fields():
    lspec = m4_l_plan_spec()
    assert lspec.name == "m4_l_plan"
    assert lspec.footprint.kind == "L"
    assert lspec.footprint.bays_x == 8
    assert lspec.footprint.wing_depth == 2

    uspec = m4_u_plan_spec()
    assert uspec.footprint.kind == "U"

    cspec = m4_courtyard_spec()
    assert cspec.footprint.kind == "courtyard"
    assert cspec.footprint.courtyard is True


def test_m4_factory_dict_round_trips():
    for factory in (m4_l_plan_dict, m4_u_plan_dict, m4_courtyard_dict):
        spec, report = load_spec(factory())
        assert report.ok is True
        assert spec is not None
        assert spec.storeys == 1


def test_m4_l_solver_non_overlapping_wings():
    massing, report = solve(m4_l_plan_spec())
    assert report.ok is True
    assert massing is not None
    enclosed = massing.enclosed_volumes()
    assert len(enclosed) == 2
    for i, a in enumerate(enclosed):
        for b in enclosed[i + 1 :]:
            assert not a.overlaps(b)


def test_m4_u_solver_non_overlapping_wings():
    massing, report = solve(m4_u_plan_spec())
    assert report.ok is True
    assert massing is not None
    enclosed = massing.enclosed_volumes()
    assert len(enclosed) == 3
    for i, a in enumerate(enclosed):
        for b in enclosed[i + 1 :]:
            assert not a.overlaps(b)


def test_m4_courtyard_role_outside_envelope():
    massing, report = solve(m4_courtyard_spec())
    assert report.ok is True
    assert massing is not None
    courts = [v for v in massing.volumes if v.role == "courtyard"]
    assert len(courts) == 1
    enclosed_cells = set()
    for v in massing.enclosed_volumes():
        enclosed_cells |= v.cells()
    assert not (courts[0].cells() & enclosed_cells)


def test_m4_courtyard_plan_marks_courtyard_cells():
    massing, _ = solve(m4_courtyard_spec())
    fp, report = plan(massing)
    assert report.ok is True
    assert fp is not None
    court = {
        c for c, r in fp.storeys[0].cells.items() if r == CellRole.COURTYARD
    }
    assert len(court) == 16
    interior = {
        c
        for c, r in fp.storeys[0].cells.items()
        if r in (CellRole.INTERIOR, CellRole.WALL_LINE)
    }
    assert court.isdisjoint(interior)


def test_m4_l_inner_reentrant_walls_placed():
    assembly, floor_plan, _ = _assembly_from_spec(m4_l_plan_spec())
    grid = floor_plan.storeys[0]
    reentrant = {
        c
        for c, r in grid.cells.items()
        if r == CellRole.WALL_LINE
        and any(
            grid.get(c[0] + dx, c[1] + dy) == CellRole.EXTERIOR
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        )
    }
    wall_cells = {p.cell for p in assembly.placements if p.kind == "wall"}
    assert reentrant.issubset(wall_cells), sorted(reentrant - wall_cells)[:6]


def test_m4_courtyard_inner_walls_and_no_roof_over_hole():
    assembly, floor_plan, _ = _assembly_from_spec(m4_courtyard_spec())
    grid = floor_plan.storeys[0]
    court = {c for c, r in grid.cells.items() if r == CellRole.COURTYARD}
    inner_faces = {
        c
        for c, r in grid.cells.items()
        if r == CellRole.WALL_LINE
        and any(
            grid.get(c[0] + dx, c[1] + dy) == CellRole.COURTYARD
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        )
    }
    wall_cells = {p.cell for p in assembly.placements if p.kind == "wall"}
    assert len(inner_faces) == 16
    assert inner_faces.issubset(wall_cells)

    for p in assembly.placements:
        if p.kind in ("floor", "roof", "ground"):
            assert p.cell not in court

    roofs = [p for p in assembly.placements if p.kind == "roof"]
    assert len(roofs) == 4
    cx, cy = 3, 3
    wx, wy = cx * MODULE_CM, cy * MODULE_CM
    for r in roofs:
        bb_min, bb_max = placement_world_aabb(
            r.cell[0],
            r.cell[1],
            r.level,
            r.yaw,
            r.size_cm,
            r.offset_cm,
        )
        covers = (
            bb_min[0] <= wx
            and bb_min[1] <= wy
            and bb_max[0] >= wx + MODULE_CM
            and bb_max[1] >= wy + MODULE_CM
        )
        assert not covers


def test_m4_l_validate_end_to_end():
    _, _, assembly, stage_report = run_through_assemble(m4_l_plan_spec())
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []


def test_m4_courtyard_validate_end_to_end():
    _, _, assembly, stage_report = run_through_assemble(m4_courtyard_spec())
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []


def test_m4_u_validate_end_to_end():
    _, _, assembly, stage_report = run_through_assemble(m4_u_plan_spec())
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []


def test_m1_south_gap_and_roof_tuck_regression():
    """M4 inner walls must not regress M1 south corner or E/N roof tuck."""
    spec = m1_box_house_spec()
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True
    south = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 270}
    assert (0, 0) in south
    east = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 180}
    north = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 90}
    assert east == {(4, 0), (4, 1), (4, 2)}
    assert north == {(0, 3), (1, 3), (2, 3), (3, 3)}
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []

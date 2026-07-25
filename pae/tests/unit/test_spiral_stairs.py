"""Phase 3.1 — spiral tower stairs (solver → plan → assemble)."""

from __future__ import annotations

from pae.contract import MODULE_CM, STOREY_CM
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.plan import CellRole, plan
from pae.primitives.catalog import get as get_primitive
from pae.solver import solve
from pae.spec import m_spiral_tower_spec, school_academy_dict, school_academy_spec
from pae.spec import load_spec
from pae.trim import covered_cells
from pae.validate import validate, _check_stair_exit_clearance


def _spiral_assembly():
    spec = m_spiral_tower_spec()
    massing, mreport = solve(spec)
    assert mreport.ok, [f.message for f in mreport.failures]
    assert massing is not None
    assert massing.stair_cells == [(-1, 0)]
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]
    assert floor_plan is not None
    _, _, assembly, areport = run_through_assemble(spec)
    assert areport.ok, [f.message for f in areport.failures]
    return assembly, floor_plan, massing


def test_spiral_solver_places_single_tower_cell():
    spec = m_spiral_tower_spec()
    massing, report = solve(spec)
    assert report.ok
    assert massing is not None
    assert len(massing.stair_cells) == 1
    tower = next(v for v in massing.volumes if v.role == "tower")
    assert massing.stair_cells[0] == (tower.x0, tower.y0)


def test_spiral_plan_marks_stair_and_void_well():
    _, floor_plan, massing = _spiral_assembly()
    cell = massing.stair_cells[0]
    assert floor_plan.storeys[0].get(*cell) == CellRole.STAIR
    assert floor_plan.storeys[1].get(*cell) == CellRole.VOID


def test_spiral_emits_four_quarters_per_storey_climb():
    assembly, floor_plan, massing = _spiral_assembly()
    spirals = [p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"]
    climbs = len(floor_plan.storeys) - 1
    assert climbs >= 1
    assert len(spirals) == 4 * climbs
    quarter = get_primitive("stair_spiral_quarter")
    quarter_rise = quarter.size_cm[2]
    stair_cell = tuple(massing.stair_cells[0])
    for level in range(climbs):
        level_pieces = [p for p in spirals if p.level == level]
        assert len(level_pieces) == 4
        assert {p.yaw for p in level_pieces} == {0, 90, 180, 270}
        assert {p.cell for p in level_pieces} == {stair_cell}
        assert all(p.rotates_about_center for p in level_pieces)
        z_offs = sorted(p.offset_cm[2] for p in level_pieces)
        assert z_offs == [0.0, quarter_rise, 2 * quarter_rise, 3 * quarter_rise]


def test_spiral_stair_reachability_and_exit_clearance():
    spec = m_spiral_tower_spec()
    massing, mreport = solve(spec)
    assert mreport.ok
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]
    assert not any(f.check == "stair_reachability" for f in preport.failures)

    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok, [f.message for f in stage_report.failures]
    exit_fails = _check_stair_exit_clearance(assembly)
    assert not exit_fails, [f.message for f in exit_fails]


def test_spiral_validate_interpenetration_with_tower_arcs_is_warning_only():
    """Spiral wedges occupy the same drum cell as tower_arc quarters — non-critical."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    _, vreport = validate(assembly)
    interpen = [f for f in vreport.failures if f.check == "interpenetration"]
    assert interpen
    assert all(not f.critical for f in interpen)
    assert not vreport.critical, [f.message for f in vreport.critical]


def test_spiral_without_tower_rejected_for_auto_placement():
    data = school_academy_dict()
    data["circulation"]["stair_kind"] = "spiral"
    spec, report = load_spec(data)
    assert spec is not None
    assert report.ok
    massing, sreport = solve(spec)
    assert massing is None
    assert not sreport.ok
    assert any(f.check == "stair_kind" for f in sreport.failures)


def test_spiral_school_spec_parses_but_solver_requires_tower():
    spiral_spec = school_academy_spec()
    spiral_spec.circulation.stair_kind = "spiral"
    massing, sreport = solve(spiral_spec)
    assert massing is None
    assert any("tower" in f.message for f in sreport.failures)


def test_spiral_quarter_covered_cells_include_stair_anchor():
    """Rule 5.1: stair anchor cell must lie inside each quarter's covered_cells."""
    assembly, _, massing = _spiral_assembly()
    cell = tuple(massing.stair_cells[0])
    spirals = [p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"]
    for p in spirals[:4]:
        cells = covered_cells(p)
        assert cell in cells
        assert len(cells) <= 2  # drum-offset wedge may kiss an adjacent bay


def test_spiral_exit_holes_match_covered_cells():
    """Rule 5.1: floor_hole on storey above must cover every stair exit bay."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    holes = [p for p in assembly.placements if p.asset_id == "floor_hole"]
    hole_by_level: dict[int, set[tuple[int, int]]] = {}
    for h in holes:
        hole_by_level.setdefault(h.level, set()).update(covered_cells(h))

    for stair in assembly.placements:
        if stair.asset_id != "stair_spiral_quarter":
            continue
        top = stair.level + 1
        exit_cells = covered_cells(stair)
        assert exit_cells <= hole_by_level.get(top, set()), (
            f"stair L{stair.level} exit {exit_cells} missing holes at L{top}"
        )


def test_spiral_exit_clearance_green():
    spec = m_spiral_tower_spec()
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok, [f.message for f in stage_report.failures]
    exit_fails = _check_stair_exit_clearance(assembly)
    assert not exit_fails, [f.message for f in exit_fails]


def test_spiral_trim_path_passes_validate():
    _, _, _, stage_report = run_through_validate_trim(m_spiral_tower_spec())
    assert stage_report.ok, [f.message for f in stage_report.critical]

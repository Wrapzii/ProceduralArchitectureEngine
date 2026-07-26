"""RoomSpec + double-height hall (Phase 2.1 / 2.4)."""

from __future__ import annotations

from enum import Enum

from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.solver import solve
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    RoomSpec,
    load_spec,
    school_academy_dict,
    school_academy_spec,
)
from pae.validate import _check_room_specs, _cell_role_is, validate


def _hall_inner_cells_at_level(massing, level: int) -> set[tuple[int, int]]:
    """Hall interior cells excluding the perimeter gallery ring."""
    hall = next(v for v in massing.volumes if v.role == "hall")
    floor_plan, _ = plan(massing)
    grid = floor_plan.storeys[level]
    inner: set[tuple[int, int]] = set()
    for x, y in hall.cells():
        role = grid.get(x, y)
        if role in (CellRole.WALL_LINE, CellRole.STAIR, CellRole.DOOR):
            continue
        if any(
            grid.get(x + dx, y + dy) == CellRole.WALL_LINE
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        ):
            continue
        inner.add((x, y))
    return inner


def _count_double_void(assembly) -> int:
    return sum(
        1
        for layer in assembly.floor_plan.values()
        for row in layer.cells
        for role in row
        if _cell_role_is(role, CellRole.DOUBLE_VOID)
    )


def test_room_spec_loader_round_trip():
    raw = school_academy_dict()
    assert raw["rooms"]
    assert any(r["double_height"] for r in raw["rooms"])
    spec, report = load_spec(raw)
    assert report.ok, [f.message for f in report.failures]
    assert len(spec.rooms) == 2
    hall = next(r for r in spec.rooms if r.kind == "hall")
    assert hall.double_height is True
    assert hall.name == "great_hall"


def test_double_height_hall_marks_l1_double_void():
    spec = school_academy_spec()
    massing, mreport = solve(spec)
    assert mreport.ok
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]

    inner = _hall_inner_cells_at_level(massing, 1)
    assert inner, "expected inner hall cells at L1"
    level1 = floor_plan.storeys[1]
    for cell in inner:
        assert level1.get(*cell) == CellRole.DOUBLE_VOID, (
            f"inner hall cell {cell} role={level1.get(*cell).name}"
        )

    hall = next(v for v in massing.volumes if v.role == "hall")
    gallery = {
        (x, y)
        for x, y in hall.cells()
        if level1.get(x, y) == CellRole.INTERIOR
    }
    assert gallery, "expected gallery INTERIOR ring at L1"
    assert any(
        role == CellRole.DOUBLE_VOID for role in level1.cells.values()
    ), "expected DOUBLE_VOID cells after double-height carve"


def test_double_height_hall_no_l1_solid_floor():
    spec = school_academy_spec()
    massing, _ = solve(spec)
    inner = _hall_inner_cells_at_level(massing, 1)
    _, _, assembly, _ = run_through_assemble(spec)

    level = 1
    # Cells OPENED, not hole pieces: a rectangular well is one spanning placement.
    from pae.trim import covered_cells

    holes: set = set()
    for p in assembly.placements:
        if p.level == level and p.asset_id == "floor_hole":
            holes |= covered_cells(p)
    assert inner <= holes, f"missing holes for {inner - holes}"

    _, report = validate(assembly)
    assert not any(f.check == "double_height_no_floor" for f in report.failures)


def test_double_height_validate_no_solid_floor_under_void():
    spec = school_academy_spec()
    _, _, assembly, _ = run_through_assemble(spec)
    _, report = validate(assembly)
    assert not any(
        f.check == "double_height_no_floor" for f in report.failures
    ), [(f.check, f.message) for f in report.failures]


def test_school_academy_still_validates_with_double_height_hall():
    spec = school_academy_spec()
    _m, _p, assembly, report = run_through_validate_trim(spec)
    assert report.ok, [(f.check, f.message) for f in report.critical]
    assert report.critical == []
    assert assembly.room_specs
    assert any(r.get("double_height") for r in assembly.room_specs)
    assert _count_double_void(assembly) > 0
    assert not any(
        f.check == "room_spec" and f.critical for f in report.failures + report.critical
    )
    assert not any(
        f.check == "stair_reachability" for f in report.failures + report.critical
    ), [(f.check, f.message) for f in report.failures if f.check == "stair_reachability"]


def test_double_height_factory_without_rooms_unchanged():
    """Non-school spec without rooms must not invent DOUBLE_VOID cells."""
    spec = BuildingSpec(
        name="m2_box",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
    )
    massing, _ = solve(spec)
    floor_plan, preport = plan(massing)
    assert preport.ok
    for grid in floor_plan.storeys:
        assert CellRole.DOUBLE_VOID not in grid.cells.values()


def test_double_height_carve_fail_closed_without_volume():
    """double_height RoomSpec with unmapped kind must fail plan, not silently skip."""
    spec = BuildingSpec(
        name="orphan_dh",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        rooms=[RoomSpec(name="ghost_hall", kind="observatory", double_height=True)],
    )
    massing, _ = solve(spec)
    massing.rooms = list(spec.rooms)
    floor_plan, preport = plan(massing)
    assert floor_plan is None
    assert any(f.check == "double_height_carve" for f in preport.failures), [
        (f.check, f.message) for f in preport.failures
    ]


def test_room_spec_double_height_uses_role_value_not_identity():
    """Stale CellRole enums (reload_pae pollution) must not false-fail room_spec."""

    class StaleCellRole(Enum):
        EXTERIOR = 0
        INTERIOR = 1
        WALL_LINE = 2
        DOOR = 3
        STAIR = 4
        VOID = 5
        COURTYARD = 6
        CORRIDOR = 7
        CLASSROOM = 8
        DOUBLE_VOID = 9
        ROOM = 10
        HALL = 11
        SERVICE = 12
        ARCADE = 13

    assert StaleCellRole.DOUBLE_VOID is not CellRole.DOUBLE_VOID
    assert StaleCellRole.DOUBLE_VOID != CellRole.DOUBLE_VOID
    assert _cell_role_is(StaleCellRole.DOUBLE_VOID, CellRole.DOUBLE_VOID)

    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    # Rewrite layer cells to the stale enum twin so identity equality fails.
    for layer in assembly.floor_plan.values():
        for ly, row in enumerate(layer.cells):
            for lx, role in enumerate(row):
                layer.cells[ly][lx] = StaleCellRole(role.value)

    fresh_void = any(
        role == CellRole.DOUBLE_VOID
        for layer in assembly.floor_plan.values()
        for row in layer.cells
        for role in row
    )
    assert not fresh_void, "identity compare must fail against stale enum cells"
    assert _count_double_void(assembly) > 0

    failures = _check_room_specs(assembly)
    critical = [f for f in failures if f.critical and f.check == "room_spec"]
    assert critical == [], [(f.message) for f in critical]


def test_room_spec_double_height_still_critical_when_voids_absent():
    """Value compare must remain fail-closed when DOUBLE_VOID is truly missing."""
    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    for layer in assembly.floor_plan.values():
        for ly, row in enumerate(layer.cells):
            for lx, role in enumerate(row):
                if _cell_role_is(role, CellRole.DOUBLE_VOID):
                    layer.cells[ly][lx] = CellRole.INTERIOR
    failures = _check_room_specs(assembly)
    critical = [f for f in failures if f.critical and f.check == "room_spec"]
    assert critical, "expected critical room_spec when double_height has no voids"
    assert any("DOUBLE_VOID" in f.message for f in critical)


def test_reload_pae_does_not_false_fail_school_room_spec():
    """Regression: openings-proof reload_pae left stale validate CellRole imports."""
    from pae.blender_build import reload_pae
    from pae.validate import _check_room_specs as stale_check

    reload_pae()
    from pae.pipeline import run_through_assemble as rta
    from pae.spec import school_academy_spec as sas

    _, _, assembly, _ = rta(sas())
    failures = stale_check(assembly)
    critical = [f for f in failures if f.critical and f.check == "room_spec"]
    assert critical == [], [(f.message) for f in critical]
    assert _count_double_void(assembly) > 0

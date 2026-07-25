"""Phase 2.3 — corridor circulation spine reaches stairs."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.assemble import assemble
from pae.plan import (
    CellRole,
    _corridor_component_reaches_stair,
    plan,
)
from pae.pipeline import run_through_assemble
from pae.solver import solve
from pae.spec import load_style, school_academy_spec
from pae.validate import (
    _cell_role_is,
    _check_classroom_corridor_connectivity,
    _check_corridor_stair_connectivity,
    validate,
)


def _corridor_reaches_stair_on_level(grid, stair_xy) -> bool:
    corr = {
        (x, y)
        for (x, y), role in grid.cells.items()
        if _cell_role_is(role, CellRole.CORRIDOR)
    }
    goals = {
        (x, y)
        for (x, y) in stair_xy
        if _cell_role_is(grid.get(x, y), CellRole.STAIR)
        or _cell_role_is(grid.get(x, y), CellRole.VOID)
    }
    return _corridor_component_reaches_stair(corr, goals, grid) if corr else False


def test_school_corridor_spine_reaches_stairs_on_every_storey():
    spec = school_academy_spec()
    massing, mreport = solve(spec)
    assert mreport.ok
    floor_plan, preport = plan(massing)
    assert preport.ok, [(f.check, f.message) for f in preport.failures]
    assert floor_plan.corridor_cells
    assert floor_plan.classroom_cells
    for grid in floor_plan.storeys:
        assert _corridor_reaches_stair_on_level(grid, massing.stair_cells), (
            f"level {grid.level}: corridor must adjoin stair/void well"
        )


def test_school_corridor_stair_validate_critical_empty():
    spec = school_academy_spec()
    _, _, assembly, _ = run_through_assemble(spec)
    stair_fails = _check_corridor_stair_connectivity(assembly)
    assert stair_fails == []
    class_fails = _check_classroom_corridor_connectivity(assembly)
    assert class_fails == []
    _, report = validate(assembly)
    assert not any(
        f.check in ("corridor_stair", "classroom_corridor", "room_spec") and f.critical
        for f in report.failures + report.critical
    )


def test_corridor_stair_fails_when_spine_severed():
    """If corridor cells exist but are isolated from the stair well, fail closed."""
    spec = school_academy_spec()
    massing, _ = solve(spec)
    floor_plan, preport = plan(massing)
    assert preport.ok
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    assert _check_corridor_stair_connectivity(assembly) == []

    # Blank every CORRIDOR cell that is not in the classroom wing (hall spine),
    # leaving wing corridors orphaned from the stair well.
    stair_xy = set(massing.stair_cells)
    for level, layer in assembly.floor_plan.items():
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if not _cell_role_is(role, CellRole.CORRIDOR):
                    continue
                cx, cy = ox + lx, oy + ly
                # Demote corridor cells that sit in the hall (near stairs) or on the
                # bridge — keep only cells far from the well so the check trips.
                if abs(cx - 1) + abs(cy - 1) <= 8:
                    layer.cells[ly][lx] = CellRole.INTERIOR

    fails = _check_corridor_stair_connectivity(assembly)
    assert fails, "orphaned wing corridor must fail corridor_stair"
    assert all(f.check == "corridor_stair" and f.critical for f in fails)


def test_spine_helper_links_wing_corridor_without_stairs_is_noop():
    """Single-storey school: corridor program still carves; corridor_stair skips."""
    spec1 = replace(school_academy_spec(), storeys=1, storey_use=["classroom"])
    m1, mr = solve(spec1)
    assert mr.ok
    fp, pr = plan(m1)
    assert pr.ok
    assert fp.corridor_cells
    assert fp.classroom_cells
    _, _, assembly, _ = run_through_assemble(spec1)
    assert _check_corridor_stair_connectivity(assembly) == []
    assert _check_classroom_corridor_connectivity(assembly) == []


def test_cell_role_is_still_value_compare_for_corridor():
    """Preserve VAL_ROOMS _cell_role_is contract for corridor roles too."""

    class StaleCellRole:
        CORRIDOR = type("E", (), {"value": 7})()
        CLASSROOM = type("E", (), {"value": 8})()
        DOUBLE_VOID = type("E", (), {"value": 9})()

    assert _cell_role_is(StaleCellRole.CORRIDOR, CellRole.CORRIDOR)
    assert _cell_role_is(StaleCellRole.CLASSROOM, CellRole.CLASSROOM)
    assert _cell_role_is(StaleCellRole.DOUBLE_VOID, CellRole.DOUBLE_VOID)

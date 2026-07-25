"""Monumental multi-storey stairs must shift by stair width — never stack in XY."""

from __future__ import annotations

from dataclasses import replace

from pae.assemble import _monumental_flight_pads
from pae.assembly_types import Assembly
from pae.pipeline import run_through_assemble
from pae.spec import school_academy_spec
from pae.trim import covered_cells
from pae.validate import _check_stair_flight_stack, validate


def test_school_switchback_flights_are_laterally_offset():
    """3-storey academy: L0 and L1 switchbacks must not share covered cells."""
    massing, _, assembly, _ = run_through_assemble(school_academy_spec())
    assert len(massing.stair_cells) >= 8, massing.stair_cells
    pads = _monumental_flight_pads(massing.stair_cells)
    assert pads is not None
    pad0, pad1 = pads
    assert not (set(pad0) & set(pad1))

    switchbacks = [
        p for p in assembly.placements if p.asset_id == "stair_switchback"
    ]
    by_level = {p.level: p for p in switchbacks}
    assert 0 in by_level and 1 in by_level
    low = covered_cells(by_level[0])
    high = covered_cells(by_level[1])
    assert low == set(pad0)
    assert high == set(pad1)
    assert not (low & high)


def test_school_stair_flight_stack_check_is_clean():
    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    assert _check_stair_flight_stack(assembly) == []
    _, report = validate(assembly)
    assert not any(f.check == "stair_flight_stack" for f in report.critical)


def test_stacked_same_xy_flights_fire_stair_flight_stack():
    """Deliberately stack two switchbacks in the same cells — check must fire."""
    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    switchbacks = [
        p for p in assembly.placements if p.asset_id == "stair_switchback"
    ]
    assert len(switchbacks) >= 2
    lower = next(p for p in switchbacks if p.level == 0)
    poisoned = []
    for p in assembly.placements:
        if p.asset_id == "stair_switchback" and p.level == 1:
            poisoned.append(
                replace(p, cell=lower.cell, offset_cm=lower.offset_cm, yaw=lower.yaw)
            )
        else:
            poisoned.append(p)

    bad = Assembly(
        placements=poisoned,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(assembly.room_specs),
        building_class=assembly.building_class,
        stair_kind=assembly.stair_kind,
        wide_stair_well_available=assembly.wide_stair_well_available,
    )
    hits = _check_stair_flight_stack(bad)
    assert hits, "stacked same-XY monumental flights must be reported"
    assert all(f.check == "stair_flight_stack" and f.critical for f in hits)

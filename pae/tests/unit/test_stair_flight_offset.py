"""Monumental multi-storey stairs must shift by stair width — never stack in XY.

Verification contract (must not regress):
1. Happy path — school switchback + industrial wide offset pads
2. Can-fire — deliberately stacked same-XY flights → critical ``stair_flight_stack``
3. Assemble fail-closed — 2×2 well on 3+ storeys emits ``stair_flight_stack``
4. Property — random multi-storey monumental specs never stack
"""

from __future__ import annotations

import random
from dataclasses import replace

from pae.assemble import _monumental_flight_pads, assemble
from pae.assembly_types import Assembly
from pae.pipeline import run_through_assemble
from pae.plan import plan as plan_floor
from pae.solver import Massing, Volume, solve
from pae.spec import industrial_workshop_spec, school_academy_spec
from pae.trim import covered_cells
from pae.validate import _check_stair_flight_stack, validate


MONUMENTAL = frozenset({"stair_switchback", "stair_wide", "stair_straight"})


def _monumental_by_level(assembly: Assembly) -> dict:
    out = {}
    for p in assembly.placements:
        if p.asset_id in MONUMENTAL:
            out.setdefault(p.level, []).append(p)
    return out


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


def test_industrial_wide_flights_are_laterally_offset():
    """Industrial 3-storey wide stairs also shift — not only school switchbacks."""
    massing, _, assembly, _ = run_through_assemble(industrial_workshop_spec())
    assert massing.stair_kind == "wide"
    assert len(massing.stair_cells) >= 8
    pads = _monumental_flight_pads(massing.stair_cells)
    assert pads is not None
    by_level = _monumental_by_level(assembly)
    assert 0 in by_level and 1 in by_level
    low = covered_cells(by_level[0][0])
    high = covered_cells(by_level[1][0])
    assert low == set(pads[0])
    assert high == set(pads[1])
    assert not (low & high)
    assert _check_stair_flight_stack(assembly) == []


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
    assert "shift by stair width" in hits[0].message

    _, report = validate(bad)
    assert any(
        f.check == "stair_flight_stack" and f.critical for f in report.critical
    ), "validate() must surface stair_flight_stack as critical"


def test_undersized_2x2_well_on_three_storeys_fails_closed_at_assemble():
    """Explicit 2×2 stair_cells + 3 storeys must not silently stack — assemble critical."""
    hall = Volume(
        id="hall",
        x0=0,
        y0=0,
        x1=8,
        y1=6,
        storeys=3,
        role="hall",
        entrance=True,
    )
    massing = Massing(
        volumes=[hall],
        entrance_volume_id="hall",
        storeys=3,
        seed=42,
        stair_kind="switchback",
        stair_cells=[(1, 1), (2, 1), (1, 2), (2, 2)],
    )
    floor_plan, _ = plan_floor(massing)
    _assembly, areport = assemble(floor_plan, asset_db=None, style=None)
    stack_fails = [f for f in areport.failures if f.check == "stair_flight_stack"]
    assert stack_fails, (
        "assemble must emit stair_flight_stack when climbing ≥2 flights "
        "inside a single 2×2 pad"
    )
    assert all(f.critical for f in stack_fails)


def test_random_monumental_multi_storey_never_stacks(seed_count: int = 40):
    """Property: random 3–4 storey switchback/wide builds never stair_flight_stack."""
    from pae.tests.property.spec_factory import random_building_spec

    stacked = []
    checked = 0
    for i in range(seed_count * 3):
        if checked >= seed_count:
            break
        rng = random.Random(10_000 + i)
        spec = random_building_spec(rng)
        if spec.storeys < 3:
            continue
        if spec.circulation.stair_kind not in ("switchback", "wide"):
            # Force monumental when footprint can host it.
            spec = replace(
                spec,
                circulation=replace(
                    spec.circulation,
                    stair_kind="switchback",
                    stair_cells=[],
                ),
                building_class="academy",
            )
        massing, mreport = solve(spec)
        if massing is None or not mreport.ok:
            continue
        if massing.stair_kind not in ("switchback", "wide"):
            continue
        if len(massing.stair_cells) < 8:
            # Solver could not expand — should fail closed at assemble, not stack.
            floor_plan, _ = plan_floor(massing)
            assembly, areport = assemble(floor_plan, asset_db=None, style=None)
            if any(f.check == "stair_flight_stack" and f.critical for f in areport.failures):
                checked += 1
                continue
            stacked.append(("undersized_silent", spec.seed, massing.stair_cells))
            checked += 1
            continue
        _, _, assembly, _ = run_through_assemble(spec)
        hits = _check_stair_flight_stack(assembly)
        by_level = _monumental_by_level(assembly)
        levels = sorted(by_level)
        for a, b in zip(levels, levels[1:]):
            for lo in by_level[a]:
                for hi in by_level[b]:
                    if covered_cells(lo) & covered_cells(hi):
                        stacked.append(("cell_overlap", spec.seed, lo.piece_id, hi.piece_id))
        if hits:
            stacked.append(("check_fire", spec.seed, [f.message for f in hits]))
        checked += 1

    assert checked >= 8, f"too few monumental multi-storey samples: {checked}"
    assert not stacked, f"stair_flight_stack regressions: {stacked[:5]}"


def test_fortress_gatehouse_straight_flights_are_laterally_offset():
    """3-storey straight hall: L0/L1 must not share cells or yaw (D3-3)."""
    from dataclasses import replace

    from pae.spec import BuildingSpec, CirculationSpec, FootprintSpec, RoofSpec

    spec = BuildingSpec(
        name="straight_hall_3",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=8, bays_y=5),
        storeys=3,
        storey_use=["hall"] * 3,
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        seed=99,
        ground_slab=True,
        building_class="house",
    )
    massing, _, assembly, _ = run_through_assemble(spec)
    assert massing.stair_kind == "straight"
    assert len(massing.stair_cells) >= 8, massing.stair_cells
    pads = _monumental_flight_pads(massing.stair_cells)
    assert pads is not None

    straights = [p for p in assembly.placements if p.asset_id == "stair_straight"]
    by_level = {p.level: p for p in straights}
    assert 0 in by_level and 1 in by_level
    low = covered_cells(by_level[0])
    high = covered_cells(by_level[1])
    assert not (low & high), "stacked straight flights must shift pads"
    assert by_level[0].yaw != by_level[1].yaw, "alternate yaw required for straight pads"
    assert _check_stair_flight_stack(assembly) == []


def test_fortress_gatehouse_offset_stairs_link_stair_graph():
    """6×4×3 gatehouse: offset pads must pass plan stair_graph (D3-3)."""
    from pae.spec import fortress_gatehouse_spec
    from pae.solver import solve
    from pae.plan import plan as plan_floor

    spec = fortress_gatehouse_spec()
    massing, mreport = solve(spec)
    assert mreport.ok, [f.message for f in mreport.failures]
    assert len(massing.stair_cells) >= 8
    _, prep = plan_floor(massing)
    graph_fails = [f for f in prep.failures if f.check == "stair_graph"]
    assert graph_fails == [], [f.message for f in graph_fails]
    _, _, assembly, areport = run_through_assemble(spec)
    assert areport.ok, [f.message for f in areport.failures]
    assert _check_stair_flight_stack(assembly) == []

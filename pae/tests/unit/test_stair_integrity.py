"""Stair integrity — the defects a person sees immediately and no check caught.

USER-REPORTED, from renders:
  "still seeing single piece staircases outside that should be inside"
  "it looks like it went to place 2 different facing staircases for the same spot"
  "still have staircases that start or end into walls!!!!"

All three are real and are reproduced below. These tests are FAILING ON PURPOSE: they are
the target for the stair lanes, not a claim that the engine is clean. Do not weaken them to
get green — fix the placement.

Owning lanes: @RM_SPIRAL (overlap + outside envelope), stair solver (landing clearance).
"""

from __future__ import annotations

from collections import defaultdict

import pytest

import pae.spec as spec_mod
from pae.pipeline import run_through_assemble
from pae.trim import covered_cells
from pae.validate import validate

STAIR_SPECS = [
    "m2_two_storey_stair_spec",
    "m3_keep_tower_spec",
    "m8_entrances_spec",
    "school_academy_spec",
    "m_spiral_tower_spec",
]


def _assembly(name):
    factory = getattr(spec_mod, name, None)
    if factory is None:
        pytest.skip(f"{name} not defined")
    _, _, assembly, report = run_through_assemble(factory())
    if assembly is None or not report.ok:
        pytest.skip(f"{name} does not assemble cleanly")
    return assembly


def _stairs(assembly):
    return [p for p in assembly.placements if p.kind == "stair"]


@pytest.mark.parametrize("name", STAIR_SPECS)
def test_no_two_stairs_occupy_the_same_cell(name):
    """Four spiral quarters at yaw 0/90/180/270 on the SAME cells is not a helix.

    Same defect class as the old tower-arc scatter: quarters that should share a centre
    and stack vertically instead sit on top of one another.
    """
    assembly = _assembly(name)
    occupied = defaultdict(list)
    for p in _stairs(assembly):
        for c in covered_cells(p):
            occupied[(p.level, c)].append(f"{p.asset_id}@yaw{p.yaw}")
    clashes = {k: v for k, v in occupied.items() if len(v) > 1}
    assert not clashes, (
        f"{len(clashes)} cell(s) host more than one stair: "
        + "; ".join(f"L{k[0]}{k[1]}={v}" for k, v in list(clashes.items())[:4])
    )


@pytest.mark.parametrize("name", STAIR_SPECS)
def test_stairs_are_inside_the_building(name):
    """A stair outside the wall envelope is an external fire escape nobody asked for."""
    assembly = _assembly(name)
    walls = set()
    for p in assembly.placements:
        if p.kind == "wall":
            walls |= covered_cells(p)
    if not walls:
        pytest.skip("no walls")
    xs = [c[0] for c in walls]
    ys = [c[1] for c in walls]
    outside = []
    for p in _stairs(assembly):
        for c in covered_cells(p):
            if not (min(xs) <= c[0] <= max(xs) and min(ys) <= c[1] <= max(ys)):
                outside.append((p.piece_id, c))
                break
    assert not outside, f"{len(outside)} stair(s) outside the envelope: {outside[:4]}"


@pytest.mark.parametrize("name", STAIR_SPECS)
def test_stairs_do_not_run_into_walls(name):
    """`stair_exit_clearance` checks the void ABOVE a flight, never its two ends."""
    assembly = _assembly(name)
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == "stair_landing_clearance"]
    assert not hits, (
        f"{len(hits)} stair end(s) blocked by a wall:\n  "
        + "\n  ".join(f.message for f in hits[:4])
    )


def test_stair_landing_clearance_check_can_fire():
    """Guard against the check silently becoming a no-op (Handbook 6)."""
    found = False
    for name in STAIR_SPECS:
        factory = getattr(spec_mod, name, None)
        if factory is None:
            continue
        _, _, assembly, report = run_through_assemble(factory())
        if assembly is None or not report.ok:
            continue
        _, vreport = validate(assembly)
        if any(f.check == "stair_landing_clearance" for f in vreport.failures):
            found = True
            break
    assert found, "stair_landing_clearance never fires — it may have become a no-op"

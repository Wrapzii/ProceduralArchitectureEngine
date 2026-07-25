"""Stair typology by building_class — compact house vs monumental industrial/academy."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.assembly_types import Assembly, SolidPlacement
from pae.pipeline import run_through_assemble
from pae.spec import (
    COMPACT_STAIR_ASSETS,
    MONUMENTAL_STAIR_ASSETS,
    STAIR_TYPOLOGY_POLICY,
    continuity_safe_stair_kinds,
    derive_building_class,
    footprint_allows_wide_stair_well,
    industrial_workshop_spec,
    m2_two_storey_stair_spec,
    pick_stair_kind_for_class,
    school_academy_spec,
)
from pae.validate import _check_stair_typology_match, validate
from pae.variation import vary_spec


def test_policy_table_covers_all_classes():
    for cls in ("house", "cottage", "industrial", "academy", "castle", "tower", "generic"):
        assert cls in STAIR_TYPOLOGY_POLICY
        assert STAIR_TYPOLOGY_POLICY[cls]["default"] in STAIR_TYPOLOGY_POLICY[cls]["allowed"]


def test_house_fixture_is_compact():
    spec = m2_two_storey_stair_spec()
    assert derive_building_class(spec) == "house"
    assert spec.circulation.stair_kind == "straight"
    assert "wide" not in STAIR_TYPOLOGY_POLICY["house"]["allowed"]

    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, report.critical
    assert assembly.building_class == "house"
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert stairs, "expected house stair"
    assert all(p.asset_id in COMPACT_STAIR_ASSETS for p in stairs)
    assert not any(p.asset_id in MONUMENTAL_STAIR_ASSETS for p in stairs)

    hits = _check_stair_typology_match(assembly)
    assert not hits, hits
    _, vreport = validate(assembly)
    assert not [f for f in vreport.failures if f.check == "stair_typology_match"]


def test_industrial_fixture_is_monumental():
    spec = industrial_workshop_spec()
    assert derive_building_class(spec) == "industrial"
    assert footprint_allows_wide_stair_well(spec.footprint)
    assert spec.circulation.stair_kind in ("wide", "switchback")

    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, report.critical
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert stairs
    assert any(p.asset_id in MONUMENTAL_STAIR_ASSETS for p in stairs)

    _, vreport = validate(assembly)
    assert not [f for f in vreport.failures if f.check == "stair_typology_match"]


def test_school_academy_is_switchback_or_wide():
    spec = school_academy_spec()
    assert derive_building_class(spec) == "academy"
    assert spec.circulation.stair_kind in ("switchback", "wide")

    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, report.critical
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert stairs
    ids = {p.asset_id for p in stairs}
    assert ids & MONUMENTAL_STAIR_ASSETS

    _, vreport = validate(assembly)
    assert not [f for f in vreport.failures if f.check == "stair_typology_match"]


def test_vary_spec_house_stays_compact():
    base = m2_two_storey_stair_spec(seed=2)
    for seed in range(8):
        varied = vary_spec(base, seed)
        assert derive_building_class(varied) == "house"
        assert varied.circulation.stair_kind == "straight"
        safe = continuity_safe_stair_kinds(
            "house",
            has_tower=False,
            wide_well=footprint_allows_wide_stair_well(varied.footprint),
            storeys=varied.storeys,
        )
        assert varied.circulation.stair_kind in safe


def test_vary_spec_industrial_picks_monumental():
    base = industrial_workshop_spec(seed=80)
    kinds = set()
    for seed in range(12):
        varied = vary_spec(base, seed)
        assert derive_building_class(varied) == "industrial"
        kinds.add(varied.circulation.stair_kind)
        assert varied.circulation.stair_kind in ("wide", "switchback")
    assert kinds <= {"wide", "switchback"}


def test_pick_never_returns_buttress_or_unsupported():
    for cls in STAIR_TYPOLOGY_POLICY:
        kind = pick_stair_kind_for_class(
            cls,
            seed=1,
            has_tower=(cls == "tower"),
            wide_well=True,
            storeys=3,
            name=cls,
        )
        assert kind in ("straight", "switchback", "wide", "spiral")
        assert "buttress" not in kind


def _poison_stair_asset(assembly: Assembly, asset_id: str) -> Assembly:
    """Replace every stair placement's asset_id (typology poison)."""
    out = []
    for p in assembly.placements:
        if p.kind == "stair":
            out.append(
                SolidPlacement(
                    piece_id=p.piece_id,
                    asset_id=asset_id,
                    kind=p.kind,
                    cell=p.cell,
                    level=p.level,
                    yaw=p.yaw,
                    offset_cm=p.offset_cm,
                    size_cm=p.size_cm,
                    rotates_about_center=p.rotates_about_center,
                    tags=p.tags,
                )
            )
        else:
            out.append(p)
    return Assembly(
        placements=out,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(assembly.room_specs),
        building_class=assembly.building_class,
        stair_kind="wide" if "wide" in asset_id else assembly.stair_kind,
        wide_stair_well_available=assembly.wide_stair_well_available,
    )


def test_poisoned_house_with_stair_wide_fires_critical():
    _, _, assembly, report = run_through_assemble(m2_two_storey_stair_spec())
    assert report.ok
    poisoned = _poison_stair_asset(assembly, "stair_wide")
    poisoned = replace(poisoned, stair_kind="wide")
    hits = _check_stair_typology_match(poisoned)
    assert hits, "expected stair_typology_match on house+stair_wide"
    assert any(f.check == "stair_typology_match" and f.critical for f in hits)


def test_poisoned_industrial_undersized_straight_fires_warning():
    _, _, assembly, report = run_through_assemble(industrial_workshop_spec())
    assert report.ok
    poisoned = _poison_stair_asset(assembly, "stair_straight")
    poisoned = replace(
        poisoned,
        stair_kind="straight",
        wide_stair_well_available=True,
    )
    hits = _check_stair_typology_match(poisoned)
    assert hits, "expected undersized industrial typology hit"
    assert any(
        f.check == "stair_typology_match" and not f.critical for f in hits
    ), hits


def test_buttress_as_stair_fires_critical():
    _, _, assembly, report = run_through_assemble(m2_two_storey_stair_spec())
    assert report.ok
    poisoned = _poison_stair_asset(assembly, "buttress")
    hits = _check_stair_typology_match(poisoned)
    assert any(
        f.check == "stair_typology_match"
        and f.critical
        and "buttress" in f.message.lower()
        for f in hits
    )


def test_load_spec_building_class():
    from pae.spec import load_spec

    data = {
        "name": "typed_house",
        "style": "townhouse",
        "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
        "storeys": 2,
        "storey_use": ["hall", "hall"],
        "building_class": "house",
        "circulation": {"stair_kind": "straight", "stair_cells": []},
    }
    spec, report = load_spec(data)
    assert report.ok and spec is not None
    assert spec.building_class == "house"

    bad = dict(data)
    bad["building_class"] = "palace"
    _, breport = load_spec(bad)
    assert not breport.ok
    assert any(f.check == "spec_parse" for f in breport.failures)

"""VAL_ROOF_CONNECT — roof variation under connection continuity rules.

Connection suite (must stay fail-closed across flat / pitched / hip / steep):
  canopy_attachment, roof_bears_on_wall, freestanding, roof_penetration,
  roof_valley_join (L/U hip), roof_covers_enclosed (watertight progress).

Deliberately broken fixtures prove each new check FIRES with a useful message.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, VERTICAL_SUPPORT_TOL_CM
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import catalog_by_id
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    m1_box_house_spec,
    m3_keep_tower_spec,
    m4_l_plan_spec,
    school_academy_spec,
)
from pae.style_pack import (
    choose_roof_kind,
    resolve_roof_kind,
    resolve_roof_pitch,
    resolve_style_pack,
)
from pae.validate import (
    _check_canopy_attachment,
    _check_roof_bears_on_wall,
    _check_roof_covers_enclosed,
    _check_roof_penetration,
    _check_roof_valley_join,
    validate,
)

# Connection / support / exclusion checks that varied roofs must keep clean.
_ROOF_CONNECTION_SUITE = frozenset(
    {
        "canopy_attachment",
        "roof_bears_on_wall",
        "freestanding",
        "roof_penetration",
        "roof_valley_join",
        "end_connectivity",
    }
)


def _piece(asset_id, cell, level=0, offset=(0.0, 0.0, 0.0), size_cm=None, tags=None):
    d = catalog_by_id()[asset_id]
    return SolidPlacement(
        piece_id=f"{asset_id}_{cell[0]}_{cell[1]}_{level}",
        asset_id=asset_id,
        kind=d.kind,
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=offset,
        size_cm=size_cm or d.size_cm,
        rotates_about_center=d.rotates_about_center,
        tags=(d.tags | (tags or frozenset())),
    )


def _with_roof(spec: BuildingSpec, roof: RoofSpec) -> BuildingSpec:
    return replace(spec, roof=roof)


def _assembly(spec: BuildingSpec) -> Assembly:
    _, _, assembly, stage = run_through_assemble(spec)
    assert stage.ok is True, [f.message for f in stage.failures]
    return assembly


def _suite_hits(report) -> list:
    return [
        f
        for f in report.critical
        if f.check in _ROOF_CONNECTION_SUITE
    ]


# --- style/spec kind hooks ---------------------------------------------------


def test_resolve_roof_kind_spec_wins_over_style_default():
    pack = resolve_style_pack("wizard_academy")
    assert pack is not None
    assert pack.roof.kind_default == "pitched"
    assert resolve_roof_kind(pack, spec_kind="flat") == "flat"
    assert resolve_roof_kind(pack, spec_kind="hip") == "hip"
    assert resolve_roof_kind(pack, spec_kind="auto") == "pitched"
    assert resolve_roof_kind(pack, spec_kind=None) == "pitched"


def test_resolve_roof_kind_engine_default_is_flat():
    assert resolve_roof_kind({}, spec_kind=None) == "flat"
    assert resolve_roof_kind({}, spec_kind="auto") == "flat"


def test_choose_roof_kind_seed_stable_and_varied():
    a = choose_roof_kind({}, seed=1, spec_kind="auto")
    b = choose_roof_kind({}, seed=1, spec_kind="auto")
    c = choose_roof_kind({}, seed=2, spec_kind="auto")
    assert a == b
    assert a in ("flat", "pitched", "hip")
    # Different seeds may collide; force a distinct pool pick via explicit choices.
    assert choose_roof_kind({}, seed=0, choices=("flat",)) == "flat"
    assert choose_roof_kind({}, seed=0, choices=("hip",)) == "hip"
    assert c in ("flat", "pitched", "hip")


def test_auto_roof_kind_uses_wizard_academy_pitched():
    """Solver resolves kind=auto through StylePack kind_default."""
    base = m1_box_house_spec()
    spec = replace(
        base,
        name="m1_auto_roof",
        style="wizard_academy",
        roof=RoofSpec(kind="auto", pitch=1.0),
    )
    assembly = _assembly(spec)
    pitched = [p for p in assembly.placements if "pitched" in p.asset_id or "gable" in p.asset_id]
    assert pitched, "wizard_academy auto should place pitched roof kit"
    # Steep silhouette clamps pitch ≥ 1.6
    assert resolve_roof_pitch(resolve_style_pack("wizard_academy"), spec_pitch=1.0) >= 1.6


# --- deliberately broken fixtures --------------------------------------------


def test_floating_roof_fails_roof_bears_on_wall():
    """Broken fixture: roof slab raised clear of wall heads — Support check fires."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    raised = []
    for p in base.placements:
        if p.kind == "roof":
            ox, oy, oz = p.offset_cm
            raised.append(
                SolidPlacement(
                    piece_id=p.piece_id,
                    asset_id=p.asset_id,
                    kind=p.kind,
                    cell=p.cell,
                    level=p.level,
                    yaw=p.yaw,
                    offset_cm=(ox, oy, oz + VERTICAL_SUPPORT_TOL_CM + 40.0),
                    size_cm=p.size_cm,
                    rotates_about_center=p.rotates_about_center,
                    tags=p.tags,
                )
            )
        else:
            raised.append(p)
    poisoned = Assembly(
        placements=raised,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    hits = _check_roof_bears_on_wall(poisoned)
    assert hits, "raised roof must fail roof_bears_on_wall"
    assert all(f.check == "roof_bears_on_wall" and f.critical for f in hits)
    assert "bear on a wall" in hits[0].message
    assert hits[0].world_xyz is not None


def test_detached_canopy_still_fails_canopy_attachment():
    """Broken fixture: roof on posts only — Connection check (not silenced)."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    stray = [
        _piece("pier_square", (30, 30)),
        _piece("roof_flat", (30, 30), level=1),
    ]
    poisoned = Assembly(
        placements=list(base.placements) + stray,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    canopy = _check_canopy_attachment(poisoned)
    assert canopy, "detached canopy must fail canopy_attachment"
    assert canopy[0].check == "canopy_attachment"
    assert "detached canopy" in canopy[0].message


def test_blade_through_roof_still_critical_roof_penetration():
    """Broken fixture: wall rises through roof — Exclusion stays critical."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    blade = SolidPlacement(
        piece_id="blade_wall",
        asset_id="wall_plain",
        kind="wall",
        cell=(1, 1),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM * 2),
        tags=frozenset({"wall"}),
    )
    assembly = Assembly(
        placements=list(base.placements) + [blade],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        storeys=base.storeys,
    )
    hits = _check_roof_penetration(assembly)
    assert hits, "blade must fire roof_penetration"
    assert hits[0].critical is True
    assert hits[0].check == "roof_penetration"
    assert "blade_wall" in hits[0].message


def test_compound_hips_skip_cross_building_valley_join():
    """Fortress campus: separate building hips must not require shared valleys."""
    from pae.compound import build_fortress_compound

    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    assert _check_roof_valley_join(assembly) == []


def test_stripped_valleys_fail_roof_valley_join():
    """Broken fixture: L-plan hip with valleys removed — Existence check fires."""
    spec = _with_roof(m4_l_plan_spec(), RoofSpec(kind="hip", pitch=1.0))
    base = _assembly(spec)
    assert any(p.asset_id == "roof_valley" for p in base.placements)
    stripped = [
        p for p in base.placements if p.asset_id != "roof_valley"
    ]
    poisoned = Assembly(
        placements=stripped,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    hits = _check_roof_valley_join(poisoned)
    assert hits, "missing valleys must fail roof_valley_join"
    assert hits[0].check == "roof_valley_join"
    assert hits[0].critical is True
    assert "valley" in hits[0].message.lower()


def test_uncovered_interior_fires_roof_covers_enclosed():
    """Broken fixture: remove all roofs — watertight progress warning fires."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    bare = [p for p in base.placements if p.kind != "roof"]
    poisoned = Assembly(
        placements=bare,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    hits = _check_roof_covers_enclosed(poisoned)
    assert hits, "roofless enclosed cells must warn roof_covers_enclosed"
    assert hits[0].check == "roof_covers_enclosed"
    assert hits[0].critical is False
    assert "without roof coverage" in hits[0].message


# --- varied roofs still pass connection suite --------------------------------


@pytest.mark.parametrize(
    "roof",
    [
        RoofSpec(kind="flat", pitch=1.0),
        RoofSpec(kind="pitched", pitch=0.9),
        RoofSpec(kind="pitched", pitch=1.7),  # steep S-011
        RoofSpec(kind="hip", pitch=1.0),
        RoofSpec(kind="hip", pitch=1.8),  # steep hip
    ],
    ids=["flat", "pitched", "steep_pitched", "hip", "steep_hip"],
)
def test_m1_varied_roofs_pass_connection_suite(roof: RoofSpec):
    spec = _with_roof(m1_box_house_spec(), roof)
    assembly = _assembly(spec)
    _, report = validate(assembly)
    bad = _suite_hits(report)
    assert bad == [], [f"{f.check}: {f.message}" for f in bad]
    assert _check_roof_bears_on_wall(assembly) == []
    assert _check_roof_penetration(assembly) == []
    assert _check_canopy_attachment(assembly) == []


@pytest.mark.parametrize(
    "roof",
    [
        RoofSpec(kind="flat", pitch=1.0),
        RoofSpec(kind="pitched", pitch=0.9),
        RoofSpec(kind="hip", pitch=1.05),
    ],
    ids=["flat", "pitched", "hip"],
)
def test_m3_varied_roofs_pass_connection_suite(roof: RoofSpec):
    spec = _with_roof(m3_keep_tower_spec(), roof)
    assembly = _assembly(spec)
    _, report = validate(assembly)
    bad = _suite_hits(report)
    assert bad == [], [f"{f.check}: {f.message}" for f in bad]


def test_school_academy_flat_passes_connection_suite():
    """School sample stays on flat gothic roofs — connection suite clean."""
    assembly = _assembly(school_academy_spec())
    _, report = validate(assembly)
    bad = _suite_hits(report)
    assert bad == [], [f"{f.check}: {f.message}" for f in bad]
    assert _check_roof_penetration(assembly) == []
    covers = _check_roof_covers_enclosed(assembly)
    # School may warn on double-height voids; never critical connection defects.
    assert all(not f.critical for f in covers)


def test_l_plan_hip_valley_passes_connection_and_valley_join():
    spec = _with_roof(m4_l_plan_spec(), RoofSpec(kind="hip", pitch=1.0))
    assembly = _assembly(spec)
    assert any(p.asset_id == "roof_valley" for p in assembly.placements)
    assert _check_roof_valley_join(assembly) == []
    _, report = validate(assembly)
    bad = _suite_hits(report)
    assert bad == [], [f"{f.check}: {f.message}" for f in bad]


def test_m1_default_still_bears_and_covers():
    assembly = _assembly(m1_box_house_spec())
    assert _check_roof_bears_on_wall(assembly) == []
    assert _check_roof_covers_enclosed(assembly) == []

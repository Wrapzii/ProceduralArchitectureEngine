"""M7 defect 0.3 — roof_penetration triage for school academy and blade promotion."""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.spec import m1_box_house_spec, school_academy_spec
from pae.validate import (
    _check_roof_penetration,
    _designed_roof_penetration_eave_tuck,
    validate,
)


def test_school_academy_roof_penetration_triage_clean():
    """Gothic academy: flat roofs sit FLOOR_T above wall heads — no blades, no warnings.

    Triage table (M7 / defect 0.3):
    | Class                         | School hits | Decision                          |
    |-------------------------------|-------------|-----------------------------------|
    | Flat roof above wall head     | 0           | Geometry correct (no exemption)   |
    | Eave tuck into flat slab      | 0           | Exempt helper exists if it arises |
    | Gable ridge / pitched infill  | n/a         | School uses roof_flat only          |
    | Real blade through roof       | 0           | Would be critical if present        |
    """
    _, _, assembly, report = run_through_validate_trim(school_academy_spec())
    assert report.ok
    hits = [f for f in report.failures if f.check == "roof_penetration"]
    assert hits == [], [f.message for f in hits]
    assert report.critical == []


def test_real_blade_through_roof_is_critical():
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    blade = SolidPlacement(
        piece_id="blade",
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
        circulation=base.circulation,
        storeys=base.storeys,
    )
    hits = _check_roof_penetration(assembly)
    assert len(hits) == 1
    assert hits[0].critical is True
    assert "blade" in hits[0].message


def test_eave_tuck_into_flat_roof_is_exempt():
    wall = SolidPlacement(
        piece_id="w",
        asset_id="wall_plain",
        kind="wall",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"wall"}),
    )
    rise = FLOOR_T_CM - 1.0
    assert _designed_roof_penetration_eave_tuck(
        wall, rise_cm=rise, roof_asset_id="roof_flat"
    )
    roof = SolidPlacement(
        piece_id="r",
        asset_id="roof_flat",
        kind="roof",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, STOREY_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"roof"}),
    )
    # Wall top at STOREY; roof bottom at STOREY — tuck rise within FLOOR_T band.
    assembly = Assembly(
        placements=[wall, roof],
        circulation=[],
        storeys=1,
    )
    # Nudge wall 20 cm into roof slab — still within eave tuck band.
    tucked = SolidPlacement(
        piece_id="w2",
        asset_id="wall_plain",
        kind="wall",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM + 20.0),
        tags=frozenset({"wall"}),
    )
    asm2 = Assembly(placements=[tucked, roof], circulation=[], storeys=1)
    assert _check_roof_penetration(asm2) == []


def test_m1_box_house_passes_roof_penetration():
    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == "roof_penetration"]
    assert hits == [], [f.message for f in hits]

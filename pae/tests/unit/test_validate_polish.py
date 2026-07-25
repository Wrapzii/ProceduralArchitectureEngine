"""§7.4 interpenetration polish — designed overlaps stay quiet, real defects stay loud."""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.assets.db import AssetDB
from pae.assemble import assemble
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    floor_placement_z_cm,
    rotation_offset_cm,
)
from pae.plan import plan
from pae.solver import solve
from pae.spec import (
    load_style,
    m1_box_house_spec,
    m2_two_storey_stair_spec,
    m3_keep_tower_spec,
    m4_l_plan_spec,
)
from pae.tests.fixtures.broken_all_defects import EXPECTED_CHECKS, make_broken_assembly
from pae.validate import validate


def _pipeline_validate(spec):
    style = load_style(spec.style)
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    db = AssetDB()
    assembly, _ = assemble(floor_plan, db, style)
    _, report = validate(assembly)
    return assembly, report


def _interpenetration_count(report) -> int:
    return sum(1 for f in report.failures if f.check == "interpenetration")


def test_m3_interpenetration_warns_drop_below_threshold():
    _, report = _pipeline_validate(m3_keep_tower_spec())
    assert report.ok is True
    assert report.critical == []
    assert _interpenetration_count(report) < 20


def test_m1_m2_m4_still_validate_clean():
    for spec in (m1_box_house_spec(), m2_two_storey_stair_spec(), m4_l_plan_spec()):
        _, report = _pipeline_validate(spec)
        assert report.ok is True, spec.name
        assert report.critical == [], spec.name


def test_m1_m4_m3_aperture_gap_warnings_zero():
    """Wave F APERTURE_GAPS — perimeter milestones should have no residual aperture warns.

    ``stair_landing_clearance`` on m3 is a separate stair/landing lane (present with or
    without Phase 0.6 drum windows) — do not conflate it with aperture gaps here.
    """
    aperture_checks = {
        "aperture_sanity",
        "aperture_reachability",
        "no_bare_aperture",
        "aperture_gap",
    }
    for spec in (m1_box_house_spec(), m3_keep_tower_spec(), m4_l_plan_spec()):
        _, report = _pipeline_validate(spec)
        warns = [
            f
            for f in report.failures
            if not f.critical and f.check in aperture_checks
        ]
        assert warns == [], f"{spec.name}: {[(f.check, f.message) for f in warns]}"


def test_m3_interpenetration_zero():
    _, report = _pipeline_validate(m3_keep_tower_spec())
    inter = [f for f in report.failures if f.check == "interpenetration"]
    assert inter == []


def test_broken_fixture_still_reports_interpenetration():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    assert report.ok is False
    found = {f.check for f in report.failures}
    assert "interpenetration" in found
    assert EXPECTED_CHECKS <= found
    inter = [f for f in report.failures if f.check == "interpenetration"]
    assert len(inter) >= 3
    floor_ids = {f.piece_id for f in inter}
    assert "floor_overlap_a" in floor_ids or any(
        "floor_overlap" in f.message for f in inter
    )


def test_designed_tower_arc_quarters_same_cell_not_flagged():
    arc_size = (MODULE_CM, MODULE_CM, STOREY_CM)
    cell = (2, 2)
    placements = [
        SolidPlacement(
            piece_id=f"arc_{yaw}",
            asset_id="tower_arc_quarter",
            kind="tower_arc",
            cell=cell,
            level=0,
            yaw=yaw,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=arc_size,
            rotates_about_center=True,
        )
        for yaw in (0, 90, 180, 270)
    ]
    _, report = validate(Assembly(placements=placements, storeys=1))
    assert _interpenetration_count(report) == 0


def test_designed_wall_corner_overlap_not_flagged():
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    placements = [
        SolidPlacement(
            piece_id="west",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=rotation_offset_cm(0, sx, sy) + (0.0,),
            size_cm=(sx, sy, sz),
        ),
        SolidPlacement(
            piece_id="south",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=270,
            offset_cm=rotation_offset_cm(270, sx, sy) + (0.0,),
            size_cm=(sx, sy, sz),
        ),
    ]
    _, report = validate(Assembly(placements=placements, storeys=1))
    assert _interpenetration_count(report) == 0


def test_accidental_floor_double_slab_still_flagged():
    floor_z = floor_placement_z_cm(0)
    size = (MODULE_CM, MODULE_CM, FLOOR_T_CM)
    placements = [
        SolidPlacement(
            piece_id="floor_a",
            asset_id="floor",
            kind="floor",
            cell=(1, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, floor_z),
            size_cm=size,
        ),
        SolidPlacement(
            piece_id="floor_b",
            asset_id="floor",
            kind="floor",
            cell=(1, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, floor_z),
            size_cm=size,
        ),
    ]
    _, report = validate(Assembly(placements=placements, storeys=1))
    assert _interpenetration_count(report) >= 1

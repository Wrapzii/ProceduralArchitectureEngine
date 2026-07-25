"""Unit tests for pae.validate — broken fixture must expose every §7 defect."""

from __future__ import annotations

from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM, placement_world_aabb, rotation_offset_cm
from pae.tests.fixtures.broken_all_defects import EXPECTED_CHECKS, make_broken_assembly
from pae.validate import validate


def test_broken_fixture_fails_validation():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    assert report.ok is False
    assert len(report.critical) > 0


def test_broken_fixture_detects_all_check_classes():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    found = {f.check for f in report.failures}
    missing = EXPECTED_CHECKS - found
    assert not missing, f"missing defect checks: {sorted(missing)}; found={sorted(found)}"
    assert "stair_exit_clearance" in found


def test_broken_fixture_critical_categories():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    critical_checks = {f.check for f in report.critical}
    assert "end_connectivity" in critical_checks
    assert "vertical_support" in critical_checks
    assert "enclosure" in critical_checks
    assert "stair_reachability" in critical_checks


def test_dangling_end_has_world_coordinates():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    dangling = [f for f in report.failures if f.check == "end_connectivity"]
    assert dangling, "expected dangling end failure"
    dangle_ids = {f.piece_id for f in dangling}
    assert "wall_dangle" in dangle_ids
    for f in dangling:
        assert f.world_xyz is not None


def test_collinear_gap_near_three_metres():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    gaps = [f for f in report.failures if f.check == "collinear_gap"]
    assert gaps
    msg = gaps[0].message
    assert "300" in msg or "299" in msg or "301" in msg


def test_run_fit_reports_176cm_leftover():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    run_failures = [f for f in report.failures if f.check == "run_fit"]
    assert run_failures
    assert "176" in run_failures[0].message


def test_validation_is_deterministic():
    assembly = make_broken_assembly()
    _, r1 = validate(assembly)
    _, r2 = validate(assembly)
    sig1 = [(f.check, f.piece_id, f.world_xyz, f.message) for f in r1.failures]
    sig2 = [(f.check, f.piece_id, f.world_xyz, f.message) for f in r2.failures]
    assert sig1 == sig2


def test_happy_minimal_assembly_passes():
    from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
    from pae.contract import (
        FLOOR_T_CM,
        STOREY_CM,
        WALL_T_CM,
        floor_placement_z_cm,
        rotation_offset_cm,
    )
    from pae.plan import CellRole

    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    wall_off = rotation_offset_cm(0, sx, sy) + (0.0,)
    floor_z = floor_placement_z_cm(0)

    layer = FloorPlanLayer(
        level=0,
        width=2,
        height=2,
        origin_cell=(0, 0),
        cells=[
            [CellRole.EXTERIOR, CellRole.EXTERIOR],
            [CellRole.EXTERIOR, CellRole.INTERIOR],
        ],
    )
    placements = [
        SolidPlacement(
            piece_id="w_s",
            asset_id="wall",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=270,
            offset_cm=rotation_offset_cm(270, sx, sy) + (0.0,),
            size_cm=(sx, sy, sz),
        ),
        SolidPlacement(
            piece_id="w_w",
            asset_id="wall",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=wall_off,
            size_cm=(sx, sy, sz),
        ),
        SolidPlacement(
            piece_id="w_e",
            asset_id="wall",
            kind="wall",
            cell=(1, 0),
            level=0,
            yaw=180,
            offset_cm=rotation_offset_cm(180, sx, sy) + (0.0,),
            size_cm=(sx, sy, sz),
        ),
        SolidPlacement(
            piece_id="w_n",
            asset_id="wall",
            kind="wall",
            cell=(0, 1),
            level=0,
            yaw=90,
            offset_cm=rotation_offset_cm(90, sx, sy) + (0.0,),
            size_cm=(sx, sy, sz),
        ),
        SolidPlacement(
            piece_id="floor0",
            asset_id="floor",
            kind="floor",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, floor_z),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        ),
        SolidPlacement(
            piece_id="ground",
            asset_id="ground",
            kind="ground",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM * 2, MODULE_CM * 2, FLOOR_T_CM),
        ),
    ]
    asm = Assembly(placements=placements, floor_plan={0: layer}, storeys=1)
    _, report = validate(asm)
    assert report.ok is True
    assert report.critical == []


def test_placement_world_aabb_yaw90_wall():
    bb_min, bb_max = placement_world_aabb(
        0,
        0,
        0,
        90,
        (WALL_T_CM, MODULE_CM, STOREY_CM),
        rotation_offset_cm(90, WALL_T_CM, MODULE_CM) + (0.0,),
    )
    assert abs(bb_max[0] - bb_min[0] - MODULE_CM) < TOL_CM
    assert abs(bb_max[1] - bb_min[1] - WALL_T_CM) < TOL_CM

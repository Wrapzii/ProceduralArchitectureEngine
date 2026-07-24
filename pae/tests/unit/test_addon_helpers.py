"""Pure helper tests for the PAE add-on (no bpy)."""

from __future__ import annotations

import math

from pae.addon.helpers import (
    OBJECT_NAME_PREFIX,
    build_spec_from_ui,
    build_validate_draw_groups,
    cm_to_blender_location,
    defect_to_select_id,
    export_gate_allows,
    export_gate_message,
    frame_camera_from_bounds,
    frame_camera_from_world_point,
    list_style_ids,
    object_name_to_piece_id,
    piece_id_to_object_name,
)
from pae.addon.session import failure_from_dict, failure_to_dict, report_from_json, report_to_json
from pae.contract import MODULE_CM, STOREY_CM
from pae.report import Failure, Report
from pae.tests.fixtures.broken_all_defects import make_broken_assembly
from pae.validate import validate


def test_piece_id_object_name_roundtrip():
    assert piece_id_to_object_name("wall_0_0") == f"{OBJECT_NAME_PREFIX}wall_0_0"
    assert object_name_to_piece_id(f"{OBJECT_NAME_PREFIX}wall_0_0") == "wall_0_0"
    assert object_name_to_piece_id("Other") is None


def test_defect_to_select_id_prefers_piece_id():
    f = Failure(check="x", message="m", piece_id="wall_a", world_xyz=(1.0, 2.0, 3.0))
    assert defect_to_select_id(f) == "wall_a"
    f2 = Failure(check="x", message="m", world_xyz=(0.0, 0.0, 0.0))
    assert defect_to_select_id(f2) is None


def test_frame_camera_from_world_point_distance():
    frame = frame_camera_from_world_point((0.0, 0.0, 100.0), distance_cm=500.0)
    loc = frame["location"]
    tgt = frame["target"]
    assert tgt == (0.0, 0.0, 100.0)
    dist = math.sqrt(sum((loc[i] - tgt[i]) ** 2 for i in range(3)))
    assert abs(dist - 500.0) < 0.01


def test_frame_camera_from_bounds():
    frame = frame_camera_from_bounds(
        (0.0, 0.0, 0.0),
        (MODULE_CM, MODULE_CM, STOREY_CM),
    )
    assert "location" in frame and "target" in frame


def test_cm_to_blender_location():
    assert cm_to_blender_location((100.0, 200.0, 300.0)) == (1.0, 2.0, 3.0)


def test_build_validate_draw_groups_from_broken_fixture():
    _, report = validate(make_broken_assembly())
    groups = build_validate_draw_groups(report)
    assert groups
    critical = [g for g in groups if g.severity == "critical"]
    assert critical
    total_items = sum(len(g.items) for g in groups)
    assert total_items == len(report.failures)
    first = critical[0].items[0]
    assert first.select_id is not None or first.world_xyz is not None


def test_report_json_roundtrip():
    _, report = validate(make_broken_assembly())
    raw = report_to_json(report)
    restored = report_from_json(raw)
    assert restored is not None
    assert restored.ok == report.ok
    assert len(restored.failures) == len(report.failures)
    assert failure_from_dict(failure_to_dict(report.failures[0])).check == report.failures[0].check


def test_export_gate():
    ok_report = Report(ok=True, failures=[], critical=[], warnings=[])
    bad_report = Report.from_failures(
        [Failure(check="x", message="bad", critical=True)]
    )
    assert export_gate_allows(ok_report)
    assert not export_gate_allows(bad_report)
    assert not export_gate_allows(None)
    assert "blocked" in export_gate_message(bad_report).lower()


def test_build_spec_from_ui():
    spec = build_spec_from_ui(
        name="test",
        style="townhouse",
        storeys=2,
        bays_x=4,
        bays_y=3,
        footprint_kind="rect",
        seed=7,
    )
    assert spec.footprint.bays_x == 4
    assert spec.seed == 7


def test_list_style_ids_non_empty():
    ids = list_style_ids()
    assert "townhouse" in ids

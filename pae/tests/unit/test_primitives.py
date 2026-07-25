"""WP-3: primitive descriptors / MODULE footprint contract (no Blender)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.primitives import (
    all_descriptors,
    footprint_contract_errors,
    get,
    measurement_rows,
    measurement_table_markdown,
    piece_ids,
)
from pae.primitives.bpy_util import HAS_BPY, require_bpy
from pae.primitives.roofs import DEFAULT_ROOF_PITCH, roof_rise_cm


REQUIRED_IDS = [
    "wall_plain",
    "wall_window",
    "wall_arrowslit",
    "wall_door",
    "wall_arcade",
    "floor",
    "floor_hole",
    "stair_straight",
    "stair_spiral_quarter",
    "tower_arc_quarter",
    "tower_crown",
    "tower_cap",
    "battlement",
    "roof_pitched_gable",
    "roof_flat",
    "ground_plinth",
]


def test_catalog_contains_required_kit():
    ids = set(piece_ids())
    missing = [i for i in REQUIRED_IDS if i not in ids]
    assert missing == [], f"missing primitives: {missing}"


def test_every_piece_within_module_tolerance():
    failures = []
    for desc in all_descriptors():
        errs = footprint_contract_errors(desc, tol_cm=TOL_CM)
        if errs:
            failures.extend(errs)
    assert failures == [], "\n".join(failures)


def test_min_corner_origin_for_non_centred():
    for desc in all_descriptors():
        if desc.rotates_about_center:
            continue
        assert desc.origin == "min_corner"
        assert desc.aabb_min_cm == pytest.approx((0.0, 0.0, 0.0), abs=TOL_CM)


def test_wall_long_axis_is_one_module():
    for wid in (
        "wall_plain",
        "wall_window",
        "wall_arrowslit",
        "wall_door",
        "wall_arcade",
    ):
        w = get(wid)
        assert w.size_cm[0] == pytest.approx(WALL_T_CM)
        assert w.size_cm[1] == pytest.approx(MODULE_CM)
        assert w.size_cm[2] == pytest.approx(STOREY_CM)
        names = {s.name for s in w.sockets}
        assert {"end_a", "end_b"} <= names


def test_wall_door_reaches_floor_window_does_not():
    door = get("wall_door")
    window = get("wall_window")
    assert door.aperture is not None and door.aperture.min_cm[2] == pytest.approx(0.0)
    assert window.aperture is not None and window.aperture.min_cm[2] > TOL_CM


def test_arcade_outer_footprint_still_one_module():
    arcade = get("wall_arcade")
    assert arcade.size_cm[1] == pytest.approx(MODULE_CM)
    assert arcade.aperture is not None
    assert arcade.aperture.kind == "arch"
    # Opening stays inside the bay (jambs on both sides).
    assert arcade.aperture.min_cm[1] > 0.0
    assert arcade.aperture.max_cm[1] < MODULE_CM


def test_stair_straight_spans_two_modules_one_storey():
    s = get("stair_straight")
    assert s.footprint_modules == (2, 1)
    assert s.size_cm == pytest.approx((2.0 * MODULE_CM, MODULE_CM, STOREY_CM))
    assert s.height_storeys == pytest.approx(1.0)


def test_spiral_quarter_rise_is_quarter_storey():
    s = get("stair_spiral_quarter")
    assert s.height_storeys == pytest.approx(0.25)
    assert s.size_cm[2] == pytest.approx(STOREY_CM * 0.25)
    assert s.rotates_about_center is True


def test_tower_arc_is_centred():
    t = get("tower_arc_quarter")
    assert t.rotates_about_center is True
    assert t.size_cm[0] == pytest.approx(MODULE_CM)
    assert t.size_cm[2] == pytest.approx(STOREY_CM)


def test_roof_includes_gable_height():
    roof = get("roof_pitched_gable")
    rise = roof_rise_cm(DEFAULT_ROOF_PITCH, MODULE_CM)
    assert roof.size_cm[2] == pytest.approx(rise + FLOOR_T_CM)
    assert roof.size_cm[0] == pytest.approx(MODULE_CM)
    assert "gable" in roof.tags


def test_roof_flat_module_footprint():
    flat = get("roof_flat")
    assert flat.size_cm == pytest.approx((MODULE_CM, MODULE_CM, FLOOR_T_CM))
    assert flat.footprint_modules == (1, 1)
    assert "flat" in flat.tags


def test_ground_plinth_thickness():
    p = get("ground_plinth")
    assert p.size_cm == pytest.approx((MODULE_CM, MODULE_CM, FLOOR_T_CM))
    assert p.kind == "plinth"


def test_measurement_table_all_ok():
    rows = measurement_rows(all_descriptors())
    assert all(r["ok"] for r in rows)
    md = measurement_table_markdown(all_descriptors())
    assert "wall_arcade" in md
    assert "All pieces within tolerance" in md


def test_measurement_doc_matches_catalog():
    """Docs/PRIMITIVE_MEASUREMENTS.md stays in sync with descriptors."""
    doc = Path(__file__).resolve().parents[3] / "Docs" / "PRIMITIVE_MEASUREMENTS.md"
    assert doc.is_file(), f"missing measurement table at {doc}"
    generated = measurement_table_markdown(all_descriptors())
    # Compare body ignoring trailing whitespace differences.
    assert doc.read_text(encoding="utf-8").strip() == generated.strip()


def test_bpy_require_raises_outside_blender():
    if HAS_BPY:
        pytest.skip("bpy present in this environment")
    with pytest.raises(RuntimeError, match="bpy is not available"):
        require_bpy()

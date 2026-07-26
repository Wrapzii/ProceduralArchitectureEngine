"""Unit tests — BuildingSpec loader (§3)."""

from __future__ import annotations

from pae.spec import (
    BuildingSpec,
    load_spec,
    load_style,
    m1_box_house_dict,
    m1_box_house_spec,
    m2_two_storey_stair_dict,
    m3_keep_tower_dict,
    m3_keep_tower_spec,
)


def test_load_spec_rejects_unknown_fields():
    data = m2_two_storey_stair_dict()
    data["storeis"] = 2
    spec, report = load_spec(data)
    assert spec is None
    assert not report.ok
    assert "unknown field" in report.critical[0].message


def test_loader_rejects_world_coordinate_fields():
    data = {
        "name": "bad",
        "style": "townhouse",
        "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
        "storeys": 1,
        "storey_use": ["hall"],
        "location": {"x": 1200.0, "y": 800.0, "z": 0.0},
    }
    spec, report = load_spec(data)
    assert spec is None
    assert report.ok is False
    assert any(f.check == "spec_no_world_coords" for f in report.failures)


def test_loader_rejects_centimetre_placement_fields():
    data = {
        "name": "bad_cm",
        "style": "townhouse",
        "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
        "storeys": 1,
        "offset_cm": [400.0, 0.0, 0.0],
        "storey_use": ["hall"],
    }
    spec, report = load_spec(data)
    assert spec is None
    assert report.ok is False
    assert any("offset_cm" in f.message for f in report.failures)


def test_loader_rejects_nested_xyz():
    data = {
        "name": "nested",
        "style": "townhouse",
        "footprint": {"kind": "rect", "bays_x": 2, "bays_y": 2},
        "storeys": 1,
        "storey_use": ["hall"],
        "towers": [{"cell": [1, 1], "storeys": 2, "x": 400}],
    }
    spec, report = load_spec(data)
    assert spec is None
    assert report.ok is False


def test_loader_accepts_valid_bay_spec():
    data = m1_box_house_dict()
    spec, report = load_spec(data)
    assert report.ok is True
    assert isinstance(spec, BuildingSpec)
    assert spec.footprint.bays_x == 4
    assert spec.footprint.bays_y == 3
    assert spec.storeys == 1
    assert spec.ground_slab is True
    assert spec.openings.doors_ground == 1
    assert spec.openings.windows_ground == 2


def test_m1_box_house_factory():
    spec = m1_box_house_spec()
    assert spec.name == "m1_box_house"
    assert spec.footprint.kind == "rect"
    assert spec.roof.kind == "flat"
    assert spec.storeys == 1
    assert spec.towers == []


def test_m3_keep_tower_factory_does_not_break_m1():
    """M3 factory is additive — M1 remains flat/no-tower."""
    m1 = m1_box_house_spec()
    m3 = m3_keep_tower_spec()
    assert m1.roof.kind == "flat"
    assert m1.towers == []
    assert m3.name == "m3_keep_tower"
    assert m3.style == "keep"
    assert m3.roof.kind == "pitched"
    assert len(m3.towers) == 1
    assert m3.towers[0].attached_to == "wall"
    data = m3_keep_tower_dict()
    loaded, report = load_spec(data)
    assert report.ok is True
    assert loaded is not None
    assert loaded.roof.kind == "pitched"
    assert len(loaded.towers) == 1


def test_style_townhouse_loads():
    style, report = load_style("townhouse")
    assert report.ok is True
    assert style is not None
    assert style["id"] == "townhouse"

"""Unit tests — BuildingSpec loader (§3)."""

from __future__ import annotations

from pae.spec import (
    BuildingSpec,
    load_spec,
    load_style,
    m1_box_house_dict,
    m1_box_house_spec,
)


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


def test_style_townhouse_loads():
    style, report = load_style("townhouse")
    assert report.ok is True
    assert style is not None
    assert style["id"] == "townhouse"

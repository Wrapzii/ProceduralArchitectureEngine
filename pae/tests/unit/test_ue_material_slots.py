"""UE material slots + Stage K mask round-trip (MP-WS-UEMAT).

RAM-safe single-file tests. Proves every exported placement has ``material_slot``
and that wear/damp masks survive manifest → spawn table.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.export.manifest import build_manifest  # noqa: E402
from pae.export.materials import (  # noqa: E402
    MASK_CHANNEL_CONTRACT,
    MATERIAL_SLOT_BY_KIND,
    masks_from_tags,
    material_slot_for,
    placement_material_fields,
)
from pae.pipeline import run_through_decorate  # noqa: E402
from pae.spec import m1_box_house_spec  # noqa: E402
from tools.ue_spawn_table import build_spawn_table  # noqa: E402


REQUIRED_KINDS = (
    "wall",
    "roof",
    "floor",
    "ground",
    "stair",
    "tower",
    "door",
    "window",
    "band",
    "trim",
    "plinth",
    "cornice",
)


def test_kind_to_slot_mapping_covers_architecture_kinds():
    for kind in REQUIRED_KINDS:
        slot = MATERIAL_SLOT_BY_KIND.get(kind) or material_slot_for(kind)
        assert isinstance(slot, str) and slot.startswith("MI_") or slot == "None"


def test_course_tags_refine_plinth_and_cornice():
    assert material_slot_for("band", tags={"course:plinth", "band"}) == "MI_Plinth"
    assert material_slot_for("band", tags={"course:cornice", "band"}) == "MI_Cornice"
    assert material_slot_for("band", asset_id="band_course") == "MI_Trim"


def test_window_door_asset_ids_map_to_slots():
    assert material_slot_for("wall", asset_id="wall_window_lancet") == "MI_Window"
    assert material_slot_for("wall", asset_id="wall_door") == "MI_Door"


def test_masks_from_tags_round_trip_channels():
    masks = masks_from_tags(
        {
            "wear:high",
            "dampness:base",
            "weather:damp",
            "weather:streak",
            "orient:south",
            "mat_var:L0",
            "detail_meta",
        },
        level=0,
    )
    assert masks["wear"] == pytest.approx(0.9)
    assert masks["dampness"] == pytest.approx(0.85)
    assert masks["streak"] == 1.0
    assert masks["orientation"] == "south"
    assert masks["channels"]["R"] == masks["wear"]
    assert masks["channels"]["G"] == masks["dampness"]
    assert masks["channels"]["B"] == masks["height_band"]
    assert masks["channels"]["A"] == masks["streak"]
    assert len(masks["custom_data"]) == 4
    assert MASK_CHANNEL_CONTRACT["vertex_color"]["R"] == "wear"


def test_manifest_placements_have_material_slot_and_masks():
    """Tiny M1 + Stage K detail — every piece gets a slot; masks present."""
    from pae.validate import validate

    spec = m1_box_house_spec(seed=5)
    _m, _p, assembly, report = run_through_decorate(spec, apply_detail=True)
    assert report.ok, [f.message for f in report.critical[:5]]
    _, vreport = validate(assembly)
    assert vreport.ok, [f.message for f in vreport.critical[:5]]

    manifest = build_manifest(assembly, vreport)
    assert manifest.get("materials", {}).get("schema") == "pae.materials/1"
    assert manifest["materials"]["nanite"]["recommend"] is True

    assert manifest["placements"], "expected placements"
    for row in manifest["placements"]:
        assert row.get("material_slot"), f"missing material_slot on {row.get('piece_id')}"
        assert isinstance(row["material_slot"], str)
        assert "masks" in row
        assert "wear" in row["masks"]
        assert "dampness" in row["masks"]
        assert "custom_data" in row["masks"]
        assert len(row["masks"]["custom_data"]) == 4

    for asset in manifest["assets"]:
        assert asset.get("material_slot"), f"asset {asset.get('id')} missing material_slot"

    slots = {row["material_slot"] for row in manifest["placements"]}
    assert "MI_Wall" in slots or "MI_Floor" in slots


def test_masks_survive_spawn_table_round_trip():
    from dataclasses import replace

    from pae.spec import RoofSpec
    from pae.validate import validate

    spec = replace(
        m1_box_house_spec(seed=9),
        style="rustic",
        name="mat_slot_rustic",
        roof=RoofSpec(kind="auto", pitch=1.0),
    )
    _m, _p, assembly, report = run_through_decorate(spec, apply_detail=True)
    assert report.ok, [f.message for f in report.critical[:5]]
    _, vreport = validate(assembly)
    assert vreport.ok, [f.message for f in vreport.critical[:5]]

    manifest = build_manifest(assembly, vreport)
    table = build_spawn_table(
        manifest,
        milestone="m1",
        source_manifest="test_manifest.json",
    )
    assert table["rows"]
    for row in table["rows"]:
        assert row.get("material_slot"), row.get("piece_id")
        assert "masks" in row
        assert len(row["masks"]["custom_data"]) == 4
        assert row["masks"]["channels"]["R"] == row["masks"]["wear"]

    for group in table["ism_groups"]:
        for inst in group["instances"]:
            assert "material_slot" in inst
            if "masks" in inst:
                assert "custom_data" in inst
                assert len(inst["custom_data"]) == 4

    damp_or_wear = [
        r
        for r in table["rows"]
        if r["masks"]["wear"] > 0 or r["masks"]["dampness"] > 0
    ]
    assert damp_or_wear, "expected Stage K weathering masks on rustic walls"


def test_placement_material_fields_helper():
    fields = placement_material_fields(
        kind="band",
        asset_id="band_course",
        tags={"course:plinth", "band", "wear:medium"},
        level=0,
    )
    assert fields["material_slot"] == "MI_Plinth"
    assert fields["masks"]["wear"] == pytest.approx(0.55)

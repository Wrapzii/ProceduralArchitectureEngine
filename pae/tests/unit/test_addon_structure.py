"""StructureSpec addon helper tests (no bpy)."""

from __future__ import annotations

from pae.addon.structure_helpers import (
    GATEHOUSE_PRESET_YAML,
    build_structure_from_ui,
    coerce_pipeline_spec,
    default_level_sketch,
    ensure_default_levels,
    parse_structure_yaml_to_ui_values,
    structure_ui_values_from_spec,
    structure_yaml_from_ui,
)
from pae.structure_spec import load_structure_yaml


def test_default_level_sketch():
    assert default_level_sketch(rows=2, cols=3) == "###\n###\n"


def test_build_structure_from_ui_single_level():
    structure = build_structure_from_ui(
        name="box",
        style="townhouse",
        seed=3,
        levels=[{"sketch": "####\n####\n", "height_units": 2}],
    )
    assert structure.name == "box"
    assert structure.level_height_units() == (2,)
    assert len(structure.resolved_foundation_cells()) == 8


def test_build_structure_from_ui_with_foundation():
    structure = build_structure_from_ui(
        name="found",
        style="townhouse",
        seed=1,
        levels=[{"sketch": "####\n", "height_units": 1}],
        use_foundation=True,
        foundation_sketch="######\n",
    )
    assert len(structure.resolved_foundation_cells()) == 6


def test_structure_yaml_round_trip_from_ui():
    yaml_text = structure_yaml_from_ui(
        name="gate",
        style="townhouse",
        seed=7,
        levels=[
            {"sketch": "####\n####\n", "height_units": 1},
            {"sketch": "##..\n##..\n", "height_units": 2, "wall_style": "arcade"},
        ],
        use_foundation=True,
        foundation_sketch="######\n######\n",
    )
    spec, report = load_structure_yaml(yaml_text)
    assert report.ok and spec is not None
    assert spec.level_height_units() == (1, 2)
    assert spec.levels[1].wall_style == "arcade"


def test_parse_gatehouse_preset_to_ui_values():
    values, report = parse_structure_yaml_to_ui_values(GATEHOUSE_PRESET_YAML)
    assert report.ok and values is not None
    assert values["building_name"] == "gatehouse"
    assert len(values["structure_levels"]) == 3
    assert values["structure_use_foundation"] is True

    rebuilt = build_structure_from_ui(
        name=values["building_name"],
        style=values["style"],
        seed=values["seed"],
        levels=values["structure_levels"],
        foundation_sketch=values["structure_foundation_sketch"],
        use_foundation=values["structure_use_foundation"],
        roof_kind=values["roof_kind"],
        roof_pitch=values["roof_pitch"],
        stair_kind=values["stair_kind"],
    )
    again = structure_ui_values_from_spec(rebuilt)
    assert again["structure_levels"][2]["wall_style"] == "arcade"


def test_ensure_default_levels():
    levels = ensure_default_levels([], rows=1, cols=2)
    assert len(levels) == 1
    assert levels[0]["sketch"] == "##\n"


def test_coerce_pipeline_spec_from_structure():
    structure = build_structure_from_ui(
        name="coerce",
        style="townhouse",
        seed=1,
        levels=[{"sketch": "####\n", "height_units": 1}],
    )
    from pae.spec import BuildingSpec

    building = coerce_pipeline_spec(structure)
    assert isinstance(building, BuildingSpec)
    assert building.name == "coerce"
    assert building.storeys == 1

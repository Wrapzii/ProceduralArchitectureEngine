"""Master Plan Stage H — openings as a style choice."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.pipeline import run_through_assemble
from pae.spec import m1_box_house_spec, m2_two_storey_stair_spec
from pae.structure_spec import LevelSpec, StructureSpec, structure_to_building_spec
from pae.style_pack import (
    normalize_aperture_tag,
    resolve_door_piece_id,
    resolve_window_piece_id,
)
from pae.validate import validate
from tools.me_style_interchange_proof import interchange_spec


def _hall_window_assets(assembly) -> dict[int, set[str]]:
    """Per-level exterior window piece ids (excludes tower drum glazing)."""
    out: dict[int, set[str]] = {}
    for p in assembly.placements:
        if p.kind != "wall" or "window" not in p.asset_id:
            continue
        if "drum_window" in p.tags or p.piece_id.startswith("tower_win_"):
            continue
        out.setdefault(p.level, set()).add(p.asset_id)
    return out


def _primary_window_asset(assembly, *, level: int = 0) -> str:
    assets = _hall_window_assets(assembly).get(level, set())
    assert assets, f"no hall windows on level {level}"
    assert len(assets) == 1, f"expected one window family on level {level}, got {assets}"
    return next(iter(assets))


@pytest.mark.parametrize(
    "alias,expected_piece",
    [
        ("square", "wall_window"),
        ("lancet", "wall_window_lancet"),
        ("round", "wall_window_round"),
        ("mullioned", "wall_window_mullioned"),
        ("oculus", "wall_window_oculus"),
    ],
)
def test_window_shape_aliases_resolve_to_piece_ids(alias: str, expected_piece: str):
    assert resolve_window_piece_id(None, level_override=alias) == expected_piece


def test_normalize_aperture_tag_accepts_profile_names():
    assert normalize_aperture_tag("window_round") == "window_round"
    assert normalize_aperture_tag("door_gothic", kind="door") == "door_gothic"


@pytest.mark.parametrize("style_id,expected_window", [
    ("townhouse", "wall_window"),
    ("civic", "wall_window_round"),
    ("medieval", "wall_window_mullioned"),
    ("wizard_academy", "wall_window_lancet"),
])
def test_style_pack_selects_distinct_window_pieces(style_id: str, expected_window: str):
    spec = interchange_spec(style_id)
    _massing, _plan, assembly, report = run_through_assemble(spec)
    assert report.ok, [f.message for f in report.failures]
    _, vreport = validate(assembly)
    assert vreport.critical == []
    assert _primary_window_asset(assembly) == expected_window


def test_same_sketch_different_packs_emit_different_window_piece_ids():
    pieces = {
        interchange_spec(sid).style: _primary_window_asset(run_through_assemble(interchange_spec(sid))[2])
        for sid in ("townhouse", "civic", "medieval")
    }
    assert len(set(pieces.values())) >= 3, pieces


def test_level_window_tag_override_changes_upper_storey_only():
    base = replace(m2_two_storey_stair_spec(seed=4), style="civic")
    overridden = replace(base, level_window_tags=(None, "lancet"))

    _, _, base_asm, base_report = run_through_assemble(base)
    assert base_report.ok
    _, _, ovr_asm, ovr_report = run_through_assemble(overridden)
    assert ovr_report.ok

    assert _primary_window_asset(base_asm, level=0) == "wall_window_round"
    assert _primary_window_asset(base_asm, level=1) == "wall_window_round"
    assert _primary_window_asset(ovr_asm, level=0) == "wall_window_round"
    assert _primary_window_asset(ovr_asm, level=1) == "wall_window_lancet"

    for asm in (base_asm, ovr_asm):
        _, vreport = validate(asm)
        assert vreport.critical == []


def test_structure_spec_window_tag_round_trips_to_build():
    structure = StructureSpec(
        name="opening_override",
        style="townhouse",
        seed=2,
        levels=[
            LevelSpec(sketch="####\n#S##\n####", height_units=1),
            LevelSpec(
                sketch="####\n####\n####",
                height_units=1,
                window_tag="round",
            ),
        ],
    )
    building = structure_to_building_spec(structure)
    assert building.level_window_tags == (None, "round")

    _, _, assembly, report = run_through_assemble(building)
    assert report.ok
    by_level = _hall_window_assets(assembly)
    assert len(by_level.get(0, set())) == 1
    assert by_level[0] == {"wall_window"}
    assert by_level[1] == {"wall_window_round"}
    _, vreport = validate(assembly)
    assert vreport.critical == []


def test_one_window_family_per_building_without_level_override():
    """Variation enforces one family per storey; packs must not mix on one level."""
    spec = interchange_spec("manor")
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok
    for level, assets in _hall_window_assets(assembly).items():
        assert len(assets) == 1, f"level {level} mixes {assets}"


def test_gothic_window_infers_gothic_door_when_door_tag_absent():
    style = {"window": {"tag": "window_gothic"}}
    assert resolve_door_piece_id(style, entrance_role="main") == "wall_door_gothic"


@pytest.mark.parametrize("factory", [m1_box_house_spec, m2_two_storey_stair_spec])
def test_tiny_builds_critical_empty_with_style_pack(factory):
    spec = replace(factory(), style="medieval")
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok
    _, vreport = validate(assembly)
    assert vreport.critical == []
    assert _primary_window_asset(assembly) == "wall_window_mullioned"

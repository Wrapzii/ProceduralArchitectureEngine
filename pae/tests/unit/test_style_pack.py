"""Unit tests — StylePack loader and resolution (S-001..S-011 hooks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pae.assemble import assemble
from pae.plan import plan
from pae.solver import solve
from pae.spec import STEEP_PITCH_MIN, load_style, m1_box_house_spec
from pae.style_pack import (
    ENGINE_DEFAULTS,
    StylePackError,
    choose_roof_kind,
    is_steep_silhouette_style,
    load_style_pack,
    resolve_piece_id,
    resolve_roof_kind,
    resolve_roof_pitch,
    resolve_style_pack,
)

_STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"

_ALL_BUILTIN_STYLE_IDS = (
    "townhouse",
    "keep",
    "gothic_academy",
    "wizard_academy",
    "rustic",
    "medieval",
    "manor",
    "civic",
)


@pytest.mark.parametrize("style_id", _ALL_BUILTIN_STYLE_IDS)
def test_builtin_style_packs_load(style_id: str):
    pack, report = load_style_pack(style_id)
    assert report.ok is True, [f.message for f in report.failures]
    assert pack is not None
    assert pack.id == style_id

    legacy, legacy_report = load_style(style_id)
    assert legacy_report.ok is True
    assert legacy is not None
    assert legacy["id"] == style_id
    assert legacy["roof_pitch"] == pack.geometry.roof_pitch
    assert legacy["window"]["tag"] == pack.window.tag


def test_keep_style_defaults_to_hip():
    pack, report = load_style_pack("keep")
    assert report.ok is True, [f.message for f in report.failures]
    assert pack is not None
    assert pack.roof.kind_default == "hip"
    assert resolve_roof_kind(pack, spec_kind="auto") == "hip"


def test_wizard_academy_steep_pitch_and_inheritance():
    pack, report = load_style_pack("wizard_academy")
    assert report.ok is True, [f.message for f in report.failures]
    assert pack is not None
    assert pack.geometry.roof_pitch >= STEEP_PITCH_MIN
    assert pack.roof.steep_silhouette is True
    assert pack.roof.pitch_min == STEEP_PITCH_MIN
    assert pack.roof.kind_default == "pitched"
    assert is_steep_silhouette_style(pack)
    assert resolve_roof_pitch(pack) >= STEEP_PITCH_MIN
    assert resolve_roof_kind(pack, spec_kind="auto") == "pitched"
    assert resolve_roof_kind(pack, spec_kind="flat") == "flat"
    assert choose_roof_kind(pack, seed=0, spec_kind="auto") == "pitched"
    assert pack.window.tag == "window_gothic"
    # Inherited from gothic_academy
    assert pack.materials.wall == "stone_ashlar"
    assert pack.tower.finial is True


@pytest.mark.parametrize(
    "style_id,roof_kind,window_tag,roof_pitch_min",
    [
        ("rustic", "pitched", "window_simple", 1.3),
        ("medieval", "hip", "window_mullioned", 0.8),
        ("manor", "pitched", "window_mullioned", 1.0),
        ("civic", "flat", "window_round", 0.7),
    ],
)
def test_stage_i_style_packs_distinct(
    style_id: str, roof_kind: str, window_tag: str, roof_pitch_min: float
):
    pack, report = load_style_pack(style_id)
    assert report.ok is True, [f.message for f in report.failures]
    assert pack is not None
    assert pack.id == style_id
    assert resolve_roof_kind(pack, spec_kind="auto") == roof_kind
    assert pack.window.tag == window_tag
    assert pack.geometry.roof_pitch >= roof_pitch_min
    assert pack.geometry.storey_height_cm is not None


def test_manor_has_generous_window_density():
    pack, report = load_style_pack("manor")
    assert report.ok and pack is not None
    assert pack.window.per_bay == 2
    assert pack.wall_bands.cornice_cm >= 40


def test_civic_has_grand_plinth():
    pack, report = load_style_pack("civic")
    assert report.ok and pack is not None
    assert pack.wall_bands.plinth_cm >= 65
    assert resolve_piece_id(pack.to_legacy_dict(), role="window") == "wall_window_round"


def test_medieval_tower_finial():
    pack, report = load_style_pack("medieval")
    assert report.ok and pack is not None
    assert pack.tower.cap == "cone_steep"
    assert pack.tower.finial is True
    assert resolve_piece_id(pack.to_legacy_dict(), role="window", tag="window_mullioned") == (
        "wall_window_mullioned"
    )


def test_wizard_academy_substitutes_lancet():
    style, report = load_style("wizard_academy")
    assert report.ok is True
    assert style is not None
    piece = resolve_piece_id(style, role="window", tag="window_gothic")
    assert piece == "wall_window_lancet"
    assert resolve_piece_id(style, role="window", tag="window_lancet") == "wall_window_lancet"
    assert resolve_piece_id(style, role="roof", tag="roof_pitched_slope") == "roof_pitched_slope"
    assert resolve_piece_id(style, role="roof") == "roof_pitched_slope"


def test_resolve_roof_pitch_clamps_to_style_floor():
    pack, report = load_style_pack("wizard_academy")
    assert report.ok and pack is not None
    assert resolve_roof_pitch(pack, spec_pitch=1.2) >= STEEP_PITCH_MIN
    assert resolve_roof_pitch(pack, spec_pitch=1.9) == pytest.approx(1.9)

    overridden = pack.resolve({"roof": {"pitch_min": 1.7, "steep_silhouette": True}})
    assert resolve_roof_pitch(overridden, spec_pitch=1.5) == pytest.approx(1.7)


def test_unknown_roof_nested_key_rejected(tmp_path: Path):
    bad = {
        "id": "bad_roof",
        "roof": {"pitch_min": 1.6, "unexpected": True},
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
    }
    (tmp_path / "bad_roof.json").write_text(json.dumps(bad), encoding="utf-8")

    pack, report = load_style_pack("bad_roof", styles_dir_path=tmp_path)
    assert pack is None
    assert report.ok is False
    assert any("roof" in f.message for f in report.failures)
    assert any(f.check == "style_schema" and f.critical for f in report.failures)


def test_roof_hints_known_keys_accepted(tmp_path: Path):
    """S-011 RoofHints stay first-class; only unknown nested keys fail closed."""
    good = {
        "id": "roof_ok",
        "roof": {
            "pitch_min": 1.6,
            "pitch_max": 2.0,
            "steep_silhouette": True,
            "kind_default": "pitched",
        },
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
    }
    (tmp_path / "roof_ok.json").write_text(json.dumps(good), encoding="utf-8")

    pack, report = load_style_pack("roof_ok", styles_dir_path=tmp_path)
    assert report.ok is True, [f.message for f in report.failures]
    assert pack is not None
    assert pack.roof.steep_silhouette is True
    assert pack.roof.kind_default == "pitched"
    assert pack.roof.pitch_min == pytest.approx(1.6)


def test_unknown_top_level_key_rejected(tmp_path: Path):
    bad = {
        "id": "bad_style",
        "roof_pitch": 1.0,
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
        "unexpected_field": True,
    }
    (tmp_path / "bad_style.json").write_text(json.dumps(bad), encoding="utf-8")

    pack, report = load_style_pack("bad_style", styles_dir_path=tmp_path)
    assert pack is None
    assert report.ok is False
    assert any(f.check == "style_schema" for f in report.failures)


def test_unknown_nested_key_rejected(tmp_path: Path):
    bad = {
        "id": "bad_nested",
        "geometry": {"roof_pitch": 1.2, "bogus": 1},
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
    }
    (tmp_path / "bad_nested.json").write_text(json.dumps(bad), encoding="utf-8")

    pack, report = load_style_pack("bad_nested", styles_dir_path=tmp_path)
    assert pack is None
    assert report.ok is False
    assert any("geometry" in f.message for f in report.failures)


def test_inheritance_cycle_rejected(tmp_path: Path):
    a = {"id": "cycle_a", "extends": "cycle_b", "window": {"tag": "window_plain"}}
    b = {"id": "cycle_b", "extends": "cycle_a", "window": {"tag": "window_plain"}}
    (tmp_path / "cycle_a.json").write_text(json.dumps(a), encoding="utf-8")
    (tmp_path / "cycle_b.json").write_text(json.dumps(b), encoding="utf-8")

    pack, report = load_style_pack("cycle_a", styles_dir_path=tmp_path)
    assert pack is None
    assert report.ok is False
    assert any(f.check == "style_extends" for f in report.failures)
    assert any("cycle" in f.message.lower() for f in report.failures)


def test_style_pack_error_type_on_schema(tmp_path: Path):
    """Direct resolve raises StylePackError (not bare ValueError) on bad schema."""
    bad = {
        "id": "err_type",
        "geometry": {"roof_pitch": 1.0, "nope": True},
        "window": {"tag": "window_plain"},
    }
    (tmp_path / "err_type.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(StylePackError) as ei:
        resolve_style_pack("err_type", styles_dir_path=tmp_path)
    assert ei.value.check == "style_schema"


def test_resolution_order_engine_default_then_pack_then_override():
    base = resolve_style_pack("townhouse")
    assert base is not None
    assert base.geometry.roof_pitch == 1.0

    overridden = base.resolve({"geometry": {"roof_pitch": 1.25}})
    assert overridden.geometry.roof_pitch == 1.25
    assert overridden.window.tag == base.window.tag

    assert ENGINE_DEFAULTS.geometry.roof_pitch == 1.0
    assert ENGINE_DEFAULTS.window.tag == "window_plain"


def test_m1_townhouse_still_validates():
    """M1 milestone assembly unchanged after StylePack bridge (townhouse windows)."""
    spec = m1_box_house_spec()
    massing, mreport = solve(spec)
    assert mreport.ok is True
    floor_plan, preport = plan(massing)
    assert preport.ok is True
    style, sreport = load_style(spec.style)
    assert sreport.ok is True
    assert resolve_piece_id(style, role="window") == "wall_window"
    assembly, areport = assemble(floor_plan, None, style)
    assert areport.ok is True, [f.message for f in areport.failures]
    windows = [p for p in assembly.placements if "window" in p.asset_id]
    assert len(windows) == 2
    assert {p.asset_id for p in windows} == {"wall_window"}

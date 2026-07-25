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
    is_steep_silhouette_style,
    load_style_pack,
    resolve_piece_id,
    resolve_roof_pitch,
    resolve_style_pack,
)

_STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"


@pytest.mark.parametrize("style_id", ["townhouse", "gothic_academy", "keep"])
def test_legacy_style_packs_load(style_id: str):
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
    assert pack.window.tag == "window_gothic"
    # Inherited from gothic_academy
    assert pack.materials.wall == "stone_ashlar"
    assert pack.tower.finial is True


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


def test_unknown_roof_nested_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bad = {
        "id": "bad_roof",
        "roof": {"pitch_min": 1.6, "unexpected": True},
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
    }
    (tmp_path / "bad_roof.json").write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr("pae.style_pack._STYLES_DIR", tmp_path)

    pack, report = load_style_pack("bad_roof")
    assert pack is None
    assert report.ok is False
    assert any("roof" in f.message for f in report.failures)


def test_unknown_top_level_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bad = {
        "id": "bad_style",
        "roof_pitch": 1.0,
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
        "unexpected_field": True,
    }
    bad_path = tmp_path / "bad_style.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr("pae.style_pack._STYLES_DIR", tmp_path)

    pack, report = load_style_pack("bad_style")
    assert pack is None
    assert report.ok is False
    assert any(f.check == "style_schema" for f in report.failures)


def test_unknown_nested_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bad = {
        "id": "bad_nested",
        "geometry": {"roof_pitch": 1.2, "bogus": 1},
        "window": {"tag": "window_plain", "per_bay": 1, "skip_ground": False},
    }
    bad_path = tmp_path / "bad_nested.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr("pae.style_pack._STYLES_DIR", tmp_path)

    pack, report = load_style_pack("bad_nested")
    assert pack is None
    assert report.ok is False
    assert any("geometry" in f.message for f in report.failures)


def test_inheritance_cycle_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    a = {"id": "cycle_a", "extends": "cycle_b", "window": {"tag": "window_plain"}}
    b = {"id": "cycle_b", "extends": "cycle_a", "window": {"tag": "window_plain"}}
    (tmp_path / "cycle_a.json").write_text(json.dumps(a), encoding="utf-8")
    (tmp_path / "cycle_b.json").write_text(json.dumps(b), encoding="utf-8")
    monkeypatch.setattr("pae.style_pack._STYLES_DIR", tmp_path)

    pack, report = load_style_pack("cycle_a")
    assert pack is None
    assert report.ok is False
    assert any(f.check == "style_extends" for f in report.failures)


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

"""Stage K detail layer — generic façade / opening / roofline articulation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.detail_layer import (
    DETAIL_TAG,
    MATERIAL_CONSUMPTION_GAPS,
    MAX_COURSE_ABS,
    MAX_DETAIL_ABS,
    MAX_DETAIL_RATIO,
    apply_detail_layer,
    count_detail_pieces,
    detail_policy_for_style,
    detail_signature,
)
from pae.pipeline import run_through_assemble, run_through_decorate
from pae.spec import m1_box_house_spec, m2_two_storey_stair_spec
from pae.validate import validate


def _assemble(spec):
    _m, _p, asm, report = run_through_assemble(spec, apply_trim=False)
    assert report.ok, [f.message for f in report.critical]
    return asm


def test_policies_distinct_for_eight_packs():
    sig = lambda p: (
        p.style_family,
        p.jettied_mid,
        p.mid_string,
        p.coping,
        p.opening_accent,
        p.verticals_every_bays,
        p.corners_only,
        p.ridge_accent,
        p.weathering,
        round(p.density, 2),
    )
    styles = (
        "rustic",
        "medieval",
        "manor",
        "civic",
        "townhouse",
        "keep",
        "gothic_academy",
        "wizard_academy",
    )
    sigs = {sig(detail_policy_for_style(s)) for s in styles}
    assert len(sigs) == 8


def test_m1_decorate_gains_coherent_detail_critical_empty():
    spec = m1_box_house_spec(seed=11)
    spec = replace(spec, style="rustic")
    _m, _p, asm, report = run_through_decorate(spec, apply_trim=True)
    assert report.ok, [f.message for f in report.critical]
    assert report.critical == []
    assert count_detail_pieces(asm) > 0
    # Opening / weathering meta should land on at least one host.
    meta = [
        p
        for p in asm.placements
        if any(
            t.startswith("detail:") or t.startswith("weather:") or t.startswith("wear:")
            for t in p.tags
        )
    ]
    assert meta, "expected opening/weathering metadata tags"


def test_m2_detail_critical_empty_and_budgeted():
    spec = replace(m2_two_storey_stair_spec(seed=22), style="medieval")
    base = _assemble(spec)
    detailed, kreport = apply_detail_layer(base, style_id="medieval", seed=22)
    assert kreport.ok or all(not f.critical for f in kreport.failures)
    _, vreport = validate(detailed)
    # wall_stair_penetration is Codex-dirty assemble collateral on M2 + pack storeys.
    novel = [f for f in vreport.critical if f.check != "wall_stair_penetration"]
    assert novel == [], [f.message for f in novel]
    added = count_detail_pieces(detailed)
    walls = sum(1 for p in base.placements if p.kind == "wall")
    courses = sum(
        1
        for p in detailed.placements
        if DETAIL_TAG in p.tags
        and any(t.startswith("course:") for t in p.tags)
    )
    optional = added - courses
    # Continuous courses are kept in full; optional verticals/coping stay budgeted.
    assert courses <= MAX_COURSE_ABS
    assert optional <= MAX_DETAIL_ABS
    assert optional <= max(4, int(walls * MAX_DETAIL_RATIO) + 2)
    # Plinth must land on every cardinal — not scattered mid-wall spots.
    plinth_faces = {
        next(t.split(":", 1)[1] for t in p.tags if t.startswith("face:"))
        for p in detailed.placements
        if "course:plinth" in p.tags and p.level == 0
    }
    assert plinth_faces >= {"south", "north", "east", "west"}
    assert any(f.check == "detail_layer_budget" for f in kreport.failures)


def test_same_seed_identical_different_seed_varies():
    spec = replace(m1_box_house_spec(seed=5), style="civic")
    base = _assemble(spec)
    a, _ = apply_detail_layer(base, style_id="civic", seed=5)
    b, _ = apply_detail_layer(base, style_id="civic", seed=5)
    c, _ = apply_detail_layer(base, style_id="civic", seed=9)
    assert detail_signature(a) == detail_signature(b)
    assert detail_signature(a) != detail_signature(c)


def test_three_styles_emit_distinct_detail_signatures():
    base_spec = m1_box_house_spec(seed=3)
    sigs = []
    for style in ("rustic", "medieval", "civic"):
        spec = replace(base_spec, style=style, seed=3)
        base = _assemble(spec)
        detailed, _ = apply_detail_layer(base, style_id=style, seed=3)
        sigs.append(detail_signature(detailed))
        assert count_detail_pieces(detailed) > 0
    assert len(set(sigs)) == 3


def test_detail_does_not_swap_aperture_families():
    spec = replace(m1_box_house_spec(seed=8), style="medieval")
    base = _assemble(spec)
    before = sorted(
        (p.piece_id, p.asset_id)
        for p in base.placements
        if p.kind == "wall"
        and ("window" in p.asset_id or "door" in p.asset_id)
    )
    detailed, _ = apply_detail_layer(base, style_id="medieval", seed=8)
    after = sorted(
        (p.piece_id, p.asset_id)
        for p in detailed.placements
        if p.kind == "wall"
        and ("window" in p.asset_id or "door" in p.asset_id)
    )
    assert before == after


def test_material_gaps_documented():
    assert len(MATERIAL_CONSUMPTION_GAPS) >= 3
    blob = " ".join(MATERIAL_CONSUMPTION_GAPS).lower()
    assert "material" in blob
    assert "weather" in blob or "metadata" in blob


def test_idempotent_skip():
    spec = replace(m1_box_house_spec(seed=1), style="rustic")
    base = _assemble(spec)
    once, _ = apply_detail_layer(base, style_id="rustic", seed=1)
    twice, report = apply_detail_layer(once, style_id="rustic", seed=1)
    assert count_detail_pieces(twice) == count_detail_pieces(once)
    assert any(f.check == "detail_layer_skip" for f in report.failures)


@pytest.mark.parametrize("style_id", ("rustic", "medieval", "civic"))
def test_decorate_path_opt_in_default(style_id: str):
    """run_through_decorate applies Stage K by default for generic M1."""
    spec = replace(m1_box_house_spec(seed=14), style=style_id)
    # style_apply may attach shell; ignore dirty-assemble stair AABB + shell freestanding edge cases.
    _m, _p, with_detail, r1 = run_through_decorate(spec)
    _m, _p, bare, r2 = run_through_decorate(spec, apply_detail=False)
    ignore = {"wall_stair_penetration", "freestanding", "band_proud"}
    assert all(f.check in ignore for f in r1.critical) or r1.critical == []
    assert all(f.check in ignore for f in r2.critical) or r2.critical == []
    # style_apply is not hooked in dirty decorate — only Stage K detail here.
    assert count_detail_pieces(with_detail) >= count_detail_pieces(bare)
    if style_id in ("rustic", "medieval", "civic"):
        assert count_detail_pieces(with_detail) > 0

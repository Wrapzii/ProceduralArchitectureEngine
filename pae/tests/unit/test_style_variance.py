"""STYLE-V — packs must differ on door / roof / proportion / shell axes."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.pipeline import run_through_assemble
from pae.spec import RoofSpec, m2_two_storey_stair_spec
from pae.style_apply import apply_style_shell, count_shell_pieces, style_shell_signature
from pae.style_pack import (
    load_style_pack,
    resolve_door_piece_id,
    resolve_eave_overhang_cm,
    resolve_roof_kind,
    resolve_roof_pitch,
    resolve_storey_height_cm,
    resolve_window_piece_id,
)

_ALL = (
    "rustic",
    "medieval",
    "manor",
    "civic",
    "townhouse",
    "keep",
    "gothic_academy",
    "wizard_academy",
)


def _spec(style_id: str, seed: int = 7):
    return replace(
        m2_two_storey_stair_spec(seed=seed),
        name=f"variance_{style_id}",
        style=style_id,
        roof=RoofSpec(kind="auto", pitch=1.0),
    )


def test_door_piece_ids_differ_across_packs():
    doors = {sid: resolve_door_piece_id(load_style_pack(sid)[0]) for sid in _ALL}
    assert len(set(doors.values())) >= 4, doors


def test_roof_kind_and_pitch_differ():
    kinds = set()
    pitches = set()
    for sid in _ALL:
        pack, report = load_style_pack(sid)
        assert report.ok and pack is not None
        kinds.add(resolve_roof_kind(pack, spec_kind="auto"))
        pitches.add(round(resolve_roof_pitch(pack), 2))
    assert len(kinds) >= 2
    assert len(pitches) >= 4


def test_storey_heights_span_wide_range():
    heights = {
        sid: resolve_storey_height_cm(load_style_pack(sid)[0]) for sid in _ALL
    }
    assert max(heights.values()) - min(heights.values()) >= 150, heights


def test_style_apply_swaps_doors_and_adds_shell():
    rustic_spec = _spec("rustic", 7)
    civic_spec = _spec("civic", 7)
    _, _, rustic_asm, r1 = run_through_assemble(rustic_spec)
    _, _, civic_asm, r2 = run_through_assemble(civic_spec)
    assert r1.ok and r2.ok
    rustic, _ = apply_style_shell(rustic_asm, style_id="rustic", seed=7)
    civic, _ = apply_style_shell(civic_asm, style_id="civic", seed=7)
    rustic_doors = {p.asset_id for p in rustic.placements if "door" in p.asset_id or "gate" in p.asset_id}
    civic_doors = {p.asset_id for p in civic.placements if "door" in p.asset_id or "gate" in p.asset_id}
    assert rustic_doors != civic_doors or count_shell_pieces(rustic) != count_shell_pieces(civic)
    rustic_shell = count_shell_pieces(rustic)
    civic_shell = count_shell_pieces(civic)
    # Legible entrance kit: forecourt / stoop / wall-flush door surround (jambs+lintel).
    assert "forecourt_wall" in rustic_shell or any(
        "door_jamb" in p.piece_id or "door_lintel" in p.piece_id for p in rustic.placements
    )
    assert "steps_external" in civic_shell or any(
        "door_jamb" in p.piece_id for p in civic.placements
    )
    assert "porch_post" not in rustic_shell and "porch_post" not in civic_shell
    assert not any(aid.startswith("doorcase_") for aid in rustic_shell)
    assert not any(aid.startswith("doorcase_") for aid in civic_shell)


def test_keep_skip_ground_removes_l0_windows():
    pack, _ = load_style_pack("keep")
    assert pack is not None and pack.window.skip_ground is True
    _, _, asm, report = run_through_assemble(_spec("keep", 7))
    assert report.ok
    applied, _ = apply_style_shell(asm, style_id="keep", seed=7)
    l0_glaze = [
        p
        for p in applied.placements
        if p.level == 0 and ("window" in p.asset_id or "arrowslit" in p.asset_id)
    ]
    assert l0_glaze == []


def test_same_seed_style_apply_deterministic():
    _, _, base, report = run_through_assemble(_spec("manor", 11))
    assert report.ok
    a, _ = apply_style_shell(base, style_id="manor", seed=11)
    b, _ = apply_style_shell(base, style_id="manor", seed=11)
    assert style_shell_signature(a) == style_shell_signature(b)


def test_eave_overhang_authored_and_distinct():
    eaves = {
        sid: resolve_eave_overhang_cm(load_style_pack(sid)[0]) for sid in _ALL
    }
    assert max(eaves.values()) - min(eaves.values()) >= 40, eaves


def test_window_piece_ids_cover_multiple_families():
    wins = {sid: resolve_window_piece_id(load_style_pack(sid)[0]) for sid in _ALL}
    assert len(set(wins.values())) >= 5, wins


def test_plinth_cornice_visually_large():
    for sid in ("civic", "keep", "medieval", "manor"):
        pack, report = load_style_pack(sid)
        assert report.ok and pack is not None
        assert pack.wall_bands.plinth_cm >= 70
        assert pack.wall_bands.cornice_cm >= 40

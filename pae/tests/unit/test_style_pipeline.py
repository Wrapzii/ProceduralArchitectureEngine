"""RAM-safe proof that style_pipeline wires shell before detail (≥2 packs)."""

from __future__ import annotations

from dataclasses import replace

from pae.pipeline import run_through_assemble
from pae.spec import RoofSpec, m2_two_storey_stair_spec
from pae.style_apply import count_shell_pieces
from pae.style_pipeline import apply_style_then_detail


def _spec(style_id: str, seed: int = 7):
    return replace(
        m2_two_storey_stair_spec(seed=seed),
        name=f"pipeline_{style_id}",
        style=style_id,
        roof=RoofSpec(kind="auto", pitch=1.0),
    )


_SHELL_MARKERS = frozenset(
    {
        "forecourt_wall",
        "planter_wall",
        "steps_external",
        "porch_slab",
        "porch_roof",
        "band_pilaster",  # door jambs / corner emphasis
        "band_course",  # door lintel
        "bargeboard",
        "chimney_stub",
    }
)


def _has_shell_marker(counts: dict) -> bool:
    return bool(_SHELL_MARKERS.intersection(counts))


def test_apply_style_then_detail_emits_shell_on_rustic_and_civic():
    for style_id in ("rustic", "civic"):
        _, _, base, areport = run_through_assemble(_spec(style_id, 7))
        assert areport.ok, (style_id, [f.message for f in areport.critical])
        assembly, mid_report = apply_style_then_detail(
            base, style_id=style_id, seed=7
        )
        assert not mid_report.critical, (style_id, mid_report.critical)
        counts = count_shell_pieces(assembly)
        assert _has_shell_marker(counts), (style_id, counts)
        # No freestanding portal / porch-rail geometry.
        assert "porch_post" not in counts
        assert not any(k.startswith("doorcase_") for k in counts)
        assert any("door_jamb" in p.piece_id for p in assembly.placements)


def test_style_shell_opt_out_skips_markers():
    _, _, base, areport = run_through_assemble(_spec("manor", 7))
    assert areport.ok
    assembly, _ = apply_style_then_detail(
        base, style_id="manor", seed=7, apply_style_shell=False
    )
    assert count_shell_pieces(assembly) == {}

"""D3 wiring smoke — feature reachable from showcase builds (Handbook §11d / Roadmap 10.7).

These are not validators: they assert mechanisms actually ran on paths users build.
Defects D3-3/4/5 were correct code left unwired at call sites.
"""

from __future__ import annotations

from dataclasses import replace

from pae.approach_stairs import (
    check_approach_stair_aligned_to_gate,
    check_approach_stair_height_mate,
)
from pae.assemble import _MONUMENTAL_PAD_KINDS, assemble
from pae.compound import (
    FORTRESS_CURTAIN_TRIM,
    FORTRESS_GATEHOUSE_TRIM,
    GATEHOUSE_TRIM,
    build_castle_curtain_compound,
    build_fortress_compound,
)
from pae.plan import plan as plan_floor
from pae.pipeline import run_through_assemble
from pae.roof_edging import check_roof_edging_exclusive
from pae.solver import Massing, Volume, solve
from pae.spec import fortress_gatehouse_spec
from pae.validate import _check_stair_flight_stack, validate


def test_monumental_pad_kinds_include_straight():
    assert "straight" in _MONUMENTAL_PAD_KINDS
    assert "switchback" in _MONUMENTAL_PAD_KINDS
    assert "wide" in _MONUMENTAL_PAD_KINDS


def test_assemble_fail_closed_skips_stacked_flights():
    """Undersized 2×2 well on 3 storeys: critical failure, zero stair pieces (D3-3)."""
    hall = Volume(
        id="hall",
        x0=0,
        y0=0,
        x1=6,
        y1=4,
        storeys=3,
        role="hall",
        entrance=False,
    )
    massing = Massing(
        volumes=[hall],
        entrance_volume_id="hall",
        storeys=3,
        seed=42,
        stair_kind="switchback",
        stair_cells=[(1, 1), (2, 1), (1, 2), (2, 2)],
    )
    floor_plan, _ = plan_floor(massing)
    assembly, areport = assemble(floor_plan, asset_db=None, style=None)
    stack = [f for f in areport.failures if f.check == "stair_flight_stack" and f.critical]
    assert stack, "must emit stair_flight_stack for undersized monumental well"
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert stairs == [], "fail-closed must not place stacked flights"


def test_fortress_gatehouse_straight_well_expanded():
    """6×3 gatehouse: solver expands straight well; no flight stack (D3-3)."""
    spec = fortress_gatehouse_spec()
    massing, _, assembly, _ = run_through_assemble(spec)
    assert massing.stair_kind == "straight"
    assert len(massing.stair_cells) >= 8, massing.stair_cells
    assert _check_stair_flight_stack(assembly) == []


def test_gatehouse_trim_wires_exterior_steps_repair():
    assert GATEHOUSE_TRIM.exterior_steps is True
    assert FORTRESS_GATEHOUSE_TRIM.exterior_steps is True


def test_fortress_curtain_trim_defers_parapets_for_battlements():
    """Curtain crenels post-merge — no parapet_solid on same edge (D3-4)."""
    assert FORTRESS_CURTAIN_TRIM.parapets is False


def test_fortress_compound_approach_and_edging_wired():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    approach = [
        p
        for p in assembly.placements
        if p.asset_id in ("steps_grand", "steps_external")
        and p.level == 0
    ]
    assert approach, "post-merge repair_approach_stairs must place flanking steps"
    assert check_approach_stair_height_mate(assembly) == []
    assert check_approach_stair_aligned_to_gate(assembly) == []

    battlements = [p for p in assembly.placements if p.asset_id == "battlement"]
    assert battlements, "curtain battlements must run after parapet deferral"

    assert check_roof_edging_exclusive(assembly) == []
    _, vreport = validate(assembly)
    assert not any(f.check == "roof_edging_exclusive" for f in vreport.critical)
    assert not any(f.check == "stair_flight_stack" for f in vreport.critical)


def test_castle_curtain_compound_approach_repaired_post_merge():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok, [f.message for f in report.failures]

    steps = [
        p
        for p in assembly.placements
        if p.asset_id in ("steps_grand", "steps_external") and p.level == 0
    ]
    assert steps, "castle curtain must call repair_approach_stairs post-merge (D3-5)"
    assert check_approach_stair_height_mate(assembly) == []
    assert check_roof_edging_exclusive(assembly) == []


def test_fortress_gatehouse_trim_alone_still_repairs_approach():
    """Per-range trim path must reach repair_approach_stairs, not only compound post-merge."""
    from pae.trim import trim

    _, _, assembled, _ = run_through_assemble(fortress_gatehouse_spec())
    trimmed, treport = trim(assembled, FORTRESS_GATEHOUSE_TRIM)
    assert treport.ok
    steps = [p for p in trimmed.placements if p.asset_id == "steps_grand" and p.level == 0]
    assert steps
    assert check_approach_stair_height_mate(trimmed) == []

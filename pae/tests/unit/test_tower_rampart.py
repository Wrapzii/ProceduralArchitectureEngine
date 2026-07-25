"""Phase 4.7 — tower rampart ring, walkable crown deck, view crenels.

Broken fixtures first (VALIDATION_HANDBOOK §6): each check must fail on a
hand-built poison before we assert live assemble output is green.
"""

from __future__ import annotations

from dataclasses import replace

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.spec import m3_keep_tower_spec, m_spiral_tower_spec
from pae.tower_rampart import (
    TOWER_CRENEL_TAG,
    TOWER_DECK_TAG,
    TOWER_RAMPART_TAG,
    check_tower_rampart_ring,
    check_tower_top_walkable,
    check_view_aperture_exists,
)
from pae.validate import validate


def _tower_cell(assembly: Assembly):
    crowns = [p for p in assembly.placements if p.asset_id == "tower_crown"]
    assert crowns, "expected tower_crown in assembly"
    return crowns[0].cell, crowns[0].level


# --- Broken fixtures first -------------------------------------------------


def test_broken_missing_deck_fails_tower_top_walkable():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    cell, level = _tower_cell(assembly)
    broken = Assembly(
        placements=[
            p
            for p in assembly.placements
            if not (p.cell == cell and p.level == level and TOWER_DECK_TAG in p.tags)
        ],
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    fails = check_tower_top_walkable(broken)
    assert fails, "missing crown deck must fail tower_top_walkable"
    assert all(f.check == "tower_top_walkable" for f in fails)
    assert all(f.critical for f in fails)


def test_broken_missing_crown_fails_tower_rampart_ring():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    cell, level = _tower_cell(assembly)
    broken = Assembly(
        placements=[
            p
            for p in assembly.placements
            if not (
                p.cell == cell
                and p.level == level
                and (
                    p.asset_id == "tower_crown"
                    or TOWER_RAMPART_TAG in p.tags
                    or p.kind == "battlement"
                )
            )
        ],
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    fails = check_tower_rampart_ring(broken)
    assert fails, "missing rampart ring must fail tower_rampart_ring"
    assert all(f.check == "tower_rampart_ring" for f in fails)


def test_broken_partial_battlement_fails_continuity_stub():
    """One quadrant battlement leaves a >90° gap — continuity stub must fire."""
    cell = (0, 0)
    level = 1
    # Minimal tower cue so the cell is discovered.
    arc = SolidPlacement(
        piece_id="arc0",
        asset_id="tower_arc_quarter",
        kind="tower_arc",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
        rotates_about_center=True,
        tags=frozenset({"tower", "arc"}),
    )
    # Single west-face battlement — covers only one side of the drum.
    batt = SolidPlacement(
        piece_id="batt_w",
        asset_id="battlement",
        kind="battlement",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(-MODULE_CM * 0.5 + WALL_T_CM * 0.5, 0.0, STOREY_CM),
        size_cm=(WALL_T_CM, MODULE_CM * 0.5, STOREY_CM * 0.22),
        rotates_about_center=True,
        tags=frozenset({TOWER_RAMPART_TAG, "battlement"}),
    )
    poison = Assembly(placements=[arc, batt], apertures=[])
    fails = check_tower_rampart_ring(poison)
    assert fails
    assert any(
        "continuity" in f.message or "covers only" in f.message for f in fails
    ), [f.message for f in fails]


def test_broken_missing_crenel_warns_view_aperture_exists():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    cell, level = _tower_cell(assembly)
    placements = [
        p
        for p in assembly.placements
        if not (p.cell == cell and p.level == level and TOWER_CRENEL_TAG in p.tags)
    ]
    apertures = [
        a
        for a in assembly.apertures
        if not (
            a.interior_cell == cell
            and a.level == level
            and (
                (a.wall_piece_id or "").startswith("tower_crenel_")
                or a.piece_id.startswith("crenel_")
            )
        )
    ]
    broken = Assembly(
        placements=placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    fails = check_view_aperture_exists(broken)
    assert fails, "missing crenels must fail view_aperture_exists"
    assert all(f.check == "view_aperture_exists" for f in fails)
    assert all(not f.critical for f in fails), "view_aperture_exists is warning-level"


# --- Live assemble must satisfy ---------------------------------------------


def test_m3_tower_has_walkable_deck_and_rampart_ring():
    _, _, assembly, areport = run_through_assemble(m3_keep_tower_spec())
    assert areport.ok, [f.message for f in areport.failures]
    cell, level = _tower_cell(assembly)
    decks = [
        p
        for p in assembly.placements
        if p.cell == cell and p.level == level and TOWER_DECK_TAG in p.tags
    ]
    assert decks, "expected tower_deck at crown"
    crowns = [
        p
        for p in assembly.placements
        if p.cell == cell
        and p.level == level
        and p.asset_id == "tower_crown"
        and "junction" not in p.tags
    ]
    assert crowns
    assert TOWER_RAMPART_TAG in crowns[0].tags
    assert check_tower_top_walkable(assembly) == []
    assert check_tower_rampart_ring(assembly) == []


def test_m3_tower_has_outward_crenels():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    cell, level = _tower_cell(assembly)
    crenels = [
        p
        for p in assembly.placements
        if p.cell == cell and p.level == level and TOWER_CRENEL_TAG in p.tags
    ]
    assert crenels, "expected outward crenel shells"
    # Attach face skipped — fewer than 4 when tower kisses a hall.
    assert len(crenels) >= 2
    assert check_view_aperture_exists(assembly) == []
    # Crenels face outward (kind=battlement, not wall) so roof_penetration stays clean.
    assert all(p.kind == "battlement" for p in crenels)


def test_tower_rampart_checks_pass_in_full_validate():
    for spec in (m3_keep_tower_spec(), m_spiral_tower_spec()):
        _, _, assembly, _ = run_through_assemble(spec)
        _, vreport = validate(assembly)
        rampart_fails = [
            f
            for f in vreport.failures
            if f.check
            in ("tower_rampart_ring", "tower_top_walkable", "view_aperture_exists")
        ]
        assert rampart_fails == [], [f.message for f in rampart_fails]


def test_ramparts_do_not_cause_roof_penetration_or_headroom():
    """Place ramparts so they do not falsely pierce roofs / plug headroom."""
    for spec in (m3_keep_tower_spec(), m_spiral_tower_spec()):
        _, _, assembly, _ = run_through_assemble(spec)
        _, vreport = validate(assembly)
        bad = [
            f
            for f in vreport.critical
            if f.check in ("roof_penetration", "headroom")
            and (
                TOWER_DECK_TAG in (f.message or "")
                or TOWER_CRENEL_TAG in (f.message or "")
                or "tower_crenel" in (f.piece_id or "")
                or "tower_deck" in (f.piece_id or "")
                or "battlement" in (f.message or "").lower()
            )
        ]
        assert bad == [], [f.message for f in bad]


def test_spiral_trim_still_ok_with_ramparts():
    _, _, _, stage_report = run_through_validate_trim(m_spiral_tower_spec())
    rampart_crit = [
        f
        for f in stage_report.critical
        if f.check in ("tower_rampart_ring", "tower_top_walkable")
    ]
    assert rampart_crit == [], [f.message for f in rampart_crit]


def test_deck_top_meets_crown_plate():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    cell, level = _tower_cell(assembly)
    from pae.validate import _placement_aabb

    deck = next(
        p
        for p in assembly.placements
        if p.cell == cell and p.level == level and TOWER_DECK_TAG in p.tags
    )
    crown = next(
        p
        for p in assembly.placements
        if p.cell == cell
        and p.level == level
        and p.asset_id == "tower_crown"
        and "junction" not in p.tags
    )
    deck_top = _placement_aabb(deck)[1][2]
    crown_base = _placement_aabb(crown)[0][2]
    # Deck at junction plate; crown above junction+gap — small positive clearance.
    assert deck_top <= crown_base + FLOOR_T_CM
    assert crown_base - deck_top < STOREY_CM * 0.25

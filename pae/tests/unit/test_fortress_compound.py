"""Fortress / bailey campus compound (flat-ground castle massing)."""

from __future__ import annotations

from pae.compound import (
    FORTRESS_CLOISTER_TRIM,
    FORTRESS_CURTAIN_TRIM,
    FORTRESS_GATEHOUSE_TRIM,
    FORTRESS_KEEP_TRIM,
    build_fortress_bailey_compound,
    build_fortress_compound,
    check_fortress_compound,
    check_range_chain_connection,
    fortress_bailey_ranges,
)
from pae.existence import placed_entrance_roles
from pae.spec import (
    fortress_bailey_compound_spec,
    fortress_cloister_range_spec,
    fortress_gatehouse_spec,
    fortress_keep_spec,
)
from pae.validate import validate


def test_fortress_factories_are_declarative():
    keep = fortress_keep_spec()
    gate = fortress_gatehouse_spec()
    cloister = fortress_cloister_range_spec("west_cloister", 3, 5)
    bailey = fortress_bailey_compound_spec()

    assert keep.storeys == 3
    assert keep.roof.kind == "hip"
    assert keep.roof.pitch >= 1.6
    assert len(keep.towers) >= 4
    assert any(t.attached_to == "wall" for t in keep.towers)
    assert any(t.attached_to == "corner" for t in keep.towers)
    assert len({t.storeys for t in keep.towers}) >= 2

    assert gate.footprint.bays_x >= 6
    assert gate.footprint.bays_y >= 3
    assert gate.storeys >= 2
    assert len(gate.entrances) == 2
    assert all(e.role == "gate" for e in gate.entrances)
    assert {e.bay for e in gate.entrances} == {2, 3}
    assert len(gate.towers) == 2
    # Drums taller than the hall, but still kissable (hall+1).
    assert max(t.storeys for t in gate.towers) >= gate.storeys + 1

    assert cloister.footprint.bays_x == 3
    assert cloister.roof.kind == "hip"
    assert bailey.court_bays_x >= 6
    assert bailey.approach_rows >= 1
    assert bailey.approach_clearance_bays >= 1


def test_fortress_bailey_ranges_structure():
    styles = fortress_bailey_ranges()
    names = [s.name for s in styles]
    assert names == [
        "west_curtain",
        "gatehouse",
        "east_curtain",
        "west_cloister",
        "east_cloister",
        "north_keep",
    ]
    by_name = {s.name: s for s in styles}
    assert by_name["north_keep"].trim == FORTRESS_KEEP_TRIM
    assert by_name["west_cloister"].trim == FORTRESS_CLOISTER_TRIM
    assert by_name["west_curtain"].trim == FORTRESS_CURTAIN_TRIM
    assert by_name["gatehouse"].trim == FORTRESS_GATEHOUSE_TRIM
    assert by_name["west_curtain"].trim.buttresses is True
    assert by_name["west_curtain"].trim.parapets is False
    assert by_name["north_keep"].trim.buttresses is True
    # Arcade is compound-stage (rect ranges have no COURTYARD for trim colonnade).
    assert by_name["west_cloister"].trim.colonnade is False
    assert by_name["west_cloister"].trim.arcade_piece == "wall_arcade"
    assert by_name["north_keep"].trim.spire_piece == "spire_needle"


def test_build_fortress_compound_succeeds():
    assembly, layout, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    assert "north_keep" in layout.ranges
    assert "gatehouse" in layout.ranges
    assert assembly.placements


def test_fortress_compound_has_towers_spires_gate_courts():
    assembly, layout, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    tower_arcs = [p for p in assembly.placements if p.kind == "tower_arc"]
    assert len(tower_arcs) >= 16, f"expected many tower quarters, got {len(tower_arcs)}"

    spires = [
        p
        for p in assembly.placements
        if p.asset_id in ("spire_needle", "spire_octagonal")
    ]
    assert spires, "expected needle/octagonal spires on fortress towers"

    gates = [
        p
        for p in assembly.placements
        if "gatehouse" in p.tags
        and p.kind == "wall"
        and "gate" in (p.asset_id or "").lower()
    ]
    assert len(gates) >= 2, f"twin gate arches missing; got {len(gates)}"
    assert all(
        p.asset_id in ("wall_gate_arch", "wall_gate_arch_grand") for p in gates
    )

    assert "gate" in placed_entrance_roles(assembly)

    approach = [
        p
        for p in assembly.placements
        if "approach" in p.tags or "causeway" in p.tags
    ]
    assert approach, "grand exterior approach causeway missing"
    assert all(p.asset_id in ("steps_external", "steps_grand") for p in approach)
    # Walkthrough columns under gate leaves must stay clear of step AABBs.
    leaf_xs = {g.cell[0] for g in gates}
    assert not any(s.cell[0] in leaf_xs for s in approach), (
        "approach steps must flank gate openings, not sit in passage columns"
    )

    cloister_arcade = [
        p
        for p in assembly.placements
        if p.asset_id in ("wall_arcade", "wall_arcade_monumental", "arch_freestanding")
        and any(t in p.tags for t in ("west_cloister", "east_cloister"))
    ]
    assert cloister_arcade, "cloister arcade (wall_arcade) missing"

    battlements = [p for p in assembly.placements if p.asset_id == "battlement"]
    assert battlements, "curtain battlements missing"

    buttresses = [p for p in assembly.placements if p.asset_id == "buttress"]
    assert buttresses, "curtain/keep buttresses missing (TrimOptions.buttresses=True)"
    tagged_butts = [
        p
        for p in buttresses
        if any(
            t.startswith("building:")
            or t in ("west_curtain", "east_curtain", "north_keep", "gatehouse")
            for t in p.tags
        )
    ]
    assert tagged_butts, "post-merge buttresses must carry building:/range tags"

    assert any("fortress_compound" in p.tags for p in assembly.placements)
    assert any("grand_approach" in p.tags for p in assembly.placements)

    dormers = [p for p in assembly.placements if "dormer" in p.asset_id]
    assert dormers, "keep dormers missing on hip roof"

    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    assert hips, "fortress keep/cloister wings should use roof_hip"
    gables = [p for p in assembly.placements if p.asset_id == "roof_gable_infill"]
    assert not gables, "fortress campus must not stack gable infill prisms on hips"

    assert layout.courtyard, "expected open courtyard cells in bailey campus"


def test_fortress_south_curtain_chain_connected():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    failures = check_range_chain_connection(
        assembly, ["west_curtain", "gatehouse", "east_curtain"]
    )
    assert failures == []
    assert check_fortress_compound(assembly) == []


def test_fortress_gatehouse_retains_hall_stair_and_shell_counts():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    hall = [
        p
        for p in assembly.placements
        if "gatehouse" in (p.piece_id or "")
        and (p.asset_id or "") in {
            "stair_straight",
            "stair_switchback",
            "stair_wide",
        }
        and p.level == 0
    ]
    assert hall, "gatehouse must ship an L0 hall stair well"
    stairs = sum(1 for p in assembly.placements if "stair" in (p.asset_id or ""))
    assert stairs >= 40, f"expected hall+helix stairs, got {stairs}"
    from pae.fortress_validate import (
        check_fortress_gatehouse_hall_stair,
        check_fortress_merge_wall_shell,
    )

    assert check_fortress_gatehouse_hall_stair(assembly) == []
    assert check_fortress_merge_wall_shell(assembly) == []


def test_fortress_compound_validates_critical_empty():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    _, vreport = validate(assembly)
    # buttress_outward stays CRITICAL (not demoted). Post-merge apply_buttresses
    # should clear it when kit orientation is correct; massing must not ship
    # other criticals. Buttress emit is asserted separately above.
    assert vreport.critical == [], [
        f"{f.check}: {f.message}" for f in vreport.critical
    ]


def test_fortress_compound_is_deterministic():
    a1, _, r1 = build_fortress_compound()
    a2, _, r2 = build_fortress_compound()
    assert r1.ok and r2.ok
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]


def test_build_fortress_bailey_compound_alias():
    a1, l1, r1 = build_fortress_compound()
    a2, l2, r2 = build_fortress_bailey_compound()
    assert r1.ok and r2.ok
    assert l1.ranges == l2.ranges
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]

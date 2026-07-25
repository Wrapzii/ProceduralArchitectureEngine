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
    assert keep.roof.kind == "pitched"
    assert keep.roof.pitch >= 1.6
    assert len(keep.towers) >= 4
    assert any(t.attached_to == "wall" for t in keep.towers)
    assert any(t.attached_to == "corner" for t in keep.towers)
    assert len({t.storeys for t in keep.towers}) >= 2

    assert len(gate.entrances) == 2
    assert all(e.role == "gate" for e in gate.entrances)
    assert {e.bay for e in gate.entrances} == {1, 2}
    assert len(gate.towers) == 2

    assert cloister.footprint.bays_x == 3
    assert bailey.court_bays_x >= 6
    assert bailey.approach_rows >= 2


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
    # Arcade is compound-stage (rect ranges have no COURTYARD for trim colonnade).
    assert by_name["west_cloister"].trim.colonnade is False
    assert by_name["west_cloister"].trim.arcade_piece == "arch_freestanding"
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
        if p.asset_id == "wall_gate_arch" and "gatehouse" in p.tags
    ]
    assert len(gates) >= 2, f"twin gate arches missing; got {len(gates)}"

    assert "gate" in placed_entrance_roles(assembly)

    approach = [
        p
        for p in assembly.placements
        if "approach" in p.tags or "causeway" in p.tags
    ]
    assert approach, "grand exterior approach causeway missing"
    assert all(p.asset_id == "steps_external" for p in approach)

    cloister_arcade = [
        p
        for p in assembly.placements
        if p.asset_id == "arch_freestanding"
        and any(t in p.tags for t in ("west_cloister", "east_cloister"))
    ]
    assert cloister_arcade, "cloister arcade (arch_freestanding) missing"

    battlements = [p for p in assembly.placements if p.asset_id == "battlement"]
    assert battlements, "curtain battlements missing"
    # Honest gap: trim buttresses fail buttress_outward on shallow curtain bars —
    # left off until @CASTLE_FORTRESS_KIT / trim outward pier fix. Massing still
    # requests the silhouette via FORTRESS_*_TRIM knobs once that lands.

    dormers = [p for p in assembly.placements if "dormer" in p.asset_id]
    assert dormers, "keep dormers missing on pitched roof"

    assert layout.courtyard, "expected open courtyard cells in bailey campus"


def test_fortress_south_curtain_chain_connected():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    failures = check_range_chain_connection(
        assembly, ["west_curtain", "gatehouse", "east_curtain"]
    )
    assert failures == []
    assert check_fortress_compound(assembly) == []


def test_fortress_compound_validates_critical_empty():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    _, vreport = validate(assembly)
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

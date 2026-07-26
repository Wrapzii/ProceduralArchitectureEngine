"""Castle curtain wall + gatehouse compound (Phase 4.1–4.2 greybox)."""

from __future__ import annotations

from pae.compound import (
    CURTAIN_TRIM,
    GATEHOUSE_TRIM,
    build_castle_curtain_compound,
    build_gatehouse_curtain,
    castle_curtain_ranges,
    check_range_chain_connection,
)
from pae.existence import placed_entrance_roles
from pae.spec import (
    castle_bailey_spec,
    castle_curtain_wall_spec,
    castle_gatehouse_spec,
)
from pae.validate import validate


def test_castle_factories_are_declarative():
    gh = castle_gatehouse_spec()
    west = castle_curtain_wall_spec("west_curtain", 6)
    bailey = castle_bailey_spec()

    assert len(gh.towers) == 2
    assert gh.entrances and gh.entrances[0].role == "gate"
    assert west.footprint.bays_y == 3
    assert west.footprint.bays_x == 6
    assert bailey.curtain_length_bays == 8


def test_castle_curtain_ranges_has_gatehouse_and_two_curtains():
    styles = castle_curtain_ranges()
    names = [s.name for s in styles]
    assert names == ["west_curtain", "gatehouse", "east_curtain"]
    assert styles[0].trim == CURTAIN_TRIM
    assert styles[1].trim == GATEHOUSE_TRIM


def test_build_castle_curtain_compound_succeeds():
    assembly, layout, report = build_castle_curtain_compound()
    assert report.ok, [f.message for f in report.failures]
    assert layout.ranges == ["west_curtain", "gatehouse", "east_curtain"]
    assert assembly.placements


def test_castle_compound_gate_entrance_role_exists():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok
    assert "gate" in placed_entrance_roles(assembly)


def test_castle_compound_ranges_are_connected():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok
    failures = check_range_chain_connection(
        assembly, ["west_curtain", "gatehouse", "east_curtain"]
    )
    assert failures == []


def test_castle_compound_has_gate_arch_and_twin_towers():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok

    gates = [
        p
        for p in assembly.placements
        if "gatehouse" in p.tags
        and p.kind == "wall"
        and "gate" in (p.asset_id or "").lower()
    ]
    assert gates, "gatehouse missing south gate arch leaf"

    tower_arcs = [
        p for p in assembly.placements if p.kind == "tower_arc" and "gatehouse" in p.tags
    ]
    assert len(tower_arcs) >= 8, f"expected twin towers, got {len(tower_arcs)} arc quarters"


def test_castle_compound_uses_curtain_trim_pieces():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok

    curtain = [
        p
        for p in assembly.placements
        if any(tag in p.tags for tag in ("west_curtain", "east_curtain"))
    ]
    asset_ids = {p.asset_id for p in curtain}
    assert "wall_plain" in asset_ids
    assert any(p.asset_id == "battlement" for p in curtain), (
        "curtain wall-walk must carry battlements (parapets deferred — D3-4)"
    )


def test_castle_compound_validates_clean():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok

    _, vreport = validate(assembly)
    assert vreport.ok, [f.message for f in vreport.critical]
    assert vreport.critical == []


def test_castle_compound_has_no_freestanding_curtain_ranges():
    assembly, _, report = build_castle_curtain_compound()
    assert report.ok

    _, vreport = validate(assembly)
    freestanding = [f for f in vreport.critical if f.check == "freestanding"]
    assert freestanding == []


def test_build_gatehouse_curtain_alias_matches_compound():
    a1, l1, r1 = build_castle_curtain_compound()
    a2, l2, r2 = build_gatehouse_curtain()
    assert r1.ok and r2.ok
    assert l1.ranges == l2.ranges
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]


def test_castle_compound_is_deterministic():
    a1, _, _ = build_castle_curtain_compound()
    a2, _, _ = build_castle_curtain_compound()
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]

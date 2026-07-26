"""Stage F — party walls: one mechanism for range–range and range–drum (T-105 / T-106)."""

from __future__ import annotations

from pae.compound import build_fortress_compound, fortress_compound_connections
from pae.compound_unify import unify_compound_assembly
from pae.structure_identity import (
    CHECK_STRUCTURE_PARTY_WALL,
    CHECK_STRUCTURE_REACHABLE,
    STRUCTURE_PARTY_TAG,
    check_structure_masses_reachable,
    check_structure_party_wall_open,
    make_range_drum_sealed_defect,
    repair_structure_party_walls,
    structure_tag,
)


def test_range_drum_sealed_fires_party_wall_check():
    poisoned = make_range_drum_sealed_defect()
    hits = check_structure_party_wall_open(poisoned)
    assert hits, "body|drum sealed interface must fire structure_party_wall_open"
    assert all(f.check == CHECK_STRUCTURE_PARTY_WALL and f.critical for f in hits)


def test_range_drum_sealed_fires_reachability_check():
    poisoned = make_range_drum_sealed_defect()
    hits = check_structure_masses_reachable(poisoned)
    assert hits, "sealed body|drum must fail structure_masses_reachable"
    assert any(f.check == CHECK_STRUCTURE_REACHABLE for f in hits)


def test_range_drum_party_wall_repair_opens_interface():
    poisoned = make_range_drum_sealed_defect()
    fixed = repair_structure_party_walls(poisoned)
    assert check_structure_party_wall_open(fixed) == []
    assert check_structure_masses_reachable(fixed) == []
    arches = [
        p
        for p in fixed.placements
        if p.kind == "wall"
        and "arch" in (p.asset_id or "")
        and STRUCTURE_PARTY_TAG in p.tags
    ]
    assert arches, "party repair must place interior arched opening on shared edge"


def test_structure_sealed_autofix_uses_party_repair():
    from pae.compound_unify import make_three_sealed_buildings_defect
    from pae.structure_identity import apply_structure_tags

    poisoned = apply_structure_tags(
        make_three_sealed_buildings_defect(), "fortress_bailey"
    )
    fixed = unify_compound_assembly(poisoned)
    assert check_structure_party_wall_open(fixed) == []
    links = [
        p
        for p in fixed.placements
        if p.kind == "wall"
        and ("arch" in (p.asset_id or "") or "door" in (p.asset_id or ""))
        and (
            STRUCTURE_PARTY_TAG in p.tags
            or "compound_link" in p.tags
        )
    ]
    assert links, "unify must punch walkable party openings on range–range interfaces"


def test_fortress_structure_party_walls_green():
    """Fortress green path — structure party checks, not full validate report."""
    assembly, _, _ = build_fortress_compound()
    conn = fortress_compound_connections()
    st = structure_tag("fortress_bailey")
    assert all(st in p.tags for p in assembly.placements)
    assert check_structure_party_wall_open(assembly) == []
    assert check_structure_masses_reachable(assembly) == []

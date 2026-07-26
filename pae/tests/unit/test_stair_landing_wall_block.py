"""Stair landing wall block + compound sealed-as-buildings (fail-closed).

USER: solid walls on stair landings block exit; linear halls emitted as three
sealed buildings with party walls. Verifications cannot be overridden.
"""

from __future__ import annotations

from pae.compound import build_compound, build_fortress_compound, fortress_compound_connections
from pae.compound_unify import (
    CHECK_BUILDING_DOORWAY,
    CHECK_BUILDING_IN_BUILDING,
    CHECK_COMPOUND_PARTITIONED,
    CHECK_COMPOUND_RANGE_DOORS,
    CHECK_FOOTPRINT_OVERLAP,
    check_building_doorway_exists,
    check_building_in_building,
    check_compound_not_partitioned,
    check_compound_range_doors,
    check_footprint_overlap,
    compound_ranges_ground_connected,
    make_building_in_building_defect,
    make_fortress_five_boxes_defect,
    make_three_sealed_buildings_defect,
    unify_compound_assembly,
)
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec, school_academy_spec
from pae.stair_occupancy import (
    CHECK_STAIR_LANDING_CLEAR,
    CHECK_STAIR_LANDING_STRIP_SCOPE,
    check_stair_landing_clearance,
    check_stair_landing_strip_scope,
    make_stair_landing_distant_wall_defect,
    make_stair_landing_solid_wall_defect,
    make_stair_landing_through_wall_defect,
    make_stair_landing_top_wall_block_defect,
    measure_stair_landing_strip,
    repair_stair_landing_walls,
)
from pae.validate import validate


# ---------------------------------------------------------------------------
# Broken fixtures first (Handbook §6)
# ---------------------------------------------------------------------------


def test_stair_landing_clear_fires_on_solid_bottom_wall():
    poisoned = make_stair_landing_solid_wall_defect()
    hits = check_stair_landing_clearance(poisoned)
    assert hits, "stair_landing_clear never fires — may have become a no-op"
    assert all(f.check == CHECK_STAIR_LANDING_CLEAR for f in hits)
    assert all(f.critical for f in hits)
    assert "solid" in hits[0].message.lower() or "blocked" in hits[0].message.lower()


def test_stair_landing_clear_fires_on_one_or_two_top_walls():
    """User regression: 1–2 solid walls on the TOP landing blocking floor exit."""
    poisoned = make_stair_landing_top_wall_block_defect()
    hits = check_stair_landing_clearance(poisoned)
    assert hits, "top landing wall block not detected"
    assert all(f.critical for f in hits)
    assert any("top" in f.message for f in hits)


def test_stair_landing_clear_not_warning_demotable():
    poisoned = make_stair_landing_top_wall_block_defect()
    _, report = validate(poisoned)
    crit = [f for f in report.critical if f.check == CHECK_STAIR_LANDING_CLEAR]
    warn = [f for f in report.warnings if f.check == CHECK_STAIR_LANDING_CLEAR]
    assert crit, "stair_landing_clear must be CRITICAL"
    assert not warn, "stair_landing_clear must not appear as warning"


def test_stair_landing_autofix_clears_top_blockers():
    poisoned = make_stair_landing_top_wall_block_defect()
    assert check_stair_landing_clearance(poisoned)
    before_walls = {
        p.piece_id for p in poisoned.placements if p.kind == "wall" and p.level == 1
    }
    fixed = repair_stair_landing_walls(poisoned)
    assert check_stair_landing_clearance(fixed) == []
    # Open-bay strip — both duplicate landing skins removed (not exterior doors).
    after_walls = {
        p.piece_id for p in fixed.placements if p.kind == "wall" and p.level == 1
    }
    assert before_walls - after_walls, "landing blockers must be stripped"
    plains = [
        p
        for p in fixed.placements
        if p.kind == "wall"
        and p.asset_id == "wall_plain"
        and p.piece_id in before_walls
    ]
    assert plains == [], "solid landing blockers must be stripped"


def test_stair_landing_through_wall_not_fully_stripped():
    """Perimeter run blocking landing must not be stripped through the building."""
    poisoned = make_stair_landing_through_wall_defect()
    scope_hits = check_stair_landing_strip_scope(poisoned)
    assert scope_hits, "stair_landing_strip_scope must fire on through-wall"
    assert all(f.check == CHECK_STAIR_LANDING_STRIP_SCOPE for f in scope_hits)
    assert all(f.critical for f in scope_hits)
    before = sum(1 for p in poisoned.placements if p.kind == "wall")
    fixed = repair_stair_landing_walls(poisoned)
    after = sum(1 for p in fixed.placements if p.kind == "wall")
    assert after == before, "through-wall must survive repair (not fully stripped)"
    assert any(
        p.piece_id == "poison_through_wall" for p in fixed.placements if p.kind == "wall"
    )


def test_stair_landing_distant_wall_survives_repair():
    """Wall ≥2 bays from landing pad must survive landing autofix."""
    poisoned = make_stair_landing_distant_wall_defect()
    before_far = any(p.piece_id == "poison_distant_wall" for p in poisoned.placements)
    assert before_far
    fixed = repair_stair_landing_walls(poisoned)
    assert any(
        p.piece_id == "poison_distant_wall" for p in fixed.placements if p.kind == "wall"
    ), "distant enclosure wall must survive"
    # In-zone landing blockers still stripped.
    assert not any(
        p.piece_id.startswith("poison_landing_wall")
        for p in fixed.placements
        if p.kind == "wall"
    )


def test_fortress_stair_landing_strip_counts_bounded():
    """Live fortress — strip candidates must not dwarf stair footprint."""
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.critical[:6]]
    stats = measure_stair_landing_strip(assembly)
    assert stats["strip_overscoped"] == 0
    # Repair already ran in build; candidates should be zero post-fix.
    assert stats["strip_candidates"] == 0
    assert stats["stair_covered_cells"] > 0


def test_three_sealed_buildings_fixture_fires_partition_check():
    """Top-down three blue rooms sealed by party walls — must CRITICAL-fail."""
    poisoned = make_three_sealed_buildings_defect()
    part = check_compound_not_partitioned(poisoned)
    doors = check_compound_range_doors(poisoned)
    assert part, "compound_not_partitioned_as_buildings never fires"
    assert all(f.critical for f in part)
    assert all(f.check == CHECK_COMPOUND_PARTITIONED for f in part)
    assert doors, "compound_range_doors must also fire on sealed interfaces"
    assert all(f.check == CHECK_COMPOUND_RANGE_DOORS and f.critical for f in doors)


def test_three_sealed_buildings_autofix_punches_doors():
    poisoned = make_three_sealed_buildings_defect()
    fixed = unify_compound_assembly(poisoned)
    assert check_compound_not_partitioned(fixed) == []
    assert check_compound_range_doors(fixed) == []
    # B and C lacked doors — ensure_building_doorways + interface punch.
    assert check_building_doorway_exists(fixed) == []


def test_building_in_building_fixture_fires_and_repairs():
    poisoned = make_building_in_building_defect()
    hits = check_building_in_building(poisoned)
    assert hits, "building_in_building never fires"
    assert all(f.check == CHECK_BUILDING_IN_BUILDING and f.critical for f in hits)
    fixed = unify_compound_assembly(poisoned)
    assert check_building_in_building(fixed) == []


def test_fortress_five_boxes_fixture_fires_partition_and_overlap():
    """3 front overlapping barbican boxes + 2 sealed side wings — user top-down."""
    poisoned = make_fortress_five_boxes_defect()
    conn = fortress_compound_connections()
    part = check_compound_not_partitioned(poisoned, connections=conn)
    overlap = check_footprint_overlap(poisoned)
    assert part, "compound_not_partitioned must fire on double-skin barbican"
    assert overlap, "footprint_overlap must fire on overlapping south envelopes"
    assert all(f.critical for f in part + overlap)


def test_fortress_five_boxes_autofix_unifies_south_barbican():
    poisoned = make_fortress_five_boxes_defect()
    conn = fortress_compound_connections()
    fixed = unify_compound_assembly(poisoned, connections=conn)
    assert check_compound_not_partitioned(fixed, connections=conn) == []
    assert check_footprint_overlap(fixed, connections=conn) == []
    south = ("west_curtain", "gatehouse", "east_curtain")
    assert compound_ranges_ground_connected(fixed, south)


def test_fortress_compound_ground_graph_one_campus():
    """Live fortress — walk room-to-room across former party walls."""
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.critical[:6]]
    all_ranges = (
        "west_curtain",
        "gatehouse",
        "east_curtain",
        "west_cloister",
        "east_cloister",
        "north_keep",
    )
    assert compound_ranges_ground_connected(assembly, all_ranges)
    conn = fortress_compound_connections()
    assert check_footprint_overlap(assembly, connections=conn) == []
    assert check_compound_not_partitioned(assembly, connections=conn) == []


# ---------------------------------------------------------------------------
# Live milestones — after autofix, landing/partition criticals empty
# ---------------------------------------------------------------------------


def test_m2_stair_landing_clear_critical_empty():
    _, _, assembly, report = run_through_assemble(m2_two_storey_stair_spec())
    assert report.ok or not any(
        f.check == CHECK_STAIR_LANDING_CLEAR for f in report.critical
    )
    hits = [
        f
        for f in validate(assembly)[1].failures
        if f.check == CHECK_STAIR_LANDING_CLEAR
    ]
    assert hits == []


def test_school_compound_not_sealed_as_buildings():
    assembly, _layout, report = build_compound()
    assert report.ok, [f.message for f in report.critical[:6]]
    part = [
        f
        for f in validate(assembly)[1].critical
        if f.check
        in (CHECK_COMPOUND_PARTITIONED, CHECK_COMPOUND_RANGE_DOORS, CHECK_BUILDING_DOORWAY)
    ]
    assert part == [], [f.message for f in part]


def test_fortress_compound_not_sealed_as_buildings():
    assembly, _layout, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.critical[:6]]
    part = [
        f
        for f in validate(assembly)[1].critical
        if f.check
        in (
            CHECK_COMPOUND_PARTITIONED,
            CHECK_COMPOUND_RANGE_DOORS,
            CHECK_BUILDING_DOORWAY,
            CHECK_BUILDING_IN_BUILDING,
            CHECK_STAIR_LANDING_CLEAR,
        )
    ]
    assert part == [], [f.message for f in part]


def test_school_academy_stair_landing_clear_empty():
    factory = school_academy_spec
    _, _, assembly, _ = run_through_assemble(factory())
    hits = check_stair_landing_clearance(assembly)
    assert hits == [], [f.message for f in hits[:4]]

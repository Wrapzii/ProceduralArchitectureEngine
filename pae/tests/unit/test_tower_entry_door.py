"""Hall→spiral/tower stairwell doorway — existence + aperture_reachability.

Handbook §2 seven questions (tower_entry family):
  1 Touch — attach-face drum rim / hall envelope
  2 Under — hall floor at that storey
  5 Isolation — no (joins drum via AABB)
  6 Use — walk-through → aperture_reachability treats hall floor as landing
  7 Spec — critical tower_entry_door when spiral / tower stair present

Written with the check (Handbook §6): missing door must fail.
"""

from __future__ import annotations

from pae.assembly_types import Assembly
from pae.existence import (
    CHECK_TOWER_ENTRY_DOOR,
    TOWER_ENTRY_TAG,
    check_tower_entry_door,
    placed_tower_entry_doors,
)
from pae.pipeline import run_through_assemble
from pae.spec import m3_keep_tower_spec, m_spiral_tower_spec
from pae.validate import validate, _check_stair_exit_clearance


def test_spiral_places_tower_entry_on_attach_face():
    _, _, assembly, areport = run_through_assemble(m_spiral_tower_spec())
    assert areport.ok, [f.message for f in areport.failures]
    entries = placed_tower_entry_doors(assembly)
    assert entries, "expected tower_entry door(s) on hall↔drum attach face"
    assert all(TOWER_ENTRY_TAG in p.tags for p in entries)
    assert any(p.level == 0 for p in entries)
    # Prefer a door on each hall landing storey (hall is 2 storeys).
    levels = {p.level for p in entries}
    assert 0 in levels and 1 in levels
    # Attach yaw for west tower is 180 (east face toward hall).
    assert all(int(p.yaw) % 360 == 180 for p in entries)


def test_spiral_tower_entry_existence_and_reachability_pass():
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    assert check_tower_entry_door(assembly) == []
    _, vreport = validate(assembly)
    assert not any(
        f.check == CHECK_TOWER_ENTRY_DOOR for f in vreport.failures
    ), [f.message for f in vreport.failures if f.check == CHECK_TOWER_ENTRY_DOOR]
    reach = [f for f in vreport.failures if f.check == "aperture_reachability"]
    tower_reach = [
        f
        for f in reach
        if f.piece_id
        and any(
            p.piece_id == f.piece_id and TOWER_ENTRY_TAG in p.tags
            for p in assembly.placements
        )
    ]
    assert not tower_reach, [f.message for f in tower_reach]


def test_missing_tower_entry_door_fails_critical():
    """Handbook §6 — deliberately strip the door; existence must catch it."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    stripped = [
        p for p in assembly.placements if TOWER_ENTRY_TAG not in p.tags
    ]
    keep_ids = {p.piece_id for p in stripped}
    apertures = [
        a
        for a in assembly.apertures
        if a.wall_piece_id in keep_ids or a.kind != "door"
    ]
    broken = Assembly(
        placements=stripped,
        apertures=apertures,
        wall_runs=list(assembly.wall_runs),
        floor_plan=dict(assembly.floor_plan),
        circulation=list(assembly.circulation),
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(assembly.room_specs),
    )
    fails = check_tower_entry_door(broken)
    assert fails
    assert fails[0].check == CHECK_TOWER_ENTRY_DOOR
    assert fails[0].critical

    _, vreport = validate(broken)
    hits = [f for f in vreport.critical if f.check == CHECK_TOWER_ENTRY_DOOR]
    assert hits, "validate must surface tower_entry_door as critical"


def test_spiral_tower_entry_does_not_block_stair_exit():
    """Rim doorway is a passage leaf — not a stair-exit headroom plug."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    exit_fails = _check_stair_exit_clearance(assembly)
    blocked_by_entry = [
        f
        for f in exit_fails
        if f.piece_id and "tower_entry" in f.piece_id
    ]
    assert not blocked_by_entry, [f.message for f in blocked_by_entry]


def test_m_spiral_tower_no_tower_entry_critical():
    """m_spiral_tower must not fail tower_entry_door (doors placed)."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    _, vreport = validate(assembly)
    assert not any(
        f.check == CHECK_TOWER_ENTRY_DOOR for f in vreport.critical
    ), [f.message for f in vreport.critical if f.check == CHECK_TOWER_ENTRY_DOOR]
    assert placed_tower_entry_doors(assembly)


def test_spiral_tower_entry_aperture_sanity_walkable():
    """Hall↔drum door must resolve onto walkable hall + drum cells (not WALL_LINE)."""
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    _, vreport = validate(assembly)
    te_ids = {p.piece_id for p in placed_tower_entry_doors(assembly)}
    bad = [
        f
        for f in vreport.failures
        if f.check == "aperture_sanity"
        and f.piece_id
        and any(pid in f.piece_id for pid in te_ids)
    ]
    assert bad == [], [f.message for f in bad]
    for ap in assembly.apertures:
        if ap.wall_piece_id not in te_ids:
            continue
        layer = assembly.floor_plan[ap.level]
        assert layer.role_at(*ap.interior_cell) is not None
        # Exterior side is the hall landing — must not be WALL_LINE attach cell.
        hall_role = layer.role_at(*ap.exterior_cell)
        assert hall_role is not None and hall_role.name != "WALL_LINE", (
            ap.exterior_cell,
            hall_role,
        )


def test_outdoor_tower_deck_excluded_from_storey_egress():
    """Option B: crown tower_deck is outdoor — STOREY/VOLUME must not fire on it alone."""
    from pae.validate import _check_storey_egress

    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    decks = [p for p in assembly.placements if "tower_deck" in p.tags]
    assert decks, "expected a crown tower_deck"
    deck_levels = {p.level for p in decks}
    # Indoor stairs only climb hall storeys; crown deck may sit above them.
    eg = _check_storey_egress(assembly)
    for level in deck_levels:
        storey_hits = [
            f
            for f in eg
            if f.check == "storey_egress" and f"storey {level}" in f.message
        ]
        assert storey_hits == [], [f.message for f in storey_hits]


def test_m3_keep_tower_no_spiral_existence_requirement():
    """Keep tower has no spiral / tower stair — existence does not fire."""
    _, _, assembly, areport = run_through_assemble(m3_keep_tower_spec())
    assert areport.ok, [f.message for f in areport.failures]
    stripped = Assembly(
        placements=[p for p in assembly.placements if TOWER_ENTRY_TAG not in p.tags]
    )
    assert check_tower_entry_door(stripped) == []
    _, vreport = validate(assembly)
    assert not any(
        f.check == CHECK_TOWER_ENTRY_DOOR for f in vreport.failures
    )


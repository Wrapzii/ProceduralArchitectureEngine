"""Phase 4.7 — fortress/castle keep drums are habitable vertical circulation.

User report: no staircase inside tower keeps, no windows, junk inside, wrong
hall connection, no floor-to-floor entry/exit.

Proofs (fail-closed):
  * each multi-storey fortress keep tower has a spiral climb + newel
  * outward drum windows (tower_arc_quarter_window / drum_window)
  * tower_entry doors at ground + hall landings
  * no interior fitout / plain inner walls / buttress / colonnade in the drum
  * aperture_reachability clean for tower_entry doors
"""

from __future__ import annotations

from collections import Counter

from pae.compound import build_fortress_compound
from pae.contract import DRUM_WINDOW_CHORD_FRAC, MODULE_CM
from pae.drum import CHECK_SPIRAL_REACHES_TOP, check_spiral_reaches_top, drum_levels
from pae.drum import drum_cells
from pae.existence import TOWER_ENTRY_TAG, placed_tower_entry_doors
from pae.pipeline import run_through_assemble
from pae.spec import fortress_gatehouse_spec, fortress_keep_spec
from pae.tower_entry import CHECK_TOWER_ENTRY_CLEARS_STAIR, check_tower_entry_clears_stair
from pae.trim import covered_cells
from pae.validate import validate


_JUNK_KINDS = frozenset({"prop"})
_JUNK_ASSETS = frozenset(
    {
        "wall_plain",
        "buttress",
        "fitout_bench",
        "fitout_table",
        "fitout_crate",
    }
)
_JUNK_TAGS = frozenset({"fitout_greybox", "colonnade", "buttress"})
# Required drum shell — never "junk".
_DRUM_OK_ASSETS = frozenset(
    {
        "spiral_newel",
        "stair_spiral_quarter",
        "tower_arc_quarter",
        "tower_arc_quarter_window",
        "tower_junction",
        "tower_crown",
        "tower_cap",
        "floor",
        "floor_hole",
        "wall_door",
        "wall_window",
        "wall_arrowslit",
    }
)


def _drum_set(assembly):
    return drum_cells(assembly)


def _spirals_by_cell(assembly):
    out = Counter()
    for p in assembly.placements:
        if p.asset_id == "stair_spiral_quarter":
            out[p.cell] += 1
    return out


def _tower_anchor_cells(assembly):
    return {p.cell for p in assembly.placements if p.kind == "tower_arc"}


def _spiral_max_level_by_cell(assembly):
    out = {}
    for p in assembly.placements:
        if p.asset_id == "stair_spiral_quarter":
            out[p.cell] = max(out.get(p.cell, -1), p.level)
    return out


def test_tower_entry_clears_stair_broken_fixture_first():
    """Attach-face tread under a tower_entry door must fail before the fix."""
    from pae.assembly_types import Assembly, SolidPlacement
    from pae.primitives.catalog import get as get_primitive

    from pae.contract import WALL_T_CM

    spiral = get_primitive("stair_spiral_quarter")
    door = SolidPlacement(
        piece_id="tower_entry_180_0_0_0",
        asset_id="wall_door",
        kind="wall",
        cell=(0, 0),
        level=0,
        yaw=180,
        offset_cm=(170.0, 200.0, 0.0),
        size_cm=(WALL_T_CM, 168.0, 257.0),
        rotates_about_center=True,
        tags=frozenset({"tower", TOWER_ENTRY_TAG}),
    )
    tread = SolidPlacement(
        piece_id="stair_spiral_180_0_0_0",
        asset_id=spiral.id,
        kind="stair",
        cell=(0, 0),
        level=0,
        yaw=180,
        offset_cm=(0.0, 200.0, 0.0),
        size_cm=spiral.size_cm,
        rotates_about_center=True,
        tags=spiral.tags,
    )
    poison = Assembly(placements=[door, tread])
    fails = check_tower_entry_clears_stair(poison)
    assert fails and fails[0].check == CHECK_TOWER_ENTRY_CLEARS_STAIR


def test_spiral_reaches_top_broken_fixture_first():
    """Helix stopping short of the crown landing must fail."""
    from pae.assembly_types import Assembly, SolidPlacement
    from pae.primitives.catalog import get as get_primitive

    arc = get_primitive("tower_arc_quarter")
    spiral = get_primitive("stair_spiral_quarter")
    cell = (0, 0)
    placements = []
    for level in range(3):
        for yaw in (0, 90, 270):
            placements.append(
                SolidPlacement(
                    piece_id=f"arc_{yaw}_{level}",
                    asset_id=arc.id,
                    kind="tower_arc",
                    cell=cell,
                    level=level,
                    yaw=yaw,
                    offset_cm=(0.0, 200.0, 0.0),
                    size_cm=arc.size_cm,
                    rotates_about_center=True,
                    tags=arc.tags,
                )
            )
    placements.append(
        SolidPlacement(
            piece_id="spiral_0",
            asset_id=spiral.id,
            kind="stair",
            cell=cell,
            level=0,
            yaw=0,
            offset_cm=(0.0, 200.0, 0.0),
            size_cm=spiral.size_cm,
            rotates_about_center=True,
            tags=spiral.tags | frozenset({"habitable_drum"}),
        )
    )
    poison = Assembly(placements=placements)
    fails = check_spiral_reaches_top(poison)
    assert fails and fails[0].check == CHECK_SPIRAL_REACHES_TOP


def test_fortress_keep_towers_declare_spiral():
    keep = fortress_keep_spec()
    assert keep.circulation.stair_kind == "switchback"
    assert keep.towers
    assert all(t.stair_kind == "spiral" for t in keep.towers)
    gate = fortress_gatehouse_spec()
    assert all(t.stair_kind == "spiral" for t in gate.towers)


def test_fortress_keep_assemble_has_spiral_windows_entry():
    _, _, assembly, areport = run_through_assemble(fortress_keep_spec())
    assert areport.ok, [f.message for f in areport.failures]

    anchors = _tower_anchor_cells(assembly)
    assert len(anchors) >= 4

    spirals = _spirals_by_cell(assembly)
    min_chord = MODULE_CM * DRUM_WINDOW_CHORD_FRAC - 1.0
    drum_wins = [p for p in assembly.placements if "drum_window" in p.tags]
    for p in drum_wins:
        assert max(p.size_cm[0], p.size_cm[1]) >= min_chord, p.size_cm
    for cell in anchors:
        assert spirals[cell] >= 4, f"tower {cell} missing full spiral turn ({spirals[cell]})"
        levels = drum_levels(assembly).get(cell, [])
        if levels:
            assert _spiral_max_level_by_cell(assembly).get(cell, -1) >= max(levels) - 1

    win_arcs = [
        p for p in assembly.placements if p.asset_id == "tower_arc_quarter_window"
    ]
    assert win_arcs or drum_wins, "expected outward drum windows on keep towers"

    entries = placed_tower_entry_doors(assembly)
    assert entries, "expected tower_entry doors hall↔drum"
    levels = {p.level for p in entries}
    assert 0 in levels, "ground-level tower_entry required"
    assert levels & {1, 2}, "landing-storey tower_entry required for multi-storey keep"


def test_fortress_keep_no_interior_drum_junk():
    _, _, assembly, _ = run_through_assemble(fortress_keep_spec())
    # Anchor cells only — drum AABB covered_cells expand into abutting hall wall
    # bays (kiss), which must not count as "junk inside the drum".
    anchors = _tower_anchor_cells(assembly)
    assert anchors

    junk = []
    for p in assembly.placements:
        if p.cell not in anchors:
            continue
        if p.asset_id in _DRUM_OK_ASSETS or p.kind in (
            "tower_arc",
            "tower_crown",
            "tower_cap",
            "stair",
        ):
            continue
        tags = set(p.tags or ())
        if TOWER_ENTRY_TAG in tags or "drum_window" in tags or "tower" in tags:
            continue
        if p.kind in _JUNK_KINDS or p.asset_id in _JUNK_ASSETS or tags & _JUNK_TAGS:
            junk.append((p.piece_id, p.asset_id, p.kind))
        # Rectangular plain walls through the drum (not rim tower_entry / window).
        if p.kind == "wall" and p.asset_id == "wall_plain":
            junk.append((p.piece_id, p.asset_id, "plain_wall_in_drum"))
    assert not junk, f"interior drum junk: {junk[:20]}"


def test_fortress_keep_tower_entry_reachability_clean():
    _, _, assembly, _ = run_through_assemble(fortress_keep_spec())
    _, vreport = validate(assembly)
    te_ids = {p.piece_id for p in placed_tower_entry_doors(assembly)}
    assert te_ids
    reach = [
        f
        for f in vreport.failures
        if f.check == "aperture_reachability"
        and f.piece_id
        and (
            f.piece_id in te_ids
            or f.piece_id.replace("door_", "") in te_ids
        )
    ]
    assert not reach, [f.message for f in reach]
    entry_crit = [f for f in vreport.critical if f.check == "tower_entry_door"]
    assert not entry_crit, [f.message for f in entry_crit]
    assert check_tower_entry_clears_stair(assembly) == []
    assert check_spiral_reaches_top(assembly) == []


def test_fortress_compound_habitable_keep_towers():
    """Full bailey compound: keep + gatehouse drums stay climbable and clean."""
    assembly, layout, _report = build_fortress_compound()
    assert "north_keep" in layout.ranges

    keep_arcs = [
        p
        for p in assembly.placements
        if p.kind == "tower_arc" and ("north_keep" in p.tags or "building:north_keep" in p.tags)
    ]
    # Tags may be range-stamped on walls more than arcs — fall back to spiral count.
    spirals = [
        p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"
    ]
    assert len(spirals) >= 3 * 4, (
        f"expected spirals in ≥4 keep/gate towers, got {len(spirals)} quarters"
    )
    entries = placed_tower_entry_doors(assembly)
    assert entries and any(p.level == 0 for p in entries)
    assert any(p.level >= 1 for p in entries)

    # Keep / gatehouse drums only — curtain walls may share a cell index after
    # compound merge without being inside a keep drum.
    keep_gate_anchors = {
        p.cell
        for p in assembly.placements
        if p.kind == "tower_arc"
        and (
            "north_keep" in p.tags
            or "gatehouse" in p.tags
            or "building:north_keep" in p.tags
            or "building:gatehouse" in p.tags
        )
    }
    if not keep_gate_anchors:
        keep_gate_anchors = _tower_anchor_cells(assembly)
    plain_in_drum = [
        p
        for p in assembly.placements
        if p.asset_id == "wall_plain"
        and p.cell in keep_gate_anchors
        and TOWER_ENTRY_TAG not in p.tags
        and "drum_window" not in p.tags
        and (
            "north_keep" in p.tags
            or "gatehouse" in p.tags
            or "building:north_keep" in p.tags
            or "building:gatehouse" in p.tags
            or not any(t.startswith("building:") for t in p.tags)
        )
    ]
    assert not plain_in_drum, (
        f"plain walls still cut through drums: "
        f"{[(p.piece_id, p.cell, p.level) for p in plain_in_drum[:12]]}"
    )

    win = [
        p
        for p in assembly.placements
        if p.asset_id == "tower_arc_quarter_window" or "drum_window" in p.tags
    ]
    assert win, "compound keep/gate drums need outward windows"

    _, vreport = validate(assembly)
    # Do not demote fortress / aperture criticals — only assert our owned gates.
    # Cloister balcony aperture_reachability is owned by the arcade/balcony lane.
    te_ids = {p.piece_id for p in entries}
    owned_checks = {
        "tower_entry_door",
        "tower_entry_clears_stair",
        "spiral_reaches_top",
        "spiral_newel_exists",
        "spiral_drum_enclosure",
    }
    bad = [f for f in vreport.critical if f.check in owned_checks]
    bad.extend(
        f
        for f in vreport.critical
        if f.check == "aperture_reachability"
        and f.piece_id
        and (
            f.piece_id in te_ids
            or f.piece_id.replace("door_", "") in te_ids
            or "tower_entry" in (f.piece_id or "")
        )
    )
    assert not bad, [(f.check, f.message) for f in bad[:20]]

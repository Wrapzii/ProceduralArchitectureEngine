"""Unit tests — MMO street row builder."""

from __future__ import annotations

from pae.contract import EAVE_OVERHANG_CM, MODULE_CM, placement_world_aabb
from pae.facade_grammar import metres_to_bays
from pae.street_row import build_street_row, row_context_for_index


def test_row_context_for_five_unit_row():
    assert row_context_for_index(0, 5) == "end_left"
    assert row_context_for_index(1, 5) == "mid"
    assert row_context_for_index(2, 5) == "mid"
    assert row_context_for_index(3, 5) == "mid"
    assert row_context_for_index(4, 5) == "end_right"


def test_street_row_five_party_contexts():
    assembly, report, stats = build_street_row(5, frontage_m=10.0, depth_m=8.0)
    assert stats["count"] == 5
    contexts = [b["row_context"] for b in stats["buildings"]]
    assert contexts == ["end_left", "mid", "mid", "mid", "end_right"]
    seeds = [b["seed"] for b in stats["buildings"]]
    assert len(set(seeds)) == 5
    assert assembly.placements
    assert stats["placement_count"] == len(assembly.placements)
    assert not report.critical


def test_street_row_no_gap_between_footprints():
    frontage_m = 10.0
    depth_m = 8.0
    count = 5
    assembly, _, stats = build_street_row(
        count, frontage_m=frontage_m, depth_m=depth_m, storeys=2
    )
    bays_x = metres_to_bays(frontage_m) or 3
    expected_width = count * bays_x * MODULE_CM
    # Floor slabs mark each building footprint at level 0
    floors = [
        p
        for p in assembly.placements
        if p.asset_id == "shell_floor_slab" and p.level == 0
    ]
    assert len(floors) == count
    xs = []
    for fl in floors:
        pmin, pmax = placement_world_aabb(
            fl.cell[0], fl.cell[1], fl.level, fl.yaw, fl.size_cm, fl.offset_cm
        )
        xs.extend([pmin[0], pmax[0]])
    assert max(xs) <= expected_width + 1.0
    offsets = [b["cell_offset"][0] for b in stats["buildings"]]
    assert offsets == [i * bays_x for i in range(count)]

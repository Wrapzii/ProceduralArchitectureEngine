"""Fail-closed stair exit clearance — no ceiling/wall dead-ends."""

from __future__ import annotations

from pae.assembly_types import Assembly, CirculationEdge, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec
from pae.trim import covered_cells
from pae.validate import (
    placement_footprint_cells,
    validate,
    _check_stair_exit_clearance,
    _check_stair_run_floor_clear,
)


def _stair(**kwargs) -> SolidPlacement:
    base = dict(
        piece_id="stair_a",
        asset_id="stair_straight",
        kind="stair",
        cell=(1, 0),
        level=0,
        yaw=90,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(2.0 * MODULE_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"stair"}),
    )
    base.update(kwargs)
    return SolidPlacement(**base)


def _stair_exit_cells(stair: SolidPlacement) -> set[tuple[int, int]]:
    """Exit bays on the storey above — Rule 5.1 uses covered_cells, not p.cell."""
    return covered_cells(stair)


def _hole(cell, level=1, piece_id=None) -> SolidPlacement:
    return SolidPlacement(
        piece_id=piece_id or f"hole_{cell[0]}_{cell[1]}",
        asset_id="floor_hole",
        kind="floor",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor", "hole"}),
    )


def _solid_floor(cell, level=1, piece_id=None) -> SolidPlacement:
    return SolidPlacement(
        piece_id=piece_id or f"floor_{cell[0]}_{cell[1]}",
        asset_id="floor",
        kind="floor",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )


def test_placement_footprint_cells_straight_run_yaw90():
    stair = _stair()
    cells = set(placement_footprint_cells(stair))
    # Anchor-based footprint differs from world AABB under yaw — see Rule 5.1.
    assert cells == {(1, 0), (1, 1)}
    assert _stair_exit_cells(stair) == {(0, 0), (0, 1)}


def test_missing_floor_hole_is_critical():
    assembly = Assembly(
        placements=[_stair()],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert fails
    assert all(f.check == "stair_exit_clearance" and f.critical for f in fails)
    assert any("missing floor_hole" in f.message for f in fails)
    messages = " ".join(f.message for f in fails if "missing" in f.message)
    assert "(0, 0)" in messages and "(0, 1)" in messages


def test_holes_at_stair_origin_only_do_not_satisfy_exit():
    """Ledger D-5: matching h.cell to stair anchor misses yawed exit bays."""
    stair = _stair()
    exits = _stair_exit_cells(stair)
    assert stair.cell not in exits
    assembly = Assembly(
        placements=[
            stair,
            _hole(stair.cell),
            _hole((stair.cell[0], stair.cell[1] + 1)),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("missing floor_hole" in f.message for f in fails)


def test_spanning_floor_hole_covers_exit_bays_not_stair_origin():
    """One spanning floor_hole whose origin != stair.cell still opens both exit bays."""
    stair = _stair()
    exits = sorted(_stair_exit_cells(stair))
    assert exits == [(0, 0), (0, 1)]
    assert stair.cell == (1, 0)
    assert stair.cell not in exits
    assembly = Assembly(
        placements=[
            stair,
            SolidPlacement(
                piece_id="span_hole",
                asset_id="floor_hole",
                kind="floor",
                cell=(0, 0),  # origin differs from stair anchor (1, 0)
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(MODULE_CM, 2.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor", "hole"}),
            ),
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    assert _check_stair_exit_clearance(assembly) == []


def test_holes_at_covered_exit_cells_pass_with_spanning_deck():
    """Hole origin may differ from stair origin when covered_cells still align."""
    stair = _stair()
    exits = sorted(_stair_exit_cells(stair))
    assert exits == [(0, 0), (0, 1)]
    assembly = Assembly(
        placements=[
            stair,
            _hole((0, 0)),
            _hole((0, 1)),
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    assert _check_stair_exit_clearance(assembly) == []


def test_spanning_deck_without_holes_at_covered_exit_fails():
    stair = _stair()
    assembly = Assembly(
        placements=[
            stair,
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("missing floor_hole" in f.message for f in fails)


def test_solid_floor_pad_on_exit_is_critical():
    stair = _stair()
    exits = _stair_exit_cells(stair)
    assembly = Assembly(
        placements=[
            stair,
            *[_hole(c) for c in sorted(exits)],
            _solid_floor(next(iter(exits)), piece_id="plug"),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("plugged by solid floor" in f.message for f in fails)


def test_solid_pad_covering_exit_via_covered_cells_not_origin():
    """A pad whose origin cell differs from the exit still plugs when it covers it."""
    stair = _stair()
    exits = _stair_exit_cells(stair)
    plug_cell = (1, 2)  # not an exit cell — but AABB will overlap (0, 1)
    assembly = Assembly(
        placements=[
            stair,
            *[_hole(c) for c in sorted(exits)],
            SolidPlacement(
                piece_id="offset_plug",
                asset_id="floor",
                kind="floor",
                cell=plug_cell,
                level=1,
                yaw=0,
                offset_cm=(-MODULE_CM, -MODULE_CM, -FLOOR_T_CM),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    assert (0, 1) in exits
    assert plug_cell not in exits
    fails = _check_stair_exit_clearance(assembly)
    assert any("plugged by solid floor" in f.message for f in fails)


def test_open_holes_pass_clearance():
    stair = _stair()
    exits = _stair_exit_cells(stair)
    assembly = Assembly(
        placements=[
            stair,
            *[_hole(c) for c in sorted(exits)],
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    assert _check_stair_exit_clearance(assembly) == []


def test_wall_in_head_clearance_is_critical():
    stair = _stair()
    exits = _stair_exit_cells(stair)
    assembly = Assembly(
        placements=[
            stair,
            *[_hole(c) for c in sorted(exits)],
            SolidPlacement(
                piece_id="wall_blocks_exit",
                asset_id="wall",
                kind="wall",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(160.0, 160.0, 0.0),
                size_cm=(80.0, 80.0, STOREY_CM),
                tags=frozenset({"wall"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("blocked by wall" in f.message for f in fails)


def test_roof_in_head_clearance_is_critical():
    stair = _stair()
    exits = _stair_exit_cells(stair)
    assembly = Assembly(
        placements=[
            stair,
            *[_hole(c) for c in sorted(exits)],
            SolidPlacement(
                piece_id="roof_plugs_exit",
                asset_id="roof_flat",
                kind="roof",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(100.0, 100.0, 0.0),
                size_cm=(200.0, 200.0, FLOOR_T_CM),
                tags=frozenset({"roof"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("blocked by roof" in f.message for f in fails)


def test_m2_assembly_passes_stair_exit_clearance():
    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    _, report = validate(assembly)
    clearance = [f for f in report.failures if f.check == "stair_exit_clearance"]
    assert clearance == [], [f.message for f in clearance]
    run_clear = [f for f in report.failures if f.check == "stair_run_floor_clear"]
    assert run_clear == [], [f.message for f in run_clear]
    assert report.ok is True


def test_stair_run_floor_clear_fires_when_hole_covers_only_half_run():
    """Broken fixture FIRST (F-7): 1×1 hole on a 2-bay stair under a spanning deck."""
    stair = _stair()
    exits = sorted(_stair_exit_cells(stair))
    assert exits == [(0, 0), (0, 1)]
    assembly = Assembly(
        placements=[
            stair,
            # Only the first exit bay opened — second bay stays solid floor.
            _hole(exits[0]),
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_run_floor_clear(assembly)
    assert fails
    assert all(f.check == "stair_run_floor_clear" and f.critical for f in fails)
    assert any(str(exits[1]) in f.message for f in fails)
    assert any("full stair footprint" in f.message for f in fails)


def test_spanning_hole_passes_stair_run_floor_clear():
    stair = _stair()
    exits = sorted(_stair_exit_cells(stair))
    assembly = Assembly(
        placements=[
            stair,
            SolidPlacement(
                piece_id="span_hole",
                asset_id="floor_hole",
                kind="floor",
                cell=exits[0],
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(MODULE_CM, 2.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor", "hole"}),
            ),
            SolidPlacement(
                piece_id="deck",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            ),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    assert _check_stair_run_floor_clear(assembly) == []
    assert _check_stair_exit_clearance(assembly) == []

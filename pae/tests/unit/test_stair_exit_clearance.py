"""Fail-closed stair exit clearance — no ceiling/wall dead-ends."""

from __future__ import annotations

from pae.assembly_types import Assembly, CirculationEdge, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec
from pae.validate import (
    placement_footprint_cells,
    validate,
    _check_stair_exit_clearance,
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
    assert cells == {(1, 0), (1, 1)}


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


def test_solid_floor_pad_on_exit_is_critical():
    assembly = Assembly(
        placements=[
            _stair(),
            _hole((1, 0)),
            _hole((1, 1)),
            _solid_floor((1, 0), piece_id="plug"),
        ],
        circulation=[CirculationEdge("stair_a", 0, 1)],
        storeys=2,
    )
    fails = _check_stair_exit_clearance(assembly)
    assert any("plugged by solid floor" in f.message for f in fails)


def test_open_holes_pass_clearance():
    assembly = Assembly(
        placements=[
            _stair(),
            _hole((1, 0)),
            _hole((1, 1)),
            # Spanning deck covering the footprint is allowed with holes present.
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
    assembly = Assembly(
        placements=[
            _stair(),
            _hole((1, 0)),
            _hole((1, 1)),
            # Block the character pass at hole centre (not just the rim).
            SolidPlacement(
                piece_id="wall_blocks_exit",
                asset_id="wall",
                kind="wall",
                cell=(1, 0),
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
    assembly = Assembly(
        placements=[
            _stair(),
            _hole((1, 0)),
            _hole((1, 1)),
            SolidPlacement(
                piece_id="roof_plugs_exit",
                asset_id="roof_flat",
                kind="roof",
                cell=(1, 0),
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
    assert report.ok is True

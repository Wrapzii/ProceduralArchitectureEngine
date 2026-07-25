"""S-130 headroom — walkable surfaces need 2.1 m standing clearance."""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, floor_placement_z_cm
from pae.validate import HEADROOM_CLEARANCE_CM, _check_headroom, validate


def _floor(cell=(0, 0), level=0, piece_id="floor0") -> SolidPlacement:
    floor_z = floor_placement_z_cm(level)
    return SolidPlacement(
        piece_id=piece_id,
        asset_id="floor",
        kind="floor",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, floor_z),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )


def test_low_roof_blocking_headroom_is_critical():
    """Broken fixture: solid roof slab within standing clearance above floor."""
    floor = _floor()
    floor_top = floor_placement_z_cm(0) + FLOOR_T_CM
    low_z = floor_top + 80.0
    assembly = Assembly(
        placements=[
            floor,
            SolidPlacement(
                piece_id="low_roof",
                asset_id="roof_flat",
                kind="roof",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, low_z),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"roof"}),
            ),
        ],
        storeys=1,
    )
    fails = _check_headroom(assembly)
    assert fails
    assert all(f.check == "headroom" and f.critical for f in fails)
    assert any("low_roof" in f.message for f in fails)
    _, report = validate(assembly)
    assert not report.ok
    assert any(f.check == "headroom" for f in report.critical)


def test_open_storey_has_no_headroom_failure():
    floor = _floor()
    assembly = Assembly(placements=[floor], storeys=1)
    assert _check_headroom(assembly) == []


def test_headroom_clearance_constant_is_two_point_one_metres():
    assert HEADROOM_CLEARANCE_CM == 210.0

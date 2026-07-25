"""Phase 9.2 — upper_exterior entrance landing (validation-first).

Ties EntranceSpec role ``upper_exterior`` to ``aperture_reachability`` via the
dedicated critical check ``upper_entrance_landing``.
"""

from __future__ import annotations

from pae.assemble import _door_asset_for_role
from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM, floor_placement_z_cm, rotation_offset_cm
from pae.existence import entrance_role_tag
from pae.spec import EntranceSpec, ENTRANCE_ROLES, load_spec
from pae.upper_entrance import (
    CHECK_UPPER_ENTRANCE_LANDING,
    UPPER_EXTERIOR_ROLE,
    make_upper_landing,
)
from pae.validate import validate


def _upper_door(
    *,
    level: int = 1,
    cell=(2, 0),
    yaw: int = 180,
    tagged: bool = True,
) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    tags = {"wall"}
    if tagged:
        tags.add(entrance_role_tag(UPPER_EXTERIOR_ROLE))
    return SolidPlacement(
        piece_id=f"door_l{level}",
        asset_id="wall_door",
        kind="wall",
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=rotation_offset_cm(yaw, sx, sy) + (0.0,),
        size_cm=(sx, sy, sz),
        tags=frozenset(tags),
    )


def _interior_floor(cell=(2, 1), level: int = 1) -> SolidPlacement:
    return SolidPlacement(
        piece_id=f"floor_{cell[0]}_{cell[1]}_l{level}",
        asset_id="floor",
        kind="floor",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, floor_placement_z_cm(level)),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )


def test_upper_exterior_role_in_entrance_roles():
    assert UPPER_EXTERIOR_ROLE in ENTRANCE_ROLES


def test_door_asset_for_upper_exterior():
    assert _door_asset_for_role("upper_exterior", None) == "wall_door"


def test_load_spec_upper_exterior_defaults_storey_one():
    spec, report = load_spec(
        {
            "name": "upper_door_spec",
            "style": "keep",
            "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
            "storeys": 2,
            "storey_use": ["hall", "hall"],
            "entrances": [{"role": "upper_exterior", "facade": "south"}],
        }
    )
    assert report.ok, [f.message for f in report.failures]
    assert spec is not None
    assert spec.entrances[0].role == "upper_exterior"
    assert spec.entrances[0].storey == 1


def test_load_spec_upper_exterior_rejects_ground_storey():
    spec, report = load_spec(
        {
            "name": "bad_upper",
            "style": "keep",
            "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
            "storeys": 2,
            "storey_use": ["hall", "hall"],
            "entrances": [
                {"role": "upper_exterior", "facade": "south", "storey": 0}
            ],
        }
    )
    assert spec is None
    assert not report.ok
    assert any("storey" in f.message for f in report.failures)


def test_upper_exterior_without_landing_is_critical():
    assembly = Assembly(
        placements=[_upper_door(), _interior_floor()],
        storeys=2,
    )
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == CHECK_UPPER_ENTRANCE_LANDING]
    assert hits, [f.check for f in report.failures]
    assert all(f.critical for f in hits)
    # Same geometry also fails the shared aperture_reachability rule.
    reach = [f for f in report.failures if f.check == "aperture_reachability"]
    assert reach
    assert all(f.critical for f in reach)


def test_upper_exterior_with_landing_passes_both_checks():
    # Door on south face of cell (2,0); landing south of it at (2, -1).
    door = _upper_door(cell=(2, 0), yaw=180)
    landing = make_upper_landing((2, -1), level=1)
    interior = _interior_floor(cell=(2, 1), level=1)
    assembly = Assembly(
        placements=[door, landing, interior],
        storeys=2,
    )
    _, report = validate(assembly)
    upper = [f for f in report.failures if f.check == CHECK_UPPER_ENTRANCE_LANDING]
    reach = [f for f in report.failures if f.check == "aperture_reachability"]
    assert not upper, [f.message for f in upper]
    assert not reach, [f.message for f in reach]


def test_untagged_upper_door_does_not_fire_upper_entrance_check():
    """Untagged doors stay under aperture_reachability only."""
    assembly = Assembly(
        placements=[_upper_door(tagged=False)],
        storeys=2,
    )
    _, report = validate(assembly)
    upper = [f for f in report.failures if f.check == CHECK_UPPER_ENTRANCE_LANDING]
    reach = [f for f in report.failures if f.check == "aperture_reachability"]
    assert not upper
    assert reach


def test_entrance_spec_storey_field():
    e = EntranceSpec(role="upper_exterior", facade="south", storey=2)
    assert e.storey == 2
    assert e.role == UPPER_EXTERIOR_ROLE

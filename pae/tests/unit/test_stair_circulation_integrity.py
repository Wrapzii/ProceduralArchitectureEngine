"""P0 circulation integrity — poison fixtures first (Handbook §6).

User regression: fancy manor L1 stair flush to exterior wall, opposite-facing
stacked flights with no landing, full-depth void slot bisecting floors — yet
``critical=[]``. These checks must fire forever.
"""

from __future__ import annotations

from pae.fancy_manor import build_fancy_manor
from pae.stair_occupancy import (
    CHECK_FLOOR_ISLAND,
    CHECK_STAIR_EXIT_INTO_WALL,
    CHECK_STAIR_FLIGHT_DIRECTION,
    CHECK_STAIR_UNREACHABLE_LANDING,
    check_floor_islands,
    check_stair_exit_into_wall,
    check_stair_flight_direction_incoherent,
    check_stair_unreachable_landing,
    landing_cells_for_stair,
    make_floor_island_defect,
    make_stair_exit_into_wall_defect,
    make_stair_flight_direction_defect,
)
from pae.trim import covered_cells
from pae.validate import validate


def test_poison_stair_exit_into_wall_is_critical():
    poisoned = make_stair_exit_into_wall_defect()
    hits = check_stair_exit_into_wall(poisoned)
    assert hits, "stair_exit_into_wall must fire on flush exterior exit"
    assert all(f.check == CHECK_STAIR_EXIT_INTO_WALL and f.critical for f in hits)
    _, report = validate(poisoned)
    assert any(f.check == CHECK_STAIR_EXIT_INTO_WALL for f in report.critical)


def test_poison_stair_flight_direction_incoherent_is_critical():
    poisoned = make_stair_flight_direction_defect()
    hits = check_stair_flight_direction_incoherent(poisoned)
    assert hits, "stair_flight_direction_incoherent must fire on opposite trap"
    assert all(f.check == CHECK_STAIR_FLIGHT_DIRECTION and f.critical for f in hits)
    _, report = validate(poisoned)
    assert any(f.check == CHECK_STAIR_FLIGHT_DIRECTION for f in report.critical)


def test_poison_floor_island_is_critical():
    poisoned = make_floor_island_defect()
    hits = check_floor_islands(poisoned)
    assert hits, "floor_island must fire on bisected deck"
    assert all(f.check == CHECK_FLOOR_ISLAND and f.critical for f in hits)
    _, report = validate(poisoned)
    assert any(f.check == CHECK_FLOOR_ISLAND for f in report.critical)


def test_landing_cells_follow_yaw_not_geometric_hi():
    """Yaw 270 ascends south — top pad is toward decreasing Y, not geo hi."""
    from pae.assembly_types import SolidPlacement
    from pae.contract import MODULE_CM, STOREY_CM, rotation_offset_cm

    sx, sy = 2 * MODULE_CM, MODULE_CM
    ox, oy = rotation_offset_cm(270, sx, sy, rotates_about_center=False)
    st = SolidPlacement(
        piece_id="yaw_probe",
        asset_id="stair_straight",
        kind="stair",
        cell=(2, 2),
        level=1,
        yaw=270,
        offset_cm=(ox, oy, 0.0),
        size_cm=(sx, sy, STOREY_CM),
        tags=frozenset({"straight"}),
    )
    assert sorted(covered_cells(st)) == [(2, 2), (2, 3)]
    probes = {name: pad for name, pad, *_ in landing_cells_for_stair(st)}
    assert probes["top"] == (2, 1), probes
    assert probes["bottom"] == (2, 4), probes


def test_fancy_manor_circulation_critical_empty():
    _m, _p, assembly, report = build_fancy_manor(validate_assembly=True)
    assert report.critical == [], [f.check for f in report.critical]
    assert check_stair_exit_into_wall(assembly) == []
    assert check_stair_flight_direction_incoherent(assembly) == []
    assert check_floor_islands(assembly) == []
    assert check_stair_unreachable_landing(assembly) == []
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert len(stairs) >= 2
    yaws = sorted({int(p.yaw) % 360 for p in stairs})
    assert yaws, "stairs must have cardinal yaws"
    # Landings stay inside the 7×4 footprint (x 0..6, y 0..3).
    for st in stairs:
        for name, pad, level, _f, _t in landing_cells_for_stair(st):
            if name != "top":
                continue
            assert 0 <= pad[0] <= 6 and 0 <= pad[1] <= 3, (
                f"{st.piece_id} top pad {pad} outside footprint"
            )

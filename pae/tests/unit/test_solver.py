"""Unit tests — constraint solver (§5.1)."""

from __future__ import annotations

from pae.solver import Massing, Volume, solve, _tower_touches
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    TowerSpec,
    m1_box_house_spec,
)


def test_rect_massing_m1():
    spec = m1_box_house_spec()
    massing, report = solve(spec)
    assert report.ok is True
    assert isinstance(massing, Massing)
    assert len(massing.enclosed_volumes()) == 1
    main = massing.volumes[0]
    assert main.x0 == 0 and main.y0 == 0
    assert main.x1 == 3 and main.y1 == 2  # 4×3 bays inclusive
    assert main.storeys == 1
    assert massing.ground_slab is True
    assert massing.entrance_volume_id == main.id


def test_volumes_do_not_overlap():
    spec = BuildingSpec(
        name="L",
        style="townhouse",
        footprint=FootprintSpec(kind="L", bays_x=6, bays_y=5, wing_depth=2),
        storeys=1,
        storey_use=["hall"],
    )
    massing, report = solve(spec)
    assert report.ok is True
    assert massing is not None
    enclosed = massing.enclosed_volumes()
    for i, a in enumerate(enclosed):
        for b in enclosed[i + 1 :]:
            assert not a.overlaps(b), f"{a.id} overlaps {b.id}"


def test_tower_must_attach():
    # Far-away tower — local repair should snap it to a corner, then pass.
    spec = BuildingSpec(
        name="towered",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[TowerSpec(cell=(50, 50), storeys=3, attached_to="corner")],
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=1),
        roof=RoofSpec(kind="flat"),
    )
    massing, report = solve(spec)
    assert report.ok is True
    assert massing is not None
    towers = [v for v in massing.volumes if v.role == "tower"]
    assert len(towers) == 1
    body = next(v for v in massing.volumes if v.role == "main")
    t = towers[0]
    # Must be adjacent after repair (not still at 50,50).
    assert abs(t.x0 - 50) + abs(t.y0 - 50) > 0 or _touches(t, body)
    assert _touches(t, body)


def test_interior_tower_repaired_outside_footprint():
    """Interior tower cells overlapped the body and used to fail solve.

    Local repair must push them to an exterior wall/corner attach.
    """
    spec = BuildingSpec(
        name="interior_tower",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[TowerSpec(cell=(1, 1), storeys=3, attached_to="wall")],
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=1),
        roof=RoofSpec(kind="flat"),
    )
    massing, report = solve(spec)
    assert report.ok is True, report.critical
    assert massing is not None
    body = next(v for v in massing.volumes if v.role == "main")
    tower = next(v for v in massing.volumes if v.role == "tower")
    assert not tower.overlaps(body)
    assert (tower.x0, tower.y0) != (1, 1)
    assert _touches(tower, body)


def test_detached_tower_snaps_to_hall_wall():
    """Far-away tower on school massing must repair onto hall (WING_ROLES body)."""
    spec = BuildingSpec(
        name="school_tower",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="school",
            bays_x=12,
            bays_y=12,
            wing_depth=5,
            courtyard=True,
        ),
        storeys=2,
        storey_use=["classroom", "classroom"],
        towers=[TowerSpec(cell=(80, 2), storeys=4, attached_to="wall")],
        circulation=CirculationSpec(stair_kind="switchback", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=2),
        roof=RoofSpec(kind="flat"),
    )
    massing, report = solve(spec)
    assert report.ok is True, report.critical
    assert massing is not None
    tower = next(v for v in massing.volumes if v.role == "tower")
    hall = next(v for v in massing.volumes if v.role == "hall")
    assert (tower.x0, tower.y0) != (80, 2)
    assert not tower.overlaps(hall)
    assert _tower_touches(tower, hall)


def test_courtyard_bbox_tower_snaps_to_wing():
    """Tower on footprint bbox edge but not touching a wing must repair (C-5)."""
    spec = BuildingSpec(
        name="cloister_tower",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="courtyard",
            bays_x=8,
            bays_y=8,
            wing_depth=1,
            courtyard=True,
        ),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[TowerSpec(cell=(8, 7), storeys=3, attached_to="wall")],
        circulation=CirculationSpec(
            stair_kind="straight",
            stair_cells=[(1, 0), (1, 1)],
        ),
        openings=OpeningPolicy(doors_ground=1),
        roof=RoofSpec(kind="flat"),
    )
    massing, report = solve(spec)
    assert report.ok is True, report.critical
    tower = next(v for v in massing.volumes if v.role == "tower")
    wings = [v for v in massing.volumes if v.role in ("main", "wing")]
    assert any(_tower_touches(tower, w) for w in wings)
    assert not any(tower.overlaps(w) for w in wings)


def test_exterior_tower_candidates_walk_full_perimeter():
    """Courtyard wings expose attach cells along entire edges, not bbox midpoints."""
    from pae.solver import WING_ROLES, _place_footprint, exterior_tower_attach_cells

    vols = _place_footprint(
        FootprintSpec(kind="courtyard", bays_x=8, bays_y=8, wing_depth=1, courtyard=True),
        2,
    )
    bodies = [v for v in vols if v.role in WING_ROLES]
    cells = set(exterior_tower_attach_cells(bodies))
    assert (8, 4) in cells  # east wing run, not only bbox corner (8, 7)
    assert (-1, 4) in cells  # west wing run


def _touches(tower: Volume, body: Volume) -> bool:
    body_cells = body.cells()
    for tx, ty in tower.cells():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if (tx + dx, ty + dy) in body_cells:
                    return True
                if (tx, ty) in body_cells:
                    return True
    return False


def test_courtyard_is_outside_envelope_role():
    spec = BuildingSpec(
        name="cloister",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="courtyard", bays_x=8, bays_y=8, wing_depth=2, courtyard=True
        ),
        storeys=1,
        storey_use=["hall"],
    )
    massing, report = solve(spec)
    assert report.ok is True
    assert massing is not None
    courts = [v for v in massing.volumes if v.role == "courtyard"]
    assert len(courts) == 1
    # Courtyard cells must not appear in enclosed volume cells.
    enclosed_cells = set()
    for v in massing.enclosed_volumes():
        enclosed_cells |= v.cells()
    assert not (courts[0].cells() & enclosed_cells)

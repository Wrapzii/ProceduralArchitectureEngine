"""Unit tests — constraint solver (§5.1)."""

from __future__ import annotations

from pae.solver import Massing, Volume, solve
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

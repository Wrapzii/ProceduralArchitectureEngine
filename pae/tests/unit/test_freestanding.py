"""Freestanding-entity checks (§7.12).

WHY: vertical support only asks "is something under me". A canopy on its own posts, or a
whole outbuilding placed 40 m away, satisfies every previous check while being a separate
object floating beside the real building. Both shipped.
"""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_compound
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import catalog_by_id
from pae.spec import m1_box_house_spec
from pae.trim import trim
from pae.validate import validate


def _piece(asset_id, cell, level=0, offset=(0.0, 0.0, 0.0), tags=frozenset()):
    d = catalog_by_id()[asset_id]
    return SolidPlacement(
        piece_id=f"{asset_id}_{cell[0]}_{cell[1]}_{level}",
        asset_id=asset_id,
        kind=d.kind,
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=offset,
        size_cm=d.size_cm,
        rotates_about_center=d.rotates_about_center,
        tags=d.tags | tags,
    )


def test_detached_island_is_reported():
    """A wall+floor pair 40 bays away is a separate building, not part of this one."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    stray = [_piece("floor", (40, 40)), _piece("wall_plain", (40, 40))]
    poisoned = Assembly(
        placements=list(base.placements) + stray,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    _, report = validate(poisoned)
    islands = [f for f in report.critical if f.check == "freestanding"]
    assert islands, "detached group not reported"
    assert "2 piece" in islands[0].message


def test_site_surfaces_and_boundary_fence_are_not_islands():
    """A boundary fence is SUPPOSED to stand apart — exempting it is deliberate."""
    from pae.site import build_site

    trimmed, _ = trim(_assembled())
    sited, _, _ = build_site(trimmed)
    _, report = validate(sited)
    assert [f.message for f in report.critical] == []


def _assembled():
    _, _, a, _ = run_through_assemble(m1_box_house_spec())
    return a


def test_detached_canopy_is_reported():
    """A roof touching only columns is a canopy, not a roof."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    # A roof slab out in the field, held up by a pier: supported, but attached to nothing.
    stray = [
        _piece("pier_square", (30, 30)),
        _piece("roof_flat", (30, 30), level=1),
    ]
    poisoned = Assembly(
        placements=list(base.placements) + stray,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    _, report = validate(poisoned)
    checks = {f.check for f in report.critical}
    assert "canopy_attachment" in checks or "freestanding" in checks


def test_compound_gallery_roof_is_coplanar_with_the_range_roof():
    """The gallery canopy sat 30 cm low, meeting the range roof with a step and a gap."""
    from pae.contract import placement_world_aabb

    assembly, _, _ = build_compound()

    def top(p):
        return placement_world_aabb(
            p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )[1][2]

    roofs = [p for p in assembly.placements if p.kind == "roof"]
    gallery = {round(top(p), 1) for p in roofs if "balcony" in p.tags}
    main = {round(top(p), 1) for p in roofs if "balcony" not in p.tags}
    assert gallery and main
    assert gallery == main, (gallery, main)


def test_compound_has_no_freestanding_entities():
    assembly, _, _ = build_compound()
    _, report = validate(assembly)
    bad = [f for f in report.critical if f.check in ("freestanding", "canopy_attachment")]
    assert not bad, [f.message for f in bad]


def test_covered_cells_does_not_leak_into_the_next_cell():
    """A thin piece flush against a cell's far boundary must stay in ITS cell.

    The inset used to be a flat MODULE/4 = 100 cm, larger than a 60 cm wall, so a wall on
    the east edge of cell 9 reported as cell 10. Every range came out one cell too big and
    the balcony gallery landed a full bay off the wall.
    """
    from pae.contract import MODULE_CM, WALL_T_CM
    from pae.trim import covered_cells

    wall = _piece("wall_plain", (9, 0), offset=(MODULE_CM - WALL_T_CM, 0.0, 0.0))
    assert covered_cells(wall) == {(9, 0)}


def test_compound_balcony_decks_touch_their_range():
    """The deck must butt the wall it serves, not stand a bay away from it."""
    from pae.contract import placement_world_aabb, TOL_CM

    assembly, _, _ = build_compound()

    def bb(p):
        return placement_world_aabb(
            p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )

    decks = [p for p in assembly.placements if "balcony" in p.tags and p.kind == "floor"]
    walls = [p for p in assembly.placements if p.kind == "wall"]
    assert decks
    wall_boxes = [bb(w) for w in walls]
    for d in decks:
        dmn, dmx = bb(d)
        touching = any(
            min(dmx[0], wmx[0]) - max(dmn[0], wmn[0]) > -TOL_CM
            and min(dmx[1], wmx[1]) - max(dmn[1], wmn[1]) > -TOL_CM
            and min(dmx[2], wmx[2]) - max(dmn[2], wmn[2]) > -TOL_CM
            for wmn, wmx in wall_boxes
        )
        assert touching, f"{d.piece_id} touches no wall"

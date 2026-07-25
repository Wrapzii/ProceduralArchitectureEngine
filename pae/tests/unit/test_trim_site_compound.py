"""Trim / site / compound stages — the placement wave.

These tests exist because the previous failure mode was *pieces that existed but were never
placed*. A unit test proving ``spire_octagonal`` has the right bounding box passes happily
while no building in the repo has ever contained one. So the assertions here are about
REACHABILITY and PHYSICAL CORRECTNESS, not about dimensions.
"""

from __future__ import annotations

import pytest

from pae.boundary import boundary_offset_cm, outward_offset_cm, rotation_offset_cm
from pae.compound import CHAPEL_TRIM, SERVICE_TRIM, build_compound
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM, placement_world_aabb
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import catalog_by_id
from pae.site import build_site, place_buildings, BuildingInstance
from pae.spec import (
    m1_box_house_spec,
    m2_two_storey_stair_spec,
    m3_keep_tower_spec,
    m4_courtyard_spec,
)
from pae.trim import TrimOptions, covered_cells, trim
from pae.validate import validate


def _assemble(spec):
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, [f.message for f in report.failures]
    return assembly


def _aabb(p):
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


# --- boundary table ---------------------------------------------------------


def test_rotation_offset_matches_the_documented_table():
    """§2.2. Getting this wrong put parapets a full module outside the building."""
    size = (WALL_T_CM, MODULE_CM, STOREY_CM)
    assert rotation_offset_cm(0, size) == (0.0, 0.0)
    assert rotation_offset_cm(90, size) == (MODULE_CM, 0.0)
    assert rotation_offset_cm(180, size) == (WALL_T_CM, MODULE_CM)
    assert rotation_offset_cm(270, size) == (0.0, WALL_T_CM)


@pytest.mark.parametrize("face", ["south", "north", "west", "east"])
def test_boundary_offset_keeps_piece_inside_its_own_cell(face):
    """A barrier on any face must land within its cell, flush to that edge."""
    desc = catalog_by_id()["railing_metal"]
    from pae.boundary import FACE_YAW

    yaw = FACE_YAW[face]
    off = boundary_offset_cm(face, desc.size_cm)
    mn, mx = placement_world_aabb(0, 0, 0, yaw, desc.size_cm, off)
    assert mn[0] >= -0.01 and mn[1] >= -0.01
    assert mx[0] <= MODULE_CM + 0.01 and mx[1] <= MODULE_CM + 0.01


def test_outward_offset_projects_away_from_the_cell():
    """A buttress must stand OUTSIDE the wall it braces, not inside the room."""
    desc = catalog_by_id()["buttress"]
    yaw, off = outward_offset_cm("west", desc.size_cm)
    mn, _mx = placement_world_aabb(0, 0, 0, yaw, desc.size_cm, off)
    assert mn[0] < 0.0


# --- trim reachability ------------------------------------------------------


def test_trim_is_additive_and_never_drops_a_placement():
    base = _assemble(m1_box_house_spec())
    trimmed, report = trim(base)
    assert report.ok
    assert len(trimmed.placements) > len(base.placements)
    base_ids = {p.piece_id for p in base.placements}
    assert base_ids <= {p.piece_id for p in trimmed.placements}


@pytest.mark.parametrize(
    "spec_factory",
    [m1_box_house_spec, m2_two_storey_stair_spec, m3_keep_tower_spec, m4_courtyard_spec],
)
def test_trimmed_buildings_still_validate(spec_factory):
    """Trim must not introduce floating or interpenetrating geometry."""
    trimmed, report = trim(_assemble(spec_factory()))
    assert report.ok
    _, vreport = validate(trimmed)
    assert vreport.ok, [f.message for f in vreport.critical]


def test_m2_upper_deck_and_stairwell_get_railings():
    """Two-storey building: the stair void must be guarded."""
    trimmed, _ = trim(_assemble(m2_two_storey_stair_spec()))
    rails = [p for p in trimmed.placements if p.kind == "barrier" and "trim" in p.tags]
    assert rails, "no railings placed on a two-storey building"
    assert any("hole" in p.piece_id for p in rails)


def test_hole_railings_stand_on_the_deck_not_over_the_void():
    """A railing placed in the hole cell has nothing under it."""
    trimmed, _ = trim(_assemble(m2_two_storey_stair_spec()))
    holes = {
        c
        for p in trimmed.placements
        if p.kind == "floor" and "hole" in p.asset_id
        for c in covered_cells(p)
    }
    for p in trimmed.placements:
        if "hole" in p.piece_id and p.kind == "barrier":
            assert p.cell not in holes


def test_m3_tower_gets_a_spire_and_finial():
    trimmed, _ = trim(_assemble(m3_keep_tower_spec()))
    ids = {p.asset_id for p in trimmed.placements}
    assert "spire_octagonal" in ids
    assert "finial" in ids


def test_courtyard_building_gets_a_colonnade():
    trimmed, _ = trim(_assemble(m4_courtyard_spec()))
    arcs = [p for p in trimmed.placements if p.asset_id == "arch_freestanding"]
    assert arcs, "courtyard faces should carry a cloister walk"


def test_trim_options_can_switch_families_off():
    base = _assemble(m4_courtyard_spec())
    off, _ = trim(base, TrimOptions(railings=False, buttresses=False,
                                    roofline=False, colonnade=False, parapets=False))
    assert len(off.placements) == len(base.placements)


def test_parapet_sits_on_the_roof_not_at_the_storey_datum():
    trimmed, _ = trim(_assemble(m1_box_house_spec()))
    parapets = [p for p in trimmed.placements if p.asset_id == "parapet_solid"]
    assert parapets
    roofs = [p for p in trimmed.placements if p.kind == "roof"]
    roof_top = max(_aabb(p)[1][2] for p in roofs)
    for p in parapets:
        assert _aabb(p)[0][2] >= roof_top - 1.0


# --- site -------------------------------------------------------------------


def test_site_lays_walks_and_lawn_around_a_building():
    trimmed, _ = trim(_assemble(m1_box_house_spec()))
    sited, layout, report = build_site(trimmed)
    assert report.ok
    assert layout.walk, "no sidewalk laid"
    assert layout.lawn, "no grounds laid"
    ids = {p.asset_id for p in sited.placements}
    assert "sidewalk_slab" in ids and "kerb_edge" in ids and "fence_picket" in ids


def test_surfaces_are_laid_flush_with_the_ground():
    """A walk you step up onto is a bug — surface tops sit at z = 0."""
    sited, _, _ = build_site(_assemble(m1_box_house_spec()))
    for p in sited.placements:
        if p.kind == "surface" and "kerb" not in p.asset_id:
            assert _aabb(p)[1][2] == pytest.approx(0.0, abs=0.5)


def test_site_validates():
    trimmed, _ = trim(_assemble(m4_courtyard_spec()))
    sited, _, _ = build_site(trimmed)
    _, vreport = validate(sited)
    assert vreport.ok, [f.message for f in vreport.critical]


def test_place_buildings_shifts_cells_and_keeps_names_unique():
    base = _assemble(m1_box_house_spec())
    merged, report = place_buildings(
        [BuildingInstance(base, (0, 0), "a"), BuildingInstance(base, (20, 0), "b")]
    )
    assert report.ok
    assert len(merged.placements) == 2 * len(base.placements)
    assert len({p.piece_id for p in merged.placements}) == len(merged.placements)


def test_place_buildings_rejects_duplicate_names():
    base = _assemble(m1_box_house_spec())
    _, report = place_buildings(
        [BuildingInstance(base, (0, 0), "a"), BuildingInstance(base, (20, 0), "a")]
    )
    assert not report.ok


# --- compound ---------------------------------------------------------------


def test_compound_builds_four_ranges_round_a_courtyard():
    assembly, layout, report = build_compound()
    assert report.ok, [f.message for f in report.failures]
    assert len(layout.ranges) == 4
    assert layout.courtyard, "compound has no courtyard"


def test_compound_validates_clean():
    assembly, _, _ = build_compound()
    _, vreport = validate(assembly)
    assert vreport.ok, [f.message for f in vreport.critical]


def test_compound_ranges_are_trimmed_DIFFERENTLY():
    """Four copies of one spec must not read as one asset placed four times."""
    _, layout, _ = build_compound()
    counts = set(layout.per_range_trim.values())
    assert len(counts) > 1, f"all ranges trimmed identically: {layout.per_range_trim}"


def test_chapel_and_service_trim_differ_in_family():
    assert CHAPEL_TRIM.parapets != SERVICE_TRIM.parapets
    assert CHAPEL_TRIM.colonnade != SERVICE_TRIM.colonnade


def test_balcony_has_deck_posts_and_balustrade():
    """All three or it is a defect: no posts = floating, no rail = a drop."""
    assembly, layout, _ = build_compound()
    assert layout.balcony_cells, "no balcony gallery generated"
    balcony = [p for p in assembly.placements if "balcony" in p.tags]
    kinds = {p.kind for p in balcony}
    assert {"floor", "column", "barrier"} <= kinds, kinds


def test_balcony_can_be_switched_off():
    with_b, layout_b, _ = build_compound(balconies=True)
    without, layout_n, _ = build_compound(balconies=False)
    assert len(with_b.placements) > len(without.placements)
    assert not layout_n.balcony_cells


def test_compound_is_deterministic():
    a1, _, _ = build_compound()
    a2, _, _ = build_compound()
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]


# --- balcony spec + boundary corner fix (verification pass) -----------------


def test_boundary_fence_pieces_stay_inside_their_own_cell():
    """site.py carried its own _face_offset with NO yaw compensation, so every
    south/north fence — which is yawed 90 deg — landed a full module out. It read as
    gates and fences being off by one at the corners."""
    from pae.contract import MODULE_CM as M

    sited, _, _ = build_site(_assemble(m1_box_house_spec()))
    for p in sited.placements:
        if p.kind != "barrier":
            continue
        mn, mx = _aabb(p)
        cx0, cy0 = p.cell[0] * M, p.cell[1] * M
        assert mn[0] >= cx0 - 0.01 and mn[1] >= cy0 - 0.01, p.piece_id
        assert mx[0] <= cx0 + M + 0.01 and mx[1] <= cy0 + M + 0.01, p.piece_id


def test_default_compound_is_a_real_quadrangle():
    """Four copies of one square pavilion can never enclose a court."""
    _, layout, report = build_compound()
    assert report.ok
    assert len(layout.courtyard) >= 12, layout.courtyard


def test_balcony_always_has_a_door():
    """A balcony with no door is a balcony you cannot reach."""
    assembly, layout, _ = build_compound()
    assert layout.balcony_cells
    doors = [p for p in assembly.placements if "balcony_door" in p.tags]
    assert doors, "gallery has no access door"


def test_balcony_door_count_is_configurable():
    from pae.compound import BalconySpec

    few, _, _ = build_compound(balcony=BalconySpec(doors_per_range=1))
    many, _, _ = build_compound(balcony=BalconySpec(doors_per_range=4))
    n_few = sum(1 for p in few.placements if "balcony_door" in p.tags)
    n_many = sum(1 for p in many.placements if "balcony_door" in p.tags)
    assert n_many > n_few, (n_few, n_many)


def test_balcony_sides_can_be_restricted():
    from pae.compound import BalconySpec

    one, layout_one, _ = build_compound(balcony=BalconySpec(sides=("south_hall",)))
    allr, layout_all, _ = build_compound(balcony=BalconySpec())
    assert len(layout_one.balcony_cells) < len(layout_all.balcony_cells)


def test_balcony_railing_and_roof_are_optional():
    from pae.compound import BalconySpec

    plain, _, _ = build_compound(
        balcony=BalconySpec(railing=False, under_roof=False)
    )
    ids = {p.asset_id for p in plain.placements if "balcony" in p.tags}
    assert "balustrade_stone" not in ids
    assert not any(
        p.asset_id == "roof_flat" and "balcony" in p.tags for p in plain.placements
    )


def test_balcony_railing_only_on_open_edges():
    """A rail between two walkway cells is not a balcony edge — placing one on every
    non-built face turned the whole court into a grid of fences."""
    assembly, layout, _ = build_compound()
    rails = [
        p for p in assembly.placements
        if "balcony" in p.tags and p.kind == "barrier"
    ]
    assert len(rails) <= len(layout.balcony_cells), (len(rails), len(layout.balcony_cells))


def test_gallery_cells_are_claimed_once():
    """A corner cell touches two ranges; claiming per range duplicated its deck."""
    assembly, layout, _ = build_compound()
    decks = [
        p for p in assembly.placements
        if "balcony" in p.tags and p.kind == "floor"
    ]
    assert len(decks) == len(layout.balcony_cells), (len(decks), len(layout.balcony_cells))


def test_covered_gallery_is_carried_to_the_roof():
    """Posts must continue past the deck to the roof, or the roof floats."""
    from pae.compound import BalconySpec

    assembly, _, _ = build_compound(balcony=BalconySpec(under_roof=True))
    _, vreport = validate(assembly)
    assert vreport.ok, [f.message for f in vreport.critical]

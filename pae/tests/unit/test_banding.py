"""Banding / coping — façade articulation placeable anywhere.

Reference: Wealden hall house. Horizontal courses (plinth, bressummer, wall plate) and
vertical members (studs, corner posts) with diagonal braces, dividing each elevation into
panels. Coping is not a parapet cap — it is edging, and it goes wherever you say.

WRITTEN BEFORE THE IMPLEMENTATION, per Docs/VALIDATION_HANDBOOK.md §6. The seven questions
(§2) for this family:

  1 touch      every band must lie against the wall face it articulates  -> band_attachment
  2 support    NONE. A stringcourse at mid-height has nothing beneath it by design,
               so bands are EXEMPT from vertical_support and rely on 1 instead.
  3 overlap    bands sit proud of the wall; they must not sink INTO it     -> band_proud
  4 penetrate  covered by roof_penetration (bands are not exempt)
  5 isolation  no  -> must be caught by `freestanding`, no exemption
  6 use        no, decorative
  7 requested  yes -> spec asks for N courses at H, N must appear at H     -> existence
"""

from __future__ import annotations

import pytest

from pae.banding import BandingSpec, CourseSpec, band, band_faces_of
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM, placement_world_aabb
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import catalog_by_id
from pae.spec import m1_box_house_spec, m2_two_storey_stair_spec
from pae.validate import validate


def _assembled(spec=None):
    _, _, a, r = run_through_assemble(spec or m1_box_house_spec())
    assert r.ok
    return a


def _aabb(p):
    return placement_world_aabb(
        p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


# --- registration completeness (Handbook §3) --------------------------------


def test_band_pieces_are_in_the_catalog():
    cat = catalog_by_id()
    for piece in ("band_course", "band_pilaster", "band_brace", "coping_cap"):
        assert piece in cat, piece
        assert cat[piece].kind == "band"


def test_band_kind_has_a_footprint_rule():
    """A kind with no measure.py branch falls to 'unknown kind' and is checked by nothing."""
    from pae.primitives.measure import footprint_contract_errors

    for piece in ("band_course", "band_pilaster", "band_brace", "coping_cap"):
        errs = footprint_contract_errors(catalog_by_id()[piece])
        assert not any("unknown kind" in e for e in errs), errs


# --- the checks this family owes --------------------------------------------


def test_detached_band_is_reported():
    """Q1: a band floating clear of any wall is a defect."""
    from pae.assembly_types import Assembly, SolidPlacement

    base = _assembled()
    d = catalog_by_id()["band_course"]
    stray = SolidPlacement(
        piece_id="stray_band",
        asset_id="band_course",
        kind="band",
        cell=(50, 50),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, STOREY_CM * 0.5),
        size_cm=d.size_cm,
        tags=d.tags,
    )
    poisoned = Assembly(
        placements=list(base.placements) + [stray],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        storeys=base.storeys,
    )
    _, report = validate(poisoned)
    checks = {f.check for f in report.critical}
    assert "band_attachment" in checks or "freestanding" in checks


def test_bands_are_exempt_from_vertical_support():
    """Q2: a mid-height course has nothing under it BY DESIGN. Documented exemption."""
    banded, _ = band(_assembled(), BandingSpec())
    _, report = validate(banded)
    floaters = [
        f for f in report.critical
        if f.check == "vertical_support" and "band" in (f.piece_id or "")
    ]
    assert not floaters, [f.message for f in floaters]


def test_bands_sit_proud_of_the_wall_not_inside_it():
    """Q3: a band buried in the wall is invisible and pointless."""
    banded, _ = band(_assembled(), BandingSpec())
    _, report = validate(banded)
    sunk = [f for f in report.critical if f.check == "band_proud"]
    assert not sunk, [f.message for f in sunk]


def test_requested_courses_all_appear():
    """Q7: existence. The spec asked for three courses; three must exist."""
    spec = BandingSpec(courses=(
        CourseSpec("plinth", 0.02),
        CourseSpec("sill", 0.30),
        CourseSpec("eaves", 0.92),
    ), verticals_every_bays=0, braces=False)
    banded, report = band(_assembled(), spec)
    assert report.ok
    names = {p.tags and next((t for t in p.tags if t.startswith("course:")), None)
             for p in banded.placements if p.kind == "band"}
    for c in spec.courses:
        assert f"course:{c.name}" in names, (c.name, names)


# --- placeable anywhere ------------------------------------------------------


def test_course_lands_at_the_requested_height():
    """'Anywhere' means the height you asked for, within a tolerance."""
    spec = BandingSpec(courses=(CourseSpec("mid", 0.5),),
                       verticals_every_bays=0, braces=False)
    banded, _ = band(_assembled(), spec)
    courses = [p for p in banded.placements
               if p.kind == "band" and "course:mid" in p.tags]
    assert courses
    want = STOREY_CM * 0.5
    for p in courses:
        assert abs(_aabb(p)[0][2] - want) < 1.0


def test_vertical_members_and_braces_can_be_requested():
    spec = BandingSpec(courses=(), verticals_every_bays=1, braces=True)
    banded, _ = band(_assembled(), spec)
    ids = {p.asset_id for p in banded.placements if p.kind == "band"}
    assert "band_pilaster" in ids
    assert "band_brace" in ids


def test_banding_can_be_restricted_to_named_faces():
    everywhere, _ = band(_assembled(), BandingSpec())
    south_only, _ = band(_assembled(), BandingSpec(faces=("south",)))
    n_all = sum(1 for p in everywhere.placements if p.kind == "band")
    n_one = sum(1 for p in south_only.placements if p.kind == "band")
    assert 0 < n_one < n_all


def test_banding_applies_to_every_storey():
    two, _ = band(_assembled(m2_two_storey_stair_spec()), BandingSpec())
    levels = {p.level for p in two.placements if p.kind == "band"}
    assert levels >= {0, 1}, levels


def test_coping_can_cap_any_wall_top():
    spec = BandingSpec(courses=(), verticals_every_bays=0, braces=False, coping=True)
    banded, _ = band(_assembled(), spec)
    caps = [p for p in banded.placements if p.asset_id == "coping_cap"]
    assert caps, "coping requested but none placed"


def test_banding_is_additive_and_deterministic():
    base = _assembled()
    a1, _ = band(base, BandingSpec())
    a2, _ = band(base, BandingSpec())
    assert [p.piece_id for p in a1.placements] == [p.piece_id for p in a2.placements]
    assert len(a1.placements) > len(base.placements)
    assert {p.piece_id for p in base.placements} <= {p.piece_id for p in a1.placements}


def test_banded_building_still_validates():
    banded, _ = band(_assembled(m2_two_storey_stair_spec()), BandingSpec())
    _, report = validate(banded)
    assert report.ok, [f.message for f in report.critical]


def test_band_faces_of_reports_the_outward_face_per_wall():
    """Bands must know which way a wall faces, or they land inside the room."""
    base = _assembled()
    faces = band_faces_of(base)
    assert faces, "no outward faces derived"
    assert set(faces.values()) <= {"south", "north", "west", "east"}

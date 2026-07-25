"""Straight stair + floor_hole mesh geometry — import-safe (no Blender)."""

from __future__ import annotations

import pytest

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM
from pae.primitives import get
from pae.primitives.bpy_util import mesh_aabb_from_verts
from pae.primitives.floors import (
    floor_hole_frame_verts_faces,
    floor_hole_inner_aabb_cm,
    floor_hole_margin_cm,
)
from pae.primitives.stairs import (
    straight_stair_step_count,
    straight_stair_verts_faces,
)


def test_straight_stair_step_count_and_descriptor_aabb():
    desc = get("stair_straight")
    steps = straight_stair_step_count()
    assert steps == 20
    assert STOREY_CM / steps == pytest.approx(17.5)
    assert (2.0 * MODULE_CM) / steps == pytest.approx(40.0)

    verts, faces = straight_stair_verts_faces(*desc.size_cm)
    # Each step = riser box + tread box (8 verts / 6 faces each).
    assert len(verts) == steps * 16
    assert len(faces) == steps * 12

    bb_min, bb_max = mesh_aabb_from_verts(verts)
    # Nose overhang extends slightly past x=0; stay within one tread of origin.
    assert bb_min[0] <= 0.0
    assert bb_min[0] >= -50.0
    assert bb_min[1] == pytest.approx(0.0, abs=TOL_CM)
    assert bb_min[2] == pytest.approx(0.0, abs=TOL_CM)
    assert bb_max[0] == pytest.approx(desc.size_cm[0], abs=TOL_CM)
    assert bb_max[1] == pytest.approx(desc.size_cm[1], abs=TOL_CM)
    assert bb_max[2] == pytest.approx(desc.size_cm[2], abs=TOL_CM)

    riser_h = desc.size_cm[2] / steps
    for i in range(steps):
        tread_top_z = (i + 1) * riser_h
        assert any(abs(v[2] - tread_top_z) < 1e-6 for v in verts)


def test_floor_hole_aperture_matches_stair_footprint():
    fh = get("floor_hole")
    assert fh.aperture is not None
    margin = floor_hole_margin_cm()
    ap = fh.aperture
    inner_w = ap.max_cm[0] - ap.min_cm[0]
    inner_d = ap.max_cm[1] - ap.min_cm[1]
    expected_opening = MODULE_CM - 2.0 * margin
    assert inner_w == pytest.approx(expected_opening)
    assert inner_d == pytest.approx(expected_opening)
    assert ap.min_cm[0] == pytest.approx(margin)
    assert ap.min_cm[1] == pytest.approx(margin)
    assert fh.size_cm == pytest.approx((MODULE_CM, MODULE_CM, FLOOR_T_CM))

    void_min, void_max = floor_hole_inner_aabb_cm()
    assert void_max[0] - void_min[0] == pytest.approx(expected_opening)
    assert void_max[1] - void_min[1] == pytest.approx(expected_opening)


def test_floor_hole_frame_mesh_has_clear_center_void():
    margin = floor_hole_margin_cm()
    verts, faces = floor_hole_frame_verts_faces(
        MODULE_CM, MODULE_CM, FLOOR_T_CM, margin=margin
    )
    assert len(faces) == 4 * 6
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min == pytest.approx((0.0, 0.0, 0.0), abs=TOL_CM)
    assert bb_max == pytest.approx((MODULE_CM, MODULE_CM, FLOOR_T_CM), abs=TOL_CM)

    probe_inset = margin + 4.0
    probe_limit = MODULE_CM - margin - 4.0
    inside_hole = [
        v
        for v in verts
        if probe_inset < v[0] < probe_limit and probe_inset < v[1] < probe_limit
    ]
    assert inside_hole == []


def test_spanning_deck_mesh_punches_stair_voids():
    """Upper floor deck must open at VOID bays — not a solid ceiling at stair top."""
    from pae.primitives.floors import (
        hole_rects_for_deck_cm,
        slab_with_rect_holes_verts_faces,
    )

    sx, sy, sz = 4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM
    hole_cells = [(1, 0), (1, 1)]
    rects = hole_rects_for_deck_cm((0, 0), hole_cells)
    assert len(rects) == 2
    verts, faces = slab_with_rect_holes_verts_faces(sx, sy, sz, rects)
    assert faces
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min == pytest.approx((0.0, 0.0, 0.0), abs=TOL_CM)
    assert bb_max == pytest.approx((sx, sy, sz), abs=TOL_CM)

    margin = floor_hole_margin_cm()
    # Center of first VOID bay must contain no geometry.
    cx = 1.0 * MODULE_CM + 0.5 * MODULE_CM
    cy = 0.0 * MODULE_CM + 0.5 * MODULE_CM
    inside = [
        v
        for v in verts
        if abs(v[0] - cx) < (MODULE_CM * 0.5 - margin - 2.0)
        and abs(v[1] - cy) < (MODULE_CM * 0.5 - margin - 2.0)
    ]
    assert inside == []


def test_is_spanning_floor_deck_and_hole_rects():
    from types import SimpleNamespace

    from pae.blender_build import is_spanning_floor_deck, spanning_floor_hole_rects_cm

    deck = SimpleNamespace(
        asset_id="floor",
        kind="floor",
        cell=(0, 0),
        level=1,
        size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
    )
    assert is_spanning_floor_deck(deck)
    holes = [
        SimpleNamespace(asset_id="floor_hole", cell=(1, 0), level=1),
        SimpleNamespace(asset_id="floor_hole", cell=(1, 1), level=1),
        SimpleNamespace(asset_id="floor_hole", cell=(1, 0), level=2),  # other storey
    ]
    rects = spanning_floor_hole_rects_cm(deck, holes)
    assert len(rects) == 2
    assert rects[0][0] == pytest.approx(MODULE_CM + floor_hole_margin_cm())

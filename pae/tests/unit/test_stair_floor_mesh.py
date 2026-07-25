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
    assert len(verts) == steps * 8
    assert len(faces) == steps * 6

    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min == pytest.approx((0.0, 0.0, 0.0), abs=TOL_CM)
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

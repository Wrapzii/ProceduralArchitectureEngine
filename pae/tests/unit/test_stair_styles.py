"""Unit tests for school stair kit styles (import-safe, no Blender)."""

from __future__ import annotations

import pytest

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM
from pae.primitives import get
from pae.primitives.bpy_util import mesh_aabb_from_verts
from pae.primitives.stairs import (
    helical_quarter_step_verts_faces,
    straight_stair_verts_faces,
    switchback_stair_verts_faces,
)


def test_stair_kit_ids_present():
    for sid in (
        "stair_straight",
        "stair_half",
        "stair_landing",
        "stair_switchback",
        "stair_wide",
        "stair_spiral_quarter",
    ):
        assert get(sid).kind == "stair"


def test_stair_half_is_half_storey_one_bay():
    h = get("stair_half")
    assert h.footprint_modules == (1, 1)
    assert h.size_cm[2] == pytest.approx(STOREY_CM * 0.5)
    verts, faces = straight_stair_verts_faces(*h.size_cm, steps=10)
    assert faces
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_max[2] == pytest.approx(h.size_cm[2], abs=TOL_CM)


def test_stair_landing_pad_thickness():
    land = get("stair_landing")
    assert land.size_cm[2] == pytest.approx(FLOOR_T_CM * 1.5)
    assert land.footprint_modules == (1, 1)


def test_stair_switchback_two_by_two_and_has_mid_landing_z():
    sw = get("stair_switchback")
    assert sw.footprint_modules == (2, 2)
    assert sw.size_cm == pytest.approx((2 * MODULE_CM, 2 * MODULE_CM, STOREY_CM))
    verts, faces = switchback_stair_verts_faces(*sw.size_cm)
    assert len(faces) > 12
    zs = sorted({round(v[2], 3) for v in verts})
    # Mid landing around half storey
    assert any(abs(z - STOREY_CM * 0.5) < 20.0 for z in zs)
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_max[0] == pytest.approx(2 * MODULE_CM, abs=5.0)
    assert bb_max[1] == pytest.approx(2 * MODULE_CM, abs=5.0)
    assert bb_max[2] == pytest.approx(STOREY_CM, abs=TOL_CM)


def test_stair_wide_double_corridor():
    w = get("stair_wide")
    assert w.footprint_modules == (2, 2)
    verts, faces = straight_stair_verts_faces(*w.size_cm, steps=16, along="x")
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_max[1] == pytest.approx(2 * MODULE_CM, abs=TOL_CM)
    assert bb_max[2] == pytest.approx(STOREY_CM, abs=TOL_CM)


def test_helical_quarter_has_distinct_step_heights():
    outer = MODULE_CM
    inner = MODULE_CM * 0.35
    rise = STOREY_CM * 0.25
    verts, faces = helical_quarter_step_verts_faces(outer, inner, 0.0, rise, steps=6)
    assert faces
    zs = sorted({round(v[2], 2) for v in verts})
    assert len(zs) >= 4  # multiple tread elevations, not one solid wedge
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_max[2] == pytest.approx(rise, abs=1.0)

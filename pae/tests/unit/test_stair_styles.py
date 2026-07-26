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


def test_stair_switchback_second_flight_beside_first_not_on_landing():
    """Regression: flight 2 must sit in the SW bay, not stacked on the N flats.

    Broken layout put the upper flight in the same XY as the mid landing, so the
    well read as stair → flat → stair facing the wrong way.
    """
    sx = sy = 2 * MODULE_CM
    sz = STOREY_CM
    half_x = sx * 0.5
    half_y = sy * 0.5
    half_z = sz * 0.5
    verts, _faces = switchback_stair_verts_faces(sx, sy, sz)

    def _quad(x0, x1, y0, y1, z0, z1):
        return [
            v
            for v in verts
            if x0 - 1 <= v[0] <= x1 + 1
            and y0 - 1 <= v[1] <= y1 + 1
            and z0 - 1 <= v[2] <= z1 + 1
        ]

    # North bays are mid flats only — no upper-half flight solid filling them.
    nw_upper = _quad(0.0, half_x, half_y, sy, half_z + 40.0, sz)
    ne_upper = _quad(half_x, sx, half_y, sy, half_z + 40.0, sz)
    assert len(nw_upper) == 0, f"NW landing must not host flight-2 treads: {len(nw_upper)}"
    assert len(ne_upper) == 0, f"NE landing must not host flight-2 treads: {len(ne_upper)}"

    # Both mid flats exist near half storey.
    ne_flat = _quad(half_x, sx, half_y, sy, half_z - 40.0, half_z + 5.0)
    nw_flat = _quad(0.0, half_x, half_y, sy, half_z - 40.0, half_z + 5.0)
    assert len(ne_flat) >= 4
    assert len(nw_flat) >= 4

    # Upper flight lives in SW: high Z in the south-west bay.
    sw_upper = _quad(0.0, half_x, 0.0, half_y, half_z + 20.0, sz)
    assert len(sw_upper) >= 8, "flight 2 must occupy SW bay"

    # Top exit is at south of west flight (y≈0), not mid-well.
    top = get("stair_switchback").sockets[1]
    assert top.name == "top"
    assert top.pos_cm[1] == pytest.approx(0.0, abs=1.0)
    assert top.pos_cm[2] == pytest.approx(sz, abs=1.0)


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

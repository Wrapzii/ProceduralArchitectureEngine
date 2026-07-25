"""Wall door/window aperture bounds vs contract (no Blender)."""

from __future__ import annotations

import pytest

from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.primitives import get
from pae.primitives.walls import (
    _ARCH_JAMB,
    _ARCH_SPRING,
    _CUTTER_PAD_X_FRAC,
    _DOOR_H,
    _DOOR_W,
    _SLIT_H,
    _SLIT_SILL,
    _SLIT_W,
    _WINDOW_H,
    _WINDOW_SILL,
    _WINDOW_W,
    aperture_cutter_bounds,
    aperture_opening_run_vertical,
    aperture_opening_yz,
    wall_aperture_frame_parts_cm,
    wall_aperture_is_solid_at,
)


def _opening_inside_wall(desc) -> None:
    ap = desc.aperture
    assert ap is not None
    y0, y1, z0, z1 = aperture_opening_yz(ap)
    assert 0.0 <= y0 < y1 <= MODULE_CM + TOL_CM
    assert 0.0 <= z0 < z1 <= STOREY_CM + TOL_CM
    # logical opening must not exceed wall AABB
    assert y1 - y0 <= MODULE_CM + TOL_CM
    assert z1 - z0 <= STOREY_CM + TOL_CM


@pytest.mark.parametrize(
    "piece_id",
    ("wall_window", "wall_arrowslit", "wall_door", "wall_arcade"),
)
def test_aperture_opening_inside_wall_aabb(piece_id: str):
    _opening_inside_wall(get(piece_id))


def test_door_width_is_forty_percent_bay():
    door = get("wall_door")
    y0, y1, _, _ = aperture_opening_yz(door.aperture)
    width = y1 - y0
    assert width == pytest.approx(MODULE_CM * _DOOR_W)
    assert width == pytest.approx(MODULE_CM * 0.40)


def test_window_width_and_margins_use_contract_fractions():
    window = get("wall_window")
    y0, y1, z0, z1 = aperture_opening_yz(window.aperture)
    assert y1 - y0 == pytest.approx(MODULE_CM * _WINDOW_W)
    assert z0 == pytest.approx(STOREY_CM * _WINDOW_SILL)
    assert z1 - z0 == pytest.approx(STOREY_CM * _WINDOW_H)
    head_margin = STOREY_CM - z1
    assert head_margin == pytest.approx(STOREY_CM * (1.0 - _WINDOW_SILL - _WINDOW_H))


def test_door_reaches_floor_with_head_margin():
    door = get("wall_door")
    _, _, z0, z1 = aperture_opening_yz(door.aperture)
    assert z0 == pytest.approx(0.0)
    assert z1 == pytest.approx(STOREY_CM * _DOOR_H)
    assert STOREY_CM - z1 == pytest.approx(STOREY_CM * (1.0 - _DOOR_H))


def test_arrowslit_narrow_and_raised_sill():
    slit = get("wall_arrowslit")
    y0, y1, z0, z1 = aperture_opening_yz(slit.aperture)
    assert y1 - y0 == pytest.approx(MODULE_CM * _SLIT_W)
    assert z0 == pytest.approx(STOREY_CM * _SLIT_SILL)
    assert z1 - z0 == pytest.approx(STOREY_CM * _SLIT_H)


def test_arcade_jambs_and_spring_from_fractions():
    arcade = get("wall_arcade")
    y0, y1, z0, z1 = aperture_opening_yz(arcade.aperture)
    assert y0 == pytest.approx(MODULE_CM * _ARCH_JAMB)
    assert y1 == pytest.approx(MODULE_CM * (1.0 - _ARCH_JAMB))
    assert z0 == pytest.approx(STOREY_CM * _ARCH_SPRING)
    assert z1 == pytest.approx(STOREY_CM * 0.92)


def test_cutter_x_pierces_both_wall_faces():
    door = get("wall_door")
    cmin, cmax = aperture_cutter_bounds(door.aperture, door.size_cm)
    pad_x = WALL_T_CM * _CUTTER_PAD_X_FRAC
    assert cmin[0] == pytest.approx(-pad_x)
    assert cmax[0] == pytest.approx(WALL_T_CM + pad_x)
    assert cmin[0] < 0.0
    assert cmax[0] > WALL_T_CM


def test_cutter_yz_overrun_for_coplanar_guard():
    window = get("wall_window")
    cmin, cmax = aperture_cutter_bounds(window.aperture, window.size_cm)
    y0, y1, z0, z1 = aperture_opening_yz(window.aperture)
    assert cmin[1] < y0
    assert cmax[1] > y1
    assert cmin[2] < z0
    assert cmax[2] > z1


def test_m1_door_aperture_width_sane_band():
    """Door opening ~1–1.6 m in a 4 m bay — not half the wall missing."""
    door = get("wall_door")
    y0, y1, _, _ = aperture_opening_yz(door.aperture)
    width_cm = y1 - y0
    assert 100.0 <= width_cm <= 170.0
    assert width_cm <= MODULE_CM * 0.45


def _door_frame_parts():
    door = get("wall_door")
    run0, run1, z0, z1 = aperture_opening_run_vertical(door.aperture, door.size_cm)
    return door.size_cm, wall_aperture_frame_parts_cm(door.size_cm, run0, run1, z0, z1)


def test_wall_frame_punches_full_thin_axis():
    """Opening must be hollow through the entire wall thickness (X), not a side notch."""
    size_cm, parts = _door_frame_parts()
    wx, wy, wz = size_cm
    run0, run1, z0, z1 = aperture_opening_run_vertical(
        get("wall_door").aperture, size_cm
    )
    for lx in (0.0, wx * 0.5, wx):
        for ly in (run0 + 4.0, (run0 + run1) * 0.5, run1 - 4.0):
            for lz in (z0 + 4.0, (z0 + z1) * 0.5, z1 - 4.0):
                assert not wall_aperture_is_solid_at(parts, lx, ly, lz)


def test_wall_frame_exterior_face_void_is_rectangle():
    """Thin face (x=0) void must be a single run×vertical rectangle — no P/flag ears."""
    size_cm, parts = _door_frame_parts()
    wx, wy, wz = size_cm
    run0, run1, z0, z1 = aperture_opening_run_vertical(
        get("wall_door").aperture, size_cm
    )
    step = 5.0
    for ly in range(0, int(wy) + 1, int(step)):
        for lz in range(0, int(wz) + 1, int(step)):
            is_void = not wall_aperture_is_solid_at(parts, 0.0, float(ly), float(lz))
            inside = run0 < ly < run1 and z0 <= lz <= z1
            if inside:
                assert is_void, f"opening blocked at thin face (0, {ly}, {lz})"
            elif is_void:
                pytest.fail(f"unexpected void outside opening at (0, {ly}, {lz})")


def test_wall_frame_no_run_end_notch():
    """Run-axis end faces (y=0 / y=wy) stay solid — no side-slot notch."""
    size_cm, parts = _door_frame_parts()
    wx, wy, wz = size_cm
    for ly in (0.0, wy):
        for lz in range(0, int(wz) + 1, 20):
            for lx in (0.0, wx * 0.5, wx):
                assert wall_aperture_is_solid_at(parts, lx, ly, float(lz))


def test_wall_frame_parts_span_full_thickness():
    """Every frame box must span the full thin axis [0, wx]."""
    size_cm, parts = _door_frame_parts()
    wx = size_cm[0]
    for origin, size in parts:
        assert origin[0] == pytest.approx(0.0)
        assert size[0] == pytest.approx(wx)

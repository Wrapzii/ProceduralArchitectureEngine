"""Monumental gate / arcade arch mesh smoothness — band count and curve fidelity."""

from __future__ import annotations

import pytest

from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.fortress_validate import MIN_GATE_CLEAR_HEIGHT_CM, MIN_GATE_CLEAR_WIDTH_CM
from pae.primitives import get
from pae.primitives.apertures import MONUMENTAL_HEAD_BANDS, frame_parts, get_profile
from pae.primitives.measure import (
    arch_clear_opening_cm,
    arch_curve_max_deviation_cm,
    arch_head_band_step_cm,
    footprint_contract_errors,
    monumental_arch_mesh_smooth,
    monumental_arch_sane,
)
from pae.primitives.walls import (
    aperture_opening_run_vertical,
    wall_aperture_is_solid_at,
)


_MONUMENTAL_PROFILES = ("gate_arch", "gate_arch_grand", "arcade_round")
_MONUMENTAL_WALLS = (
    "wall_gate_arch",
    "wall_gate_arch_grand",
    "wall_arcade",
)


@pytest.mark.parametrize("profile_name", _MONUMENTAL_PROFILES)
def test_monumental_profiles_use_high_head_bands(profile_name: str):
    profile = get_profile(profile_name)
    assert profile.head_bands >= MONUMENTAL_HEAD_BANDS
    assert monumental_arch_mesh_smooth(profile_name) == []


@pytest.mark.parametrize("profile_name", _MONUMENTAL_PROFILES)
def test_monumental_arch_band_step_under_eight_cm(profile_name: str):
    step = arch_head_band_step_cm(profile_name)
    assert step > 0.0
    assert step <= 8.0 + TOL_CM


@pytest.mark.parametrize("profile_name", _MONUMENTAL_PROFILES)
def test_monumental_arch_curve_deviation_under_five_cm(profile_name: str):
    dev = arch_curve_max_deviation_cm(profile_name)
    assert dev <= 5.0 + TOL_CM


@pytest.mark.parametrize("piece_id", _MONUMENTAL_WALLS)
def test_monumental_wall_footprint_unchanged(piece_id: str):
    desc = get(piece_id)
    assert footprint_contract_errors(desc) == []


@pytest.mark.parametrize("piece_id", _MONUMENTAL_WALLS)
def test_monumental_wall_opening_still_monumental(piece_id: str):
    desc = get(piece_id)
    assert desc.profile is not None
    assert monumental_arch_sane(desc.profile) == []


def test_gate_arch_grand_clear_opening_meets_fortress_mins():
    """Gate-through sibling: opening bounds unchanged — only mesh bands improved."""
    desc = get("wall_gate_arch_grand")
    run0, run1, z0, z1 = aperture_opening_run_vertical(desc.aperture, desc.size_cm)
    assert (run1 - run0) >= MIN_GATE_CLEAR_WIDTH_CM - TOL_CM
    assert (z1 - z0) >= MIN_GATE_CLEAR_HEIGHT_CM - TOL_CM


def test_gate_arch_frame_punches_full_thickness():
    """Curved head must still be a through-hole on thin X, not a side notch."""
    desc = get("wall_gate_arch")
    parts = frame_parts(get_profile(desc.profile), desc.size_cm)
    wx = desc.size_cm[0]
    run0, run1, z0, _z1 = aperture_opening_run_vertical(desc.aperture, desc.size_cm)
    _, spring, apex = arch_clear_opening_cm(desc.profile)
    run_centre = (run0 + run1) * 0.5
    for lx in (0.0, wx * 0.5, wx):
        for lz in (z0 + 4.0, (spring + apex) * 0.5, apex - 4.0):
            assert not wall_aperture_is_solid_at(parts, lx, run_centre, lz)


def test_arcade_round_head_has_more_bands_than_default_window():
    from pae.primitives.apertures import HEAD_BANDS

    arcade = get_profile("arcade_round")
    window = get_profile("window_round")
    assert arcade.head_bands > HEAD_BANDS
    assert window.head_bands == HEAD_BANDS


def test_gate_arch_clear_height_fraction():
    run_w, spring, apex = arch_clear_opening_cm("gate_arch")
    clear_h = apex - spring
    assert run_w >= MODULE_CM * 0.55
    assert clear_h >= STOREY_CM * 0.72

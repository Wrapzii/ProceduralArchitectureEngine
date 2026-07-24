"""Smoke: contract constants are importable and non-zero."""

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM


def test_contract_constants():
    assert MODULE_CM == 400.0
    assert STOREY_CM == 350.0
    assert WALL_T_CM == 60.0
    assert FLOOR_T_CM == 30.0


def test_rotation_offset_table():
    from pae.contract import rotation_offset_cm

    sx, sy = 60.0, 400.0
    assert rotation_offset_cm(0, sx, sy) == (0.0, 0.0)
    assert rotation_offset_cm(90, sx, sy) == (sy, 0.0)
    assert rotation_offset_cm(180, sx, sy) == (sx, sy)
    assert rotation_offset_cm(270, sx, sy) == (0.0, sx)
    assert rotation_offset_cm(90, sx, sy, rotates_about_center=True) == (0.0, 0.0)


def test_snap_fit_rejects_176cm_pillar():
    from pae.assets.fit import snap_fit

    decision, factor = snap_fit(176.0)
    assert decision in ("scale", "reject")
    assert decision != "ok"

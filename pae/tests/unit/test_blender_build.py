"""Unit tests for ``pae.blender_build`` (no Blender required)."""

from __future__ import annotations

import sys

import pytest

from pae.primitives.bpy_util import HAS_BPY


def test_reload_pae_drops_cached_modules():
    import pae.assemble
    import pae.spec
    from pae.blender_build import reload_pae

    assert "pae.spec" in sys.modules
    dropped = reload_pae()
    assert "pae.spec" in dropped
    assert "pae.assemble" in dropped
    assert "pae.blender_build" in sys.modules
    assert "pae.spec" not in sys.modules


def test_gallery_factories_include_m1_through_m4_l():
    from pae.blender_build import _gallery_factories

    factories = _gallery_factories()
    labels = [lbl for lbl, _coll, _fn in factories]
    assert labels == ["m1", "m2", "m3", "m4_l"]
    coll_names = [coll for _lbl, coll, _fn in factories]
    assert coll_names == ["PAE_M1", "PAE_M2", "PAE_M3", "PAE_M4_L"]


def test_assembly_bounds_cm_positive_extent():
    from pae.blender_build import assembly_bounds_cm, assembly_footprint_extent_m
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec

    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    bb_min, bb_max = assembly_bounds_cm(assembly)
    assert bb_max[0] > bb_min[0]
    assert bb_max[1] > bb_min[1]
    extent = assembly_footprint_extent_m(assembly)
    assert all(v > 0 for v in extent)


def test_build_gallery_headless_all_milestones():
    from pae.blender_build import build_gallery

    result = build_gallery(write_png=False)
    assert result["ok"] is True
    assert result["mode"] == "gallery"
    assert len(result["milestones"]) == 4
    for entry in result["milestones"]:
        assert entry["ok"] is True
        assert entry["placements"] > 0
        assert entry["collection"].startswith("PAE_")
    if not HAS_BPY:
        assert result["blender"] is False
        assert result["screenshot"] is None


def test_build_gallery_headless_subset():
    from pae.blender_build import build_gallery

    result = build_gallery(write_png=False, milestones=("m1", "m4_l"))
    labels = [m["label"] for m in result["milestones"]]
    assert labels == ["m1", "m4_l"]


def test_build_live_m1_still_works():
    from pae.blender_build import build_live

    result = build_live(write_png=False, milestones=("m1",))
    assert result["ok"] is True
    assert result["milestones"][0]["label"] == "m1"
    assert result["milestones"][0]["ok"] is True
    assert result["milestones"][0]["placements"] > 0


def test_write_gallery_screenshot_no_bpy_is_noop():
    from pae.blender_build import write_gallery_screenshot

    if HAS_BPY:
        pytest.skip("headless no-op only without bpy")
    assert write_gallery_screenshot() is None

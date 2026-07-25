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


def test_gallery_factories_include_m1_through_m4_c():
    from pae.blender_build import _gallery_factories

    factories = _gallery_factories()
    labels = [lbl for lbl, _coll, _fn in factories]
    assert labels == ["m1", "m2", "m3", "m4_l", "m4_u", "m4_c"]
    coll_names = [coll for _lbl, coll, _fn in factories]
    assert coll_names == [
        "PAE_M1",
        "PAE_M2",
        "PAE_M3",
        "PAE_M4_L",
        "PAE_M4_U",
        "PAE_M4_C",
    ]


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


def test_placement_instance_scale_cm_roof_span():
    """M1 roof spans 4×3 modules plus eaves — Blender instance scales XY from catalog."""
    from pae.blender_build import placement_instance_scale_cm
    from pae.contract import EAVE_OVERHANG_CM, MODULE_CM
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec

    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    roof = next(p for p in assembly.placements if p.kind == "roof")
    sx, sy, sz = placement_instance_scale_cm(roof)
    oh = EAVE_OVERHANG_CM
    assert sx == pytest.approx((4 * MODULE_CM + 2 * oh) / MODULE_CM)
    assert sy == pytest.approx((3 * MODULE_CM + 2 * oh) / MODULE_CM)
    assert sz == pytest.approx(1.0)

    wall = next(p for p in assembly.placements if p.asset_id == "wall_plain")
    wx, wy, wz = placement_instance_scale_cm(wall)
    assert wx == pytest.approx(1.0)
    assert wy == pytest.approx(1.0)
    assert wz == pytest.approx(1.0)


def test_build_gallery_headless_all_milestones():
    from pae.blender_build import build_gallery

    result = build_gallery(write_png=False)
    assert result["ok"] is True
    assert result["mode"] == "gallery"
    assert len(result["milestones"]) == 6
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


def test_gallery_m4_courtyard_no_roof_over_court():
    """Open courtyard gallery milestone: no roof deck spans the court hole."""
    from pae.blender_build import assemble_and_validate
    from pae.contract import MODULE_CM, placement_world_aabb
    from pae.plan import CellRole
    from pae.pipeline import run_through_assemble
    from pae.spec import m4_courtyard_spec

    _, floor_plan, assembly, _ = run_through_assemble(m4_courtyard_spec())
    assembly, report = assemble_and_validate("m4_c", m4_courtyard_spec)
    assert report.ok is True

    grid = floor_plan.storeys[0]
    court = {c for c, r in grid.cells.items() if r == CellRole.COURTYARD}
    assert len(court) > 0

    for p in assembly.placements:
        if p.kind in ("floor", "roof", "ground"):
            assert p.cell not in court

    roofs = [p for p in assembly.placements if p.kind == "roof"]
    assert len(roofs) == 4

    cx, cy = 3, 3
    wx, wy = cx * MODULE_CM, cy * MODULE_CM
    for r in roofs:
        bb_min, bb_max = placement_world_aabb(
            r.cell[0],
            r.cell[1],
            r.level,
            r.yaw,
            r.size_cm,
            r.offset_cm,
        )
        covers = (
            bb_min[0] <= wx
            and bb_min[1] <= wy
            and bb_max[0] >= wx + MODULE_CM
            and bb_max[1] >= wy + MODULE_CM
        )
        assert not covers


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


def test_camera_pose_from_bounds_m_targets_center():
    import math

    from pae.blender_build import GALLERY_CAM_DIRECTION, camera_pose_from_bounds_m

    bb_min = (0.0, 0.0, 0.0)
    bb_max = (4.0, 3.0, 6.0)
    pose = camera_pose_from_bounds_m(bb_min, bb_max)
    assert pose["target"] == (2.0, 1.5, 3.0)
    loc = pose["location"]
    tgt = pose["target"]
    dist = math.sqrt(sum((loc[i] - tgt[i]) ** 2 for i in range(3)))
    assert dist == pytest.approx(pose["radius_m"], rel=1e-6)
    dx = loc[0] - tgt[0]
    dy = loc[1] - tgt[1]
    dz = loc[2] - tgt[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    dir_x = dx / length
    dir_y = dy / length
    dir_z = dz / length
    exp_x, exp_y, exp_z = GALLERY_CAM_DIRECTION
    exp_len = math.sqrt(exp_x * exp_x + exp_y * exp_y + exp_z * exp_z)
    assert dir_x == pytest.approx(exp_x / exp_len, abs=1e-6)
    assert dir_y == pytest.approx(exp_y / exp_len, abs=1e-6)
    assert dir_z == pytest.approx(exp_z / exp_len, abs=1e-6)
    assert pose["ortho"] is True
    assert pose["ortho_scale"] > 0


def test_assembly_world_bounds_m_matches_gallery_offsets():
    from pae.blender_build import CM_TO_M, assembly_bounds_cm, assembly_world_bounds_m, build_gallery
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec, m2_two_storey_stair_spec

    _, _, m1, _ = run_through_assemble(m1_box_house_spec())
    _, _, m2, _ = run_through_assemble(m2_two_storey_stair_spec())
    m1_min, m1_max = assembly_bounds_cm(m1)
    m2_min, m2_max = assembly_bounds_cm(m2)
    m1_width_m = (m1_max[0] - m1_min[0]) * CM_TO_M
    gap = 2.0
    offset_m2 = (
        m1_width_m + gap - m2_min[0] * CM_TO_M,
        -m2_min[1] * CM_TO_M,
        -m2_min[2] * CM_TO_M,
    )
    wmin, wmax = assembly_world_bounds_m(m2, offset_m2)
    assert wmin[0] == pytest.approx(m1_width_m + gap, abs=1e-6)
    assert wmin[1] == pytest.approx(0.0, abs=1e-6)
    assert wmin[2] == pytest.approx(0.0, abs=1e-6)
    assert wmax[0] > wmin[0]


def test_gallery_headless_offsets_are_monotonic_along_x():
    from pae.blender_build import build_gallery

    result = build_gallery(write_png=False)
    assert len(result["milestones"]) == 6
    # Headless path records extent; blender path records offset_m — check labels order.
    labels = [m["label"] for m in result["milestones"]]
    assert labels == ["m1", "m2", "m3", "m4_l", "m4_u", "m4_c"]


def test_stair_proof_visibility_allowlist():
    from pae.blender_build import is_stair_proof_visible_asset
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    assert is_stair_proof_visible_asset("stair_straight")
    assert is_stair_proof_visible_asset("floor_hole")
    assert is_stair_proof_visible_asset("wall", piece_id="stair_landing")
    assert is_stair_proof_visible_asset("floor", level=1)
    assert not is_stair_proof_visible_asset("floor", level=0)
    assert not is_stair_proof_visible_asset("floor")
    assert not is_stair_proof_visible_asset("wall_segment")
    assert not is_stair_proof_visible_asset("ground_slab")
    assert not is_stair_proof_visible_asset("roof_flat")

    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    visible = [
        p
        for p in assembly.placements
        if is_stair_proof_visible_asset(p.asset_id, p.piece_id, level=p.level)
    ]
    hidden = [
        p
        for p in assembly.placements
        if not is_stair_proof_visible_asset(p.asset_id, p.piece_id, level=p.level)
    ]
    assert any(p.asset_id == "floor_hole" for p in visible)
    assert any(p.asset_id == "floor" and p.level >= 1 for p in visible)
    assert all(not (p.asset_id == "floor" and p.level >= 1) for p in hidden)
    assert {p.kind for p in hidden} >= {"wall", "roof"}
    assert len(visible) + len(hidden) == len(assembly.placements)


def test_stair_proof_bounds_cm_includes_stair_and_holes():
    from pae.blender_build import is_stair_proof_placement, stair_proof_bounds_cm
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    proof = [p for p in assembly.placements if is_stair_proof_placement(p)]
    assert len(proof) == 3  # 1 stair + 2 floor_hole
    assert any(p.asset_id == "stair_straight" or p.kind == "stair" for p in proof)
    assert sum(1 for p in proof if p.asset_id == "floor_hole") == 2

    bb_min, bb_max = stair_proof_bounds_cm(assembly)
    assert bb_max[0] > bb_min[0]
    assert bb_max[1] > bb_min[1]
    assert bb_max[2] > bb_min[2]


def test_stair_proof_camera_pose_targets_stair_aabb_center():
    import math

    from pae.blender_build import (
        stair_proof_bounds_m,
        stair_proof_camera_direction_from_bounds_m,
        stair_proof_camera_pose_from_bounds_m,
        stair_proof_ortho_scale_from_bounds_m,
    )
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    bb_min, bb_max = stair_proof_bounds_m(assembly)
    pose = stair_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    cx = (bb_min[0] + bb_max[0]) * 0.5
    cy = (bb_min[1] + bb_max[1]) * 0.5
    cz = (bb_min[2] + bb_max[2]) * 0.5
    assert pose["target"] == (cx, cy, cz)
    loc = pose["location"]
    tgt = pose["target"]
    dist = math.sqrt(sum((loc[i] - tgt[i]) ** 2 for i in range(3)))
    assert dist == pytest.approx(pose["radius_m"], rel=1e-6)
    dx = loc[0] - tgt[0]
    dy = loc[1] - tgt[1]
    dz = loc[2] - tgt[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    exp_x, exp_y, exp_z = stair_proof_camera_direction_from_bounds_m(bb_min, bb_max)
    assert dx / length == pytest.approx(exp_x, abs=1e-6)
    assert dy / length == pytest.approx(exp_y, abs=1e-6)
    assert dz / length == pytest.approx(exp_z, abs=1e-6)
    assert pose["ortho_scale"] == pytest.approx(
        stair_proof_ortho_scale_from_bounds_m(bb_min, bb_max), rel=1e-9
    )


def test_stair_proof_camera_offset_y_when_run_longer_in_x():
    from pae.blender_build import stair_proof_camera_pose_from_bounds_m

    bb_min = (0.0, 0.0, 0.0)
    bb_max = (10.0, 3.0, 2.5)
    pose = stair_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    loc = pose["location"]
    tgt = pose["target"]
    assert abs(loc[1] - tgt[1]) > abs(loc[0] - tgt[0])
    assert loc[2] > tgt[2]


def test_stair_proof_camera_offset_x_when_run_longer_in_y():
    from pae.blender_build import stair_proof_camera_pose_from_bounds_m

    bb_min = (0.0, 0.0, 0.0)
    bb_max = (3.0, 10.0, 2.5)
    pose = stair_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    loc = pose["location"]
    tgt = pose["target"]
    assert abs(loc[0] - tgt[0]) > abs(loc[1] - tgt[1])
    assert loc[2] > tgt[2]


def test_m2_stair_proof_camera_perpendicular_to_y_run():
    """M2 straight run spans Y in world space — camera offsets along X, not Y."""
    from pae.blender_build import stair_proof_bounds_m, stair_proof_camera_pose_from_bounds_m
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    bb_min, bb_max = stair_proof_bounds_m(assembly)
    assert bb_max[1] - bb_min[1] > bb_max[0] - bb_min[0]
    pose = stair_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    loc = pose["location"]
    tgt = pose["target"]
    assert abs(loc[0] - tgt[0]) > abs(loc[1] - tgt[1])


def test_build_m2_stair_proof_headless():
    from pae.blender_build import M2_STAIR_PROOF_SCREENSHOT_REL, build_m2_stair_proof

    result = build_m2_stair_proof(write_png=False)
    assert result["ok"] is True
    assert result["mode"] == "stair_proof"
    assert result["stair_proof_placements"] == 3
    assert result["camera_pose"]["ortho"] is True
    if not HAS_BPY:
        assert result["blender"] is False
        assert result["screenshot"] is None
    assert str(M2_STAIR_PROOF_SCREENSHOT_REL).endswith("m2_stair_proof.png")


def test_write_m2_stair_proof_screenshot_no_bpy_is_noop():
    from pae.blender_build import write_m2_stair_proof_screenshot

    if HAS_BPY:
        pytest.skip("headless no-op only without bpy")
    assert write_m2_stair_proof_screenshot() is None


def test_openings_proof_bounds_cm_includes_door_and_windows():
    from pae.blender_build import (
        is_openings_proof_aperture_placement,
        is_openings_proof_placement,
        openings_proof_bounds_cm,
    )
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec

    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    apertures = [p for p in assembly.placements if is_openings_proof_aperture_placement(p)]
    assert len(apertures) == 3
    shell = [p for p in assembly.placements if is_openings_proof_placement(p)]
    assert len(shell) >= 3
    bb_min, bb_max = openings_proof_bounds_cm(assembly)
    assert bb_max[0] > bb_min[0]
    assert bb_max[1] > bb_min[1]
    assert bb_max[2] > bb_min[2]
    assert bb_min[0] == pytest.approx(0.0)
    assert bb_min[1] == pytest.approx(0.0)


def test_openings_proof_camera_pose_targets_shell_center_se():
    import math

    from pae.blender_build import (
        OPENINGS_PROOF_CAM_DIRECTION,
        openings_proof_bounds_m,
        openings_proof_camera_pose_from_bounds_m,
    )
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec

    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    bb_min, bb_max = openings_proof_bounds_m(assembly)
    pose = openings_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    cx = (bb_min[0] + bb_max[0]) * 0.5
    cy = (bb_min[1] + bb_max[1]) * 0.5
    cz = (bb_min[2] + bb_max[2]) * 0.5
    assert pose["target"] == (cx, cy, cz)
    loc = pose["location"]
    tgt = pose["target"]
    dist = math.sqrt(sum((loc[i] - tgt[i]) ** 2 for i in range(3)))
    assert dist == pytest.approx(pose["radius_m"], rel=1e-6)
    dx = loc[0] - tgt[0]
    dy = loc[1] - tgt[1]
    dz = loc[2] - tgt[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    exp_x, exp_y, exp_z = OPENINGS_PROOF_CAM_DIRECTION
    exp_len = math.sqrt(exp_x * exp_x + exp_y * exp_y + exp_z * exp_z)
    assert dx / length == pytest.approx(exp_x / exp_len, abs=1e-6)
    assert dy / length == pytest.approx(exp_y / exp_len, abs=1e-6)
    assert dz / length == pytest.approx(exp_z / exp_len, abs=1e-6)
    assert pose["ortho"] is True


def test_openings_proof_visible_asset_hides_north_east():
    from pae.blender_build import is_openings_proof_visible_asset

    assert is_openings_proof_visible_asset("wall_door", "wall_south_0_0_0")
    assert is_openings_proof_visible_asset("wall_window", "wall_west_0_0_1")
    assert not is_openings_proof_visible_asset("wall_plain", "wall_north_0_3_0")
    assert not is_openings_proof_visible_asset("wall_plain", "wall_east_4_0_0")
    assert not is_openings_proof_visible_asset("roof_flat", "roof_0_0_0")
    assert not is_openings_proof_visible_asset("floor", "floor_0_0_0")
    assert is_openings_proof_visible_asset("ground_plinth", "ground_0_0_0")


def test_build_m1_openings_proof_headless():
    from pae.blender_build import M1_OPENINGS_PROOF_SCREENSHOT_REL, build_m1_openings_proof

    result = build_m1_openings_proof(write_png=False)
    assert result["ok"] is True
    assert result["mode"] == "openings_proof"
    assert result["openings_proof_apertures"] == 3
    assert result["openings_proof_placements"] >= 3
    assert result["camera_pose"]["ortho"] is True
    if not HAS_BPY:
        assert result["blender"] is False
        assert result["screenshot"] is None
    assert str(M1_OPENINGS_PROOF_SCREENSHOT_REL).endswith("m1_openings_proof.png")


def test_write_m1_openings_proof_screenshot_no_bpy_is_noop():
    from pae.blender_build import write_m1_openings_proof_screenshot

    if HAS_BPY:
        pytest.skip("headless no-op only without bpy")
    assert write_m1_openings_proof_screenshot() is None


_GALLERY_PRIMARY_KINDS = (
    "wall",
    "floor",
    "ground",
    "roof",
    "stair",
    "tower_arc",
    "tower_crown",
    "tower_cap",
    "door",
    "window",
)


def test_kind_material_colors_required_keys():
    from pae.blender_build import KIND_MATERIAL_COLORS

    assert set(_GALLERY_PRIMARY_KINDS) <= set(KIND_MATERIAL_COLORS.keys())


def test_kind_material_colors_are_distinct():
    from pae.blender_build import material_color_for_kind

    rgbs = [material_color_for_kind(k)[:3] for k in _GALLERY_PRIMARY_KINDS]
    for i, a in enumerate(rgbs):
        for b in rgbs[i + 1 :]:
            dist = sum(abs(a[j] - b[j]) for j in range(3))
            assert dist > 0.12, f"colors too similar: {a} vs {b}"


def test_material_color_for_kind_fallback():
    from pae.blender_build import material_color_for_kind

    assert material_color_for_kind("unknown_kind") == (0.75, 0.75, 0.75, 1.0)


def test_kind_material_colors_workbench_friendly():
    from pae.blender_build import KIND_MATERIAL_COLORS

    for _kind, (r, g, b, a) in KIND_MATERIAL_COLORS.items():
        assert 0.15 <= r <= 0.85
        assert 0.15 <= g <= 0.85
        assert 0.15 <= b <= 0.85
        assert a == 1.0


_TINTED_ASSET_IDS = (
    "wall_door",
    "wall_window",
    "roof_flat",
    "roof_gable_infill",
    "roof_pitched_slope",
    "tower_arc_quarter",
    "tower_crown",
    "tower_cap",
    "stair_straight",
    "stair_half",
    "stair_landing",
    "stair_switchback",
    "stair_wide",
    "stair_spiral_quarter",
    "floor_hole",
)


def test_material_key_for_placement_uses_asset_id_for_tints():
    from pae.blender_build import material_key_for_placement

    assert material_key_for_placement("wall_door", "wall") == "wall_door"
    assert material_key_for_placement("wall_window", "wall") == "wall_window"
    assert material_key_for_placement("roof_flat", "roof") == "roof_flat"
    assert material_key_for_placement("tower_crown", "tower_crown") == "tower_crown"
    assert material_key_for_placement("stair_straight", "stair") == "stair_straight"
    assert material_key_for_placement("floor_hole", "floor") == "floor_hole"
    assert material_key_for_placement("wall_plain", "wall") == "wall"
    assert material_key_for_placement("floor", "floor") == "floor"


def test_material_color_door_window_differ_from_plain_wall():
    from pae.blender_build import material_color_for_placement

    wall = material_color_for_placement("wall_plain", "wall")
    door = material_color_for_placement("wall_door", "wall")
    window = material_color_for_placement("wall_window", "wall")
    assert door != wall
    assert window != wall
    assert door != window
    for a, b in ((door, wall), (window, wall), (door, window)):
        dist = sum(abs(a[i] - b[i]) for i in range(3))
        assert dist > 0.12


def test_asset_material_colors_required_keys():
    from pae.blender_build import ASSET_MATERIAL_COLORS

    assert set(_TINTED_ASSET_IDS) <= set(ASSET_MATERIAL_COLORS.keys())


def test_asset_material_colors_are_distinct():
    from pae.blender_build import material_color_for_placement

    rgbs = [
        material_color_for_placement(asset_id, asset_id.split("_", 1)[0])[:3]
        for asset_id in _TINTED_ASSET_IDS
    ]
    for i, a in enumerate(rgbs):
        for b in rgbs[i + 1 :]:
            dist = sum(abs(a[j] - b[j]) for j in range(3))
            assert dist > 0.12, f"colors too similar: {a} vs {b}"


def test_material_color_for_placement_kind_fallback():
    from pae.blender_build import material_color_for_kind, material_color_for_placement

    assert material_color_for_placement("wall_plain", "wall") == material_color_for_kind("wall")
    assert material_color_for_placement("floor", "floor") == material_color_for_kind("floor")


def test_configure_workbench_screenshot_scene_sets_material_shading():
    from types import SimpleNamespace

    from pae.blender_build import (
        WORKBENCH_SCREENSHOT_RESOLUTION,
        WORKBENCH_SCREENSHOT_VIEW_TRANSFORM,
        configure_workbench_screenshot_scene,
    )

    shading = SimpleNamespace(type="", light="", color_type="")
    display = SimpleNamespace(shading=shading)
    view_settings = SimpleNamespace(view_transform="", look="")
    render = SimpleNamespace(
        engine="",
        resolution_x=0,
        resolution_y=0,
        resolution_percentage=0,
        image_settings=SimpleNamespace(file_format=""),
    )
    scene = SimpleNamespace(render=render, display=display, view_settings=view_settings)
    configure_workbench_screenshot_scene(scene)
    w, h = WORKBENCH_SCREENSHOT_RESOLUTION
    assert render.engine == "BLENDER_WORKBENCH"
    assert render.resolution_x == w
    assert render.resolution_y == h
    assert render.resolution_percentage == 100
    assert render.image_settings.file_format == "PNG"
    assert shading.type == "SOLID"
    assert shading.light == "STUDIO"
    assert shading.color_type == "MATERIAL"
    assert view_settings.view_transform == WORKBENCH_SCREENSHOT_VIEW_TRANSFORM
    assert view_settings.look == "None"


def test_apply_material_base_color_sets_diffuse_and_principled():
    from types import SimpleNamespace

    from pae.blender_build import apply_material_base_color

    rgba = (0.55, 0.28, 0.12, 1.0)
    bsdf = SimpleNamespace(
        inputs={
            "Base Color": SimpleNamespace(default_value=(0.0, 0.0, 0.0, 1.0)),
            "Roughness": SimpleNamespace(default_value=0.5),
        }
    )
    mat = SimpleNamespace(
        diffuse_color=(0.0, 0.0, 0.0, 1.0),
        use_nodes=True,
        node_tree=SimpleNamespace(nodes={"Principled BSDF": bsdf}),
    )
    apply_material_base_color(mat, rgba)
    assert mat.diffuse_color == rgba
    assert bsdf.inputs["Base Color"].default_value == rgba
    assert bsdf.inputs["Roughness"].default_value == 0.7

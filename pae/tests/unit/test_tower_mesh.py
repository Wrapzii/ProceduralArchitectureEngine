"""Tower kit mesh geometry — import-safe (no Blender required)."""

from __future__ import annotations

import math

import pytest

from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.primitives import get
from pae.primitives.bpy_util import (
    ARC_SEGMENTS_FULL,
    TOWER_ARC_SEGMENTS_FULL,
    annulus_battlement_ring_verts,
    annulus_quarter_verts,
    cone_verts,
    mesh_aabb_from_verts,
)
from pae.primitives.towers import _CAP_H_FRAC, _CROWN_H_FRAC


def _rotate_z_xy(x: float, y: float, yaw_deg: int) -> tuple[float, float]:
    a = math.radians(float(yaw_deg))
    ca, sa = math.cos(a), math.sin(a)
    return x * ca - y * sa, x * sa + y * ca


def _outer_bottom_ring(verts: list, *, segments_full: int = ARC_SEGMENTS_FULL) -> list:
    n = max(3, segments_full // 4)
    stride = n + 1
    return verts[0:stride]


def _tower_arc_kwargs() -> dict:
    return {
        "segments_full": TOWER_ARC_SEGMENTS_FULL,
        "cap_horizontal": False,
    }


def test_arc_quarter_segment_count_and_verts():
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    n = ARC_SEGMENTS_FULL // 4
    stride = n + 1
    verts, faces = annulus_quarter_verts(outer, inner, 0.0, STOREY_CM)
    assert len(verts) == 4 * stride
    assert len(faces) == 4 * n + 2
    ring = _outer_bottom_ring(verts)
    assert ring[0][0] == pytest.approx(outer, abs=1e-6)
    assert ring[0][1] == pytest.approx(0.0, abs=1e-6)
    assert ring[n][0] == pytest.approx(0.0, abs=1e-6)
    assert ring[n][1] == pytest.approx(outer, abs=1e-6)
    inner_ring = verts[stride : 2 * stride]
    assert inner_ring[0][0] == pytest.approx(inner, abs=1e-6)


def test_tower_arc_quarter_open_cylinder():
    """Tower drum: denser tessellation, no horizontal caps (stackable straight wall)."""
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    n = TOWER_ARC_SEGMENTS_FULL // 4
    stride = n + 1
    verts, faces = annulus_quarter_verts(
        outer, inner, 0.0, STOREY_CM, **_tower_arc_kwargs()
    )
    assert len(verts) == 4 * stride
    assert len(faces) == 2 * n + 2  # outer+inner walls + radial caps only


def test_tower_arc_outer_wall_is_true_cylinder():
    """Outer wall columns share (x,y) from z0→z1 — constant radius, no torus bulge."""
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    n = TOWER_ARC_SEGMENTS_FULL // 4
    stride = n + 1
    verts, _ = annulus_quarter_verts(
        outer, inner, 0.0, STOREY_CM, **_tower_arc_kwargs()
    )
    bot_outer = verts[0:stride]
    top_outer = verts[2 * stride : 3 * stride]
    for i in range(n + 1):
        assert bot_outer[i][0] == pytest.approx(top_outer[i][0], abs=1e-9)
        assert bot_outer[i][1] == pytest.approx(top_outer[i][1], abs=1e-9)
        r = math.hypot(bot_outer[i][0], bot_outer[i][1])
        assert r == pytest.approx(outer, abs=TOL_CM * 0.01)


def test_four_quarters_radial_seams_meet():
    """Adjacent quarter instances share seam vertices on cardinal axes."""
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    n = TOWER_ARC_SEGMENTS_FULL // 4
    base_verts, _ = annulus_quarter_verts(
        outer, inner, 0.0, STOREY_CM, **_tower_arc_kwargs()
    )
    ring = _outer_bottom_ring(base_verts, segments_full=TOWER_ARC_SEGMENTS_FULL)

    seams = (
        (0, 90, n, 0),
        (90, 180, n, 0),
        (180, 270, n, 0),
        (270, 0, n, 0),
    )
    for yaw_a, yaw_b, idx_a, idx_b in seams:
        xa, ya, _ = ring[idx_a]
        xb, yb, _ = ring[idx_b]
        wa = _rotate_z_xy(xa, ya, yaw_a)
        wb = _rotate_z_xy(xb, yb, yaw_b)
        assert wa[0] == pytest.approx(wb[0], abs=TOL_CM)
        assert wa[1] == pytest.approx(wb[1], abs=TOL_CM)
        r = math.hypot(wa[0], wa[1])
        assert r == pytest.approx(outer, abs=TOL_CM)


def test_four_quarters_no_large_outer_gap():
    """Outer ring samples from four yaw-rotated quarters stay on the drum."""
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    base_verts, _ = annulus_quarter_verts(
        outer, inner, 0.0, STOREY_CM, **_tower_arc_kwargs()
    )
    ring = _outer_bottom_ring(base_verts, segments_full=TOWER_ARC_SEGMENTS_FULL)
    samples: list[tuple[float, float]] = []
    for yaw in (0, 90, 180, 270):
        for pt in ring:
            samples.append(_rotate_z_xy(pt[0], pt[1], yaw))
    radii = [math.hypot(x, y) for x, y in samples]
    assert max(radii) - min(radii) <= TOL_CM


def test_crown_mesh_aabb_matches_descriptor():
    crown = get("tower_crown")
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    h = STOREY_CM * _CROWN_H_FRAC
    verts, faces = annulus_battlement_ring_verts(outer, inner, 0.0, h)
    assert len(verts) > 8
    assert len(faces) > 4
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min[0] == pytest.approx(-outer, abs=TOL_CM)
    assert bb_max[0] == pytest.approx(outer, abs=TOL_CM)
    assert bb_min[1] == pytest.approx(-outer, abs=TOL_CM)
    assert bb_max[1] == pytest.approx(outer, abs=TOL_CM)
    assert bb_min[2] == pytest.approx(0.0, abs=TOL_CM)
    assert bb_max[2] == pytest.approx(h, abs=TOL_CM)
    assert crown.size_cm[2] == pytest.approx(h)


def test_crown_has_parapet_drum_and_merlon_teeth():
    """Crown = straight parapet ring + discrete merlon blocks (not wavy outer ring)."""
    outer = MODULE_CM
    inner = MODULE_CM - WALL_T_CM
    h = STOREY_CM * _CROWN_H_FRAC
    verts, _ = annulus_battlement_ring_verts(outer, inner, 0.0, h)
    parapet_z = h * 0.42
    outer_radii = [math.hypot(v[0], v[1]) for v in verts if v[2] <= parapet_z + 1e-6]
    assert outer_radii
    assert max(outer_radii) == pytest.approx(outer, abs=TOL_CM)
    merlon_tops = [v for v in verts if abs(v[2] - h) < 1e-6]
    assert len(merlon_tops) >= 4


def test_cap_cone_aabb_and_apex():
    cap = get("tower_cap")
    outer = MODULE_CM
    h = STOREY_CM * _CAP_H_FRAC
    verts, faces = cone_verts(outer, 0.0, h, segments_full=TOWER_ARC_SEGMENTS_FULL)
    assert verts[0] == pytest.approx((0.0, 0.0, h))
    assert len(verts) == TOWER_ARC_SEGMENTS_FULL + 1
    assert len(faces) == TOWER_ARC_SEGMENTS_FULL
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min[0] == pytest.approx(-outer, abs=TOL_CM)
    assert bb_max[0] == pytest.approx(outer, abs=TOL_CM)
    assert bb_min[2] == pytest.approx(0.0, abs=TOL_CM)
    assert bb_max[2] == pytest.approx(h, abs=TOL_CM)
    assert cap.size_cm[2] == pytest.approx(h)


def test_tower_crown_cap_stack_z_offsets():
    """Junction sits on drum top; crown on junction; cap on crown."""
    from pae.plan import plan
    from pae.solver import solve
    from pae.spec import load_style, m3_keep_tower_spec
    from pae.assemble import assemble

    spec = m3_keep_tower_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    towers = [v for v in massing.volumes if v.role == "tower"]
    assert len(towers) == 1
    vol = towers[0]
    drum_top_z = vol.storeys * STOREY_CM
    junction_desc = get("tower_junction")
    crown_desc = get("tower_crown")
    junctions = [p for p in assembly.placements if p.asset_id == "tower_junction"]
    crowns = [p for p in assembly.placements if p.asset_id == "tower_crown"]
    caps = [p for p in assembly.placements if p.asset_id == "tower_cap"]
    assert len(junctions) == 1 and len(crowns) == 1 and len(caps) == 1
    j_z = junctions[0].level * STOREY_CM + junctions[0].offset_cm[2]
    crown_z = crowns[0].level * STOREY_CM + crowns[0].offset_cm[2]
    cap_z = caps[0].level * STOREY_CM + caps[0].offset_cm[2]
    assert j_z == pytest.approx(drum_top_z, abs=1.0)
    assert crown_z == pytest.approx(j_z + junction_desc.size_cm[2], abs=2.0)
    assert cap_z == pytest.approx(crown_z + crown_desc.size_cm[2], abs=2.0)

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
    # Each step = riser box + tread box + a string box down EACH side (4 boxes,
    # 8 verts / 6 faces each). The strings carry the flight; without them the run
    # was treads hanging in mid-air with no visible support.
    boxes_per_step = 4
    assert len(verts) == steps * boxes_per_step * 8
    assert len(faces) == steps * boxes_per_step * 6

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


def test_origin_only_hole_punch_is_half_a_two_bay_run():
    """Ledger F-7 / D-24 broken contract: listing only h.cell punches ~1 module, not 2.

    Fail-closed lock — if someone reverts spanning punch to origin-only, this
    documents why stairs end up buried under half a floor slab.
    """
    from pae.primitives.floors import (
        hole_rects_for_deck_cm,
        hole_rects_merged_for_deck_cm,
    )

    margin = floor_hole_margin_cm()
    origin_only = hole_rects_for_deck_cm((0, 0), [(1, 1)])
    full_run = hole_rects_merged_for_deck_cm((0, 0), [(1, 1), (1, 2)])
    assert len(origin_only) == 1 and len(full_run) == 1
    ox0, oy0, ox1, oy1 = origin_only[0]
    fx0, fy0, fx1, fy1 = full_run[0]
    assert (oy1 - oy0) == pytest.approx(MODULE_CM - 2.0 * margin)
    assert (fy1 - fy0) == pytest.approx(2.0 * MODULE_CM - 2.0 * margin)
    assert (fy1 - fy0) > (oy1 - oy0) * 1.5


def test_spanning_deck_mesh_punches_stair_voids():
    """Upper floor deck must open the FULL stair run — one merged well, no rib."""
    from pae.primitives.floors import (
        hole_rects_merged_for_deck_cm,
        slab_with_rect_holes_verts_faces,
    )

    sx, sy, sz = 4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM
    hole_cells = [(1, 0), (1, 1)]
    rects = hole_rects_merged_for_deck_cm((0, 0), hole_cells)
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    margin = floor_hole_margin_cm()
    assert (x1 - x0) == pytest.approx(MODULE_CM - 2.0 * margin)
    assert (y1 - y0) == pytest.approx(2.0 * MODULE_CM - 2.0 * margin)

    verts, faces = slab_with_rect_holes_verts_faces(sx, sy, sz, rects)
    assert faces
    bb_min, bb_max = mesh_aabb_from_verts(verts)
    assert bb_min == pytest.approx((0.0, 0.0, 0.0), abs=TOL_CM)
    assert bb_max == pytest.approx((sx, sy, sz), abs=TOL_CM)

    # Both VOID bay centres must contain no geometry (full run cleared).
    for j in (0, 1):
        cx = 1.0 * MODULE_CM + 0.5 * MODULE_CM
        cy = j * MODULE_CM + 0.5 * MODULE_CM
        inside = [
            v
            for v in verts
            if abs(v[0] - cx) < (MODULE_CM * 0.5 - margin - 2.0)
            and abs(v[1] - cy) < (MODULE_CM * 0.5 - margin - 2.0)
        ]
        assert inside == [], f"floor geometry left in void bay (1,{j})"


def test_is_spanning_floor_deck_and_hole_rects():
    from pae.assembly_types import SolidPlacement
    from pae.blender_build import is_spanning_floor_deck, spanning_floor_hole_rects_cm

    deck = SolidPlacement(
        piece_id="deck",
        asset_id="floor",
        kind="floor",
        cell=(0, 0),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(4.0 * MODULE_CM, 3.0 * MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )
    assert is_spanning_floor_deck(deck)
    # One spanning 1×2 floor_hole (assemble contract) — not two origin cells.
    holes = [
        SolidPlacement(
            piece_id="span_hole",
            asset_id="floor_hole",
            kind="floor",
            cell=(1, 0),
            level=1,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, 2.0 * MODULE_CM, FLOOR_T_CM),
            tags=frozenset({"floor", "hole"}),
        ),
        SolidPlacement(
            piece_id="other_storey",
            asset_id="floor_hole",
            kind="floor",
            cell=(1, 0),
            level=2,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({"floor", "hole"}),
        ),
    ]
    rects = spanning_floor_hole_rects_cm(deck, holes)
    assert len(rects) == 1
    margin = floor_hole_margin_cm()
    assert rects[0][0] == pytest.approx(MODULE_CM + margin)
    assert rects[0][3] - rects[0][1] == pytest.approx(2.0 * MODULE_CM - 2.0 * margin)


def test_m2_spanning_deck_punch_clears_full_stair_run():
    """Live M2 contract: hole size is 1×2 but origin-only punch was ~1×1 (F-7)."""
    from pae.blender_build import is_spanning_floor_deck, spanning_floor_hole_rects_cm
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec
    from pae.trim import covered_cells

    _, _, assembly, _ = run_through_assemble(m2_two_storey_stair_spec())
    stair = next(p for p in assembly.placements if p.kind == "stair")
    holes = [p for p in assembly.placements if p.asset_id == "floor_hole"]
    deck = next(p for p in assembly.placements if is_spanning_floor_deck(p))
    need = covered_cells(stair)
    assert len(need) == 2
    rects = spanning_floor_hole_rects_cm(deck, holes)
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    # Long axis of the well must exceed one module (half-run regression).
    assert max(x1 - x0, y1 - y0) > MODULE_CM
    dx0, dy0 = deck.cell
    for cell in need:
        cx = (cell[0] - dx0) * MODULE_CM + MODULE_CM * 0.5
        cy = (cell[1] - dy0) * MODULE_CM + MODULE_CM * 0.5
        assert any(r[0] < cx < r[2] and r[1] < cy < r[3] for r in rects), cell

"""Unit tests — assembly placement rules (§2.2–2.5, §6)."""

from __future__ import annotations

import pytest

from pae.assemble import _boundary_wall_cells, assemble
from pae.contract import (
    EAVE_OVERHANG_CM,
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    floor_placement_z_cm,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotation_offset_cm,
    wall_run_cell,
)
from pae.plan import plan
from pae.primitives.catalog import get as get_primitive
from pae.primitives.plinth import ground_plinth_span_size_cm
from pae.primitives.roofs import (
    roof_flat_span_size_cm,
    roof_gable_end_size_cm,
    roof_pitched_span_size_cm,
    roof_rise_cm,
)
from pae.solver import solve
from pae.spec import load_style, m1_box_house_spec, m3_keep_tower_spec
from pae.validate import validate


def _m1_assembly():
    spec = m1_box_house_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly, floor_plan


def _assembly_from_spec(spec):
    massing, mreport = solve(spec)
    assert mreport.ok is True, [f.message for f in mreport.failures]
    assert massing is not None
    floor_plan, preport = plan(massing)
    assert preport.ok is True, [f.message for f in preport.failures]
    assert floor_plan is not None
    style, _ = load_style(spec.style)
    assembly, areport = assemble(floor_plan, None, style)
    assert areport.ok is True, [f.message for f in areport.failures]
    return assembly, floor_plan, massing


def test_yaw_offset_table_matches_contract():
    """§2.2 — rotation offsets for min-corner walls."""
    wall = get_primitive("wall_plain")
    sx, sy, _ = wall.size_cm
    assert rotation_offset_cm(0, sx, sy) == (0.0, 0.0)
    assert rotation_offset_cm(90, sx, sy) == (sy, 0.0)
    assert rotation_offset_cm(180, sx, sy) == (sx, sy)
    assert rotation_offset_cm(270, sx, sy) == (0.0, sx)


def test_wall_boundary_cells_east_north_out_by_one():
    """§2.3 — east/north on footprint x1+1 / y1+1 (not on x1/y1)."""
    assert wall_run_cell("east", 0, 0, 3, 2) == (4, 0, 180)
    assert wall_run_cell("north", 0, 0, 3, 2) == (0, 3, 90)

    assembly, _ = _m1_assembly()
    east_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 180}
    north_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 90}
    west_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 0}
    south_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 270}

    # Footprint 0..3 × 0..2 → east column 4, north row 3.
    assert east_cells == {(4, 0), (4, 1), (4, 2)}
    assert north_cells == {(0, 3), (1, 3), (2, 3), (3, 3)}
    assert west_cells == {(0, 0), (0, 1), (0, 2)}
    assert south_cells == {(0, 0), (1, 0), (2, 0), (3, 0)}
    # Regression: must NOT sit on the old too-far-in ring.
    assert (3, 0) not in east_cells
    assert (0, 2) not in north_cells


def test_south_face_has_no_corner_bay_gap():
    """SW corner must have a south wall — omitting it leaves a one-bay hole."""
    assembly, _ = _m1_assembly()
    south = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 270}
    assert (0, 0) in south


def test_floor_covers_full_footprint():
    assembly, _ = _m1_assembly()
    floors = {p.cell for p in assembly.placements if p.kind == "floor"}
    assert floors == {
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 1),
        (2, 2),
        (3, 0),
        (3, 1),
        (3, 2),
    }


def test_floor_and_ground_z_offsets_in_placements():
    """§2.4–2.5 — floor at level_z − FLOOR_T; ground plinth origin from contract."""
    assembly, _ = _m1_assembly()
    floors = [p for p in assembly.placements if p.kind == "floor"]
    grounds = [p for p in assembly.placements if p.kind == "ground"]
    assert floors
    assert grounds
    for f in floors:
        assert f.offset_cm[2] == floor_placement_z_cm(f.level)
    for g in grounds:
        assert g.offset_cm[2] == ground_plinth_z_cm()


def test_ground_plinth_descriptor_and_m1_span():
    """ground_plinth catalog piece + assemble span helper for footprint foundation."""
    plinth = get_primitive("ground_plinth")
    assert plinth.kind == "plinth"
    assert plinth.footprint_modules == (1, 1)
    assert plinth.size_cm == (MODULE_CM, MODULE_CM, FLOOR_T_CM)
    assert ground_plinth_span_size_cm(4, 3) == (
        4 * MODULE_CM,
        3 * MODULE_CM,
        FLOOR_T_CM,
    )

    assembly, _ = _m1_assembly()
    grounds = [p for p in assembly.placements if p.kind == "ground"]
    assert len(grounds) == 1
    assert grounds[0].asset_id == "ground_plinth"
    assert grounds[0].size_cm == ground_plinth_span_size_cm(4, 3)
    assert grounds[0].offset_cm == (0.0, 0.0, ground_plinth_z_cm())


def test_m1_validate_passes():
    """Milestone 1 — full assemble output must satisfy §7 validator."""
    assembly, _ = _m1_assembly()
    _, report = validate(assembly)
    assert report.ok is True, [f.message for f in report.critical]
    assert report.critical == []


def test_m1_east_wall_aabb_on_outer_boundary():
    """East wall thickness tucks under roof: [4*MODULE − WALL_T, 4*MODULE]."""
    assembly, _ = _m1_assembly()
    east = next(p for p in assembly.placements if p.kind == "wall" and p.cell == (4, 1))
    bb_min, bb_max = placement_world_aabb(
        east.cell[0],
        east.cell[1],
        east.level,
        east.yaw,
        east.size_cm,
        east.offset_cm,
    )
    edge = 4 * MODULE_CM
    assert abs(bb_min[0] - (edge - WALL_T_CM)) < 1.0
    assert abs(bb_max[0] - edge) < 1.0
    assert abs(bb_max[2] - STOREY_CM) < 1.0


def test_m1_north_and_east_tuck_under_footprint_roof():
    """North/east thickness under roof; west/south already on the low edges."""
    assembly, _ = _m1_assembly()
    roof = next(p for p in assembly.placements if p.kind == "roof")
    roof_min, roof_max = placement_world_aabb(
        roof.cell[0],
        roof.cell[1],
        roof.level,
        roof.yaw,
        roof.size_cm,
        roof.offset_cm,
    )

    def _aabb(p):
        return placement_world_aabb(
            p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm
        )

    for p in assembly.placements:
        if p.kind != "wall":
            continue
        mn, mx = _aabb(p)
        # Entire wall XY footprint under (or flush with) the roof slab.
        assert mn[0] >= roof_min[0] - 1.0, (p.piece_id, mn, roof_min)
        assert mn[1] >= roof_min[1] - 1.0, (p.piece_id, mn, roof_min)
        assert mx[0] <= roof_max[0] + 1.0, (p.piece_id, mx, roof_max)
        assert mx[1] <= roof_max[1] + 1.0, (p.piece_id, mx, roof_max)

    east = next(p for p in assembly.placements if p.cell == (4, 1) and p.kind == "wall")
    north = next(p for p in assembly.placements if p.cell == (1, 3) and p.kind == "wall")
    e_min, e_max = _aabb(east)
    n_min, n_max = _aabb(north)
    oh = EAVE_OVERHANG_CM
    assert abs(e_max[0] - (roof_max[0] - oh)) < 1.0
    assert abs(n_max[1] - (roof_max[1] - oh)) < 1.0
    assert e_min[0] < roof_max[0] - oh  # thickness inward
    assert n_min[1] < roof_max[1] - oh


def test_m1_outer_wall_faces_inset_from_roof_eaves():
    """Outer wall AABB edges sit inside roof XY by EAVE_OVERHANG on all four faces."""
    assembly, _ = _m1_assembly()
    roof = next(p for p in assembly.placements if p.kind == "roof")
    roof_min, roof_max = placement_world_aabb(
        roof.cell[0], roof.cell[1], roof.level, roof.yaw, roof.size_cm, roof.offset_cm
    )

    def _aabb(p):
        return placement_world_aabb(
            p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm
        )

    tol = 1.0
    oh = EAVE_OVERHANG_CM
    west_x = min(_aabb(p)[0][0] for p in assembly.placements if p.kind == "wall" and p.yaw == 0)
    east_x = max(_aabb(p)[1][0] for p in assembly.placements if p.kind == "wall" and p.yaw == 180)
    south_y = min(_aabb(p)[0][1] for p in assembly.placements if p.kind == "wall" and p.yaw == 270)
    north_y = max(_aabb(p)[1][1] for p in assembly.placements if p.kind == "wall" and p.yaw == 90)

    assert abs(west_x - (roof_min[0] + oh)) < tol
    assert abs(east_x - (roof_max[0] - oh)) < tol
    assert abs(south_y - (roof_min[1] + oh)) < tol
    assert abs(north_y - (roof_max[1] - oh)) < tol


def test_m1_corner_door_south_only_not_west():
    """SW corner door must not boolean-cut both west and south (L-shaped hole)."""
    assembly, _ = _m1_assembly()
    sw = [p for p in assembly.placements if p.kind == "wall" and p.cell == (0, 0)]
    by_yaw = {p.yaw: p.asset_id for p in sw}
    assert by_yaw[270] == "wall_door"
    assert by_yaw[0] == "wall_plain"


def test_m1_window_on_west_not_north_corner():
    """NW window cell (0,2) must not open on the north run at (0,3)."""
    assembly, _ = _m1_assembly()
    north_sw = next(p for p in assembly.placements if p.kind == "wall" and p.cell == (0, 3))
    assert north_sw.asset_id == "wall_plain"
    west_nw = next(p for p in assembly.placements if p.kind == "wall" and p.cell == (0, 2))
    assert west_nw.asset_id == "wall_window"


def test_m1_door_aperture_width_sane():
    """Door opening ~1–1.6 m wide in a 4 m bay — not half the wall missing."""
    from pae.primitives.catalog import get as get_prim

    door = get_prim("wall_door")
    ap = door.aperture
    assert ap is not None
    width_cm = ap.max_cm[1] - ap.min_cm[1]
    assert 100.0 <= width_cm <= 170.0
    assert width_cm <= MODULE_CM * 0.45


def test_boundary_wall_corner_overlap_closes_perimeter():
    """SW corner is on both west and south runs (overlap) so no bay gap."""
    cells = _boundary_wall_cells(0, 0, 3, 2)
    assert (0, 0) in cells["west"]
    assert (0, 0) in cells["south"]
    assert cells["south"] == [(0, 0), (1, 0), (2, 0), (3, 0)]
    # East/north boundary lines are orthogonal — no shared grid cells.
    assert set(cells["east"]).isdisjoint(cells["north"])

    assembly, _ = _m1_assembly()
    # Same footprint cell may host two pieces (west+south at SW) with different yaw.
    pairs = {(p.cell, p.yaw) for p in assembly.placements if p.kind == "wall"}
    assert ((0, 0), 0) in pairs
    assert ((0, 0), 270) in pairs


def test_roof_eave_overhang_visible_on_m1():
    """Flat roof deck extends past outer wall faces by EAVE_OVERHANG_CM."""
    assembly, _ = _m1_assembly()
    roof = next(p for p in assembly.placements if p.kind == "roof")
    roof_min, roof_max = placement_world_aabb(
        roof.cell[0], roof.cell[1], roof.level, roof.yaw, roof.size_cm, roof.offset_cm
    )
    oh = EAVE_OVERHANG_CM
    west_x = min(
        placement_world_aabb(p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm)[0][0]
        for p in assembly.placements
        if p.kind == "wall" and p.yaw == 0
    )
    assert roof_min[0] == pytest.approx(west_x - oh, abs=1.0)
    assert roof_max[0] - roof_min[0] == pytest.approx(4 * MODULE_CM + 2 * oh, abs=1.0)


def test_roof_flat_descriptor_and_m1_span():
    """roof_flat catalog piece + assemble span helper for footprint decks."""
    roof = get_primitive("roof_flat")
    assert roof.kind == "roof"
    assert roof.footprint_modules == (1, 1)
    assert roof.size_cm == (MODULE_CM, MODULE_CM, FLOOR_T_CM)
    oh = EAVE_OVERHANG_CM
    assert roof_flat_span_size_cm(4, 3) == (
        4 * MODULE_CM + 2 * oh,
        3 * MODULE_CM + 2 * oh,
        FLOOR_T_CM,
    )

    assembly, _ = _m1_assembly()
    roofs = [p for p in assembly.placements if p.kind == "roof"]
    assert len(roofs) == 1
    assert roofs[0].asset_id == "roof_flat"
    assert roofs[0].size_cm == roof_flat_span_size_cm(4, 3)
    assert roofs[0].offset_cm[0] == pytest.approx(-oh)
    assert roofs[0].offset_cm[1] == pytest.approx(-oh)
    assert roofs[0].offset_cm[2] == STOREY_CM


def test_pitched_roof_emits_gable_pieces():
    """M3 — roof_kind=pitched must place roof_gable_infill + slope deck bays.

    Historical bug: walls stopped at eaves; nothing filled the gable triangle.
    """
    from pae.spec import BuildingSpec, FootprintSpec, OpeningPolicy, RoofSpec
    from pae.spec import CirculationSpec

    spec = BuildingSpec(
        name="m3_pitched_only",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=1, windows_ground=2),
        seed=31,
        ground_slab=True,
    )
    assembly, _, _ = _assembly_from_spec(spec)
    roofs = [p for p in assembly.placements if p.kind == "roof"]
    assert roofs, "pitched roof produced no roof placements"
    gables = [p for p in roofs if p.asset_id == "roof_gable_infill"]
    slopes = [p for p in roofs if p.asset_id == "roof_pitched_slope"]
    assert len(gables) >= 1, "expected ≥1 gable infill piece"
    assert all("gable" in p.tags for p in gables)
    assert slopes, "expected interior slope deck pieces"
    assert all(p.asset_id != "roof_flat" for p in roofs)
    # Gable infill height includes pitch rise (not a flat slab).
    pitch = 0.9
    rise = roof_rise_cm(pitch, 3 * MODULE_CM)
    span_x = 4 * MODULE_CM
    span_y = 3 * MODULE_CM
    oh = EAVE_OVERHANG_CM
    gable_h = rise + FLOOR_T_CM
    assert gables[0].size_cm[2] == pytest.approx(gable_h)
    assert gables[0].size_cm == roof_gable_end_size_cm(
        ridge_along_x=True,
        span_x_cm=span_x,
        span_y_cm=span_y,
        gable_height=gable_h,
    )
    # 4×3 footprint: ridge along X → 2 gable end caps (span full Y), 1 A-frame deck.
    assert len(gables) == 2
    assert len(slopes) == 1
    deck_x, deck_y = roof_pitched_span_size_cm(span_x, span_y)
    assert slopes[0].size_cm == (deck_x, deck_y, gable_h)
    assert slopes[0].offset_cm[0] == pytest.approx(-oh)
    assert slopes[0].offset_cm[1] == pytest.approx(-oh)
    gable_x = {p.cell[0] for p in gables}
    assert gable_x == {0, 3}


def test_m3_pitched_validate_passes():
    """M3 pitched-only spec must validate with no critical defects."""
    from pae.pipeline import run_through_assemble
    from pae.spec import BuildingSpec, CirculationSpec, FootprintSpec, OpeningPolicy, RoofSpec

    spec = BuildingSpec(
        name="m3_pitched_only",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(doors_ground=1, windows_ground=2),
        seed=31,
        ground_slab=True,
    )
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True
    _, report = validate(assembly)
    assert report.ok is True, [f.message for f in report.critical]
    assert report.critical == []


def _hall_footprint_bbox_cm(massing):
    """Axis-aligned hall envelope (main/wing floor cells) in world cm."""
    mains = [v for v in massing.volumes if v.role in ("main", "wing")]
    assert mains
    x0 = min(v.x0 for v in mains)
    y0 = min(v.y0 for v in mains)
    x1 = max(v.x1 for v in mains)
    y1 = max(v.y1 for v in mains)
    return (
        (x0 * MODULE_CM, y0 * MODULE_CM),
        ((x1 + 1) * MODULE_CM, (y1 + 1) * MODULE_CM),
    )


def _tower_drum_center_cm(assembly, *, level: int = 0) -> tuple[float, float]:
    arcs = [
        p
        for p in assembly.placements
        if p.asset_id == "tower_arc_quarter" and p.level == level
    ]
    assert arcs
    p = arcs[0]
    return (
        p.cell[0] * MODULE_CM + p.offset_cm[0],
        p.cell[1] * MODULE_CM + p.offset_cm[1],
    )


def _on_hall_exterior(
    center: tuple[float, float],
    hall_min: tuple[float, float],
    hall_max: tuple[float, float],
    *,
    tol: float = TOL_CM,
) -> bool:
    """Centre is outside the open hall interior or on the footprint bbox shell."""
    cx, cy = center
    hx0, hy0 = hall_min
    hx1, hy1 = hall_max
    inside_x = hx0 - tol < cx < hx1 + tol
    inside_y = hy0 - tol < cy < hy1 + tol
    if inside_x and inside_y:
        return False
    on_shell = (
        abs(cx - hx0) <= tol
        or abs(cx - hx1) <= tol
        or abs(cy - hy0) <= tol
        or abs(cy - hy1) <= tol
    )
    return on_shell or not (inside_x and inside_y)


def test_m3_tower_arcs_same_cell():
    """M3 — 4× tower_arc_quarter share one cell; rotates_about_center; shared XY offset.

    Historical bug: quarters offset to four cells → no curved wall.
    """
    assembly, _, massing = _assembly_from_spec(m3_keep_tower_spec())
    towers = [v for v in massing.volumes if v.role == "tower"]
    assert len(towers) == 1
    tower_cell = (towers[0].x0, towers[0].y0)
    arcs = [p for p in assembly.placements if p.asset_id == "tower_arc_quarter"]
    assert arcs, "no tower_arc_quarter placements"
    # All quarters at the SAME cell (no 4-cell scatter).
    assert {p.cell for p in arcs} == {tower_cell}
    assert all(p.rotates_about_center is True for p in arcs)
    offsets = {(p.offset_cm[0], p.offset_cm[1]) for p in arcs}
    assert len(offsets) == 1, "all quarters share one drum-centre offset"
    # Four yaws per tower storey.
    for level in range(towers[0].storeys):
        level_arcs = [p for p in arcs if p.level == level]
        assert {p.yaw for p in level_arcs} == {0, 90, 180, 270}
        assert len(level_arcs) == 4
    assert len(arcs) == 4 * towers[0].storeys
    # Crown + cap present on the drum.
    assert any(p.asset_id == "tower_crown" for p in assembly.placements)
    assert any(p.asset_id == "tower_cap" for p in assembly.placements)


def test_m3_tower_drum_outside_hall_footprint():
    """M3 drum centre clears the hall bbox; east drum edge kisses west wall."""
    assembly, _, massing = _assembly_from_spec(m3_keep_tower_spec())
    hall_min, hall_max = _hall_footprint_bbox_cm(massing)
    center = _tower_drum_center_cm(assembly)
    assert _on_hall_exterior(center, hall_min, hall_max)
    r = MODULE_CM
    cx, cy = center
    # West tower: drum east AABB edge kisses hall west face (x = hall_min.x).
    assert cx + r == pytest.approx(hall_min[0], abs=TOL_CM)
    assert cy == pytest.approx(200.0, abs=TOL_CM)


def test_m3_tower_touches_hall_after_drum_offset():
    """M3 tower stack must stay in the structural touch graph after drum offset."""
    from pae.validate import _placement_aabb, aabb_intersects

    assembly, _, massing = _assembly_from_spec(m3_keep_tower_spec())
    _, report = validate(assembly)
    assert not any(f.check == "freestanding" for f in report.critical)

    hall_min, hall_max = _hall_footprint_bbox_cm(massing)
    center = _tower_drum_center_cm(assembly)
    r = MODULE_CM
    cx, cy = center
    assert cx + r == pytest.approx(hall_min[0], abs=TOL_CM)

    tower_pieces = [
        p
        for p in assembly.placements
        if p.asset_id.startswith("tower_") or p.kind in ("tower_arc", "tower_crown", "tower_cap")
    ]
    envelope = [
        p
        for p in assembly.placements
        if p.kind in ("wall", "floor", "ground", "roof", "battlement")
        or (p.kind == "barrier" and "parapet" in p.tags)
    ]
    assert tower_pieces and envelope
    connected = False
    for tp in tower_pieces:
        tbb = _placement_aabb(tp)
        for ep in envelope:
            if aabb_intersects(tbb[0], tbb[1], *_placement_aabb(ep)):
                connected = True
                break
        if connected:
            break
    assert connected, "tower pieces must AABB-touch hall envelope after drum offset"


def _hall_tower_xy_union_cm(assembly, massing) -> tuple[tuple[float, float], tuple[float, float]]:
    """Axis-aligned XY union of hall footprint and tower drum (M3 gallery floater probe)."""
    hall_min, hall_max = _hall_footprint_bbox_cm(massing)
    cx, cy = _tower_drum_center_cm(assembly)
    r = MODULE_CM
    union_min = (min(hall_min[0], cx - r), min(hall_min[1], cy - r))
    union_max = (max(hall_max[0], cx + r), max(hall_max[1], cy + r))
    return union_min, union_max


def _placement_xy_center_cm(p) -> tuple[float, float]:
    mn, mx = placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=getattr(p, "rotates_about_center", False),
    )
    return ((mn[0] + mx[0]) * 0.5, (mn[1] + mx[1]) * 0.5)


def test_m3_no_disconnected_ground_plinth_far_from_hall_tower_union():
    """M3 — one hall-spanning ground slab; no orphan at tower grid cell."""
    assembly, _, massing = _assembly_from_spec(m3_keep_tower_spec())
    union_min, union_max = _hall_tower_xy_union_cm(assembly, massing)
    margin = TOL_CM

    grounds = [p for p in assembly.placements if p.kind == "ground"]
    assert len(grounds) == 1, "hall footprint gets one spanning ground slab"
    assert grounds[0].size_cm == ground_plinth_span_size_cm(4, 4)

    for p in grounds:
        cx, cy = _placement_xy_center_cm(p)
        assert union_min[0] - margin <= cx <= union_max[0] + margin
        assert union_min[1] - margin <= cy <= union_max[1] + margin

    tower_cell = next(v for v in massing.volumes if v.role == "tower")
    tc = (tower_cell.x0, tower_cell.y0)
    assert not any(p.cell == tc for p in grounds)
    assert not any(
        p.kind == "floor" and p.level == 0 and p.cell == tc
        for p in assembly.placements
    )
    assert not any(
        p.kind == "floor" and p.level == 0 and p.cell == tc
        for p in assembly.placements
    )

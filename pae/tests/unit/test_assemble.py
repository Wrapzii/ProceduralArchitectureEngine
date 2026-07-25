"""Unit tests — assembly placement rules (§2.2–2.5, §6)."""

from __future__ import annotations

from pae.assemble import _boundary_wall_cells, assemble
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    floor_placement_z_cm,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotation_offset_cm,
    wall_run_cell,
)
from pae.plan import plan
from pae.primitives.catalog import get as get_primitive
from pae.primitives.roofs import roof_flat_span_size_cm
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
    assert south_cells == {(1, 0), (2, 0), (3, 0)}
    # Regression: must NOT sit on the old too-far-in ring.
    assert (3, 0) not in east_cells
    assert (0, 2) not in north_cells


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


def test_m1_validate_passes():
    """Milestone 1 — full assemble output must satisfy §7 validator."""
    assembly, _ = _m1_assembly()
    _, report = validate(assembly)
    assert report.ok is True, [f.message for f in report.critical]
    assert report.critical == []


def test_m1_east_wall_aabb_on_outer_boundary():
    """East wall outer strip sits on x = (x1+1)*MODULE = 4*MODULE."""
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
    # After §2.2 offset, yaw-180 wall occupies [4*MODULE, 4*MODULE+WALL_T] in X…
    # actually low-X strip after 180+offset lands with min at 4*MODULE.
    assert abs(bb_min[0] - 4 * MODULE_CM) < 1.0
    assert abs(bb_max[0] - (4 * MODULE_CM + WALL_T_CM)) < 1.0
    assert abs(bb_max[2] - STOREY_CM) < 1.0


def test_boundary_wall_corner_ownership_no_duplicate_cells():
    """Each wall grid cell appears at most once — SW corner owned by west."""
    cells = _boundary_wall_cells(0, 0, 3, 2)
    assert (0, 0) in cells["west"]
    assert (0, 0) not in cells["south"]
    assert cells["south"] == [(1, 0), (2, 0), (3, 0)]
    # East/north boundary lines are orthogonal — no shared grid cells.
    assert set(cells["east"]).isdisjoint(cells["north"])

    assembly, _ = _m1_assembly()
    wall_cells = [p.cell for p in assembly.placements if p.kind == "wall"]
    assert len(wall_cells) == len(set(wall_cells))


def test_roof_flat_descriptor_and_m1_span():
    """roof_flat catalog piece + assemble span helper for footprint decks."""
    roof = get_primitive("roof_flat")
    assert roof.kind == "roof"
    assert roof.footprint_modules == (1, 1)
    assert roof.size_cm == roof_flat_span_size_cm(1, 1)
    assert roof_flat_span_size_cm(4, 3) == (4 * MODULE_CM, 3 * MODULE_CM, FLOOR_T_CM)

    assembly, _ = _m1_assembly()
    roofs = [p for p in assembly.placements if p.kind == "roof"]
    assert len(roofs) == 1
    assert roofs[0].asset_id == "roof_flat"
    assert roofs[0].size_cm == roof_flat_span_size_cm(4, 3)
    assert roofs[0].offset_cm[2] == STOREY_CM


def test_pitched_roof_emits_gable_pieces():
    """M3 — roof_kind=pitched must place roof_pitched_gable (gable infill).

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
    assert all(p.asset_id == "roof_pitched_gable" for p in roofs)
    assert all("gable" in p.tags for p in roofs)
    assert all(p.asset_id != "roof_flat" for p in roofs)
    # One bay per enclosed footprint cell (4×3).
    assert len(roofs) == 12


def test_tower_arc_quarters_same_cell_no_scatter():
    """M3 — 4× tower_arc_quarter share one cell; rotates_about_center; XY offset 0.

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
    assert all(p.offset_cm[0] == 0.0 and p.offset_cm[1] == 0.0 for p in arcs)
    # Four yaws per tower storey.
    for level in range(towers[0].storeys):
        level_arcs = [p for p in arcs if p.level == level]
        assert {p.yaw for p in level_arcs} == {0, 90, 180, 270}
        assert len(level_arcs) == 4
    assert len(arcs) == 4 * towers[0].storeys
    # Crown + cap present on the drum.
    assert any(p.asset_id == "tower_crown" for p in assembly.placements)
    assert any(p.asset_id == "tower_cap" for p in assembly.placements)
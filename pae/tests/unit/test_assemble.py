"""Unit tests — assembly placement rules (§2.2–2.5, §6)."""

from __future__ import annotations

from pae.assemble import assemble
from pae.contract import (
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
from pae.solver import solve
from pae.spec import load_style, m1_box_house_spec
from pae.validate import validate


def _m1_assembly():
    spec = m1_box_house_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly, floor_plan


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

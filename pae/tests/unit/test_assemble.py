"""Unit tests — assembly placement rules (§2.2–2.5, §6)."""

from __future__ import annotations

from pae.assemble import assemble
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


def test_wall_boundary_cells_east_north():
    """§2.3 — east/north runs on interior x1+1 / y1+1 boundary-line cells."""
    # Interior x=1..2, y=1 → east column 3, north row 2 (not footprint x1/y1).
    assert wall_run_cell("east", 1, 1, 2, 1) == (3, 1, 180)
    assert wall_run_cell("north", 1, 1, 2, 1) == (1, 2, 90)

    assembly, _ = _m1_assembly()
    east_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 180}
    north_cells = {p.cell for p in assembly.placements if p.kind == "wall" and p.yaw == 90}
    assert (3, 0) in east_cells
    assert (3, 1) in east_cells
    assert (3, 2) in east_cells
    assert (2, 3) not in east_cells  # footprint x1, not east boundary
    assert (0, 2) in north_cells
    assert (1, 2) in north_cells
    assert (0, 1) not in north_cells  # interior row, not north boundary


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


def test_m1_wall_aabb_touches_boundary():
    """East wall AABB sits on interior x1+1 module line (cell x=3)."""
    assembly, _ = _m1_assembly()
    east = next(p for p in assembly.placements if p.kind == "wall" and p.cell == (3, 1))
    bb_min, bb_max = placement_world_aabb(
        east.cell[0],
        east.cell[1],
        east.level,
        east.yaw,
        east.size_cm,
        east.offset_cm,
    )
    assert abs(bb_min[0] - 3 * MODULE_CM) < 1.0
    assert abs(bb_max[0] - (3 * MODULE_CM + WALL_T_CM)) < 1.0
    assert abs(bb_max[2] - STOREY_CM) < 1.0

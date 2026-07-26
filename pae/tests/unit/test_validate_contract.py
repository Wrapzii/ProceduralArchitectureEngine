"""Contract geometry helpers used by validate."""

import re
from pathlib import Path

from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    aabb_overlap,
    cell_to_world_cm,
    floor_placement_z_cm,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotate_local_xy,
    rotation_offset_cm,
    storey_datum_z_cm,
    wall_run_cell,
)


def test_cell_to_world():
    assert cell_to_world_cm(2, 3, 1) == (
        2 * MODULE_CM,
        3 * MODULE_CM,
        STOREY_CM,
    )


def test_wall_run_cell_east_north_boundary():
    assert wall_run_cell("east", 0, 0, 3, 2) == (4, 0, 180)
    assert wall_run_cell("north", 0, 0, 3, 2) == (0, 3, 90)


def test_floor_and_ground_z():
    assert floor_placement_z_cm(1) == STOREY_CM - FLOOR_T_CM
    assert ground_plinth_z_cm() == -2.0 * FLOOR_T_CM


def test_storey_datum_accessor_matches_legacy():
    assert storey_datum_z_cm(0) == 0.0
    assert storey_datum_z_cm(2) == 2 * STOREY_CM
    assert floor_placement_z_cm(1) == storey_datum_z_cm(1) - FLOOR_T_CM
    assert cell_to_world_cm(0, 0, 3)[2] == storey_datum_z_cm(3)
    half = STOREY_CM * 0.5
    assert floor_placement_z_cm(1, datum_offset_cm=half) == (
        storey_datum_z_cm(1, datum_offset_cm=half) - FLOOR_T_CM
    )


_HARDCODED_DATUM_Z = re.compile(
    r"(?<![\w.])\w+\.level\s*\*\s*STOREY_CM|(?<![\w.])level\s*\*\s*STOREY_CM"
)


def test_no_hardcoded_level_times_storey_cm_outside_accessor():
    """Datum Z must route through storey_datum_z_cm (Roadmap 10.6 prep)."""
    root = Path(__file__).resolve().parents[3]
    pae = root / "pae"
    offenders: list[str] = []
    for path in sorted(pae.rglob("*.py")):
        if path.name == "contract.py":
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if _HARDCODED_DATUM_Z.search(line):
                offenders.append(f"{path.relative_to(root)}:{i}: {line.strip()}")
    assert not offenders, "hardcoded datum Z:\n" + "\n".join(offenders)


def test_rotate_local_xy_table():
    """Pure yaw about min-corner — compensation lives in rotation_offset_cm."""
    sx, sy = WALL_T_CM, MODULE_CM
    assert rotate_local_xy(0, 0, 0, sx, sy) == (0.0, 0.0)
    assert rotate_local_xy(0, 0, 90, sx, sy) == (0.0, 0.0)
    assert rotate_local_xy(sx, 0, 90, sx, sy) == (0.0, sx)
    assert rotate_local_xy(0, sy, 90, sx, sy) == (-sy, 0.0)
    assert rotate_local_xy(sx, sy, 180, sx, sy) == (-sx, -sy)
    # Placement origin + offset must bring yaw-90 back into the cell.
    assert rotation_offset_cm(90, sx, sy) == (sy, 0.0)


def test_aabb_overlap_requires_all_axes():
    span = MODULE_CM
    a = ((0, 0, 0), (span, span, span))
    b_touch = ((span, 0, 0), (2 * span, span, span))
    b_overlap = ((span / 2, span / 2, span / 2), (1.5 * span, 1.5 * span, 1.5 * span))
    assert not aabb_overlap(*a, *b_touch)
    assert aabb_overlap(*a, *b_overlap)


def test_placement_world_aabb_yaw0():
    bb_min, bb_max = placement_world_aabb(
        1,
        2,
        0,
        0,
        (WALL_T_CM, MODULE_CM, STOREY_CM),
        rotation_offset_cm(0, WALL_T_CM, MODULE_CM) + (0.0,),
    )
    assert bb_min[0] == MODULE_CM
    assert bb_max[1] - bb_min[1] == MODULE_CM

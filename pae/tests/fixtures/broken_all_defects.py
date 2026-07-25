"""Deliberately broken assembly — one instance of each §7 defect class.

Used test-first by WP-1 validator tests.
"""

from __future__ import annotations

from pae.assembly_types import (
    Aperture,
    Assembly,
    CirculationEdge,
    FloorPlanLayer,
    SolidPlacement,
    StyleAperturePolicy,
    WallRun,
)
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    floor_placement_z_cm,
    rotation_offset_cm,
)
from pae.plan import CellRole

# --- fixture layout (4 × 3 module footprint, 2 storeys) ---------------------
# World cells: x=0..3, y=0..2.  Interior at (1,1) and (2,1).  Origin cell (0,0).

_ORIGIN = (0, 0)
_WIDTH = 4
_HEIGHT = 3


def _wall_size() -> tuple[float, float, float]:
    return (WALL_T_CM, MODULE_CM, STOREY_CM)


def _floor_size() -> tuple[float, float, float]:
    return (MODULE_CM, MODULE_CM, FLOOR_T_CM)


def _wall_offset(yaw: int) -> tuple[float, float, float]:
    sx, sy, _ = _wall_size()
    ox, oy = rotation_offset_cm(yaw, sx, sy)
    return (ox, oy, 0.0)


def make_broken_assembly() -> Assembly:
    """Assembly containing every validator defect class (§7.1–§7.9)."""
    floor_plan_l0 = FloorPlanLayer(
        level=0,
        width=_WIDTH,
        height=_HEIGHT,
        origin_cell=_ORIGIN,
        cells=[
            [
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
            ],
            [
                CellRole.EXTERIOR,
                CellRole.INTERIOR,
                CellRole.INTERIOR,
                CellRole.EXTERIOR,
            ],
            [
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
                CellRole.EXTERIOR,
            ],
        ],
    )
    floor_plan_l1 = FloorPlanLayer(
        level=1,
        width=_WIDTH,
        height=_HEIGHT,
        origin_cell=_ORIGIN,
        cells=[
            [CellRole.EXTERIOR] * _WIDTH,
            [CellRole.EXTERIOR, CellRole.INTERIOR, CellRole.VOID, CellRole.EXTERIOR],
            [CellRole.EXTERIOR] * _WIDTH,
        ],
    )

    placements: list[SolidPlacement] = []

    # §7.1 — isolated wall with dangling ends (away from main envelope)
    placements.append(
        SolidPlacement(
            piece_id="wall_dangle",
            asset_id="wall_plain",
            kind="wall",
            cell=(5, 1),
            level=0,
            yaw=0,
            offset_cm=_wall_offset(0),
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )

    # §7.2 — floater (no slab beneath)
    placements.append(
        SolidPlacement(
            piece_id="prop_float",
            asset_id="prop_brazier",
            kind="prop",
            cell=(1, 1),
            level=1,
            yaw=0,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(80.0, 80.0, 120.0),
        )
    )

    # §7.3 — collinear gap ≈ 3 m between two segments on y=0 plane
    gap_extra = MODULE_CM - 100.0  # 300 cm between module-aligned segments
    off_a = _wall_offset(90)
    off_b = (
        off_a[0] + gap_extra,
        off_a[1],
        off_a[2],
    )
    placements.append(
        SolidPlacement(
            piece_id="wall_gap_a",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=90,
            offset_cm=off_a,
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )
    placements.append(
        SolidPlacement(
            piece_id="wall_gap_b",
            asset_id="wall_plain",
            kind="wall",
            cell=(1, 0),
            level=0,
            yaw=90,
            offset_cm=off_b,
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )

    # §7.4 — interpenetrating floor slabs (same cell)
    floor_z = floor_placement_z_cm(0)
    for pid in ("floor_overlap_a", "floor_overlap_b"):
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id="floor_slab",
                kind="floor",
                cell=(1, 1),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, floor_z),
                size_cm=_floor_size(),
            )
        )

    # Perimeter walls partially closing envelope — north row missing at x=1 (§7.5 leak)
    placements.append(
        SolidPlacement(
            piece_id="wall_south",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=270,
            offset_cm=_wall_offset(270),
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )
    placements.append(
        SolidPlacement(
            piece_id="wall_west",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 1),
            level=0,
            yaw=0,
            offset_cm=_wall_offset(0),
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )
    placements.append(
        SolidPlacement(
            piece_id="wall_east",
            asset_id="wall_plain",
            kind="wall",
            cell=(3, 1),
            level=0,
            yaw=180,
            offset_cm=_wall_offset(180),
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )
    # north wall only at x=2 — gap at x=1 lets flood in (§7.5)
    placements.append(
        SolidPlacement(
            piece_id="wall_north_partial",
            asset_id="wall_plain",
            kind="wall",
            cell=(2, 2),
            level=0,
            yaw=90,
            offset_cm=_wall_offset(90),
            size_cm=_wall_size(),
            tags=frozenset({"wall"}),
        )
    )

    # Floor under (1,1) only — (2,1) interior lacks slab (§7.6)
    placements.append(
        SolidPlacement(
            piece_id="floor_partial",
            asset_id="floor_slab",
            kind="floor",
            cell=(1, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, floor_z),
            size_cm=_floor_size(),
        )
    )

    # §7.8 — run length 576 cm → 176 cm leftover (400 + 176)
    leftover_cm = MODULE_CM - (MODULE_CM - 176.0)  # 176.0
    run_length = MODULE_CM + leftover_cm
    wall_runs = [
        WallRun(
            run_id="run_bad_fit",
            level=0,
            axis="y",
            plane_cm=0.0,
            piece_ids=["wall_gap_a"],
            start_cm=0.0,
            end_cm=run_length,
        )
    ]

    # §7.7 — storey 1 unreachable (stair only self-loop on ground)
    circulation = [
        CirculationEdge(piece_id="stair_ground_only", from_level=0, to_level=0),
    ]

    # §7.7b — stair with no floor_hole above → exit blocked (ceiling not opened)
    # Keep off (1,1) so this does not support prop_float or fix floor_coverage.
    placements.append(
        SolidPlacement(
            piece_id="stair_blocked_top",
            asset_id="stair_straight",
            kind="stair",
            cell=(2, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({"stair"}),
        )
    )

    floor_z_l0 = 0.0
    apertures = [
        # §7.9 — window sill at floor
        Aperture(
            piece_id="win_bad_sill",
            kind="window",
            wall_piece_id="wall_west",
            level=0,
            sill_z_cm=floor_z_l0,
            floor_z_cm=floor_z_l0,
            interior_cell=(1, 1),
            exterior_cell=(0, 1),
            world_xyz=(MODULE_CM, MODULE_CM + MODULE_CM * 0.5, floor_z_l0),
        ),
        # §7.9 — door opens to non-walkable exterior cell (interior courtyard)
        Aperture(
            piece_id="door_bad_exit",
            kind="door",
            wall_piece_id="wall_dangle",
            level=0,
            sill_z_cm=floor_z_l0,
            floor_z_cm=floor_z_l0,
            interior_cell=(2, 1),
            exterior_cell=(2, 1),
            world_xyz=(3 * MODULE_CM, MODULE_CM * 1.5, floor_z_l0),
        ),
    ]

    return Assembly(
        placements=placements,
        floor_plan={0: floor_plan_l0, 1: floor_plan_l1},
        circulation=circulation,
        wall_runs=wall_runs,
        apertures=apertures,
        storeys=2,
        aperture_policy=StyleAperturePolicy(),
    )


# Expected defect checks for assertions in tests.
EXPECTED_CHECKS = frozenset(
    {
        "end_connectivity",
        "vertical_support",
        "collinear_gap",
        "interpenetration",
        "enclosure",
        "floor_coverage",
        "stair_reachability",
        "stair_exit_clearance",
        "run_fit",
        "aperture_sanity",
    }
)

"""Engineering continuity — wall runs, wall-head bearing, tower↔hall kiss.

Test-first poisoned fixtures (Handbook §6). Variation may restyle pieces inside a
kind; connection / support / exclusion must still hold (Handbook § variation vs
continuity).
"""

from __future__ import annotations

from dataclasses import replace

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    rotation_offset_cm,
)
from pae.pipeline import run_through_assemble
from pae.spec import m1_box_house_spec, m3_keep_tower_spec
from pae.validate import (
    _check_collinear_gaps,
    _check_tower_hall_kiss,
    validate,
)


def _wall(
    pid: str,
    cell: tuple[int, int],
    yaw: int,
    *,
    ox: float = 0.0,
    oy: float = 0.0,
) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    rx, ry = rotation_offset_cm(yaw, sx, sy)
    return SolidPlacement(
        piece_id=pid,
        asset_id="wall_plain",
        kind="wall",
        cell=cell,
        level=0,
        yaw=yaw,
        offset_cm=(rx + ox, ry + oy, 0.0),
        size_cm=(sx, sy, sz),
        tags=frozenset({"wall"}),
    )


# --- wall-run continuity -----------------------------------------------------


def test_collinear_gap_within_tol_plane_offset_is_reported():
    """False-negative audit: same face, plane offset ≤ TOL, span gap > TOL.

    Exact ``round(plane, 3)`` bucketing used to miss this (planes 0 vs 4).
    """
    a = _wall("gap_a", (0, 0), 90)
    b = _wall("gap_b", (1, 0), 90, ox=50.0, oy=4.0)
    asm = Assembly(placements=[a, b], storeys=1)
    gaps = _check_collinear_gaps(asm)
    assert gaps, "collinear gap across within-TOL plane offset not reported"
    assert "50.0" in gaps[0].message or "50" in gaps[0].message
    assert gaps[0].world_xyz is not None


def test_dangling_end_not_rescued_by_prop():
    """end_connectivity must require structure — a prop at the tip is not a joint."""
    wall = _wall("dangle", (8, 8), 0)
    prop = SolidPlacement(
        piece_id="prop_tip",
        asset_id="prop_brazier",
        kind="prop",
        cell=(8, 8),
        level=0,
        yaw=0,
        # Sit on the +Y end probe of a yaw-0 wall (long axis Y).
        offset_cm=(WALL_T_CM * 0.25, MODULE_CM + 1.0, STOREY_CM * 0.25),
        size_cm=(40.0, 40.0, 80.0),
    )
    # No ground slab — a cell-sized ground AABB would kiss both wall ends and
    # mask the defect under test.
    asm = Assembly(placements=[wall, prop], storeys=1)
    _, report = validate(asm)
    dangling = [f for f in report.critical if f.check == "end_connectivity"]
    assert dangling, "prop must not satisfy end_connectivity"
    assert any(f.piece_id == "dangle" for f in dangling)


# --- tower ↔ hall kiss -------------------------------------------------------


def test_attached_tower_passes_hall_kiss():
    """M3 wall-attached drum AABB kisses the hall within TOL."""
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    kisses = _check_tower_hall_kiss(assembly)
    assert kisses == [], [f.message for f in kisses]
    _, report = validate(assembly)
    assert not any(f.check == "tower_hall_kiss" for f in report.critical)


def test_freestanding_tower_fails_hall_kiss():
    """Poison: shift every tower solid away from the hall — kiss must go critical."""
    _, _, base, _ = run_through_assemble(m3_keep_tower_spec())
    # M3 tower attaches on the west face at cell (-1, 0) — detach = shift west (-X).
    shift = -MODULE_CM * 6.0
    poisoned = []
    for p in base.placements:
        if p.kind in ("tower_arc", "tower_crown", "tower_cap") or "tower" in p.tags:
            ox, oy, oz = p.offset_cm
            poisoned.append(replace(p, offset_cm=(ox + shift, oy, oz)))
        else:
            poisoned.append(p)
    asm = Assembly(
        placements=poisoned,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    _, report = validate(asm)
    kisses = [f for f in report.critical if f.check == "tower_hall_kiss"]
    assert kisses, "freestanding drum must fail tower_hall_kiss"
    assert all(f.world_xyz is not None for f in kisses)


# --- wall-head bearing (roof / parapet) --------------------------------------


def test_roof_on_posts_only_fails_bearing():
    """Roof borne only by a pier fails roof_bears_on_wall (VAL_ROOF) / continuity."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    pier = SolidPlacement(
        piece_id="pier_only",
        asset_id="pier_square",
        kind="column",
        cell=(20, 20),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, WALL_T_CM, STOREY_CM),
    )
    roof = SolidPlacement(
        piece_id="roof_posts",
        asset_id="roof_flat",
        kind="roof",
        cell=(20, 20),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, STOREY_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
    )
    asm = Assembly(
        placements=list(base.placements) + [pier, roof],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
    )
    _, report = validate(asm)
    bearing = [
        f
        for f in report.critical
        if f.check == "roof_bears_on_wall" and f.piece_id == "roof_posts"
    ]
    assert bearing, "roof on posts must fail roof_bears_on_wall"


def test_m1_roof_passes_bearing_checks():
    """Happy M1 roof sits on perimeter wall heads — no roof/parapet bearing failure."""
    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    _, report = validate(assembly)
    bearing = [
        f
        for f in report.critical
        if f.check in ("roof_bears_on_wall", "vertical_support")
        and ("bear" in f.message or "wall-head" in f.message)
    ]
    assert bearing == []


def test_parapet_on_prop_fails_wall_head_bearing():
    """Parapet must rest on a wall/roof head, not a decorative prop."""
    prop = SolidPlacement(
        piece_id="prop_block",
        asset_id="prop_brazier",
        kind="prop",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM * 0.5, MODULE_CM * 0.5, STOREY_CM),
    )
    parapet = SolidPlacement(
        piece_id="para_float",
        asset_id="parapet_solid",
        kind="barrier",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, STOREY_CM),
        size_cm=(MODULE_CM, WALL_T_CM * 0.5, WALL_T_CM),
        tags=frozenset({"parapet", "exterior", "roof_edge"}),
    )
    ground = SolidPlacement(
        piece_id="g0",
        asset_id="ground",
        kind="ground",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
    )
    asm = Assembly(placements=[prop, parapet, ground], storeys=1)
    _, report = validate(asm)
    bearing = [
        f
        for f in report.critical
        if f.check == "vertical_support" and "wall-head bearing" in f.message
    ]
    assert bearing, "parapet on prop must fail wall-head bearing"
    assert bearing[0].piece_id == "para_float"
    assert bearing[0].world_xyz is not None

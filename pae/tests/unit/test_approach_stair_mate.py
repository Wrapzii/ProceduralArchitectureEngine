"""Approach stair mate + alignment — broken fixtures first (Handbook §11b).

User: 9 scattered ``steps_grand`` (3×3 causeway grid), tops at 175 cm while L0
floor / gate sill is z≈0; misaligned with twin gate arches.
"""

from __future__ import annotations

from dataclasses import replace

from pae.approach_stairs import (
    CHECK_APPROACH_STAIR_ALIGNED_TO_GATE,
    CHECK_APPROACH_STAIR_HEIGHT_MATE,
    check_approach_stair_aligned_to_gate,
    check_approach_stair_height_mate,
    expected_flank_cells,
    mated_step_pose,
    plan_gate_approach_steps,
    repair_approach_stairs,
    resolve_approach_mate_z,
)
from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_fortress_compound
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM, placement_world_aabb
from pae.existence import entrance_role_tag
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import catalog_by_id
from pae.spec import castle_gatehouse_spec, fortress_gatehouse_spec
from pae.trim import TrimOptions, trim
from pae.validate import validate, _check_stair_flight_stack


def _gate_wall(
    pid: str,
    cell: tuple[int, int],
    *,
    asset_id: str = "wall_gate_arch_grand",
    yaw: int = 270,
) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    from pae.contract import rotation_offset_cm

    rx, ry = rotation_offset_cm(yaw, sx, sy)
    return SolidPlacement(
        piece_id=pid,
        asset_id=asset_id,
        kind="wall",
        cell=cell,
        level=0,
        yaw=yaw,
        offset_cm=(rx, ry, 0.0),
        size_cm=(sx, sy, sz),
        tags=frozenset({"wall", "gate", entrance_role_tag("gate"), "gatehouse"}),
    )


def _floor_at_gate(cell: tuple[int, int]) -> SolidPlacement:
    return SolidPlacement(
        piece_id=f"floor_{cell[0]}_{cell[1]}",
        asset_id="floor_deck",
        kind="floor",
        cell=cell,
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor", "gatehouse"}),
    )


def _overshoot_step(cell: tuple[int, int], gate_cell: tuple[int, int]) -> SolidPlacement:
    desc = catalog_by_id()["steps_grand"]
    return SolidPlacement(
        piece_id=f"bad_{cell[0]}_{cell[1]}",
        asset_id="steps_grand",
        kind="surface",
        cell=cell,
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=desc.size_cm,
        tags=frozenset(
            {
                "approach",
                "grand_approach",
                f"approach_gate_{gate_cell[0]}_{gate_cell[1]}",
            }
        ),
    )


def test_catalog_grand_step_overshoots_flat_gate_fixture():
    """Broken fixture: fixed 175 cm rise vs z=0 threshold."""
    gate = _gate_wall("g0", (2, 0))
    floor = _floor_at_gate((2, 0))
    asm = Assembly(placements=[gate, floor])
    target = resolve_approach_mate_z(asm, gate)
    assert target <= FLOOR_T_CM + 1.0
    _, offset = mated_step_pose("steps_grand", ground_z=0.0, target_z=target)
    size = catalog_by_id()["steps_grand"].size_cm
    assert size[2] > target + 10.0, "catalog height must overshoot for this fixture"
    poison = _overshoot_step((1, -2), (2, 0))
    fails = check_approach_stair_height_mate(
        Assembly(placements=[gate, floor, poison])
    )
    assert fails
    assert all(f.check == CHECK_APPROACH_STAIR_HEIGHT_MATE and f.critical for f in fails)


def test_causeway_grid_spam_fires_alignment_and_stack():
    """Broken fixture: 3×3 grid misaligned with a single gate arch."""
    gate = _gate_wall("g0", (3, -3))
    floor = _floor_at_gate((3, -3))
    grid = [
        _overshoot_step((x, y), (3, -3))
        for y in (-5, -6, -7)
        for x in (2, 4, 6)
    ]
    asm = Assembly(placements=[gate, floor, *grid])
    align = check_approach_stair_aligned_to_gate(asm)
    assert align, "grid steps off flank columns must fail alignment"
    assert any(f.check == CHECK_APPROACH_STAIR_ALIGNED_TO_GATE for f in align)
    stack = _check_stair_flight_stack(asm)
    assert not stack, "grid on distinct cells — stack fires on same-cell dupes only"


def test_same_cell_duplicate_steps_fire_stair_flight_stack():
    gate = _gate_wall("g0", (2, 0))
    a = _overshoot_step((1, -2), (2, 0))
    b = replace(a, piece_id="dup")
    asm = Assembly(placements=[gate, a, b])
    hits = _check_stair_flight_stack(asm)
    assert hits
    assert all(f.check == "stair_flight_stack" and f.critical for f in hits)


def test_mated_step_pose_caps_to_target():
    size, offset = mated_step_pose("steps_grand", ground_z=0.0, target_z=0.0)
    assert size[2] <= 1.0 + TOL_CM
    assert offset[2] == 0.0


def test_plan_gate_approach_one_pair_per_gate():
    """One flanking pair per gate leaf; twin bays mirror N+S for through-passage.

    Fortress gatehouse punches matching north gate arches at L0
    (``assemble.north_gate_through`` / ``gate_through_passage``) so the south
    twin-bay opening continues through the hall. That yields four gate leaves
    (bays 2–3 on south and north). Adjacent bays on the same facade share flank
    cells, so step count can be below ``2 * len(gates)`` while each leaf still
    gets at most one pair in its expected flank set.
    """
    from dataclasses import replace

    spec = replace(
        fortress_gatehouse_spec(),
        storeys=2,
        storey_use=["hall", "hall"],
        wall_height_storeys=2.0,
    )
    _, _, asm, _ = run_through_assemble(spec)
    steps = plan_gate_approach_steps(asm, steps_piece="steps_grand", clearance_bays=1)
    gates = [
        p
        for p in asm.placements
        if "gate" in (p.asset_id or "") and entrance_role_tag("gate") in p.tags
    ]
    assert len(gates) == 4
    by_row: dict[int, list] = {}
    for g in gates:
        by_row.setdefault(g.cell[1], []).append(g)
    assert len(by_row) == 2
    assert all(len(leaves) == 2 for leaves in by_row.values())
    assert 2 <= len(steps) <= 2 * len(gates)
    for g in gates:
        expected = expected_flank_cells(g, clearance_bays=1)
        placed = {s.cell for s in steps if f"approach_gate_{g.cell[0]}_{g.cell[1]}" in s.tags}
        assert placed <= expected


def test_trim_exterior_steps_mated_height():
    _, _, base, _ = run_through_assemble(castle_gatehouse_spec())
    trimmed, report = trim(
        base,
        TrimOptions(
            exterior_steps=True,
            steps_piece="steps_grand",
            railings=False,
            buttresses=False,
            roofline=False,
            colonnade=False,
            parapets=False,
        ),
    )
    assert report.ok
    steps = [p for p in trimmed.placements if p.asset_id == "steps_grand"]
    assert steps
    assert check_approach_stair_height_mate(trimmed) == []
    assert check_approach_stair_aligned_to_gate(trimmed) == []


def test_trim_exterior_steps_strips_poison_grid():
    """Trim with exterior_steps must repair bad approach steps, not append (D3-5)."""
    gate = _gate_wall("g0", (3, -3))
    floor = _floor_at_gate((3, -3))
    grid = [
        _overshoot_step((x, y), (3, -3))
        for y in (-5, -6, -7)
        for x in (2, 4, 6)
    ]
    asm = Assembly(placements=[gate, floor, *grid])
    trimmed, report = trim(
        asm,
        TrimOptions(
            exterior_steps=True,
            steps_piece="steps_grand",
            railings=False,
            buttresses=False,
            roofline=False,
            colonnade=False,
            parapets=False,
        ),
    )
    assert report.ok
    steps = [p for p in trimmed.placements if p.asset_id == "steps_grand"]
    assert len(steps) == 2, f"expected repair to 2 flanking steps, got {len(steps)}"
    assert check_approach_stair_height_mate(trimmed) == []
    assert check_approach_stair_aligned_to_gate(trimmed) == []


def test_fortress_compound_approach_count_and_mate():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    steps = [p for p in assembly.placements if p.asset_id == "steps_grand"]
    assert len(steps) <= 4, f"expected ≤4 flanking steps, got {len(steps)}"
    assert len(steps) >= 2
    for s in steps:
        _smin, smax = placement_world_aabb(
            s.cell[0],
            s.cell[1],
            s.level,
            s.yaw,
            s.size_cm,
            s.offset_cm,
            rotates_about_center=s.rotates_about_center,
        )
        assert smax[2] <= TOL_CM + 2.0, f"step top {smax[2]} overshoots L0 floor"
    _, vreport = validate(assembly)
    assert not any(
        f.check in (CHECK_APPROACH_STAIR_HEIGHT_MATE, CHECK_APPROACH_STAIR_ALIGNED_TO_GATE)
        for f in vreport.critical
    )


def test_repair_strips_grid_and_replans():
    gate = _gate_wall("g0", (3, -3))
    floor = _floor_at_gate((3, -3))
    grid = [
        _overshoot_step((x, y), (3, -3))
        for y in (-5, -6, -7)
        for x in (2, 4, 6)
    ]
    asm = Assembly(placements=[gate, floor, *grid])
    fixed = repair_approach_stairs(
        asm,
        steps_piece="steps_grand",
        clearance_bays=1,
        building_name="gatehouse",
        extra_tags=frozenset({"grand_approach", "causeway", "gatehouse"}),
    )
    steps = [p for p in fixed.placements if p.asset_id == "steps_grand"]
    assert len(steps) == 2
    assert check_approach_stair_height_mate(fixed) == []
    assert check_approach_stair_aligned_to_gate(fixed) == []

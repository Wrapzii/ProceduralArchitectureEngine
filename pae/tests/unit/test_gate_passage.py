"""Gate passage clear + opening size — broken fixtures first (Handbook §6).

User: twin-tower gatehouse with tiny arches; exterior steps block walking through.
"""

from __future__ import annotations

from dataclasses import replace

from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_fortress_compound
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM, rotation_offset_cm
from pae.existence import entrance_role_tag
from pae.fortress_validate import (
    MIN_GATE_CLEAR_HEIGHT_CM,
    MIN_GATE_CLEAR_WIDTH_CM,
    check_gate_opening_size,
    check_gate_passage_clear,
    check_gate_through_passage,
)
from pae.pipeline import run_through_assemble
from pae.spec import castle_gatehouse_spec, fortress_gatehouse_spec
from pae.trim import TrimOptions, trim
from pae.validate import validate


def _gate_wall(
    pid: str,
    cell: tuple[int, int],
    *,
    asset_id: str = "wall_gate_arch_grand",
    yaw: int = 270,
) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
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


def _steps(pid: str, cell: tuple[int, int], *, asset_id: str = "steps_grand") -> SolidPlacement:
    return SolidPlacement(
        piece_id=pid,
        asset_id=asset_id,
        kind="surface",
        cell=cell,
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM * 0.5),
        tags=frozenset({"steps", "approach", "grand_approach", "causeway"}),
    )


def test_blocked_gate_steps_fire_gate_passage_clear():
    """Steps in the bay immediately south of a south gate must fail."""
    gate = _gate_wall("g0", (2, 0))
    # South of gate cell (2,0) → (2,-1) plugs the passage probe.
    poison = _steps("block", (2, -1))
    asm = Assembly(placements=[gate, poison])
    fails = check_gate_passage_clear(asm)
    assert fails, "steps in gate approach column must fail gate_passage_clear"
    assert all(f.check == "gate_passage_clear" and f.critical for f in fails)


def test_flanking_steps_pass_gate_passage_clear():
    """Steps beside the opening (not in the leaf column) stay clear."""
    gate = _gate_wall("g0", (2, 0))
    flank_l = _steps("flank_l", (1, -2))
    flank_r = _steps("flank_r", (3, -2))
    asm = Assembly(placements=[gate, flank_l, flank_r])
    assert check_gate_passage_clear(asm) == []


def test_undersized_door_as_gate_fires_gate_opening_size():
    """A house door tagged as gate is undersized vs monumental mins."""
    door = _gate_wall("tiny", (0, 0), asset_id="wall_door")
    asm = Assembly(placements=[door])
    fails = check_gate_opening_size(asm)
    assert fails, "wall_door as gate leaf must fail gate_opening_size"
    assert all(f.check == "gate_opening_size" and f.critical for f in fails)


def test_wall_gate_arch_grand_meets_min_clear():
    from pae.primitives.catalog import catalog_by_id
    from pae.primitives.walls import aperture_opening_run_vertical

    desc = catalog_by_id()["wall_gate_arch_grand"]
    run0, run1, z0, z1 = aperture_opening_run_vertical(desc.aperture, desc.size_cm)
    assert (run1 - run0) >= MIN_GATE_CLEAR_WIDTH_CM
    assert (z1 - z0) >= MIN_GATE_CLEAR_HEIGHT_CM


def test_fortress_gatehouse_spec_is_monumental():
    g = fortress_gatehouse_spec()
    assert g.footprint.bays_x >= 6
    assert g.footprint.bays_y >= 3
    assert g.footprint.bays_y <= 4
    assert g.storeys >= 3
    assert {e.bay for e in g.entrances} == {2, 3}
    assert max(t.storeys for t in g.towers) == g.storeys + 1


def test_blocked_interior_column_fires_gate_through_passage():
    """Solid north wall in a gate column must fail gate_through_passage."""
    gate = _gate_wall("g0", (2, 0))
    plug = SolidPlacement(
        piece_id="plug",
        asset_id="wall_plain",
        kind="wall",
        cell=(2, 2),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"wall"}),
    )
    asm = Assembly(placements=[gate, plug])
    fails = check_gate_through_passage(asm)
    assert fails, "interior plug in gate column must fail gate_through_passage"
    assert all(f.check == "gate_through_passage" and f.critical for f in fails)


def test_fortress_gatehouse_assemble_uses_grand_arch():
    _, _, assembly, report = run_through_assemble(fortress_gatehouse_spec())
    assert report.ok, [f.message for f in report.failures]
    gates = [
        p
        for p in assembly.placements
        if entrance_role_tag("gate") in p.tags
    ]
    assert len(gates) >= 2
    assert {p.asset_id for p in gates} == {"wall_gate_arch_grand"}
    assert check_gate_opening_size(assembly) == []
    assert check_gate_passage_clear(assembly) == []
    assert check_gate_through_passage(assembly) == []


def test_trim_exterior_steps_flank_gates():
    _, _, base, _ = run_through_assemble(castle_gatehouse_spec())
    opts = TrimOptions(
        exterior_steps=True,
        steps_piece="steps_grand",
        railings=False,
        buttresses=False,
        roofline=False,
        colonnade=False,
        parapets=False,
    )
    trimmed, report = trim(base, opts)
    assert report.ok
    gates = [
        p
        for p in trimmed.placements
        if "gate" in p.asset_id and p.level == 0
    ]
    steps = [p for p in trimmed.placements if p.asset_id == "steps_grand"]
    assert steps, "expected flanking grand steps"
    leaf_cells = {g.cell for g in gates}
    assert not any(s.cell in leaf_cells for s in steps)
    assert check_gate_passage_clear(trimmed) == []


def test_fortress_compound_gate_passage_and_size_green():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    assert check_gate_passage_clear(assembly) == []
    assert check_gate_opening_size(assembly) == []
    _, vreport = validate(assembly)
    passage = [f for f in vreport.critical if f.check == "gate_passage_clear"]
    size = [f for f in vreport.critical if f.check == "gate_opening_size"]
    assert passage == []
    assert size == []


def test_poison_compound_approach_on_leaf_column_fails():
    """Hand-inject a step into a gate leaf column on a live fortress → critical."""
    assembly, _, report = build_fortress_compound()
    assert report.ok
    gates = [
        p
        for p in assembly.placements
        if "gatehouse" in p.tags and "gate" in (p.asset_id or "").lower()
    ]
    assert gates
    g = gates[0]
    poison = _steps("poison_block", (g.cell[0], g.cell[1] - 1))
    poisoned = replace(assembly, placements=list(assembly.placements) + [poison])
    fails = check_gate_passage_clear(poisoned)
    assert fails, "injected leaf-column step must fail gate_passage_clear"

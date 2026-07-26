"""Stage I — pack ``geometry.storey_height_cm`` consumed via ``storey_datum_z_cm``."""

from __future__ import annotations

import pytest

from pae.contract import STOREY_CM, placement_world_aabb
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec
from pae.structure_spec import LevelSpec, StructureSpec, structure_to_building_spec
from pae.style_pack import load_style_pack, resolve_storey_height_cm


def _level1_floor_slab_top_z(asm) -> float:
    floors = [p for p in asm.placements if p.kind == "floor" and p.level == 1]
    assert floors, "expected level-1 floor deck"
    tops = []
    for p in floors:
        _mn, mx = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        tops.append(mx[2])
    return max(tops)


def test_tall_storey_pack_raises_level1_datum_above_short():
    short = m2_two_storey_stair_spec(seed=7)
    short.style = "rustic"  # 320 cm authored
    tall = m2_two_storey_stair_spec(seed=7)
    tall.style = "civic"  # 400 cm authored

    _, _, asm_short, _ = run_through_assemble(short)
    _, _, asm_tall, _ = run_through_assemble(tall)

    z_short = _level1_floor_slab_top_z(asm_short)
    z_tall = _level1_floor_slab_top_z(asm_tall)

    assert z_tall > z_short
    assert z_short == pytest.approx(320.0, abs=2.0)
    civic_pack, _ = load_style_pack("civic")
    assert z_tall == pytest.approx(resolve_storey_height_cm(civic_pack), abs=2.0)


def test_default_pack_uses_contract_storey_cm():
    spec = m2_two_storey_stair_spec(seed=7)
    spec.style = "townhouse"  # no geometry.storey_height_cm
    assert resolve_storey_height_cm({"id": "townhouse"}) == STOREY_CM

    _, _, asm, _ = run_through_assemble(spec)
    assert _level1_floor_slab_top_z(asm) == pytest.approx(STOREY_CM, abs=2.0)


def test_pack_storey_height_composes_with_height_units():
    """effective span = height_units × pack storey_height (medieval 340 × 2)."""
    spec = structure_to_building_spec(
        StructureSpec(
            name="tall_hall_medieval",
            style="medieval",
            seed=1,
            levels=[LevelSpec(sketch="####\n####\n", height_units=2)],
        )
    )
    _, _, asm, _ = run_through_assemble(spec)
    walls_l0 = [p for p in asm.placements if p.kind == "wall" and p.level == 0]
    assert walls_l0
    max_h = max(p.size_cm[2] for p in walls_l0)
    assert max_h == pytest.approx(2 * 340.0, abs=2.0)
    assert max_h != pytest.approx(2 * STOREY_CM, abs=2.0)

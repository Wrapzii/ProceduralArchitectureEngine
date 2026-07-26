"""Master Plan Stage A/B — StructureSpec, LevelSpec, YAML §3.1, cumulative datum."""

from __future__ import annotations

from pae.contract import STOREY_CM, placement_world_aabb, storey_datum_z_cm
from pae.pipeline import run_through_assemble
from pae.plan import CellRole
from pae.structure_identity import (
    has_structure_tags,
    structure_tag,
)
from pae.structure_spec import (
    LevelSpec,
    StructureSpec,
    load_structure,
    load_structure_yaml,
    structure_to_building_spec,
)
from pae.spec import (
    joined_wings_structure_spec,
    m1_box_house_spec,
    m2_two_storey_stair_spec,
    m4_u_plan_spec,
)


GATEHOUSE_YAML = """
name: gatehouse
style: townhouse
seed: 7

foundation: |
  ##########
  ##########

levels:
  - height_units: 1
    sketch: |
      ########
      ########
  - height_units: 1
    sketch: |
      #####...
      #####...
  - height_units: 3
    sketch: |
      ....####
      ....####
    wall_style: arcade
"""

_BUILT = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.WALL_LINE,
        CellRole.DOOR,
        CellRole.STAIR,
        CellRole.VOID,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
        CellRole.ROOM,
    }
)


def test_yaml_round_trip_section_3_1():
    spec, report = load_structure_yaml(GATEHOUSE_YAML)
    assert report.ok, [f.message for f in report.failures]
    assert spec is not None
    assert spec.name == "gatehouse"
    assert len(spec.levels) == 3
    assert spec.levels[2].height_units == 3
    assert spec.levels[2].wall_style == "arcade"
    assert len(spec.resolved_foundation_cells()) == 20

    again, report2 = load_structure(spec.to_dict())
    assert report2.ok
    assert again is not None
    assert again.name == spec.name
    assert again.level_height_units() == (1, 1, 3)
    assert again.resolved_foundation_cells() == spec.resolved_foundation_cells()

    yaml_text = spec.to_yaml()
    third, report3 = load_structure_yaml(yaml_text)
    assert report3.ok, [f.message for f in report3.failures]
    assert third is not None
    assert third.level_height_units() == (1, 1, 3)


def test_foundation_defaults_to_union_of_levels():
    data = {
        "name": "union_found",
        "style": "townhouse",
        "seed": 1,
        "levels": [
            {"height_units": 1, "sketch": "####\n####\n"},
            {"height_units": 1, "sketch": "##  \n##  \n"},
        ],
    }
    spec, report = load_structure(data)
    assert report.ok and spec is not None
    assert len(spec.resolved_foundation_cells()) == 8


def test_foundation_cell_origin_survives_dict_and_yaml_round_trip():
    original = StructureSpec(
        name="offset_foundation",
        style="townhouse",
        levels=[LevelSpec(sketch="###\n###\n")],
        foundation_cells=((7, -3), (8, -3), (9, -3), (7, -2), (8, -2), (9, -2)),
    )
    from_dict, report = load_structure(original.to_dict())
    assert report.ok and from_dict is not None
    assert from_dict.resolved_foundation_cells() == original.resolved_foundation_cells()

    from_yaml, yaml_report = load_structure_yaml(original.to_yaml())
    assert yaml_report.ok and from_yaml is not None
    assert from_yaml.resolved_foundation_cells() == original.resolved_foundation_cells()


def test_structure_rejects_unknown_fields_and_unsupported_module_size():
    base = {
        "name": "strict",
        "style": "townhouse",
        "levels": [{"sketch": "###\n###\n"}],
    }
    spec, report = load_structure({**base, "mystery": 42})
    assert spec is None and not report.ok
    assert "unknown field" in report.critical[0].message

    spec, report = load_structure({**base, "unit_cm": 250})
    assert spec is None and not report.ok
    assert "fixed module size" in report.critical[0].message


def test_program_rectangles_create_complete_room_partition_with_door():
    structure = StructureSpec(
        name="two_room_house",
        style="townhouse",
        levels=[
            LevelSpec(
                sketch="########\n########\n########\n########\n########\n########\n",
                program={
                    "living_room": [(1, 1, 3, 4)],
                    "kitchen": [(4, 1, 6, 4)],
                },
            )
        ],
        roof_kind="flat",
    )
    _massing, plan, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures]
    assert {p[3] for p in plan.program_cells} == {"living_room", "kitchen"}
    assert plan.interior_partitions
    partition_pieces = [
        p for p in assembly.placements if "partition" in set(p.tags)
    ]
    assert len(partition_pieces) == 6
    doors = [p for p in partition_pieces if "door" in set(p.tags)]
    assert len(doors) == 1
    assert all(
        assembly.floor_plan[0].role_at(x, y) == CellRole.ROOM
        for x, y, level, _name in plan.program_cells
        if level == 0
    )


def test_abutting_rect_cover_masses_share_one_open_interior():
    from pae.validate import validate

    massing, plan, assembly, report = run_through_assemble(
        joined_wings_structure_spec()
    )
    assert report.ok
    assert len(massing.enclosed_volumes()) == 2
    assert len(plan.storeys) == 2
    assert plan.interior_partitions
    # x=8 is the solver's volume-decomposition seam. It remains open through
    # the shared central hall on both levels.
    assert not any(
        x == 7 and face == "east"
        for x, _y, _level, face, _is_door in plan.interior_partitions
    )
    assert any(p.kind == "stair" for p in assembly.placements)
    assert any(p.asset_id == "floor_hole" and p.level == 1 for p in assembly.placements)
    _, validation = validate(assembly)
    assert validation.ok, [f.message for f in validation.critical]


def test_two_touching_masses_one_foundation_one_stair_core():
    """Stage A done-when: one structure tag, one L0 hall stair."""
    # L-plan: south bar + west leg — rect_cover → ≥2 volumes, one structure.
    l0 = (
        "########\n"
        "########\n"
        "##S     \n"
        "##      \n"
        "##      \n"
        "##      \n"
    )
    l1 = (
        "########\n"
        "########\n"
        "##      \n"
        "##      \n"
        "##      \n"
        "##      \n"
    )
    structure = StructureSpec(
        name="twin_mass",
        style="townhouse",
        seed=11,
        levels=[
            LevelSpec(sketch=l0, height_units=1),
            LevelSpec(sketch=l1, height_units=1),
        ],
        stair_kind="straight",
        roof_kind="flat",
    )
    massing, _plan, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures[:5]]
    assert has_structure_tags(assembly)
    st = structure_tag("twin_mass")
    assert all(st in p.tags for p in assembly.placements)
    assert len(massing.enclosed_volumes()) >= 2

    hall_stairs = [
        p
        for p in assembly.placements
        if p.kind == "stair"
        and p.level == 0
        and "spiral" not in (p.asset_id or "")
    ]
    assert len(hall_stairs) >= 1
    # Single structure identity — not one stair per volume as separate buildings.
    assert len({p.cell for p in hall_stairs}) <= 4  # one well footprint


def test_u_with_no_l1_on_one_leg_builds():
    """Stage B: upper level omits one leg of a U."""
    l0_stair = (
        "######\n"
        "######\n"
        "##  ##\n"
        "#S  ##\n"
        "##  ##\n"
        "##  ##\n"
    )
    l1 = (
        "####  \n"
        "####  \n"
        "##    \n"
        "##    \n"
        "##    \n"
        "##    \n"
    )
    structure = StructureSpec(
        name="u_partial",
        style="townhouse",
        seed=5,
        levels=[
            LevelSpec(sketch=l0_stair, height_units=1),
            LevelSpec(sketch=l1, height_units=1),
        ],
        stair_kind="straight",
        roof_kind="flat",
    )
    _m, plan, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures[:5]]
    assert assembly.placements

    l0_built = {c for c, role in plan.storeys[0].cells.items() if role in _BUILT}
    l1_built = {c for c, role in plan.storeys[1].cells.items() if role in _BUILT}
    assert len(l1_built) < len(l0_built)
    east_leg = {(4, y) for y in range(2, 6)} | {(5, y) for y in range(2, 6)}
    assert east_leg & l0_built
    assert not (east_leg & l1_built)


def test_three_unit_tall_hall_cumulative_datum():
    """height_units: 3 → walls span 3×STOREY; L2 datum is cumulative."""
    assert storey_datum_z_cm(0, height_units=(1, 3, 1)) == 0.0
    assert storey_datum_z_cm(1, height_units=(1, 3, 1)) == STOREY_CM
    assert storey_datum_z_cm(2, height_units=(1, 3, 1)) == 4 * STOREY_CM

    # 8×5 footprint so a 3-level straight well can expand to 4×2 (D3-3).
    structure = StructureSpec(
        name="tall_hall",
        style="townhouse",
        seed=3,
        levels=[
            LevelSpec(
                sketch="########\n###S####\n########\n########\n########\n",
                height_units=1,
            ),
            LevelSpec(
                sketch="########\n########\n########\n########\n########\n",
                height_units=3,
            ),
            LevelSpec(
                sketch="######  \n######  \n######  \n######  \n######  \n",
                height_units=1,
            ),
        ],
        stair_kind="straight",
        roof_kind="flat",
    )
    _massing, plan, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures[:5]]
    assert plan.level_height_units == (1, 3, 1)

    l1_walls = [p for p in assembly.placements if p.kind == "wall" and p.level == 1]
    assert l1_walls, "expected walls on tall level"
    assert any(p.size_cm[2] >= 3 * STOREY_CM - 1.0 for p in l1_walls)

    l2_floors = [p for p in assembly.placements if p.kind == "floor" and p.level == 2]
    assert l2_floors
    p = l2_floors[0]
    _mn, mx = placement_world_aabb(
        p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm
    )
    assert abs(mx[2] - 4 * STOREY_CM) < 2.0


def test_storey_datum_accessor_honours_height_units():
    assert storey_datum_z_cm(2) == 2 * STOREY_CM
    assert storey_datum_z_cm(2, height_units=(1, 1, 1)) == 2 * STOREY_CM
    assert storey_datum_z_cm(2, height_units=(2, 2, 1)) == 4 * STOREY_CM
    assert storey_datum_z_cm(0, height_units=(5,)) == 0.0


def test_legacy_factories_still_build():
    for factory in (m1_box_house_spec, m2_two_storey_stair_spec, m4_u_plan_spec):
        _m, _p, assembly, report = run_through_assemble(factory())
        assert report.ok, (factory.__name__, [f.message for f in report.failures[:3]])
        assert assembly.placements


def test_structure_to_building_spec_shim():
    structure = StructureSpec(
        name="shim",
        style="townhouse",
        levels=[LevelSpec(sketch="####\n####\n", height_units=2)],
        seed=1,
    )
    bs = structure_to_building_spec(structure)
    assert bs.storeys == 1
    assert bs.level_height_units == (2,)
    assert bs.structure_id == "shim"
    assert bs.foundation_cells

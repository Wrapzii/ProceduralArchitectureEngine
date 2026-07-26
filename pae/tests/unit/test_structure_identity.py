"""Structure identity — Roadmap 10.1–10.2 / Handbook §11d (D3-1, D3-2)."""

from __future__ import annotations

from pae.compound import build_fortress_compound, fortress_compound_connections
from pae.compound_unify import (
    CHECK_COMPOUND_PARTITIONED,
    check_compound_not_partitioned,
    make_three_sealed_buildings_defect,
    unify_compound_assembly,
)
from pae.pipeline import run_through_assemble
from pae.site import BuildingInstance, place_buildings
from pae.spec import m1_box_house_spec
from pae.structure_identity import (
    CHECK_STRUCTURE_PARTY_WALL,
    CHECK_STRUCTURE_SINGLE_STAIR,
    apply_structure_tags,
    check_structure_contiguous,
    check_structure_identity,
    check_structure_masses_reachable,
    check_structure_party_wall_open,
    check_structure_single_stair_core,
    has_structure_tags,
    make_three_stair_masses_defect,
    partition_key,
    structure_tag,
)
from pae.validate import validate, _check_structural_islands


def test_partition_key_prefers_structure_over_building():
    from pae.assembly_types import SolidPlacement

    from pae.contract import FLOOR_T_CM, MODULE_CM

    p = SolidPlacement(
        piece_id="x",
        asset_id="floor",
        kind="floor",
        cell=(0, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset(
            {"building:west_curtain", "west_curtain", structure_tag("fortress_bailey")}
        ),
    )
    assert partition_key(p) == structure_tag("fortress_bailey")


def test_three_sealed_with_structure_fires_party_wall_check():
    poisoned = apply_structure_tags(
        make_three_sealed_buildings_defect(), "fortress_bailey"
    )
    party = check_structure_party_wall_open(poisoned)
    assert party, "structure_party_wall_open must fire on sealed same-structure masses"
    assert all(f.critical for f in party)
    assert all(f.check == CHECK_STRUCTURE_PARTY_WALL for f in party)


def test_three_stair_masses_fixture_fires_single_stair_core():
    poisoned = make_three_stair_masses_defect()
    hits = check_structure_single_stair_core(poisoned)
    assert hits, "structure_single_stair_core must fire on D3-1 poison"
    assert all(f.check == CHECK_STRUCTURE_SINGLE_STAIR and f.critical for f in hits)


def test_same_structure_strengthens_compound_partition_check():
    poisoned = apply_structure_tags(
        make_three_sealed_buildings_defect(), "fortress_bailey"
    )
    conn = fortress_compound_connections()
    part = check_compound_not_partitioned(poisoned, connections=conn)
    assert part, "compound_not_partitioned must fail on same-structure sealed interface"
    assert any("structure" in f.message for f in part)


def test_fortress_connections_declares_one_structure():
    conn = fortress_compound_connections()
    assert conn.structure_id == "fortress_bailey"


def test_unify_stamps_structure_on_compound():
    from pae.compound_unify import make_fortress_five_boxes_defect, unify_compound_assembly

    poisoned = make_fortress_five_boxes_defect()
    conn = fortress_compound_connections()
    fixed = unify_compound_assembly(poisoned, connections=conn)
    st = structure_tag("fortress_bailey")
    assert sum(1 for p in fixed.placements if st in p.tags) > 0
    assert check_structure_identity(fixed) == []


def test_place_buildings_stamps_structure_from_instance():
    from pae.assembly_types import Assembly, SolidPlacement
    from pae.contract import FLOOR_T_CM, MODULE_CM

    tiny = Assembly(
        placements=[
            SolidPlacement(
                piece_id="f0",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            )
        ],
        storeys=1,
    )
    merged, _ = place_buildings(
        [
            BuildingInstance(tiny, (0, 0), "west_curtain", structure="fortress_bailey"),
            BuildingInstance(tiny, (3, 0), "gatehouse", structure="fortress_bailey"),
        ]
    )
    st = structure_tag("fortress_bailey")
    assert all(st in p.tags for p in merged.placements)


def test_street_of_houses_still_partitions_by_building():
    """Without structure tags, freestanding still keys on building: (T-102 trap)."""
    _, _, a1, _ = run_through_assemble(m1_box_house_spec())
    _, _, a2, _ = run_through_assemble(m1_box_house_spec())
    merged, _ = place_buildings(
        [
            BuildingInstance(a1, (0, 0), "house_a"),
            BuildingInstance(a2, (20, 0), "house_b"),
        ]
    )
    keys = {partition_key(p) for p in merged.placements if p.kind == "floor"}
    assert not any(t.startswith("structure:") for t in keys)
    assert "building:house_a" in keys
    assert "building:house_b" in keys


def test_structure_sealed_autofix_clears_party_wall():
    poisoned = apply_structure_tags(
        make_three_sealed_buildings_defect(), "fortress_bailey"
    )
    fixed = unify_compound_assembly(poisoned)
    assert check_structure_party_wall_open(fixed) == []
    assert check_compound_not_partitioned(fixed) == []


def test_fortress_compound_green_path_structure_identity():
    """Real build_fortress_compound — not poison-only (D3-1/D3-2 green path)."""
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    st = structure_tag("fortress_bailey")
    assert has_structure_tags(assembly)
    assert all(st in p.tags for p in assembly.placements)

    assert check_structure_contiguous(assembly) == []
    assert check_structure_party_wall_open(assembly) == []
    assert check_structure_masses_reachable(assembly) == []
    conn = fortress_compound_connections()
    assert (
        check_structure_single_stair_core(
            assembly,
            primary_circulation_mass=conn.primary_circulation_mass,
            auxiliary_circulation_masses=conn.auxiliary_circulation_masses,
        )
        == []
    )
    assert (
        check_structure_identity(
            assembly,
            primary_circulation_mass=conn.primary_circulation_mass,
            auxiliary_circulation_masses=conn.auxiliary_circulation_masses,
        )
        == []
    )

    _, vreport = validate(assembly)
    struct_crit = [f for f in vreport.critical if f.check.startswith("structure_")]
    assert struct_crit == [], [f.message for f in struct_crit]
    part_crit = [
        f for f in vreport.critical if f.check == CHECK_COMPOUND_PARTITIONED
    ]
    assert part_crit == []


def test_fortress_freestanding_partitions_on_structure():
    """T-102 — one campus island key, not per-range building: tags."""
    assembly, _, report = build_fortress_compound()
    assert report.ok
    st = structure_tag("fortress_bailey")
    keys = {
        partition_key(p)
        for p in assembly.placements
        if st in p.tags and p.kind in ("wall", "floor", "roof")
    }
    assert keys == {st}
    assert _check_structural_islands(assembly) == []

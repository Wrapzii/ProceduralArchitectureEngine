"""Phase 2.5 interior fit-out greybox — classroom / great_hall props + containment.

WRITTEN BEFORE THE IMPLEMENTATION, per Docs/VALIDATION_HANDBOOK.md §6. Seven questions
(§2) for this family are documented in ``pae.fitout`` module docstring.
"""

from __future__ import annotations

import pytest

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, placement_world_aabb
from pae.fitout import (
    GREYBOX_FITOUT_PROPS,
    fitout_candidate_cells,
    fitout_greybox,
    is_fitout_cell,
)
from pae.pipeline import run_through_validate_trim
from pae.plan import CellRole
from pae.spec import m1_box_house_spec, school_academy_spec
from pae.validate import validate


def _school_assembled():
    _, _, assembly, report = run_through_validate_trim(school_academy_spec(seed=70))
    assert report.ok, [f.message for f in report.critical]
    return assembly


def test_fitout_candidates_are_classroom_or_great_hall_only():
    assembly = _school_assembled()
    candidates = fitout_candidate_cells(assembly)
    assert candidates, "school academy must expose fit-out cells"
    layers = assembly.floor_plan
    hall_declared = any(
        str(r.get("kind", "")).lower() == "hall" for r in assembly.room_specs
    )
    assert hall_declared
    for level, cell in candidates:
        assert is_fitout_cell(layers, level, cell, hall_declared=hall_declared)
        role = layers[level].role_at(cell[0], cell[1])
        assert role in (CellRole.CLASSROOM, CellRole.INTERIOR)
        if role == CellRole.INTERIOR:
            assert level == 0, "great_hall cells are ground-floor INTERIOR only"
    corridor_hits = [
        c
        for c in candidates
        if layers[c[0]].role_at(c[1][0], c[1][1]) == CellRole.CORRIDOR
    ]
    assert not corridor_hits


def test_m1_box_has_no_fitout_candidates():
    from pae.pipeline import run_through_assemble

    _, _, assembly, report = run_through_assemble(m1_box_house_spec())
    assert report.ok
    assert fitout_candidate_cells(assembly) == []


def test_fitout_greybox_places_bench_table_crate():
    assembly = _school_assembled()
    fitted, report = fitout_greybox(assembly, seed=42, density=0.15, max_props=9)
    assert report.ok
    props = [p for p in fitted.placements if "fitout_greybox" in p.tags]
    assert len(props) >= 3
    asset_ids = {p.asset_id for p in props}
    expected = {aid for aid, _ in GREYBOX_FITOUT_PROPS}
    assert expected <= asset_ids
    for p in props:
        assert is_fitout_cell(
            fitted.floor_plan,
            p.level,
            p.cell,
            hall_declared=True,
        )


def test_fitout_greybox_seed_stable():
    assembly = _school_assembled()
    a1, _ = fitout_greybox(assembly, seed=7, density=0.1, max_props=6)
    a2, _ = fitout_greybox(assembly, seed=7, density=0.1, max_props=6)
    ids1 = sorted(p.piece_id for p in a1.placements if "fitout_greybox" in p.tags)
    ids2 = sorted(p.piece_id for p in a2.placements if "fitout_greybox" in p.tags)
    assert ids1 == ids2


def test_fitout_containment_passes_on_valid_placement():
    assembly = _school_assembled()
    fitted, _ = fitout_greybox(assembly, seed=1, density=0.12, max_props=8)
    _, report = validate(fitted)
    fitout_failures = [f for f in report.critical if f.check == "fitout_containment"]
    assert not fitout_failures, [f.message for f in fitout_failures]


def test_fitout_prop_in_corridor_fails_containment():
    assembly = _school_assembled()
    # Find a corridor cell on ground floor.
    corridor_cell = None
    for level, layer in assembly.floor_plan.items():
        if level != 0:
            continue
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                if layer.cells[ly][lx] == CellRole.CORRIDOR:
                    corridor_cell = (level, (ox + lx, oy + ly))
                    break
            if corridor_cell:
                break
        if corridor_cell:
            break
    assert corridor_cell is not None
    level, cell = corridor_cell
    poison = SolidPlacement(
        piece_id="poison_corridor_crate",
        asset_id="fitout_crate",
        kind="prop",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(175.0, 175.0, 0.0),
        size_cm=(50.0, 50.0, 80.0),
        tags=frozenset({"prop", "fitout_greybox"}),
    )
    bad = Assembly(
        placements=list(assembly.placements) + [poison],
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        storeys=assembly.storeys,
        room_specs=assembly.room_specs,
    )
    _, report = validate(bad)
    checks = {f.check for f in report.critical}
    assert "fitout_containment" in checks


def test_fitout_prop_wrong_floor_z_fails_containment():
    assembly = _school_assembled()
    candidates = fitout_candidate_cells(assembly)
    assert candidates
    level, cell = candidates[0]
    poison = SolidPlacement(
        piece_id="poison_floating_table",
        asset_id="fitout_table",
        kind="prop",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(160.0, 160.0, 50.0),
        size_cm=(80.0, 80.0, 75.0),
        tags=frozenset({"prop", "fitout_greybox"}),
    )
    bad = Assembly(
        placements=list(assembly.placements) + [poison],
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        storeys=assembly.storeys,
        room_specs=assembly.room_specs,
    )
    _, report = validate(bad)
    assert any(f.check == "fitout_containment" for f in report.critical)


def test_fitout_containment_check_is_not_a_no_op():
    """Handbook §6 — guard against a check that never fires."""
    assembly = _school_assembled()
    _, clean = validate(assembly)
    assert not any(f.check == "fitout_containment" for f in clean.critical)
    test_fitout_prop_in_corridor_fails_containment()


def test_school_pipeline_fitout_end_to_end():
    from pae.pipeline import run_through_decorate

    _, _, assembly, report = run_through_decorate(
        school_academy_spec(seed=70),
        asset_db=None,
        seed=70,
    )
    assert report.ok, [f.message for f in report.critical]
    props = [p for p in assembly.placements if "fitout_greybox" in p.tags]
    assert len(props) >= 3

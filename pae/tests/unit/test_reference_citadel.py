"""Regression proof for the independent reference-image citadel."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.assembly_types import SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM
from pae.existence import entrance_role_tag
from pae.pipeline import run_through_assemble
from pae.reference_citadel import (
    reference_citadel_components,
    reference_gatehouse_spec,
    reference_great_hall_spec,
)
from pae.validate import validate


@pytest.mark.parametrize(
    "component",
    reference_citadel_components(),
    ids=lambda component: component.name,
)
def test_every_reference_component_assembles_and_validates(component):
    _, _, assembly, stage_report = run_through_assemble(
        component.factory(), apply_arcade=component.arcade
    )
    assembly, report = validate(assembly)
    assert stage_report.critical == []
    assert report.critical == []


def test_gatehouse_has_two_clear_double_height_through_lanes():
    _, _, assembly, _ = run_through_assemble(reference_gatehouse_spec())
    gates = [
        p
        for p in assembly.placements
        if entrance_role_tag("gate") in p.tags
    ]
    assert len(gates) == 4
    assert {p.asset_id for p in gates} == {"wall_gate_arch_grand"}
    assert {p.cell for p in gates} == {(1, 0), (3, 0), (1, 4), (3, 4)}

    lane_cells = {
        (x, y)
        for x in (1, 3)
        for y in range(reference_gatehouse_spec().footprint.bays_y)
    }
    upper_lane_floors = [
        p
        for p in assembly.placements
        if p.level == 1 and p.kind == "floor" and p.cell in lane_cells
    ]
    assert upper_lane_floors == []

    # The flanking towers own vertical circulation; a hall switchback would
    # either intrude into a gate lane or demand an intermediate landing on the
    # deliberately absent second-storey deck.
    tower_stairs = [
        p
        for p in assembly.placements
        if p.kind == "stair" and p.asset_id == "stair_spiral_quarter"
    ]
    assert tower_stairs
    assert not any(
        p.kind == "stair" and p.asset_id == "stair_switchback"
        for p in assembly.placements
    )

    crossing_decks = [
        p
        for p in assembly.placements
        if p.kind == "floor"
        and p.asset_id != "floor_hole"
        and "tower_room_floor" not in p.tags
    ]
    assert not any(p.level == 1 for p in crossing_decks)
    assert any(p.level == 2 for p in crossing_decks)

    side_walls = [
        p for p in assembly.placements if "gate_passage_wall" in p.tags
    ]
    assert {
        tag
        for p in side_walls
        for tag in p.tags
        if tag.startswith("gate_passage_side_")
    } == {"gate_passage_side_west", "gate_passage_side_east"}


def test_great_hall_has_room_bearing_round_and_square_towers():
    _, floor_plan, assembly, _ = run_through_assemble(reference_great_hall_spec())
    shapes = {
        volume.tower_shape
        for volume in floor_plan.massing.volumes
        if volume.role == "tower"
    }
    assert shapes == {"round", "square"}

    room_floors = [
        p for p in assembly.placements if "tower_room_floor" in p.tags
    ]
    core_walls = [
        p
        for p in assembly.placements
        if "tower_stair_core" in p.tags
    ]
    spirals = [
        p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"
    ]
    assert room_floors
    assert core_walls == []
    assert spirals
    assert {p.cell for p in room_floors} == {(-1, 2), (10, 2)}
    assert all(
        "tower_stair_core" not in p.tags for p in assembly.placements
    )


def test_reference_courtyard_uses_generated_arcade_bays():
    courtyard = next(
        component
        for component in reference_citadel_components()
        if component.name == "courtyard"
    )
    _, _, assembly, report = run_through_assemble(
        courtyard.factory(), apply_arcade=True
    )
    assert report.critical == []
    arcade_bays = [
        p for p in assembly.placements if p.asset_id == "wall_arcade"
    ]
    assert len(arcade_bays) >= 20
    assert not any(
        p.piece_id.startswith("wall_inner_") for p in assembly.placements
    )
    assert sum(
        "gallery_support_pier" in p.tags for p in assembly.placements
    ) >= 8


def test_great_hall_is_double_height_with_alternating_roof_ribs():
    _, _, assembly, report = run_through_assemble(reference_great_hall_spec())
    assert report.critical == []
    hall_level_one_floors = [
        p
        for p in assembly.placements
        if p.kind == "floor"
        and p.level == 1
        and "tower" not in p.tags
        and p.asset_id != "floor_hole"
    ]
    assert hall_level_one_floors == []
    assert any(
        p.kind == "floor" and p.level == 2 and "tower" not in p.tags
        for p in assembly.placements
    )
    ribs = sorted(
        (
            p
            for p in assembly.placements
            if "interior_arch_rib" in p.tags
        ),
        key=lambda p: p.cell[0],
    )
    assert len(ribs) >= 4
    assert {p.asset_id for p in ribs} == {"arch_rib_freestanding"}
    assert all(
        right.cell[0] - left.cell[0] == 2
        for left, right in zip(ribs, ribs[1:])
    )


def test_reference_component_roof_zones_touch_without_plan_overlap():
    components = reference_citadel_components()
    # Gate → connector → court → connector → hall. These are deliberate,
    # contiguous ownership zones rather than one roof stretched over the site.
    expected_y_ranges = {
        "gatehouse": (0.0, 16.0),
        "gate_to_court": (16.0, 24.0),
        "courtyard": (24.0, 64.0),
        "court_to_hall": (64.0, 72.0),
        "great_hall": (72.0, 92.0),
    }
    assert [component.name for component in components] == list(expected_y_ranges)
    for previous, current in zip(components, components[1:]):
        assert expected_y_ranges[previous.name][1] == expected_y_ranges[current.name][0]


def _critical_checks(assembly):
    return {failure.check for failure in validate(assembly)[1].critical}


def test_validator_rejects_roof_tower_junction_without_notch():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    assembly.placements[:] = [
        p for p in assembly.placements if p.asset_id != "roof_hole"
    ]
    assert "attached_tower_roof_notch" in _critical_checks(assembly)


def test_validator_rejects_upper_floor_over_open_courtyard():
    courtyard = next(
        component
        for component in reference_citadel_components()
        if component.name == "courtyard"
    )
    _, _, assembly, _ = run_through_assemble(
        courtyard.factory(), apply_arcade=True
    )
    assembly.placements.append(
        SolidPlacement(
            piece_id="poison_courtyard_floor",
            asset_id="floor",
            kind="floor",
            cell=(4, 4),
            level=1,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({"floor", "slab"}),
        )
    )
    assert "floor_respects_plan_voids" in _critical_checks(assembly)


def test_validator_rejects_connector_with_blocked_end():
    connector = next(
        component
        for component in reference_citadel_components()
        if component.name == "gate_to_court"
    )
    _, _, assembly, _ = run_through_assemble(connector.factory())
    assembly.placements.append(
        SolidPlacement(
            piece_id="wall_north_poison",
            asset_id="wall_plain",
            kind="wall",
            cell=(0, 2),
            level=0,
            yaw=90,
            offset_cm=(MODULE_CM, -WALL_T_CM, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, 2.0 * STOREY_CM),
            tags=frozenset({"wall", "exterior"}),
        )
    )
    assert "connector_open_ends" in _critical_checks(assembly)


def test_validator_rejects_connector_roof_below_monumental_arches():
    connector = next(
        component
        for component in reference_citadel_components()
        if component.name == "gate_to_court"
    )
    _, _, assembly, _ = run_through_assemble(connector.factory())
    roof = next(p for p in assembly.placements if p.kind == "roof")
    roof.offset_cm = (
        roof.offset_cm[0],
        roof.offset_cm[1],
        STOREY_CM,
    )
    assert "connector_roof_clearance" in _critical_checks(assembly)


def test_validator_rejects_unenclosed_double_height_gate_lane():
    _, _, assembly, _ = run_through_assemble(reference_gatehouse_spec())
    assembly.placements[:] = [
        p
        for p in assembly.placements
        if "gate_passage_side_west" not in p.tags
    ]
    assert "gate_passage_side_enclosure" in _critical_checks(assembly)


def test_validator_rejects_upper_wall_inside_gate_lane():
    _, _, assembly, _ = run_through_assemble(reference_gatehouse_spec())
    assembly.placements.append(
        SolidPlacement(
            piece_id="wall_north_poison_gatehouse",
            asset_id="wall_plain",
            kind="wall",
            cell=(1, 1),
            level=1,
            yaw=90,
            offset_cm=(MODULE_CM, -WALL_T_CM, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({"wall", "exterior"}),
        )
    )
    assert "gate_passage_volume_clear" in _critical_checks(assembly)


def test_validator_rejects_spiral_rotated_onto_tower_door():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    door = next(
        p
        for p in assembly.placements
        if p.kind == "wall" and "tower_entry" in p.tags
    )
    first = min(
        (
            p
            for p in assembly.placements
            if p.asset_id == "stair_spiral_quarter"
            and p.cell == door.cell
            and p.level == door.level
        ),
        key=lambda p: p.offset_cm[2],
    )
    first.yaw = door.yaw
    assert "tower_spiral_door_alignment" in _critical_checks(assembly)


def test_validator_rejects_drum_arc_surviving_behind_tower_door():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    door = next(
        p
        for p in assembly.placements
        if p.kind == "wall" and "tower_entry" in p.tags
    )
    source_arc = next(
        p
        for p in assembly.placements
        if p.kind == "tower_arc"
        and p.cell == door.cell
        and p.level == door.level
    )
    assembly.placements.append(
        replace(
            source_arc,
            piece_id="poison_arc_behind_tower_door",
            asset_id="tower_arc_quarter",
            yaw=door.yaw,
            tags=frozenset(
                tag
                for tag in source_arc.tags
                if tag != "tower_door_cut_ring"
            ),
        )
    )
    assert "tower_entry_door" in _critical_checks(assembly)


def test_validator_rejects_visible_flat_drum_window_proxy():
    _, _, assembly, _ = run_through_assemble(reference_gatehouse_spec())
    proxy = next(
        p
        for p in assembly.placements
        if "non_rendering_aperture_proxy" in p.tags
    )
    proxy.tags = frozenset(
        tag for tag in proxy.tags if tag != "non_rendering_aperture_proxy"
    )
    assert "drum_window_render_ownership" in _critical_checks(assembly)


def test_validator_rejects_wall_through_spiral_core():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    assembly.placements.append(
        SolidPlacement(
            piece_id="poison_wall_through_spiral",
            asset_id="wall_plain",
            kind="wall",
            cell=(-1, 2),
            level=0,
            yaw=0,
            offset_cm=(-110.0, 200.0, 0.0),
            size_cm=(60.0, 400.0, STOREY_CM),
            rotates_about_center=True,
            tags=frozenset({"wall", "structural"}),
        )
    )
    assert "wall_stair_penetration" in _critical_checks(assembly)


def test_validator_rejects_tower_landing_that_does_not_reach_the_stair():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    landing = next(
        p
        for p in assembly.placements
        if "tower_entry_landing" in p.tags and p.level == 2
    )
    index = assembly.placements.index(landing)
    assembly.placements[index] = replace(
        landing,
        offset_cm=(
            landing.offset_cm[0],
            landing.offset_cm[1],
            landing.offset_cm[2] - MODULE_CM,
        ),
    )
    assert "tower_spiral_door_alignment" in _critical_checks(assembly)


def test_validator_rejects_floor_slab_through_spiral_treads():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    stair = next(
        p
        for p in assembly.placements
        if p.asset_id == "stair_spiral_quarter" and p.level == 0
    )
    assembly.placements.append(
        SolidPlacement(
            piece_id="poison_floor_through_spiral",
            asset_id="floor",
            kind="floor",
            cell=stair.cell,
            level=stair.level,
            yaw=0,
            offset_cm=(
                stair.offset_cm[0],
                stair.offset_cm[1],
                stair.offset_cm[2] + 40.0,
            ),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            rotates_about_center=True,
            tags=frozenset({"floor", "slab", "walkable"}),
        )
    )
    assert "wall_stair_penetration" in _critical_checks(assembly)


def test_validator_rejects_single_height_great_hall():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    assembly.placements.append(
        SolidPlacement(
            piece_id="poison_great_hall_level_one_floor",
            asset_id="floor",
            kind="floor",
            cell=(4, 2),
            level=1,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({"floor", "slab"}),
        )
    )
    assert "floor_respects_plan_voids" in _critical_checks(assembly)


def test_validator_rejects_unsupported_courtyard_gallery():
    courtyard = next(
        component
        for component in reference_citadel_components()
        if component.name == "courtyard"
    )
    _, _, assembly, _ = run_through_assemble(
        courtyard.factory(), apply_arcade=True
    )
    assembly.placements[:] = [
        p for p in assembly.placements if "gallery_support_pier" not in p.tags
    ]
    assert "gallery_support_spacing" in _critical_checks(assembly)


def test_validator_rejects_gallery_column_that_misses_its_roof_and_deck():
    courtyard = next(
        component
        for component in reference_citadel_components()
        if component.name == "courtyard"
    )
    _, _, assembly, _ = run_through_assemble(
        courtyard.factory(), apply_arcade=True
    )
    support = next(
        p for p in assembly.placements if "gallery_support_pier" in p.tags
    )
    index = assembly.placements.index(support)
    assembly.placements[index] = replace(
        support,
        offset_cm=(
            support.offset_cm[0] + MODULE_CM * 20.0,
            support.offset_cm[1],
            support.offset_cm[2],
        ),
    )
    assert "gallery_support_bearing" in _critical_checks(assembly)


def test_validator_rejects_redundant_inner_courtyard_wall():
    courtyard = next(
        component
        for component in reference_citadel_components()
        if component.name == "courtyard"
    )
    _, _, assembly, _ = run_through_assemble(
        courtyard.factory(), apply_arcade=True
    )
    source = next(
        p for p in assembly.placements if p.kind == "wall"
    )
    assembly.placements.append(
        replace(source, piece_id="wall_inner_poison_courtyard")
    )
    assert "arcade_redundant_inner_wall" in _critical_checks(assembly)


def test_validator_rejects_great_hall_without_roof_ribs():
    _, _, assembly, _ = run_through_assemble(reference_great_hall_spec())
    assembly.placements[:] = [
        p for p in assembly.placements if "interior_arch_rib" not in p.tags
    ]
    assert "interior_arch_rib_contract" in _critical_checks(assembly)

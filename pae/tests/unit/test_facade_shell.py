"""Unit tests — continuous facade shell assembly."""

from __future__ import annotations

from pae.contract import MODULE_CM, placement_world_aabb
from pae.facade_grammar import FacadeParams, build_from_params
from pae.facade_shell import (
    SHELL_DOOR_ASSET,
    SHELL_WALL_ASSET,
    build_shell_assembly,
    count_chimney_stubs,
    count_exterior_shell_walls,
    count_modular_window_kits,
    count_muntin_placements,
    count_shell_doors,
    count_window_placements,
)


def _default_params(**kwargs) -> FacadeParams:
    base = dict(
        seed=1812,
        frontage_m=10.0,
        depth_m=8.0,
        storeys=3,
        wealth=2,
        row_context="freestanding",
    )
    base.update(kwargs)
    return FacadeParams(**base)


def test_shell_has_no_modular_window_kits():
    """Regression: kit wall_window_* modules made the cell-farm exterior."""
    params = _default_params(storeys=4, wealth=4, frontage_m=22.0, depth_m=12.0)
    assembly, _ = build_shell_assembly(params)
    assert count_modular_window_kits(assembly) == 0


def test_shell_exterior_is_not_per_bay_cell_farm():
    params = _default_params(storeys=4, frontage_m=22.0, depth_m=12.0)
    assembly, _ = build_shell_assembly(params)
    assert count_modular_window_kits(assembly) == 0
    # No exterior placement may be a full-bay modular wall kit standing in for skin.
    kit_skin = [
        p
        for p in assembly.placements
        if "exterior" in p.tags
        and p.asset_id.startswith("wall_")
        and "door" not in p.asset_id
    ]
    assert kit_skin == []
    # Blind / continuous panels exist; openings are shell frames.
    assert count_exterior_shell_walls(assembly) > 0
    assert count_window_placements(assembly, "south") > 0


def test_party_wall_face_has_no_windows():
    params = _default_params(row_context="end_left")
    assembly, _ = build_shell_assembly(params)
    assert count_window_placements(assembly, "west") == 0
    west_walls = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET and "face_west" in p.tags
    ]
    assert west_walls
    assert all("party_wall" in p.tags or "blind" in p.tags for p in west_walls)
    # Blind party wall: plinth + mid + cornice per storey (no pier grid).
    mid_panels = [
        p
        for p in west_walls
        if "plinth" not in p.tags and "cornice" not in p.tags
    ]
    assert len(mid_panels) == 3
    assert all(p.size_cm[1] >= 2 * MODULE_CM - 1.0 for p in mid_panels)


def test_stair_inside_footprint():
    params = _default_params()
    assembly, _ = build_shell_assembly(params)
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert stairs
    bays_x = 3
    bays_y = 2
    max_x = bays_x * MODULE_CM
    max_y = bays_y * MODULE_CM
    for st in stairs:
        pmin, pmax = placement_world_aabb(
            st.cell[0],
            st.cell[1],
            st.level,
            st.yaw,
            st.size_cm,
            st.offset_cm,
            rotates_about_center=st.rotates_about_center,
        )
        assert pmin[0] >= -1.0
        assert pmin[1] >= -1.0
        assert pmax[0] <= max_x + 1.0
        assert pmax[1] <= max_y + 1.0


def test_floor_count_matches_storeys():
    params = _default_params(storeys=3)
    assembly, _ = build_shell_assembly(params)
    floors = [
        p
        for p in assembly.placements
        if p.kind == "floor"
        and p.asset_id in ("shell_floor_slab", "floor")
        and "facade_shell" in p.tags
    ]
    assert len(floors) == 3


def test_south_has_punched_openings_not_solid_overlay():
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    assert count_window_placements(assembly, "south") >= 2
    south_piers = [
        p
        for p in assembly.placements
        if "face_south" in p.tags and "pier" in p.tags
    ]
    assert south_piers, "glazed south face should use pier grammar, not one solid slab"
    assert count_modular_window_kits(assembly) == 0


def test_build_from_params_defaults_to_shell_mode():
    params = _default_params()
    _m, _p, assembly, report, _out = build_from_params(
        params, validate_assembly=False
    )
    assert assembly is not None
    assert count_exterior_shell_walls(assembly) > 0
    assert count_modular_window_kits(assembly) == 0
    assert not report.critical


def test_shell_door_is_inset_slab_not_kit():
    params = _default_params(storeys=2, wealth=4)
    assembly, _ = build_shell_assembly(params)
    assert count_shell_doors(assembly, "south") == 1
    doors = [p for p in assembly.placements if p.asset_id == SHELL_DOOR_ASSET]
    assert len(doors) == 1
    assert doors[0].kind == "prop"
    assert count_modular_window_kits(assembly) == 0


def test_chimney_stubs_when_wealthy():
    params = _default_params(wealth=4, storeys=3)
    assembly, _ = build_shell_assembly(params)
    assert count_chimney_stubs(assembly) >= 1


def test_window_muntins_on_glazed_faces():
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    assert count_muntin_placements(assembly) >= 4

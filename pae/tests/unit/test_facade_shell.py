"""Unit tests — continuous facade shell assembly."""

from __future__ import annotations

from pae.contract import MODULE_CM, placement_world_aabb
from pae.facade_grammar import FacadeParams, build_from_params
from pae.facade_shell import (
    SHELL_WALL_ASSET,
    build_shell_assembly,
    count_exterior_shell_walls,
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


def test_shell_exterior_wall_count_bounded():
    params = _default_params(storeys=4)
    assembly, _ = build_shell_assembly(params)
    bays_x = 3  # 10 m → 3 bays
    storeys = 4
    shell_walls = count_exterior_shell_walls(assembly)
    modular_upper_bound = bays_x * storeys * 4
    assert shell_walls == 4 * storeys
    assert shell_walls < modular_upper_bound // 2


def test_no_partition_grid_on_exterior():
    params = _default_params()
    assembly, _ = build_shell_assembly(params)
    exterior_shell = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET and "exterior" in p.tags
    ]
    assert len(exterior_shell) == 4 * 3  # 3 storeys × 4 faces
    south = [p for p in exterior_shell if "face_south" in p.tags]
    assert len(south) == 3
    assert all(p.size_cm[1] >= 3 * MODULE_CM for p in south)


def test_party_wall_face_has_no_windows():
    params = _default_params(row_context="end_left")
    assembly, _ = build_shell_assembly(params)
    assert count_window_placements(assembly, "west") == 0
    west_walls = [
        p for p in assembly.placements if p.asset_id == SHELL_WALL_ASSET and "face_west" in p.tags
    ]
    assert west_walls
    assert all("party_wall" in p.tags or "blind" in p.tags for p in west_walls)


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


def test_build_from_params_defaults_to_shell_mode():
    params = _default_params()
    _m, _p, assembly, report, _out = build_from_params(
        params, validate_assembly=False
    )
    assert assembly is not None
    assert count_exterior_shell_walls(assembly) > 0
    assert not report.critical

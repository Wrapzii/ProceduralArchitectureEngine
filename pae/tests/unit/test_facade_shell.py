"""Unit tests — continuous facade shell assembly."""

from __future__ import annotations

from pae.contract import EAVE_OVERHANG_CM, MODULE_CM, STOREY_CM, WALL_T_CM, placement_world_aabb
from pae.export.manifest import placement_loc_cm
from pae.facade_grammar import (
    FacadeParams,
    build_from_params,
    load_archetype_shell_config,
    params_to_spec,
    params_to_style_overrides,
)
from pae.facade_shell import (
    SHELL_DOOR_ASSET,
    SHELL_INTERIOR_WALL_ASSET,
    SHELL_WINDOW_FRAME_ASSET,
    SHELL_WINDOW_GLASS_ASSET,
    SHELL_WALL_ASSET,
    build_shell_assembly,
    count_chimney_stubs,
    count_exterior_shell_walls,
    count_face_shell_wall_panels,
    count_floor_holes,
    count_interior_corridor_walls,
    count_modular_window_kits,
    count_muntin_placements,
    count_opening_cutters,
    count_pier_pieces,
    count_shell_gable_ends,
    count_shell_roof_slopes,
    count_shell_doors,
    count_stair_placements,
    count_stair_shaft_pieces,
    count_style_shell_props,
    count_window_frame_bars,
    count_window_glass_placements,
    count_window_placements,
    derive_shell_variation,
    shell_roof_placements,
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
    # Blind party wall: ONE continuous panel per storey (not pier grid).
    assert count_face_shell_wall_panels(assembly, "west") == 3
    assert all(p.size_cm[2] >= STOREY_CM - 1.0 for p in west_walls)


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


def test_south_one_shell_wall_per_storey_with_cutters():
    """Glazed south: one shell_wall_solid per storey, cutters not pier farm."""
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    assert count_window_placements(assembly, "south") >= 2
    assert count_face_shell_wall_panels(assembly, "south") == 2
    assert count_pier_pieces(assembly, "south") == 0
    assert count_opening_cutters(assembly, "south") >= 2
    assert count_modular_window_kits(assembly) == 0
    south_panels = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET
        and "face_south" in p.tags
        and "boolean_parent" in p.tags
    ]
    assert len(south_panels) == 2
    assert all(p.size_cm[1] >= 2 * MODULE_CM - 1.0 for p in south_panels)


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


def test_no_interior_corridor_wall_on_west_exterior():
    """Regression: shell_corridor doubled the west face at level 0."""
    params = _default_params(storeys=3, frontage_m=10.0, depth_m=8.0)
    assembly, _ = build_shell_assembly(params)
    assert count_interior_corridor_walls(assembly) == 0
    west_exterior = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET
        and "face_west" in p.tags
        and "exterior" in p.tags
    ]
    assert west_exterior
    interior_west = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_INTERIOR_WALL_ASSET
        and "face_west" in p.tags
        and "stair_shaft" in p.tags
    ]
    for ext in west_exterior:
        emin, emax = placement_world_aabb(
            ext.cell[0],
            ext.cell[1],
            ext.level,
            ext.yaw,
            ext.size_cm,
            ext.offset_cm,
        )
        for inner in interior_west:
            imin, imax = placement_world_aabb(
                inner.cell[0],
                inner.cell[1],
                inner.level,
                inner.yaw,
                inner.size_cm,
                inner.offset_cm,
            )
            # Shaft west wall must sit inside the footprint, not on the exterior skin.
            assert imin[0] >= emax[0] - 1.0, (
                f"shaft wall overlaps west exterior: inner x={imin[0]} ext x={emax[0]}"
            )


def test_shell_has_no_style_pack_balconies():
    params = _default_params(storeys=4, wealth=4, frontage_m=22.0, depth_m=12.0)
    assembly, _ = build_shell_assembly(params)
    assert count_style_shell_props(assembly) == 0


def test_stair_and_floor_hole_counts_match_storeys():
    for storeys in (2, 3, 4):
        params = _default_params(storeys=storeys, frontage_m=12.0, depth_m=10.0)
        assembly, _ = build_shell_assembly(params)
        assert count_stair_placements(assembly) == storeys - 1
        assert count_floor_holes(assembly) == storeys - 1
        assert count_stair_shaft_pieces(assembly) >= 3 * storeys


def test_stair_shaft_pieces_inside_footprint():
    from pae.facade_grammar import metres_to_bays

    params = _default_params(storeys=3, frontage_m=12.0, depth_m=10.0)
    assembly, _ = build_shell_assembly(params)
    bays_x = metres_to_bays(params.frontage_m)
    bays_y = metres_to_bays(params.depth_m)
    max_x = bays_x * MODULE_CM
    max_y = bays_y * MODULE_CM
    shaft = [p for p in assembly.placements if "stair_shaft" in p.tags]
    assert shaft
    for piece in shaft:
        pmin, pmax = placement_world_aabb(
            piece.cell[0],
            piece.cell[1],
            piece.level,
            piece.yaw,
            piece.size_cm,
            piece.offset_cm,
            rotates_about_center=piece.rotates_about_center,
        )
        assert pmin[0] >= -1.0
        assert pmin[1] >= -1.0
        assert pmax[0] <= max_x + 1.0
        assert pmax[1] <= max_y + 1.0


def test_hollow_window_frames_and_glass():
    """Regression: solid sash box filled the opening — must be rim + thin glass."""
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    glass_count = count_window_glass_placements(assembly)
    assert glass_count >= 2
    assert count_window_frame_bars(assembly, "south") == sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WINDOW_GLASS_ASSET and "face_south" in p.tags
    ) * 4
    glass = [p for p in assembly.placements if p.asset_id == SHELL_WINDOW_GLASS_ASSET]
    assert glass
    for pane in glass:
        sx, sy, sz = pane.size_cm
        assert sx <= 3.0, "glass must be a thin plane, not a solid fill"
        assert sy < MODULE_CM * _WINDOW_W_FRAC * 0.95
        assert sz < STOREY_CM * _WINDOW_H_FRAC * 0.95


def test_window_frame_bars_do_not_fill_opening():
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    frames = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WINDOW_FRAME_ASSET and "frame_bar" in p.tags
    ]
    assert frames
    max_face = max(f.size_cm[1] * f.size_cm[2] for f in frames)
    open_area = (MODULE_CM * 0.55) * (STOREY_CM * 0.58)
    assert max_face < open_area * 0.45, "no single bar should cover most of the opening"


# Module-level aperture fractions mirrored from facade_shell (import-safe).
_WINDOW_W_FRAC = 0.55
_WINDOW_H_FRAC = 0.58


def test_generate_facade_operator_uses_shell_mode_only():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "addon" / "operators" / "generate_ops.py"
    text = src.read_text(encoding="utf-8")
    facade_block = text.split("PAE_OT_generate_facade")[1].split("classes")[0]
    assert "build_building" in facade_block
    assert "instance_facade_shell" in facade_block
    assert "sync_assembly_preview(assembly)" not in facade_block
    assert "assemble_with_style_shell_and_detail" not in facade_block
    assert "run_full_pipeline" not in facade_block


def test_window_muntins_removed_from_shell():
    params = _default_params(storeys=2)
    assembly, _ = build_shell_assembly(params)
    assert count_muntin_placements(assembly) == 0


def _demo_user_params() -> FacadeParams:
    return _default_params(
        storeys=4,
        wealth=4,
        frontage_m=22.0,
        depth_m=12.0,
        row_context="end_left",
    )


def _shell_placement_bounds_targets(assembly):
    """Placements that must sit inside the footprint AABB (plus wall skin)."""
    for p in assembly.placements:
        aid = p.asset_id
        if aid in (
            SHELL_WALL_ASSET,
            SHELL_INTERIOR_WALL_ASSET,
            SHELL_WINDOW_FRAME_ASSET,
            SHELL_WINDOW_GLASS_ASSET,
        ):
            yield p
        elif aid == SHELL_DOOR_ASSET:
            yield p
        elif "stair_shaft" in p.tags:
            yield p


def test_user_demo_placements_inside_footprint():
    """Regression: south sash Y=2100 and shaft x=3200+ when footprint is 2400×1200."""
    params = _demo_user_params()
    assembly, _ = build_shell_assembly(params)
    spec_bays_x = int(round(22.0 / (MODULE_CM / 100.0)))
    spec_bays_y = int(round(12.0 / (MODULE_CM / 100.0)))
    width = spec_bays_x * MODULE_CM
    depth = spec_bays_y * MODULE_CM
    outliers = []
    for p in _shell_placement_bounds_targets(assembly):
        loc = placement_loc_cm(p)
        if not (
            -WALL_T_CM <= loc[0] <= width + WALL_T_CM
            and -WALL_T_CM <= loc[1] <= depth + WALL_T_CM
        ):
            outliers.append((p.piece_id, loc))
    assert outliers == [], f"out-of-footprint placements: {outliers[:8]}"


def test_south_window_frames_along_frontage_not_depth():
    params = _demo_user_params()
    assembly, _ = build_shell_assembly(params)
    width = int(round(22.0 / (MODULE_CM / 100.0))) * MODULE_CM
    frames = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WINDOW_FRAME_ASSET
        and "face_south" in p.tags
        and "frame_bar" in p.tags
    ]
    assert frames
    for bar in frames:
        loc = placement_loc_cm(bar)
        assert 0.0 <= loc[0] <= width + 1.0, bar.piece_id
        assert loc[1] <= WALL_T_CM + 5.0, bar.piece_id


def test_shell_roof_is_pitched_shell_not_catalog_slope():
    params = _demo_user_params()
    assembly, _ = build_shell_assembly(params)
    assert count_shell_roof_slopes(assembly) == 2
    assert count_shell_gable_ends(assembly) == 1  # end_left — east gable only
    assert not any(p.asset_id == "roof_pitched_slope" for p in assembly.placements)


def test_wealth_one_flat_roof_no_chimney():
    params = _default_params(wealth=1, storeys=3, archetype="georgian_merchant")
    assembly, _ = build_shell_assembly(params)
    assert count_chimney_stubs(assembly) == 0
    slabs = [p for p in assembly.placements if p.asset_id == "shell_roof_slab"]
    assert slabs
    assert count_shell_roof_slopes(assembly) == 0


def test_wealth_five_twin_chimneys():
    params = _default_params(wealth=5, storeys=3, seed=9001)
    assembly, _ = build_shell_assembly(params)
    assert count_chimney_stubs(assembly) == 2


def test_seed_determinism_same_placement_counts():
    p1 = _default_params(seed=4242, wealth=3)
    p2 = FacadeParams(**{**p1.__dict__})
    a1, _ = build_shell_assembly(p1)
    a2, _ = build_shell_assembly(p2)
    assert count_opening_cutters(a1, "south") == count_opening_cutters(a2, "south")
    assert count_chimney_stubs(a1) == count_chimney_stubs(a2)


def test_seed_variation_differs_door_or_chimneys():
    params_a = _default_params(seed=100, wealth=5, storeys=3)
    params_b = _default_params(seed=999, wealth=5, storeys=3)
    spec = params_to_spec(params_a)
    cfg = load_archetype_shell_config(params_a.archetype, wealth=5)
    overrides = params_to_style_overrides(params_a)
    var_a = derive_shell_variation(
        params_a,
        bays_x=spec.footprint.bays_x,
        bays_y=spec.footprint.bays_y,
        storeys=spec.storeys,
        glazed_faces=("south", "north", "east", "west"),
        style_overrides=overrides,
        shell_cfg=cfg,
    )
    var_b = derive_shell_variation(
        params_b,
        bays_x=spec.footprint.bays_x,
        bays_y=spec.footprint.bays_y,
        storeys=spec.storeys,
        glazed_faces=("south", "north", "east", "west"),
        style_overrides=params_to_style_overrides(params_b),
        shell_cfg=cfg,
    )
    a_asm, _ = build_shell_assembly(params_a)
    b_asm, _ = build_shell_assembly(params_b)
    differs = (
        var_a.door_bay != var_b.door_bay
        or var_a.window_skip != var_b.window_skip
        or var_a.chimney_anchors != var_b.chimney_anchors
        or count_opening_cutters(a_asm) != count_opening_cutters(b_asm)
    )
    assert differs


def test_wealth_one_fewer_south_windows_than_five():
    low, _ = build_shell_assembly(_default_params(wealth=1, seed=55))
    high, _ = build_shell_assembly(_default_params(wealth=5, seed=55))
    assert count_window_placements(low, "south") < count_window_placements(high, "south")


def test_mid_terrace_party_walls_blind():
    params = _default_params(row_context="mid", storeys=3)
    assembly, _ = build_shell_assembly(params)
    assert count_window_placements(assembly, "west") == 0
    assert count_window_placements(assembly, "east") == 0
    assert count_window_placements(assembly, "south") > 0
    assert count_window_placements(assembly, "north") > 0


def test_archetype_civic_loads_distinct_window_frac():
    civic = load_archetype_shell_config("civic")
    manor = load_archetype_shell_config("manor")
    assert civic.roof_kind == "flat"
    assert civic.window_w_frac != manor.window_w_frac

def test_shell_roof_aabb_within_footprint_overhang():
    params = _demo_user_params()
    assembly, _ = build_shell_assembly(params)
    width = int(round(22.0 / (MODULE_CM / 100.0))) * MODULE_CM
    depth = int(round(12.0 / (MODULE_CM / 100.0))) * MODULE_CM
    oh = EAVE_OVERHANG_CM
    tol = 1.0
    for roof in shell_roof_placements(assembly):
        if roof.asset_id not in ("shell_roof_slope", "shell_gable_end"):
            continue
        pmin, pmax = placement_world_aabb(
            roof.cell[0],
            roof.cell[1],
            roof.level,
            roof.yaw,
            roof.size_cm,
            roof.offset_cm,
        )
        assert pmin[0] >= -oh - tol, roof.piece_id
        assert pmin[1] >= -oh - tol, roof.piece_id
        assert pmax[0] <= width + oh + tol, roof.piece_id
        assert pmax[1] <= depth + oh + tol, roof.piece_id

"""Modular kit v1 manifest contract (no Blender required)."""

from __future__ import annotations

from tools.build_modular_kit_blender import (
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    build_manifest_dict,
    kit_piece_catalog,
    manifest_aliases,
)


def test_kit_piece_count_in_v1_budget():
    pieces = kit_piece_catalog()
    assert 30 <= len(pieces) <= 40


def test_wall_modules_match_pae_contract():
    solid = next(p for p in kit_piece_catalog() if p.name == "SM_W_Solid_Stone")
    assert solid.dims_cm == (WALL_T_CM, MODULE_CM, STOREY_CM)
    assert solid.origin == "min_corner"
    assert solid.aabb_min_cm == (0.0, 0.0, 0.0)


def test_manifest_has_fbx_paths_and_aliases():
    manifest = build_manifest_dict(kit_piece_catalog())
    assert manifest["module_cm"] == MODULE_CM
    assert manifest["storey_cm"] == STOREY_CM
    names = {e["name"] for e in manifest["pieces"]}
    for alias in manifest_aliases():
        assert alias in names
    fbx_entries = [e for e in manifest["pieces"] if "fbx" in e and not e.get("alias_of")]
    assert len(fbx_entries) == manifest["piece_count"]
    assert all(e["fbx"].startswith("Saved/kit/fbx/") for e in fbx_entries)

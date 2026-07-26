"""Dress PAE assemblies with themed modular kit meshes (Saved/kit/fbx/SM_*.fbx).

Maps ``pae`` placement ``asset_id`` values to kit piece names from
``tools/build_modular_kit_blender.kit_piece_catalog``, then instances the
themed builder meshes at PAE placement transforms.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
KIT_DIR = PAE_ROOT / "Saved" / "kit"
FBX_DIR = KIT_DIR / "fbx"
MANIFEST_PATH = KIT_DIR / "kit_manifest.json"
CM_TO_M = 0.01

STYLE_WALL_KIT: Dict[str, str] = {
    "townhouse": "SM_W_Solid_Timber",
    "rustic": "SM_W_Solid_Timber",
    "medieval": "SM_W_Solid_Stone",
    "keep": "SM_W_Solid_Stone",
    "civic": "SM_W_Solid_Plaster",
    "manor": "SM_W_Solid_Stone",
    "gothic_academy": "SM_W_Solid_Stone",
    "wizard_academy": "SM_W_Solid_Stone",
}

PAE_TO_KIT: Dict[str, str] = {
    "wall_plain": "SM_W_Solid_Plaster",
    "wall_window": "SM_W_Window_Square",
    "wall_window_cross": "SM_W_Window_Cross",
    "wall_window_lancet": "SM_W_Window_Lancet",
    "wall_window_round": "SM_W_Window_Round",
    "wall_door": "SM_W_Door_Plain",
    "wall_door_arched": "SM_W_Door_Arched",
    "wall_door_double": "SM_W_Door_Double",
    "floor": "SM_F_Full",
    "floor_hole": "SM_F_Hole",
    "stair_straight": "SM_S_Straight",
    "stair_landing": "SM_S_Landing",
    "roof_pitched_slope": "SM_R_PitchedSlope",
    "roof_gable_infill": "SM_R_GableInfill",
    "roof_hip": "SM_R_Hip",
    "roof_flat": "SM_R_FlatParapet",
    "spire_conical": "SM_R_ConeCap",
    "ground_plinth": "SM_T_Plith",
    "ground": "SM_T_Plith",
    "band_course": "SM_T_String",
    "coping_cap": "SM_T_Cornice",
    "pilaster": "SM_T_Pilaster",
    "band_pilaster": "SM_T_Quoin",
    "bargeboard": "SM_T_Bargeboard",
    "steps_external": "SM_P_Steps",
    "porch_slab": "SM_P_Slab",
    "porch_roof": "SM_P_Canopy",
    "porch_post": "SM_P_Post",
    "balcony_deck": "SM_B_Deck",
    "railing_metal": "SM_B_Rail",
    "balcony_bracket": "SM_B_Bracket",
    "planter_wall": "SM_Site_Planter",
    "forecourt_wall": "SM_Site_Forecourt",
    "tower_arc_quarter": "SM_Twr_ArcQuarter",
    "tower_crown": "SM_Twr_Crown",
    "tower_cap": "SM_Twr_ConeCap",
    "paving_cobble": "SM_F_Full",
    "sidewalk_slab": "SM_F_Full",
    "kerb_edge": "SM_T_String",
}


def _style_from_tags(tags: frozenset) -> str:
    for t in tags:
        if isinstance(t, str) and t.startswith("style:"):
            return t.split(":", 1)[1]
    return "townhouse"


def kit_piece_for_placement(
    asset_id: str,
    *,
    kind: str = "wall",
    style: str = "townhouse",
) -> str:
    if asset_id in PAE_TO_KIT:
        return PAE_TO_KIT[asset_id]
    if "door" in asset_id:
        if "arched" in asset_id or "gothic" in asset_id:
            return "SM_W_Door_Arched"
        if "double" in asset_id or "grand" in asset_id:
            return "SM_W_Door_Double"
        return "SM_W_Door_Plain"
    if "window" in asset_id:
        if "lancet" in asset_id or "gothic" in asset_id:
            return "SM_W_Window_Lancet"
        if "round" in asset_id:
            return "SM_W_Window_Round"
        if "cross" in asset_id:
            return "SM_W_Window_Cross"
        return "SM_W_Window_Square"
    if kind == "roof" or asset_id.startswith("roof_") or asset_id.startswith("spire_"):
        if "hip" in asset_id:
            return "SM_R_Hip"
        if "flat" in asset_id:
            return "SM_R_FlatParapet"
        if "gable" in asset_id:
            return "SM_R_GableInfill"
        if "cone" in asset_id or "spire" in asset_id:
            return "SM_R_ConeCap"
        return "SM_R_PitchedSlope"
    if kind in ("floor", "ground") or asset_id.startswith("floor"):
        return "SM_F_Full"
    if kind == "stair" or asset_id.startswith("stair"):
        return "SM_S_Straight"
    if kind == "tower_arc" or "tower_arc" in asset_id:
        return "SM_Twr_ArcQuarter"
    if "tower_crown" in asset_id:
        return "SM_Twr_Crown"
    if "tower_cap" in asset_id:
        return "SM_Twr_ConeCap"
    return STYLE_WALL_KIT.get(style, "SM_W_Solid_Stone")


def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    from tools.build_modular_kit_blender import build_manifest_dict, kit_piece_catalog

    return build_manifest_dict(kit_piece_catalog())


def ensure_kit_manifest() -> Path:
    if not MANIFEST_PATH.is_file():
        from tools.build_modular_kit_blender import build_manifest_dict, kit_piece_catalog

        KIT_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(build_manifest_dict(kit_piece_catalog()), indent=2),
            encoding="utf-8",
        )
    return MANIFEST_PATH


def instance_assembly_kit(
    assembly,
    *,
    label: str = "street",
    target_coll=None,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    proto_coll_name: str = "KIT_StreetProtos",
) -> Tuple[int, Dict[str, int]]:
    """Instance themed kit meshes for each PAE placement."""
    from pae.blender_build import (
        is_spanning_floor_deck,
        placement_instance_local_size_cm,
        placement_instance_scale_cm,
        _mesh_for_notched_roof,
        _mesh_for_spanning_floor_deck,
    )
    from pae.export.manifest import placement_loc_cm
    from pae.primitives import bpy_util
    from pae.primitives.catalog import catalog_by_id

    bpy_util.require_bpy()
    import bpy
    from mathutils import Vector

    from tools.build_modular_kit_blender import (
        _build_mesh_for_piece,
        _ensure_materials,
        kit_piece_catalog,
    )

    ensure_kit_manifest()
    piece_by_name = {p.name: p for p in kit_piece_catalog()}
    catalog = catalog_by_id()
    coll = target_coll
    if coll is None:
        coll = bpy.data.collections.new("PAE_CityStreet")
        bpy.context.scene.collection.children.link(coll)

    proto_root = bpy.data.collections.get(proto_coll_name)
    if proto_root is None:
        proto_root = bpy.data.collections.new(proto_coll_name)
        bpy.context.scene.collection.children.link(proto_root)

    mats = _ensure_materials(bpy)
    cache: Dict[str, Any] = {}
    kit_used: Dict[str, int] = {}
    count = 0
    ox, oy, oz = offset_m

    hole_placements = [
        hp for hp in assembly.placements if getattr(hp, "asset_id", None) == "floor_hole"
    ]
    roof_hole_placements = [
        hp for hp in assembly.placements if getattr(hp, "asset_id", None) == "roof_hole"
    ]

    def _proto_for_kit(kit_name: str):
        if kit_name in cache:
            return cache[kit_name]
        piece = piece_by_name.get(kit_name)
        if piece is None:
            return None
        sub = bpy.data.collections.get(f"{proto_coll_name}_{piece.collection}")
        if sub is None:
            sub = bpy.data.collections.new(f"{proto_coll_name}_{piece.collection}")
            proto_root.children.link(sub)
        obj = _build_mesh_for_piece(piece, bpy, sub, mats)
        obj.hide_set(True)
        obj.hide_render = True
        obj.name = f"KIT_Proto_{kit_name}"
        cache[kit_name] = obj
        return obj

    for p in assembly.placements:
        if p.asset_id in ("floor_hole", "roof_hole") or (
            "non_rendering_aperture_proxy" in p.tags
        ):
            continue

        style = _style_from_tags(getattr(p, "tags", frozenset()))
        kit_name = kit_piece_for_placement(
            p.asset_id, kind=getattr(p, "kind", "wall"), style=style
        )

        if is_spanning_floor_deck(p) and hole_placements:
            proto = _mesh_for_spanning_floor_deck(p, hole_placements, cache=cache)
            sx = sy = sz = 1.0
        elif getattr(p, "kind", None) == "roof" and roof_hole_placements:
            proto = _mesh_for_notched_roof(p, roof_hole_placements, cache=cache)
            if proto is not None:
                sx = sy = sz = 1.0
            else:
                proto = _proto_for_kit(kit_name)
                sx, sy, sz = placement_instance_scale_cm(p)
        else:
            proto = _proto_for_kit(kit_name)
            if proto is None:
                from pae.blender_build import _mesh_for_asset

                proto = _mesh_for_asset(p.asset_id, tuple(p.size_cm), cache=cache)
            sx, sy, sz = placement_instance_scale_cm(p)

        if proto is None:
            continue

        loc_cm = placement_loc_cm(p)
        loc_m = (
            loc_cm[0] * CM_TO_M + ox,
            loc_cm[1] * CM_TO_M + oy,
            loc_cm[2] * CM_TO_M + oz,
        )
        desc = catalog.get(p.asset_id)
        if (
            bool(getattr(p, "rotates_about_center", False))
            and desc is not None
            and getattr(desc, "origin", "min_corner") != "center"
        ):
            local_sx, local_sy, _ = placement_instance_local_size_cm(p)
            angle = math.radians(float(p.yaw))
            half_x = local_sx * 0.5 * CM_TO_M
            half_y = local_sy * 0.5 * CM_TO_M
            rotated_half_x = math.cos(angle) * half_x - math.sin(angle) * half_y
            rotated_half_y = math.sin(angle) * half_x + math.cos(angle) * half_y
            loc_m = (
                loc_m[0] - rotated_half_x,
                loc_m[1] - rotated_half_y,
                loc_m[2],
            )

        inst = proto.copy()
        inst.data = proto.data
        inst.name = f"PAE_{label}_{p.piece_id}"
        inst.hide_set(False)
        inst.hide_render = False
        inst.location = Vector(loc_m)
        inst.scale = (sx * CM_TO_M, sy * CM_TO_M, sz * CM_TO_M)
        inst.rotation_euler = (0.0, 0.0, math.radians(float(p.yaw)))
        coll.objects.link(inst)
        kit_used[kit_name] = kit_used.get(kit_name, 0) + 1
        count += 1

    return count, kit_used

#!/usr/bin/env python3
"""Build RE modular kit v1 — real Blender meshes (PAE-contract dimensions).

Creates ``Saved/kit/modular_kit_v1.blend``, per-piece FBX under ``Saved/kit/fbx/``,
``Saved/kit/kit_manifest.json``, and a board screenshot (≤1280px).

Usage::

    blender --background --python tools/build_modular_kit_blender.py
    python tools/build_modular_kit_blender.py --dry-run

Does **not** modify ``pae/blender_build.py`` or PAE engine code.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

from pae.contract import (  # noqa: E402
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
)

KIT_DIR = PAE_ROOT / "Saved" / "kit"
FBX_DIR = KIT_DIR / "fbx"
BLEND_PATH = KIT_DIR / "modular_kit_v1.blend"
MANIFEST_PATH = KIT_DIR / "kit_manifest.json"
BOARD_SHOT = PAE_ROOT / "Saved" / "Screenshots" / "modular_kit_v1_board.png"
CLOSEUP_DIR = PAE_ROOT / "Saved" / "Screenshots"
THEME_STRIP_SHOT = CLOSEUP_DIR / "modular_kit_v1_theme_strip.png"

CM_TO_M = 0.01
BOARD_GAP_M = 1.2  # metres between pieces AFTER cm→m apply
BOARD_GAP_CM = 120.0  # used only if meshes remain in cm space
BOARD_MAX_EDGE = 1280
CLOSEUP_MAX = 640
CLOSEUP_GAP_CM = 80.0
CLOSEUP_FAMILIES = (
    "KIT_Walls",
    "KIT_Openings",
    "KIT_Floors_Stairs",
    "KIT_Roofs",
)

# Soft lookdev ground — RE anime-medieval city kit (not greybox proof colors).
WORLD_BG_RGBA = (0.12, 0.13, 0.16, 1.0)

# Stable UE material slot names (MI_* bound in editor later).
SLOT_WALL = "M_Wall_Base"          # warm cut stone (default city wall)
SLOT_WALL_PLASTER = "M_Wall_Plaster"
SLOT_TRIM = "M_Trim"
SLOT_ROOF = "M_Roof"               # terracotta tile
SLOT_ROOF_SLATE = "M_Roof_Slate"   # slate-blue tower cones
SLOT_WOOD = "M_Wood"
SLOT_GLASS = "M_Glass"
SLOT_METAL = "M_Metal"
SLOT_STONE = "M_Stone_Trim"

# Flat slot swatches for kit lookdev only — Unreal owns real MI_* textures.
# Geometry carries the theme (courses, timber, tile ribs, surrounds), not painted patterns.
SLOT_LOOK: Dict[str, Tuple[Tuple[float, float, float, float], float, float]] = {
    SLOT_WALL: ((0.70, 0.58, 0.44, 1.0), 0.85, 0.0),
    SLOT_WALL_PLASTER: ((0.92, 0.88, 0.80, 1.0), 0.75, 0.0),
    SLOT_TRIM: ((0.78, 0.72, 0.62, 1.0), 0.75, 0.0),
    SLOT_ROOF: ((0.72, 0.22, 0.14, 1.0), 0.70, 0.0),
    SLOT_ROOF_SLATE: ((0.26, 0.36, 0.50, 1.0), 0.55, 0.05),
    SLOT_WOOD: ((0.24, 0.14, 0.08, 1.0), 0.85, 0.0),
    SLOT_GLASS: ((0.65, 0.82, 0.90, 0.30), 0.05, 0.0),
    SLOT_METAL: ((0.40, 0.38, 0.35, 1.0), 0.45, 0.5),
    SLOT_STONE: ((0.55, 0.48, 0.38, 1.0), 0.88, 0.0),
}

Vec3 = Tuple[float, float, float]


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass(frozen=True)
class KitPiece:
    name: str
    collection: str
    dims_cm: Vec3
    pae_id: Optional[str] = None
    slots: Tuple[str, ...] = (SLOT_WALL,)
    sockets: Tuple[Dict[str, Any], ...] = ()
    origin: str = "min_corner"
    aabb_min_cm: Vec3 = (0.0, 0.0, 0.0)
    notes: str = ""
    builder: Optional[str] = None  # custom builder key


def _wall_sockets() -> Tuple[Dict[str, Any], ...]:
    return (
        {
            "name": "end_a",
            "pos_cm": [WALL_T_CM * 0.5, 0.0, STOREY_CM * 0.5],
            "normal": [0.0, -1.0, 0.0],
        },
        {
            "name": "end_b",
            "pos_cm": [WALL_T_CM * 0.5, MODULE_CM, STOREY_CM * 0.5],
            "normal": [0.0, 1.0, 0.0],
        },
        {
            "name": "face_out",
            "pos_cm": [0.0, MODULE_CM * 0.5, STOREY_CM * 0.5],
            "normal": [-1.0, 0.0, 0.0],
        },
    )


def _floor_sockets() -> Tuple[Dict[str, Any], ...]:
    return (
        {
            "name": "top",
            "pos_cm": [MODULE_CM * 0.5, MODULE_CM * 0.5, FLOOR_T_CM],
            "normal": [0.0, 0.0, 1.0],
        },
    )


def _tower_sockets() -> Tuple[Dict[str, Any], ...]:
    return (
        {
            "name": "bottom",
            "pos_cm": [0.0, 0.0, 0.0],
            "normal": [0.0, 0.0, -1.0],
        },
    )


def kit_piece_catalog() -> List[KitPiece]:
    """v1 kit — themed RE city meshes (stone / timber / plaster + terracotta / slate)."""
    wall_dims = (WALL_T_CM, MODULE_CM, STOREY_CM)
    ws = _wall_sockets()
    fs = _floor_sockets()
    ts = _tower_sockets()
    return [
        # --- Walls: three skin themes + corner ---
        KitPiece(
            "SM_W_Solid_Stone",
            "KIT_Walls",
            wall_dims,
            slots=(SLOT_WALL,),
            sockets=ws,
            builder="stone_coursed",
            notes="Ashlar courses as mesh relief (UE textures later).",
        ),
        KitPiece(
            "SM_W_Solid_Plaster",
            "KIT_Walls",
            wall_dims,
            pae_id="wall_plain",
            slots=(SLOT_WALL_PLASTER,),
            sockets=ws,
            notes="Smooth plaster bay.",
        ),
        KitPiece(
            "SM_W_Solid_Timber",
            "KIT_Walls",
            wall_dims,
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD),
            sockets=ws,
            builder="timber_wall",
            notes="Half-timber: plaster infill + proud oak frame (mesh).",
        ),
        KitPiece(
            "SM_W_Corner",
            "KIT_Walls",
            (MODULE_CM, MODULE_CM, STOREY_CM),
            slots=(SLOT_WALL,),
            sockets=ws,
            builder="corner_stone_coursed",
            notes="L-corner with ashlar course relief.",
        ),
        # --- Openings: plaster + timber/stone surrounds (readable theme) ---
        KitPiece(
            "SM_W_Window_Square",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_window",
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD, SLOT_GLASS),
            sockets=ws,
            builder="opening_themed",
            notes="Square window with timber surround + glass.",
        ),
        KitPiece(
            "SM_W_Window_Cross",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_window_cross",
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD, SLOT_GLASS),
            sockets=ws,
            builder="opening_themed",
        ),
        KitPiece(
            "SM_W_Window_Lancet",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_window_lancet",
            slots=(SLOT_WALL, SLOT_STONE, SLOT_GLASS),
            sockets=ws,
            builder="opening_themed",
            notes="Lancet in cut stone + limestone surround.",
        ),
        KitPiece(
            "SM_W_Window_Round",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_window_round",
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD, SLOT_GLASS),
            sockets=ws,
            builder="opening_themed",
        ),
        KitPiece(
            "SM_W_Door_Plain",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_door",
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD),
            sockets=ws,
            builder="opening_themed",
        ),
        KitPiece(
            "SM_W_Door_Arched",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_door_arched",
            slots=(SLOT_WALL, SLOT_STONE, SLOT_WOOD),
            sockets=ws,
            builder="opening_themed",
        ),
        KitPiece(
            "SM_W_Door_Double",
            "KIT_Openings",
            wall_dims,
            pae_id="wall_door_double",
            slots=(SLOT_WALL_PLASTER, SLOT_WOOD),
            sockets=ws,
            builder="opening_themed",
        ),
        # --- Floors / stairs (4) ---
        KitPiece(
            "SM_F_Full",
            "KIT_Floors_Stairs",
            (MODULE_CM, MODULE_CM, FLOOR_T_CM),
            pae_id="floor",
            slots=(SLOT_STONE,),
            sockets=fs,
        ),
        KitPiece(
            "SM_F_Hole",
            "KIT_Floors_Stairs",
            (MODULE_CM, MODULE_CM, FLOOR_T_CM),
            pae_id="floor_hole",
            slots=(SLOT_STONE,),
            sockets=fs,
        ),
        KitPiece(
            "SM_S_Straight",
            "KIT_Floors_Stairs",
            (MODULE_CM * 2, MODULE_CM, STOREY_CM),
            pae_id="stair_straight",
            slots=(SLOT_STONE, SLOT_WOOD),
            sockets=fs,
        ),
        KitPiece(
            "SM_S_Landing",
            "KIT_Floors_Stairs",
            (MODULE_CM, MODULE_CM, 45.0),
            pae_id="stair_landing",
            slots=(SLOT_STONE,),
            sockets=fs,
        ),
        # --- Roofs (5) ---
        KitPiece(
            "SM_R_PitchedSlope",
            "KIT_Roofs",
            (MODULE_CM, MODULE_CM, 240.0),
            pae_id="roof_pitched_slope",
            slots=(SLOT_ROOF, SLOT_WOOD),
            builder="roof_pitched_themed",
            notes="Terracotta pitch + timber eave/ridge.",
        ),
        KitPiece(
            "SM_R_GableInfill",
            "KIT_Roofs",
            (MODULE_CM, MODULE_CM, 240.0),
            pae_id="roof_gable_infill",
            slots=(SLOT_WALL, SLOT_ROOF),
        ),
        KitPiece(
            "SM_R_Hip",
            "KIT_Roofs",
            (MODULE_CM, MODULE_CM, 240.0),
            pae_id="roof_hip",
            slots=(SLOT_ROOF,),
        ),
        KitPiece(
            "SM_R_FlatParapet",
            "KIT_Roofs",
            (MODULE_CM, MODULE_CM, FLOOR_T_CM),
            pae_id="roof_flat",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_R_ConeCap",
            "KIT_Roofs",
            (MODULE_CM, MODULE_CM, 700.0),
            pae_id="spire_conical",
            slots=(SLOT_ROOF_SLATE,),
            origin="center",
            aabb_min_cm=(0.0, 0.0, 0.0),
            builder="cone_cap_themed",
            notes="Slate cone + mesh shingle ring relief.",
        ),
        # --- Trim (6) ---
        KitPiece(
            "SM_T_Plith",
            "KIT_Trim",
            (MODULE_CM, MODULE_CM, FLOOR_T_CM),
            pae_id="ground_plinth",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_T_String",
            "KIT_Trim",
            (WALL_T_CM * 0.25, MODULE_CM, STOREY_CM * 0.07),
            pae_id="band_course",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_T_Cornice",
            "KIT_Trim",
            (WALL_T_CM * 1.3, MODULE_CM, STOREY_CM * 0.045),
            pae_id="coping_cap",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_T_Pilaster",
            "KIT_Trim",
            (30.0, 88.0, STOREY_CM),
            pae_id="pilaster",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_T_Quoin",
            "KIT_Trim",
            (WALL_T_CM * 0.25, MODULE_CM * 0.10, STOREY_CM),
            pae_id="band_pilaster",
            slots=(SLOT_STONE,),
            notes="Vertical quoin strip (band_pilaster profile).",
        ),
        KitPiece(
            "SM_T_Bargeboard",
            "KIT_Trim",
            (21.0, MODULE_CM, 63.0),
            pae_id="bargeboard",
            slots=(SLOT_WOOD,),
        ),
        # --- Porch (4) ---
        KitPiece(
            "SM_P_Steps",
            "KIT_Porch_Balcony",
            (MODULE_CM, MODULE_CM, 63.0),
            pae_id="steps_external",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_P_Slab",
            "KIT_Porch_Balcony",
            (220.0, 380.0, 42.0),
            pae_id="porch_slab",
            slots=(SLOT_STONE,),
            notes="Sub-module porch deck (style_shell; not full 400 bay).",
        ),
        KitPiece(
            "SM_P_Canopy",
            "KIT_Porch_Balcony",
            (220.0, 392.0, 21.0),
            pae_id="porch_roof",
            slots=(SLOT_ROOF, SLOT_WOOD),
            notes="Awning slab + timber fascia.",
        ),
        KitPiece(
            "SM_P_Post",
            "KIT_Porch_Balcony",
            (48.0, 48.0, 192.5),
            pae_id="porch_post",
            slots=(SLOT_WOOD,),
        ),
        # --- Balcony (3) ---
        KitPiece(
            "SM_B_Deck",
            "KIT_Porch_Balcony",
            (280.0, 380.0, 21.0),
            pae_id="balcony_deck",
            slots=(SLOT_WOOD,),
            notes="Functional deck; sub-module footprint per style_shell.",
        ),
        KitPiece(
            "SM_B_Rail",
            "KIT_Porch_Balcony",
            (10.8, MODULE_CM, 105.0),
            pae_id="railing_metal",
            slots=(SLOT_METAL,),
        ),
        KitPiece(
            "SM_B_Bracket",
            "KIT_Porch_Balcony",
            (112.0, 48.0, 98.0),
            pae_id="balcony_bracket",
            slots=(SLOT_WOOD, SLOT_STONE),
        ),
        # --- Site (2) ---
        KitPiece(
            "SM_Site_Planter",
            "KIT_Site",
            (51.0, MODULE_CM, 77.0),
            pae_id="planter_wall",
            slots=(SLOT_STONE,),
        ),
        KitPiece(
            "SM_Site_Forecourt",
            "KIT_Site",
            (43.2, MODULE_CM, 112.0),
            pae_id="forecourt_wall",
            slots=(SLOT_STONE,),
        ),
        # --- Tower (3) ---
        KitPiece(
            "SM_Twr_ArcQuarter",
            "KIT_Tower",
            (MODULE_CM * 2, MODULE_CM * 2, STOREY_CM),
            pae_id="tower_arc_quarter",
            slots=(SLOT_WALL,),
            origin="center",
            aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
            sockets=ts,
        ),
        KitPiece(
            "SM_Twr_Crown",
            "KIT_Tower",
            (MODULE_CM * 2, MODULE_CM * 2, STOREY_CM * 0.20),
            pae_id="tower_crown",
            slots=(SLOT_STONE,),
            origin="center",
            aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
            sockets=ts,
        ),
        KitPiece(
            "SM_Twr_ConeCap",
            "KIT_Tower",
            (MODULE_CM * 2, MODULE_CM * 2, STOREY_CM * 0.85),
            pae_id="tower_cap",
            slots=(SLOT_ROOF_SLATE,),
            origin="center",
            aabb_min_cm=(-MODULE_CM, -MODULE_CM, 0.0),
            sockets=ts,
        ),
    ]


def manifest_aliases() -> Dict[str, str]:
    return {
        "SM_W_DoorBay": "SM_W_Solid_Stone",
        "SM_W_WindowBay": "SM_W_Solid_Stone",
        "SM_W_Solid": "SM_W_Solid_Stone",
    }


def piece_to_manifest_entry(piece: KitPiece, *, fbx_rel: str) -> Dict[str, Any]:
    return {
        "name": piece.name,
        "collection": piece.collection,
        "dims_cm": {"x": piece.dims_cm[0], "y": piece.dims_cm[1], "z": piece.dims_cm[2]},
        "pae_id": piece.pae_id,
        "origin": piece.origin,
        "aabb_min_cm": {
            "x": piece.aabb_min_cm[0],
            "y": piece.aabb_min_cm[1],
            "z": piece.aabb_min_cm[2],
        },
        "material_slots": list(piece.slots),
        "sockets": list(piece.sockets),
        "fbx": fbx_rel,
        "notes": piece.notes,
    }


def build_manifest_dict(pieces: Sequence[KitPiece]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for p in pieces:
        rel = f"Saved/kit/fbx/{p.name}.fbx"
        entries.append(piece_to_manifest_entry(p, fbx_rel=rel))
    for alias, target in manifest_aliases().items():
        entries.append(
            {
                "name": alias,
                "alias_of": target,
                "fbx": f"Saved/kit/fbx/{target}.fbx",
                "notes": "Same geometry as solid wall; style = MI swap only.",
            }
        )
    return {
        "version": 1,
        "module_cm": MODULE_CM,
        "storey_cm": STOREY_CM,
        "wall_t_cm": WALL_T_CM,
        "floor_t_cm": FLOOR_T_CM,
        "piece_count": len(pieces),
        "alias_count": len(manifest_aliases()),
        "pieces": entries,
        "skipped": [
            "SM_W_TJunction",
            "SM_W_EndCap",
            "SM_R_EaveOverhang",
            "SM_R_Ridge",
            "SM_R_Chimney",
            "SM_B_RailCorner",
            "SM_Twr_ArcQuarter_B/C/D (rotate A)",
        ],
    }


# ---------------------------------------------------------------------------
# Blender builders — hyperreal mesh relief (flat SLOT_LOOK swatches only)
# ---------------------------------------------------------------------------


def _hash_unit(*vals: float) -> float:
    """Deterministic 0..1 jitter from integer-ish coordinates."""
    h = 2166136261
    for v in vals:
        h ^= int(round(v * 137.0)) & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % 10000) / 10000.0


def _beveled_face_block_parts(
    origin: Vec3,
    size: Vec3,
    *,
    bevel: float = 2.2,
    proud_face: str = "x_min",
) -> List[Tuple[Vec3, Vec3]]:
    """Block with chamfered perimeter on the proud face — catches rim light without textures."""
    ox, oy, oz = origin
    sx, sy, sz = size
    if sx <= 0.0 or sy <= 0.0 or sz <= 0.0:
        return []
    b = min(bevel, sx * 0.35, sy * 0.22, sz * 0.22)
    lip = 0.4
    parts: List[Tuple[Vec3, Vec3]] = []
    if proud_face == "x_min":
        parts.append(((ox, oy + b, oz + b), (sx, sy - 2.0 * b, sz - 2.0 * b)))
        parts.extend(
            [
                ((ox - lip, oy, oz + b), (sx + lip, b, sz - 2.0 * b)),
                ((ox - lip, oy + sy - b, oz + b), (sx + lip, b, sz - 2.0 * b)),
                ((ox - lip, oy + b, oz), (sx + lip, sy - 2.0 * b, b)),
                ((ox - lip, oy + b, oz + sz - b), (sx + lip, sy - 2.0 * b, b)),
            ]
        )
    elif proud_face == "y_min":
        parts.append(((ox + b, oy, oz + b), (sx - 2.0 * b, sy, sz - 2.0 * b)))
        parts.extend(
            [
                ((ox, oy - lip, oz + b), (b, sy + lip, sz - 2.0 * b)),
                ((ox + sx - b, oy - lip, oz + b), (b, sy + lip, sz - 2.0 * b)),
                ((ox + b, oy - lip, oz), (sx - 2.0 * b, sy + lip, b)),
                ((ox + b, oy - lip, oz + sz - b), (sx - 2.0 * b, sy + lip, b)),
            ]
        )
    else:
        parts.append((origin, size))
    return parts


def _bowed_panel_slices(
    x0: float,
    y0: float,
    z0: float,
    thickness: float,
    width: float,
    height: float,
    *,
    bow_cm: float = 5.5,
    slices: int = 5,
) -> List[Tuple[Vec3, Vec3]]:
    """Recessed infill with parabolic bow toward the street face."""
    parts: List[Tuple[Vec3, Vec3]] = []
    sw = width / slices
    for i in range(slices):
        u = (i + 0.5) / slices - 0.5
        bow = bow_cm * (1.0 - 4.0 * u * u)
        parts.append(((x0 - bow, y0 + i * sw, z0), (thickness + bow * 0.25, sw * 0.97, height)))
    return parts


def _ensure_materials(bpy) -> Dict[str, Any]:
    """Flat slot colors only — theme is mesh relief; Unreal applies real MI_* later."""
    mats: Dict[str, Any] = {}
    for slot_name, (rgba, rough, metal) in SLOT_LOOK.items():
        mat = bpy.data.materials.get(slot_name)
        if mat is None:
            mat = bpy.data.materials.new(slot_name)
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = rough
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metal
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = rgba[3]
        if slot_name == SLOT_GLASS:
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.9
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = 0.9
            if "IOR" in bsdf.inputs:
                bsdf.inputs["IOR"].default_value = 1.45
            mat.blend_method = "BLEND"
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = "HASHED"
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mats[slot_name] = mat
    return mats


def _stone_course_parts(
    *,
    length_cm: float,
    height_cm: float,
    wall_t: float,
    along_axis: str = "y",
) -> List[Tuple[Vec3, Vec3]]:
    """Ashlar courses — varied blocks, deep mortar gaps, proud beveled faces."""
    mortar = 9.0
    proud_base = 26.0
    core_t = max(12.0, wall_t - proud_base)
    parts: List[Tuple[Vec3, Vec3]] = []
    face = "x_min" if along_axis == "y" else "y_min"
    if along_axis == "y":
        parts.append(((proud_base, 0.0, 0.0), (core_t, length_cm, height_cm)))
    else:
        parts.append(((0.0, proud_base, 0.0), (length_cm, core_t, height_cm)))

    z = mortar * 0.5
    row = 0
    while z + 18.0 <= height_cm:
        course_h = 28.0 + _hash_unit(row, 11.0) * 14.0
        stagger = (55.0 + _hash_unit(row, 5.0) * 40.0) if (row % 2) else 0.0
        y = -stagger
        col = 0
        while y < length_cm + stagger:
            bw = 68.0 + _hash_unit(row, col, 1.0) * 76.0
            y0 = max(0.0, y + mortar * 0.5)
            y1 = min(length_cm, y + bw - mortar * 0.5)
            bw_act = y1 - y0
            bh = min(course_h - mortar, height_cm - z - mortar)
            if bw_act > 12.0 and bh > 10.0:
                depth = proud_base - 1.5 + _hash_unit(row, col, 2.0) * 6.0
                if _hash_unit(row, col, 9.0) > 0.78:
                    depth -= 3.5
                bevel = 1.8 + _hash_unit(row, col, 4.0) * 2.2
                if along_axis == "y":
                    parts.extend(
                        _beveled_face_block_parts(
                            (0.0, y0, z), (depth, bw_act, bh), bevel=bevel, proud_face=face
                        )
                    )
                else:
                    parts.extend(
                        _beveled_face_block_parts(
                            (y0, 0.0, z), (bw_act, depth, bh), bevel=bevel, proud_face=face
                        )
                    )
            y += bw
            col += 1
        z += course_h
        row += 1
    return parts


def _corner_quoin_parts(
    *,
    height_cm: float,
    wall_t: float,
) -> List[Tuple[Vec3, Vec3]]:
    """Alternating corner quoins — longer blocks wrapping the L-junction."""
    mortar = 7.5
    proud = 25.0
    parts: List[Tuple[Vec3, Vec3]] = []
    z = mortar
    row = 0
    while z + 20.0 <= height_cm:
        qh = 36.0 + (10.0 if row % 2 == 0 else 0.0) + _hash_unit(row, 13.0) * 8.0
        qw = 30.0 + (6.0 if row % 2 else 0.0)
        depth = proud + _hash_unit(row, 17.0) * 3.0
        bevel = 2.5 + _hash_unit(row) * 1.5
        parts.extend(_beveled_face_block_parts((0.0, 0.0, z), (depth, qw, qh), bevel=bevel))
        parts.extend(
            _beveled_face_block_parts((0.0, 0.0, z), (qw, depth, qh), bevel=bevel, proud_face="y_min")
        )
        z += qh + mortar
        row += 1
    return parts


def _build_stone_coursed(bpy, name: str, collection):
    from pae.primitives import bpy_util

    parts = _stone_course_parts(
        length_cm=MODULE_CM, height_cm=STOREY_CM, wall_t=WALL_T_CM, along_axis="y"
    )
    return bpy_util.build_mesh_from_box_parts(
        name, parts, origin_at_min_corner=True, collection=collection
    )


def _build_corner_stone_coursed(bpy, name: str, collection):
    from pae.primitives import bpy_util

    a = _stone_course_parts(
        length_cm=MODULE_CM, height_cm=STOREY_CM, wall_t=WALL_T_CM, along_axis="y"
    )
    b = _stone_course_parts(
        length_cm=MODULE_CM, height_cm=STOREY_CM, wall_t=WALL_T_CM, along_axis="x"
    )
    q = _corner_quoin_parts(height_cm=STOREY_CM, wall_t=WALL_T_CM)
    return bpy_util.build_mesh_from_box_parts(
        name, a + b + q, origin_at_min_corner=True, collection=collection
    )


def _assign_slots(obj, slot_names: Sequence[str], mats: Dict[str, Any]) -> None:
    obj.data.materials.clear()
    for name in slot_names:
        obj.data.materials.append(mats[name])
    if len(slot_names) == 1 and obj.data.polygons:
        for poly in obj.data.polygons:
            poly.material_index = 0


def _apply_box_uvs(obj) -> None:
    """Planar UV projection without edit-mode ops (MCP/background safe)."""
    if not obj or not obj.data.polygons:
        return
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    uv_data = mesh.uv_layers.active.data
    scale = 0.01  # cm → UV metres-ish
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
            uv_data[loop_idx].uv = (co.y * scale, co.z * scale)


def _join_meshes(bpy, objs: Sequence[Any], name: str, collection) -> Any:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    if joined.data.name != name:
        joined.data.name = name
    for coll in list(joined.users_collection):
        coll.objects.unlink(joined)
    collection.objects.link(joined)
    return joined


def _build_corner_wall(bpy, name: str, collection):
    from pae.primitives import bpy_util

    parts = [
        ((0.0, 0.0, 0.0), (WALL_T_CM, MODULE_CM, STOREY_CM)),
        ((0.0, 0.0, 0.0), (MODULE_CM, WALL_T_CM, STOREY_CM)),
    ]
    return bpy_util.build_mesh_from_box_parts(
        name, parts, origin_at_min_corner=True, collection=collection
    )


def _build_timber_wall(bpy, name: str, collection, mats: Dict[str, Any]):
    """Half-timber bay: bowed recessed plaster + proud chamfered oak frame + pegs."""
    from pae.primitives import bpy_util

    beam = 34.0
    t = WALL_T_CM
    w = MODULE_CM
    h = STOREY_CM
    inset = 3.0
    frame_proud = 32.0
    panel_x = 22.0
    panel_t = 8.0
    cols = rows = 2
    cell_w = (w - beam * (cols + 1)) / cols
    cell_h = (h - beam * (rows + 1)) / rows
    panel_parts: List[Tuple[Vec3, Vec3]] = []
    for ix in range(cols):
        for iz in range(rows):
            y0 = beam + ix * (cell_w + beam)
            z0 = beam + iz * (cell_h + beam)
            panel_parts.extend(
                _bowed_panel_slices(
                    panel_x,
                    y0 + inset,
                    z0 + inset,
                    panel_t,
                    cell_w - 2 * inset,
                    cell_h - 2 * inset,
                    bow_cm=5.0 + _hash_unit(ix, iz) * 2.5,
                )
            )
    body = bpy_util.build_mesh_from_box_parts(
        f"{name}_body", panel_parts, origin_at_min_corner=True, collection=collection
    )
    timber_parts: List[Tuple[Vec3, Vec3]] = []
    beam_depth = frame_proud
    beam_specs = [
        ((0.0, 0.0, 0.0), (beam_depth, beam, h)),
        ((0.0, w - beam, 0.0), (beam_depth, beam, h)),
        ((0.0, beam + cell_w, 0.0), (beam_depth, beam, h)),
        ((0.0, 0.0, 0.0), (beam_depth, w, beam)),
        ((0.0, 0.0, h - beam), (beam_depth, w, beam)),
        ((0.0, 0.0, beam + cell_h), (beam_depth, w, beam)),
    ]
    for origin, size in beam_specs:
        timber_parts.extend(_beveled_face_block_parts(origin, size, bevel=4.0, proud_face="x_min"))
    # Pegs at frame intersections
    peg_r = 3.5
    peg_d = 6.0
    peg_zs = [beam * 0.5, h - beam * 0.5, beam + cell_h + beam * 0.5]
    peg_ys = [beam * 0.5, w - beam * 0.5, beam + cell_w + beam * 0.5]
    for py in peg_ys:
        for pz in peg_zs:
            timber_parts.append(((frame_proud - peg_d, py - peg_r, pz - peg_r), (peg_d + 2.0, peg_r * 2, peg_r * 2)))
    frame = bpy_util.build_mesh_from_box_parts(
        f"{name}_frame", timber_parts, origin_at_min_corner=True, collection=collection
    )
    body.data.materials.clear()
    body.data.materials.append(mats[SLOT_WALL_PLASTER])
    frame.data.materials.clear()
    frame.data.materials.append(mats[SLOT_WOOD])
    n_body = len(body.data.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    joined = _join_meshes(bpy, [body, frame], name, collection)
    joined.data.materials.clear()
    joined.data.materials.append(mats[SLOT_WALL_PLASTER])
    joined.data.materials.append(mats[SLOT_WOOD])
    for i, poly in enumerate(joined.data.polygons):
        poly.material_index = 0 if i < n_body else 1
    return joined


def _opening_reveal_parts(
    cy0: float,
    cz0: float,
    opening_w: float,
    opening_h: float,
    *,
    jamb: float = 14.0,
    steps: int = 3,
) -> List[Tuple[Vec3, Vec3]]:
    """Stepped deep reveal from outer face into wall thickness."""
    parts: List[Tuple[Vec3, Vec3]] = []
    step_depth = (WALL_T_CM - 8.0) / steps
    for i in range(steps):
        inset = jamb * (i + 1) / steps
        x0 = i * step_depth
        parts.extend(
            [
                ((x0, cy0 - inset, cz0 - inset), (step_depth + 0.5, inset, opening_h + 2 * inset)),
                ((x0, cy0 + opening_w, cz0 - inset), (step_depth + 0.5, inset, opening_h + 2 * inset)),
                ((x0, cy0 - inset, cz0 + opening_h), (step_depth + 0.5, opening_w + 2 * inset, inset)),
                ((x0, cy0 - inset, cz0 - inset), (step_depth + 0.5, opening_w + 2 * inset, inset)),
            ]
        )
    return parts


def _window_sill_hood_parts(
    cy0: float,
    cz0: float,
    win_w: float,
    win_h: float,
) -> List[Tuple[Vec3, Vec3]]:
    """Projecting sill + hood/lintel profile on both wall faces."""
    parts: List[Tuple[Vec3, Vec3]] = []
    sill_h = 12.0
    sill_proj = 10.0
    hood_h = 16.0
    hood_proj = 8.0
    for x0 in (-sill_proj, WALL_T_CM - 2.0):
        parts.append(((x0, cy0 - 6.0, cz0 - sill_h - 2.0), (sill_proj + 4.0, win_w + 12.0, sill_h)))
        parts.append(((x0, cy0 - 4.0, cz0 - 2.0), (sill_proj + 2.0, win_w + 8.0, 4.0)))
        parts.append(((x0, cy0 - hood_proj, cz0 + win_h), (hood_proj + 4.0, win_w + 2 * hood_proj, hood_h)))
        parts.append(((x0 + 2.0, cy0 - 4.0, cz0 + win_h + hood_h - 4.0), (hood_proj, win_w + 8.0, 6.0)))
    return parts


def _door_leaf_parts(
    cy0: float,
    door_w: float,
    door_h: float,
    *,
    double_leaf: bool = False,
) -> List[Tuple[Vec3, Vec3]]:
    """Planked door with stiles, rails, recessed panels, ring pull."""
    parts: List[Tuple[Vec3, Vec3]] = []
    leaf_t = 8.0
    lx = (WALL_T_CM - leaf_t) * 0.5
    stile_w = 14.0
    rail_h = 18.0
    panel_inset = 4.0

    def _single_leaf(y_start: float, width: float) -> None:
        parts.extend(
            [
                ((lx, y_start, 4.0), (leaf_t, stile_w, door_h - 8.0)),
                ((lx, y_start + width - stile_w, 4.0), (leaf_t, stile_w, door_h - 8.0)),
                ((lx, y_start, 4.0), (leaf_t, width, rail_h)),
                ((lx, y_start, door_h - rail_h - 4.0), (leaf_t, width, rail_h)),
                ((lx, y_start + door_h * 0.46, 4.0), (leaf_t, width, 14.0)),
            ]
        )
        px = lx - panel_inset
        pw = width - 2 * stile_w
        ph_top = door_h * 0.42 - rail_h
        ph_bot = door_h - 2 * rail_h - ph_top - 14.0
        parts.append(((px, y_start + stile_w, rail_h + 6.0), (leaf_t + panel_inset, pw, ph_top)))
        parts.append(
            ((px, y_start + stile_w, rail_h + ph_top + 20.0), (leaf_t + panel_inset, pw, max(12.0, ph_bot)))
        )
        plank = 26.0
        y = y_start + stile_w + 4.0
        while y < y_start + width - stile_w - 8.0:
            pw_plank = min(plank, y_start + width - stile_w - 4.0 - y)
            parts.append(((lx + 1.0, y, 8.0), (leaf_t - 2.0, pw_plank, door_h - 20.0)))
            y += plank
        parts.append(((lx - 4.0, y_start + width * 0.78, door_h * 0.52), (leaf_t + 8.0, 10.0, 10.0)))
        for hz in (door_h * 0.25, door_h * 0.72):
            parts.append(((lx - 2.0, y_start + 3.0, hz), (4.0, 8.0, 16.0)))

    if double_leaf:
        half = door_w * 0.5 - 3.0
        _single_leaf(cy0 + 3.0, half)
        _single_leaf(cy0 + door_w * 0.5 + 3.0, half)
    else:
        _single_leaf(cy0 + 4.0, door_w - 8.0)
    return parts


def _build_opening_themed(bpy, piece: KitPiece, collection, mats: Dict[str, Any]):
    """Opening mesh + deep reveal, sill/hood, glazing rebate, door hardware."""
    from pae.primitives import catalog, bpy_util

    base = catalog.build_mesh(piece.pae_id, name=f"{piece.name}_base")
    for coll in list(base.users_collection):
        coll.objects.unlink(base)
    collection.objects.link(base)

    surround_slot = SLOT_WOOD if SLOT_WOOD in piece.slots else SLOT_STONE
    parts: List[Tuple[Vec3, Vec3]] = []
    if "Door" in piece.name:
        jamb_w = 26.0
        lintel_h = 32.0
        door_w = MODULE_CM * 0.42 if "Double" not in piece.name else MODULE_CM * 0.72
        door_h = STOREY_CM * 0.72 if "Arched" not in piece.name else STOREY_CM * 0.78
        cy0 = (MODULE_CM - door_w) * 0.5
        cz0 = 0.0
        for x0 in (-14.0, WALL_T_CM - 4.0):
            parts.extend(
                [
                    ((x0, cy0 - jamb_w, 0.0), (16.0, jamb_w, door_h + lintel_h)),
                    ((x0, cy0 + door_w, 0.0), (16.0, jamb_w, door_h + lintel_h)),
                    ((x0, cy0 - jamb_w, door_h), (16.0, door_w + 2 * jamb_w, lintel_h)),
                ]
            )
            parts.extend(
                _beveled_face_block_parts(
                    (x0, cy0 - jamb_w, door_h + lintel_h - 6.0),
                    (16.0, door_w + 2 * jamb_w, 10.0),
                    bevel=2.0,
                )
            )
        parts.extend(_opening_reveal_parts(cy0, cz0 + STOREY_CM * 0.08, door_w, door_h * 0.92, jamb=18.0))
    else:
        pad = 20.0
        win_w = MODULE_CM * 0.38
        win_h = STOREY_CM * 0.36
        cy0 = (MODULE_CM - win_w) * 0.5
        cz0 = STOREY_CM * 0.38
        for x0 in (-14.0, WALL_T_CM - 4.0):
            parts.extend(
                [
                    ((x0, cy0 - pad, cz0 - pad), (16.0, pad, win_h + 2 * pad)),
                    ((x0, cy0 + win_w, cz0 - pad), (16.0, pad, win_h + 2 * pad)),
                    ((x0, cy0 - pad, cz0 + win_h), (16.0, win_w + 2 * pad, pad)),
                    ((x0, cy0 - pad, cz0 - pad), (16.0, win_w + 2 * pad, pad)),
                ]
            )
            parts.extend(
                _beveled_face_block_parts((x0, cy0 - pad, cz0 - pad), (16.0, win_w + 2 * pad, pad), bevel=2.5)
            )
        if "Cross" in piece.name:
            for x0 in (-10.0, WALL_T_CM - 6.0):
                parts.extend(_beveled_face_block_parts((x0, cy0 + win_w * 0.5 - 5.0, cz0), (12.0, 10.0, win_h), bevel=1.5))
                parts.extend(_beveled_face_block_parts((x0, cy0, cz0 + win_h * 0.5 - 5.0), (12.0, win_w, 10.0), bevel=1.5))
        parts.extend(_opening_reveal_parts(cy0, cz0, win_w, win_h, jamb=16.0))
        parts.extend(_window_sill_hood_parts(cy0, cz0, win_w, win_h))

    frame = bpy_util.build_mesh_from_box_parts(
        f"{piece.name}_frame",
        parts,
        origin_at_min_corner=True,
        collection=collection,
    )
    wall_slot = piece.slots[0]
    base.data.materials.clear()
    base.data.materials.append(mats[wall_slot])
    frame.data.materials.clear()
    frame.data.materials.append(mats[surround_slot])

    extras = [base, frame]
    # Real glass panes in the window opening (Cross = 4 panes behind mullions).
    if SLOT_GLASS in piece.slots and "Door" not in piece.name:
        win_w = MODULE_CM * 0.38
        win_h = STOREY_CM * 0.36
        cy0 = (MODULE_CM - win_w) * 0.5
        cz0 = STOREY_CM * 0.38
        glass_t = 5.0
        gx = (WALL_T_CM - glass_t) * 0.5
        mull = 10.0
        gap = 2.0
        if "Cross" in piece.name:
            hw = (win_w - mull) * 0.5 - gap
            hh = (win_h - mull) * 0.5 - gap
            pane_parts = [
                ((gx, cy0 + gap, cz0 + gap), (glass_t, hw, hh)),
                ((gx, cy0 + win_w * 0.5 + mull * 0.5 + gap, cz0 + gap), (glass_t, hw, hh)),
                ((gx, cy0 + gap, cz0 + win_h * 0.5 + mull * 0.5 + gap), (glass_t, hw, hh)),
                (
                    (gx, cy0 + win_w * 0.5 + mull * 0.5 + gap, cz0 + win_h * 0.5 + mull * 0.5 + gap),
                    (glass_t, hw, hh),
                ),
            ]
        else:
            pane_parts = [
                ((gx, cy0 + gap, cz0 + gap), (glass_t, win_w - 2 * gap, win_h - 2 * gap))
            ]
        glass = bpy_util.build_mesh_from_box_parts(
            f"{piece.name}_glass",
            pane_parts,
            origin_at_min_corner=True,
            collection=collection,
        )
        glass.data.materials.clear()
        glass.data.materials.append(mats[SLOT_GLASS])
        extras.append(glass)

    # Wood door leaf (solid plank look) so openings aren't empty holes.
    if "Door" in piece.name and SLOT_WOOD in piece.slots:
        door_w = MODULE_CM * 0.42 if "Double" not in piece.name else MODULE_CM * 0.72
        door_h = STOREY_CM * 0.72 if "Arched" not in piece.name else STOREY_CM * 0.78
        cy0 = (MODULE_CM - door_w) * 0.5
        leaf_parts = _door_leaf_parts(cy0, door_w, door_h, double_leaf="Double" in piece.name)
        leaf = bpy_util.build_mesh_from_box_parts(
            f"{piece.name}_leaf",
            leaf_parts,
            origin_at_min_corner=True,
            collection=collection,
        )
        leaf.data.materials.clear()
        leaf.data.materials.append(mats[SLOT_WOOD])
        extras.append(leaf)

    joined = _join_meshes(bpy, extras, piece.name, collection)
    # Preserve join indices; reorder slots to match piece.slots without wiping faces.
    mat_by_name = {m.name: m for m in joined.data.materials if m}
    # Map each face's current material name → desired index
    face_mat_names = []
    for poly in joined.data.polygons:
        m = joined.data.materials[poly.material_index]
        face_mat_names.append(m.name if m else piece.slots[0])
    joined.data.materials.clear()
    for s in piece.slots:
        joined.data.materials.append(mats[s])
    name_to_i = {s: i for i, s in enumerate(piece.slots)}
    for poly, mname in zip(joined.data.polygons, face_mat_names):
        poly.material_index = name_to_i.get(mname, 0)
    return joined


def _cone_shingle_ring_parts(cx: float, cy: float, z: float, radius: float, ring_h: float, *, count: int = 20) -> List[Tuple[Vec3, Vec3]]:
    """Overlapping shingle segments around a cone ring (axis-aligned approx)."""
    parts: List[Tuple[Vec3, Vec3]] = []
    shingle_w = 22.0
    shingle_d = 6.0
    for i in range(count):
        ang = (2.0 * math.pi * i) / count
        ox = cx + math.cos(ang) * radius - shingle_w * 0.5
        oy = cy + math.sin(ang) * radius - shingle_w * 0.35
        proud = 1.0 + _hash_unit(i, z) * 2.0
        parts.append(((ox, oy, z), (shingle_d + proud, shingle_w, ring_h)))
        parts.append(((ox - 0.5, oy, z - 2.0), (shingle_d + proud + 1.0, shingle_w, 3.0)))
    return parts


def _build_cone_cap_themed(bpy, piece: KitPiece, collection, mats: Dict[str, Any]):
    """Conical spire base + overlapping shingle ring relief."""
    from pae.primitives import catalog, bpy_util

    base = catalog.build_mesh(piece.pae_id, name=f"{piece.name}_base")
    for coll in list(base.users_collection):
        coll.objects.unlink(base)
    collection.objects.link(base)
    base.data.materials.clear()
    base.data.materials.append(mats[SLOT_ROOF_SLATE])

    cx = MODULE_CM * 0.5
    cy = MODULE_CM * 0.5
    h = piece.dims_cm[2]
    base_r = MODULE_CM * 0.48
    ring_parts: List[Tuple[Vec3, Vec3]] = []
    rings = 18
    for i in range(rings):
        t = (i + 1) / (rings + 2)
        z = h * 0.08 + t * h * 0.88
        r = base_r * (1.0 - t * 0.92)
        ring_h = 14.0 + _hash_unit(i) * 6.0
        count = max(12, int(20 * (r / base_r)))
        ring_parts.extend(_cone_shingle_ring_parts(cx, cy, z, r, ring_h, count=count))

    shingles = bpy_util.build_mesh_from_box_parts(
        f"{piece.name}_shingles",
        ring_parts,
        origin_at_min_corner=True,
        collection=collection,
    )
    shingles.data.materials.clear()
    shingles.data.materials.append(mats[SLOT_ROOF_SLATE])
    n_base = len(base.data.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    joined = _join_meshes(bpy, [base, shingles], piece.name, collection)
    joined.data.materials.clear()
    joined.data.materials.append(mats[SLOT_ROOF_SLATE])
    for poly in joined.data.polygons:
        poly.material_index = 0
    return joined


def _apply_cm_to_m(objects: Sequence[Any], bpy) -> None:
    """Scale kit meshes from PAE cm authoring space to metres for board/FBX consistency."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        for obj in objects:
            obj.scale = (CM_TO_M, CM_TO_M, CM_TO_M)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for obj in objects:
        obj.select_set(False)


def _roof_tile_course_parts(w: float, eave_z: float, ridge_z: float) -> List[Tuple[Vec3, Vec3]]:
    """Overlapping terracotta tile rows on both roof slopes (mesh relief, not ribs)."""
    parts: List[Tuple[Vec3, Vec3]] = []
    half = w * 0.5
    tile_y = 34.0
    tile_h = 26.0
    tile_d = 6.5
    overlap = 0.58
    rows = 16
    margin = 10.0

    def _slope_tiles(x_side: str) -> None:
        for i in range(rows):
            t = (i + 0.5) / rows
            if x_side == "left":
                x_center = margin + t * (half - margin * 1.4)
                z_base = eave_z + t * (ridge_z - eave_z) * 0.94 - i * tile_h * overlap * 0.15
            else:
                x_center = w - margin - t * (half - margin * 1.4)
                z_base = eave_z + t * (ridge_z - eave_z) * 0.94 - i * tile_h * overlap * 0.15
            y = margin
            col = 0
            while y < w - margin:
                tw = min(tile_y, w - margin - y)
                depth = tile_d + _hash_unit(i, col, 3.0) * 2.0
                # main tile body + rolled eave lip
                parts.append(((x_center - depth * 0.5, y, z_base), (depth, tw * 0.96, tile_h)))
                parts.append(((x_center - depth * 0.5 - 0.5, y, z_base - 3.0), (depth + 1.0, tw * 0.96, 4.0)))
                y += tile_y * (1.0 - overlap)
                col += 1

    _slope_tiles("left")
    _slope_tiles("right")
    # Ridge cap tiles + timber
    parts.append(((half - 14.0, margin, ridge_z - 4.0), (28.0, w - 2 * margin, 12.0)))
    parts.extend(_beveled_face_block_parts((half - 10.0, 4.0, ridge_z + 6.0), (20.0, w - 8.0, 10.0), bevel=2.0))
    return parts


def _roof_eave_fascia_parts(w: float) -> List[Tuple[Vec3, Vec3]]:
    """Fascia boards + exposed rafter tails under eaves."""
    parts: List[Tuple[Vec3, Vec3]] = []
    fascia_h = 18.0
    fascia_d = 6.0
    rafter_tail = 22.0
    spacing = 48.0
    for x0 in (-rafter_tail, w - fascia_d):
        parts.append(((x0, 0.0, 0.0), (fascia_d + (rafter_tail if x0 < 0 else 0), w, fascia_h)))
        y = spacing * 0.5
        while y < w:
            parts.append(((x0 - 4.0, y - 4.0, -6.0), (fascia_d + 8.0, 8.0, 10.0)))
            y += spacing
    return parts


def _build_roof_pitched_themed(bpy, piece: KitPiece, collection, mats: Dict[str, Any]):
    """Pitched shell + overlapping tile courses + ridge cap + eave fascia."""
    from pae.primitives import catalog, bpy_util

    base = catalog.build_mesh(piece.pae_id, name=f"{piece.name}_shell")
    for coll in list(base.users_collection):
        coll.objects.unlink(base)
    collection.objects.link(base)
    base.data.materials.clear()
    base.data.materials.append(mats[SLOT_ROOF])

    w = MODULE_CM
    eave_z = FLOOR_T_CM
    ridge_z = 225.0
    tile_parts = _roof_tile_course_parts(w, eave_z, ridge_z)
    timber_parts = _roof_eave_fascia_parts(w)
    tiles = bpy_util.build_mesh_from_box_parts(
        f"{piece.name}_tiles", tile_parts, origin_at_min_corner=True, collection=collection
    )
    eaves = bpy_util.build_mesh_from_box_parts(
        f"{piece.name}_eaves", timber_parts, origin_at_min_corner=True, collection=collection
    )
    tiles.data.materials.clear()
    tiles.data.materials.append(mats[SLOT_ROOF])
    eaves.data.materials.clear()
    eaves.data.materials.append(mats[SLOT_WOOD])
    n_shell = len(base.data.polygons)
    n_tiles = len(tiles.data.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    joined = _join_meshes(bpy, [base, tiles, eaves], piece.name, collection)
    joined.data.materials.clear()
    joined.data.materials.append(mats[SLOT_ROOF])
    joined.data.materials.append(mats[SLOT_WOOD])
    for i, poly in enumerate(joined.data.polygons):
        poly.material_index = 0 if i < n_shell + n_tiles else 1
    return joined


def _build_mesh_for_piece(piece: KitPiece, bpy, collection, mats: Dict[str, Any]):
    from pae.primitives import catalog

    if piece.builder == "corner_wall":
        obj = _build_corner_wall(bpy, piece.name, collection)
        _assign_slots(obj, piece.slots, mats)
    elif piece.builder == "stone_coursed":
        obj = _build_stone_coursed(bpy, piece.name, collection)
        _assign_slots(obj, piece.slots, mats)
    elif piece.builder == "corner_stone_coursed":
        obj = _build_corner_stone_coursed(bpy, piece.name, collection)
        _assign_slots(obj, piece.slots, mats)
    elif piece.builder == "timber_wall":
        obj = _build_timber_wall(bpy, piece.name, collection, mats)
    elif piece.builder == "opening_themed":
        obj = _build_opening_themed(bpy, piece, collection, mats)
    elif piece.builder == "roof_pitched_themed":
        obj = _build_roof_pitched_themed(bpy, piece, collection, mats)
    elif piece.builder == "cone_cap_themed":
        obj = _build_cone_cap_themed(bpy, piece, collection, mats)
    elif piece.pae_id:
        try:
            obj = catalog.build_mesh(piece.pae_id, name=piece.name)
            for coll in obj.users_collection:
                coll.objects.unlink(obj)
            collection.objects.link(obj)
        except Exception as exc:  # pragma: no cover - blender only
            raise RuntimeError(f"build_mesh({piece.pae_id!r}) failed: {exc}") from exc
        _assign_slots(obj, piece.slots, mats)
    else:
        raise RuntimeError(f"no builder for {piece.name}")

    obj.name = piece.name
    if obj.data.name != piece.name:
        obj.data.name = piece.name

    _apply_box_uvs(obj)
    return obj


def _object_aabb_m(obj) -> Tuple[Vec3, Vec3]:
    import bpy
    from mathutils import Vector

    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    corners = [
        ev.matrix_world @ Vector(corner)
        for corner in ev.bound_box
    ]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def _layout_board(objects: Sequence[Any], pieces: Sequence[KitPiece]) -> None:
    """Place pieces on a family-grouped grid (metres, post cm→m scale)."""
    families: Dict[str, List[Any]] = {}
    piece_by_name = {p.name: p for p in pieces}
    for obj in objects:
        p = piece_by_name.get(obj.name)
        fam = p.collection if p else "KIT_Other"
        families.setdefault(fam, []).append(obj)

    row_y = 0.0
    for fam in sorted(families):
        col_x = 0.0
        row_h = 0.0
        for obj in families[fam]:
            bb_min, bb_max = _object_aabb_m(obj)
            sx = bb_max[0] - bb_min[0]
            sy = bb_max[1] - bb_min[1]
            # Shift so min corner sits at layout origin then offset
            obj.location.x += col_x - bb_min[0]
            obj.location.y += row_y - bb_min[1]
            col_x += sx + BOARD_GAP_M
            row_h = max(row_h, bb_max[2] - bb_min[2])
        row_y += row_h + BOARD_GAP_M * 1.5


def _export_fbx(obj, path: Path, bpy, *, global_scale: float = CM_TO_M) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        apply_scale_options="FBX_SCALE_ALL",
        global_scale=global_scale,
        axis_forward="-Z",
        axis_up="Y",
        object_types={"MESH"},
        use_mesh_modifiers=True,
        mesh_smooth_type="FACE",
        path_mode="COPY",
        embed_textures=False,
    )


def _configure_render(scene, bpy, *, width: int, height: int) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # EEVEE exposure / ambient — keep shadows readable on dark bg.
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 32
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True
            scene.eevee.gtao_distance = 1.5
            scene.eevee.gtao_factor = 1.4
        if hasattr(scene.eevee, "use_bloom"):
            scene.eevee.use_bloom = False
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("KitWorld")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = WORLD_BG_RGBA
        bg.inputs[1].default_value = 0.45


def _scene_bounds_m(objects: Sequence[Any]) -> Tuple[Vec3, Vec3, float]:
    """Return (mins, maxs, span) in metres."""
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for obj in objects:
        bmin, bmax = _object_aabb_m(obj)
        for i in range(3):
            mins[i] = min(mins[i], bmin[i])
            maxs[i] = max(maxs[i], bmax[i])
    span = max(maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2], 1.0)
    return ((mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2]), span)


def _clear_kit_lights(scene, bpy) -> None:
    for obj in list(scene.collection.objects):
        if obj.type == "LIGHT" and obj.name.startswith("Kit"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _setup_kit_lighting(scene, bpy, center, span: float) -> None:
    """Warm key + cool fill — RE anime-medieval lookdev, not greybox studio."""
    from mathutils import Vector

    _clear_kit_lights(scene, bpy)
    key_data = bpy.data.lights.new("KitSun", type="SUN")
    key = bpy.data.objects.new("KitSun", key_data)
    scene.collection.objects.link(key)
    key.rotation_euler = (math.radians(48), math.radians(12), math.radians(28))
    key.data.energy = 5.8
    key.data.angle = math.radians(4.0)
    key.data.color = (1.0, 0.92, 0.78)

    fill_data = bpy.data.lights.new("KitFill", type="AREA")
    fill = bpy.data.objects.new("KitFill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = center + Vector((-span * 0.9, span * 0.6, span * 0.5))
    fill.rotation_euler = (center - fill.location).to_track_quat("-Z", "Y").to_euler()
    fill.data.energy = 220.0
    fill.data.size = span * 1.4
    fill.data.color = (0.75, 0.82, 0.95)

    rim_data = bpy.data.lights.new("KitRim", type="SUN")
    rim = bpy.data.objects.new("KitRim", rim_data)
    scene.collection.objects.link(rim)
    rim.rotation_euler = (math.radians(22), math.radians(155), math.radians(-8))
    rim.data.energy = 2.2
    rim.data.color = (0.55, 0.68, 0.95)


def _fit_camera_to_objects(
    objects: Sequence[Any], scene, bpy, *, perspective: bool = True, frontal: bool = False
) -> None:
    from mathutils import Vector

    if not objects:
        return
    mins, maxs, span = _scene_bounds_m(objects)
    center = Vector(
        ((mins[0] + maxs[0]) * 0.5, (mins[1] + maxs[1]) * 0.5, (mins[2] + maxs[2]) * 0.5)
    )
    # Reuse or create camera.
    cam = bpy.data.objects.get("KitBoardCam")
    if cam is None:
        cam_data = bpy.data.cameras.new("KitBoardCam")
        cam = bpy.data.objects.new("KitBoardCam", cam_data)
        scene.collection.objects.link(cam)
    scene.camera = cam
    if frontal:
        # Face openings head-on so window/door holes read.
        cam.location = center + Vector((-span * 1.35, 0.0, span * 0.15))
    else:
        # Elevated 3/4 perspective — openings and stair steps read vs flat ortho.
        cam.location = center + Vector((span * 0.95, -span * 1.25, span * 0.72))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    if perspective:
        cam.data.type = "PERSP"
        cam.data.lens = 50
        cam.data.clip_end = span * 20.0
    else:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = span * 1.45
    _setup_kit_lighting(scene, bpy, center, span)


def _render_board(objects: Sequence[Any], path: Path) -> None:
    import bpy

    scene = bpy.context.scene
    _configure_render(scene, bpy, width=BOARD_MAX_EDGE, height=int(BOARD_MAX_EDGE * 0.55))
    _fit_camera_to_objects(objects, scene, bpy, perspective=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"board screenshot missing: {path}")


def _repack_family_for_closeup(fam_objects: Sequence[Any], *, gap_m: float = 0.35) -> Dict[str, Any]:
    """Tight local row at origin so close-up camera frames geometry, not board void."""
    from mathutils import Vector

    saved: Dict[str, Any] = {}
    col_x = 0.0
    for obj in fam_objects:
        saved[obj.name] = obj.location.copy()
        bmin, bmax = _object_aabb_m(obj)
        sx = bmax[0] - bmin[0]
        obj.location += Vector((col_x - bmin[0], -bmin[1], -bmin[2]))
        col_x += sx + gap_m
    return saved


def _restore_family_locations(saved: Dict[str, Any]) -> None:
    import bpy

    for name, loc in saved.items():
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.location = loc


def _render_family_closeups(
    objects: Sequence[Any], pieces: Sequence[KitPiece], bpy
) -> List[str]:
    """Four informative family close-ups at 640px."""
    import bpy as _bpy

    piece_by_name = {p.name: p for p in pieces}
    families: Dict[str, List[Any]] = {}
    for obj in objects:
        p = piece_by_name.get(obj.name)
        if p is None:
            continue
        families.setdefault(p.collection, []).append(obj)

    paths: List[str] = []
    for fam in CLOSEUP_FAMILIES:
        if fam not in families:
            continue
        fam_objs = families[fam]
        fam_set = {o.name for o in fam_objs}
        for obj in objects:
            hide = obj.name not in fam_set
            obj.hide_render = hide
            obj.hide_viewport = hide
        saved_locs = _repack_family_for_closeup(fam_objs, gap_m=1.0)
        scene = _bpy.context.scene
        _configure_render(scene, _bpy, width=CLOSEUP_MAX, height=CLOSEUP_MAX)
        frontal = False  # 3/4 so timber / surrounds / glass all read
        _fit_camera_to_objects(fam_objs, scene, _bpy, perspective=True, frontal=frontal)
        slug = fam.replace("KIT_", "").lower()
        out = CLOSEUP_DIR / f"modular_kit_v1_{slug}.png"
        scene.render.filepath = str(out)
        _bpy.ops.render.render(write_still=True)
        _restore_family_locations(saved_locs)
        if out.is_file():
            paths.append(str(out.relative_to(PAE_ROOT)).replace("\\", "/"))
        for obj in objects:
            obj.hide_render = False
            obj.hide_viewport = False
    return paths


def _render_theme_strip(objects: Sequence[Any], path: Path) -> None:
    """Street elevation facing -X: stone courses | window+glass | door planks | timber | roof ribs."""
    import bpy
    from mathutils import Euler, Vector

    by_name = {o.name: o for o in objects}
    want = (
        "SM_W_Solid_Stone",
        "SM_W_Window_Cross",
        "SM_W_Door_Plain",
        "SM_W_Solid_Timber",
        "SM_R_PitchedSlope",
        "SM_R_ConeCap",
    )
    show = [by_name[n] for n in want if n in by_name]
    if len(show) < 3:
        return
    saved = {
        o.name: (o.location.copy(), o.rotation_euler.copy(), o.hide_render, o.hide_viewport)
        for o in objects
    }
    for o in objects:
        hide = o not in show
        o.hide_render = hide
        o.hide_viewport = hide

    bay = MODULE_CM * CM_TO_M
    storey = STOREY_CM * CM_TO_M
    # Keep native wall orientation (thickness +X, length +Y). Camera looks down -X
    # at the proud face (local x≈0) so ashlar / timber / glass read correctly.
    stone = by_name["SM_W_Solid_Stone"]
    window = by_name.get("SM_W_Window_Cross")
    door = by_name.get("SM_W_Door_Plain")
    timber = by_name["SM_W_Solid_Timber"]
    roof = by_name.get("SM_R_PitchedSlope")
    cone = by_name.get("SM_R_ConeCap")

    y = 0.0
    for obj in (stone, window, door, timber):
        if obj is None:
            continue
        obj.rotation_euler = Euler((0.0, 0.0, 0.0))
        obj.location = Vector((0.0, y, 0.0))
        y += bay + 0.2
    if roof:
        roof.rotation_euler = Euler((0.0, 0.0, 0.0))
        roof.location = Vector((-0.55, bay * 0.6, storey + 0.05))
    if cone:
        cone.rotation_euler = Euler((0.0, 0.0, 0.0))
        cone.location = Vector((0.3, y + bay * 0.35, 0.0))

    scene = bpy.context.scene
    _configure_render(scene, bpy, width=BOARD_MAX_EDGE, height=int(BOARD_MAX_EDGE * 0.48))
    mins, maxs, span = _scene_bounds_m(show)
    center = Vector(
        ((mins[0] + maxs[0]) * 0.5, (mins[1] + maxs[1]) * 0.5, (mins[2] + maxs[2]) * 0.42)
    )
    cam = bpy.data.objects.get("KitBoardCam")
    if cam is None:
        cam_data = bpy.data.cameras.new("KitBoardCam")
        cam = bpy.data.objects.new("KitBoardCam", cam_data)
        scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "PERSP"
    cam.data.lens = 40
    # Front of walls (proud ashlar at x≈0) — slight 3/4 for depth read
    cam.location = center + Vector((-span * 1.35, -span * 0.35, span * 0.28))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    _setup_kit_lighting(scene, bpy, center, span)

    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)

    for o in objects:
        loc, rot, hr, hv = saved[o.name]
        o.location = loc
        o.rotation_euler = rot
        o.hide_render = hr
        o.hide_viewport = hv


def run_blender_build(*, closeups: bool = True) -> Dict[str, Any]:
    import bpy

    pieces = kit_piece_catalog()
    KIT_DIR.mkdir(parents=True, exist_ok=True)
    FBX_DIR.mkdir(parents=True, exist_ok=True)

    # Fresh scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    mats = _ensure_materials(bpy)
    collections: Dict[str, Any] = {}
    for piece in pieces:
        if piece.collection not in collections:
            coll = bpy.data.collections.new(piece.collection)
            bpy.context.scene.collection.children.link(coll)
            collections[piece.collection] = coll
        coll = collections[piece.collection]
        _build_mesh_for_piece(piece, bpy, coll, mats)

    objects = [bpy.data.objects[p.name] for p in pieces if p.name in bpy.data.objects]
    _apply_cm_to_m(objects, bpy)
    _layout_board(objects, pieces)

    # Export FBX per piece (one at a time — RAM safe). Meshes already metres.
    fbx_count = 0
    for piece in pieces:
        obj = bpy.data.objects.get(piece.name)
        if obj is None:
            continue
        fbx_path = FBX_DIR / f"{piece.name}.fbx"
        _export_fbx(obj, fbx_path, bpy, global_scale=1.0)
        fbx_count += 1

    manifest = build_manifest_dict(pieces)
    manifest["blend"] = str(BLEND_PATH.relative_to(PAE_ROOT)).replace("\\", "/")
    manifest["board_screenshot"] = str(BOARD_SHOT.relative_to(PAE_ROOT)).replace("\\", "/")
    manifest["fbx_count"] = fbx_count

    _render_board(objects, BOARD_SHOT)
    _render_theme_strip(objects, THEME_STRIP_SHOT)
    if closeups:
        manifest["closeup_screenshots"] = _render_family_closeups(objects, pieces, bpy)
    manifest["theme_strip_screenshot"] = str(THEME_STRIP_SHOT.relative_to(PAE_ROOT)).replace(
        "\\", "/"
    )

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    return {
        "pieces": len(pieces),
        "fbx": fbx_count,
        "blend": str(BLEND_PATH),
        "manifest": str(MANIFEST_PATH),
        "board": str(BOARD_SHOT),
    }


def run_dry_run() -> Dict[str, Any]:
    pieces = kit_piece_catalog()
    manifest = build_manifest_dict(pieces)
    KIT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"pieces": len(pieces), "manifest": str(MANIFEST_PATH), "bpy": False}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build RE modular kit v1 meshes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write manifest only (no Blender required)",
    )
    parser.add_argument(
        "--no-closeups",
        action="store_true",
        help="Skip per-family 640px close-up renders",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.dry_run:
        info = run_dry_run()
        print(f"[kit] dry-run pieces={info['pieces']} manifest={info['manifest']}")
        return 0

    if not _have_bpy():
        print(
            "bpy not available — run inside Blender:\n"
            '  blender --background --python tools/build_modular_kit_blender.py',
            file=sys.stderr,
        )
        return 2

    info = run_blender_build(closeups=not args.no_closeups)
    print(
        f"[kit] pieces={info['pieces']} fbx={info['fbx']} "
        f"blend={info['blend']} board={info['board']}"
    )
    return 0


if __name__ == "__main__":
    # Blender passes its own flags before the script path; only parse args after ``--``.
    cli_args: List[str] = []
    if "--" in sys.argv:
        cli_args = sys.argv[sys.argv.index("--") + 1 :]
    raise SystemExit(main(cli_args))


__all__ = [
    "kit_piece_catalog",
    "build_manifest_dict",
    "manifest_aliases",
    "MODULE_CM",
    "STOREY_CM",
]

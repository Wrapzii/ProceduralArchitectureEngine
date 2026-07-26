"""Live Blender mesh build for PAE milestones (M1–M4 gallery + live stack).

Run **inside** Blender (MCP ``execute_blender_code`` / Text Editor / add-on).

Hardening notes
---------------
* Mesh authoring units are **centimetres**; instances use ``scale = 0.01``
  (cm → m) and locations in metres.
* Prefer ``catalog.build_mesh``; unknown assets (e.g. ``roof_flat``) fall back
  to a framed opening / solid box via ``bpy_util``.
* Always ``reload_pae()`` first — Blender caches modules across agent re-runs.

Example (Blender MCP — live M1 stack)::

    import runpy
    runpy.run_path(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py"
    )

Gallery (M1–M4 side-by-side, fixed collections)::

    from pae.blender_build import build_gallery
    build_gallery()

Or::

    exec(open(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py",
        encoding="utf-8",
    ).read())
    build_gallery()
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Path + reload (must run before other pae imports when executed as a script)
# ---------------------------------------------------------------------------

_PAE_ROOT = Path(__file__).resolve().parent.parent
if str(_PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PAE_ROOT))

# cm → m for Blender object scale / location
CM_TO_M = 0.01
SCREENSHOT_REL = Path("Saved") / "Screenshots" / "m1_live.png"
M3_SCREENSHOT_REL = Path("Saved") / "Screenshots" / "m3_pitched.png"
GALLERY_SCREENSHOT_REL = Path("Saved") / "Screenshots" / "gallery_m1_m4.png"
M2_STAIR_PROOF_SCREENSHOT_REL = Path("Saved") / "Screenshots" / "m2_stair_proof.png"
M1_OPENINGS_PROOF_SCREENSHOT_REL = Path("Saved") / "Screenshots" / "m1_openings_proof.png"
PAE_ROOT_COLLECTION = "PAE_Live"
GALLERY_ROOT_COLLECTION = "PAE_Gallery"
M2_STAIR_PROOF_COLLECTION = "PAE_M2_StairProof"
M1_OPENINGS_PROOF_COLLECTION = "PAE_M1_OpeningsProof"
FORTRESS_COLLECTION = "PAE_Fortress"
FORTRESS_SCREENSHOT_REL = Path("Saved") / "Screenshots" / "fortress_live.png"
# Gallery labels that use compound builders instead of single-spec factories.
_COMPOUND_GALLERY_LABELS = frozenset({"fortress"})
# Object name prefixes removed by :func:`clear_pae_scene`.
_PAE_OBJECT_PREFIXES = ("PAE_", "m1_", "m2_", "m3_", "fortress_")
_PAE_MATERIAL_PREFIX = "PAE_Mat_"
GALLERY_GAP_M = 2.0
# Deterministic gallery camera: SE (+X, −Y) elevated — never random orbit per run.
GALLERY_CAM_DIRECTION = (1.0, -1.0, 0.65)
GALLERY_CAM_MARGIN = 1.38
GALLERY_CAM_LENS_MM = 40.0
GALLERY_CAM_ORTHO = True
# M2 stair proof: side view perpendicular to stair run (world AABB), not along treads.
STAIR_PROOF_CAM_ELEVATION = 0.55
STAIR_PROOF_CAM_SIDE_Y = -1.0  # run longer in X → camera from −Y
STAIR_PROOF_CAM_SIDE_X = 1.0  # run longer in Y → camera from +X
STAIR_PROOF_CAM_MARGIN = 1.15
GALLERY_SUN_ENERGY = 4.5
# M1 openings proof: SE (+X, −Y) elevated on south door + west windows — exterior shell only.
OPENINGS_PROOF_CAM_DIRECTION = (1.0, -0.92, 0.58)
OPENINGS_PROOF_CAM_MARGIN = 1.22

# Workbench-friendly Base Color (RGBA 0–1) per placement kind.
# Muted hues — distinct at gallery distance, not emissive neon.
KIND_MATERIAL_COLORS: Dict[str, Tuple[float, float, float, float]] = {
    "wall": (0.72, 0.68, 0.60, 1.0),  # warm stucco
    "floor": (0.52, 0.40, 0.30, 1.0),  # plank wood brown
    "ground": (0.40, 0.48, 0.32, 1.0),  # earth / turf olive
    "roof": (0.32, 0.38, 0.52, 1.0),  # slate blue
    "stair": (0.62, 0.44, 0.34, 1.0),  # terracotta treads
    "tower_arc": (0.78, 0.64, 0.50, 1.0),  # sandstone drum
    "tower_crown": (0.48, 0.46, 0.52, 1.0),  # cool battlements
    "tower_cap": (0.58, 0.62, 0.55, 1.0),  # weathered stone cone
    "door": (0.58, 0.36, 0.24, 1.0),  # dark wood (wall tint)
    "window": (0.58, 0.72, 0.82, 1.0),  # pale glazing (wall tint)
    "prop": (0.72, 0.55, 0.38, 1.0),  # decorative accent
    "light_anchor": (0.72, 0.65, 0.28, 1.0),  # warm anchor marker (muted for workbench)
    "plinth": (0.35, 0.34, 0.33, 1.0),  # foundation stone
    "column": (0.62, 0.58, 0.52, 1.0),  # stone pier / newel
    "hole": (0.20, 0.20, 0.22, 1.0),  # void rim (rare in gallery)
}
_DEFAULT_KIND_COLOR: Tuple[float, float, float, float] = (0.75, 0.75, 0.75, 1.0)

# Asset-specific tints — placements often share ``kind`` (e.g. door/window ``kind=wall``).
# Higher contrast than kind defaults so gallery/workbench reads openings and variants.
ASSET_MATERIAL_COLORS: Dict[str, Tuple[float, float, float, float]] = {
    "wall_door": (0.55, 0.28, 0.12, 1.0),  # dark oak door
    "wall_door_gothic": (0.42, 0.18, 0.10, 1.0),  # darker gothic door
    "wall_window": (0.35, 0.65, 0.92, 1.0),  # bright sky glazing
    "wall_window_lancet": (0.25, 0.55, 0.88, 1.0),  # gothic lancet
    "roof_flat": (0.22, 0.35, 0.62, 1.0),  # deep slate deck
    "roof_gable_infill": (0.28, 0.42, 0.58, 1.0),  # slate gable end-cap
    "roof_pitched_slope": (0.26, 0.40, 0.66, 1.0),  # slate-blue pitched plane
    "roof_hip": (0.48, 0.38, 0.62, 1.0),  # slate-blue hip
    "dormer_steep": (0.30, 0.45, 0.72, 1.0),  # bright slate dormer
    "spire_needle": (0.12, 0.22, 0.48, 1.0),  # deep blue needle spire
    "spire_conical": (0.34, 0.48, 0.78, 1.0),  # bright slate conical spire
    "spire_octagonal": (0.45, 0.55, 0.82, 1.0),  # pale slate octagonal spire
    "roof_valley": (0.58, 0.32, 0.48, 1.0),  # plum valley trough
    "tower_arc_quarter": (0.82, 0.68, 0.45, 1.0),  # warm sandstone drum
    "tower_crown": (0.52, 0.42, 0.68, 1.0),  # purple-gray battlements
    "tower_cap": (0.45, 0.62, 0.38, 1.0),  # mossy stone cone
    "stair_straight": (0.82, 0.45, 0.22, 1.0),  # terracotta treads
    "stair_half": (0.42, 0.58, 0.72, 1.0),  # cool stone half-flight
    "stair_landing": (0.62, 0.58, 0.50, 1.0),
    "stair_switchback": (0.75, 0.40, 0.28, 1.0),
    "stair_wide": (0.55, 0.22, 0.48, 1.0),  # plum monumental
    "stair_spiral_quarter": (0.78, 0.52, 0.18, 1.0),  # copper spiral
    "spiral_newel": (0.55, 0.48, 0.40, 1.0),  # stone newel pillar
    "floor_hole": (0.12, 0.12, 0.18, 1.0),  # void rim
    "shell_wall_solid": (0.92, 0.88, 0.78, 1.0),  # cream render exterior
    "shell_wall_interior": (0.86, 0.84, 0.80, 1.0),  # plaster interior
    "shell_floor_slab": (0.62, 0.52, 0.40, 1.0),  # floor boards
    "shell_window_frame": (0.12, 0.12, 0.14, 1.0),  # dark sash sticks
    "shell_window_glass": (0.62, 0.74, 0.84, 0.28),  # pale glazing — see-through in Workbench
    "shell_window_muntin": (0.10, 0.10, 0.12, 1.0),  # darker muntin cross
    "shell_stair_rail": (0.42, 0.36, 0.30, 1.0),  # dark wood handrail
    "shell_door": (0.18, 0.12, 0.10, 1.0),  # dark Georgian door panel
    "shell_chimney_stub": (0.55, 0.50, 0.46, 1.0),  # brick chimney stack
    "shell_roof_slab": (0.26, 0.32, 0.44, 1.0),  # dark blue-grey slate
    "shell_roof_slope": (0.26, 0.32, 0.44, 1.0),  # dark blue-grey slate
    "shell_gable_end": (0.26, 0.32, 0.44, 1.0),  # dark blue-grey slate
}
_TINTED_ASSET_PREFIXES = ("roof_", "tower_", "stair_", "spire_", "dormer_")
_TINTED_ASSET_EXACT = frozenset(ASSET_MATERIAL_COLORS.keys())
_TRANSPARENT_ASSET_IDS = frozenset({"shell_window_glass"})

# Workbench PNGs read ``scene.display.shading`` + material viewport color — not Cycles lights.
WORKBENCH_SCREENSHOT_VIEW_TRANSFORM = "Standard"
WORKBENCH_SCREENSHOT_RESOLUTION = (1280, 720)


def material_color_for_kind(kind: str) -> Tuple[float, float, float, float]:
    """Return RGBA base color for a placement *kind* (import-safe, no bpy)."""
    return KIND_MATERIAL_COLORS.get(kind, _DEFAULT_KIND_COLOR)


def material_key_for_placement(asset_id: str, kind: str = "wall") -> str:
    """Blender material slot key — asset_id when tinted, else kind."""
    if asset_id in _TINTED_ASSET_EXACT:
        return asset_id
    for prefix in _TINTED_ASSET_PREFIXES:
        if asset_id.startswith(prefix):
            return asset_id
    return kind


def material_color_for_placement(
    asset_id: str,
    kind: str = "wall",
) -> Tuple[float, float, float, float]:
    """Return RGBA for a placement — asset tint first, then kind fallback."""
    if asset_id in ASSET_MATERIAL_COLORS:
        return ASSET_MATERIAL_COLORS[asset_id]
    if material_key_for_placement(asset_id, kind) != kind:
        return material_color_for_kind(kind)
    return material_color_for_kind(kind)


def configure_workbench_screenshot_scene(scene: Any) -> None:
    """Configure Workbench render + solid shading so material base colors appear in PNGs."""
    w, h = WORKBENCH_SCREENSHOT_RESOLUTION
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    if hasattr(scene.render, "image_settings"):
        scene.render.image_settings.file_format = "PNG"
    view_settings = getattr(scene, "view_settings", None)
    if view_settings is not None:
        view_settings.view_transform = WORKBENCH_SCREENSHOT_VIEW_TRANSFORM
        if hasattr(view_settings, "look"):
            view_settings.look = "None"
    display = getattr(scene, "display", None)
    if display is not None and hasattr(display, "shading"):
        shading = display.shading
        if hasattr(shading, "type"):
            shading.type = "SOLID"
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        if hasattr(shading, "show_transparent_back"):
            shading.show_transparent_back = True


def apply_material_base_color(mat: Any, rgba: Tuple[float, float, float, float]) -> None:
    """Set Principled Base Color and viewport diffuse — Workbench MATERIAL mode uses both."""
    mat.diffuse_color = rgba
    alpha = float(rgba[3]) if len(rgba) > 3 else 1.0
    if alpha < 0.999:
        mat.blend_method = "BLEND"
        if hasattr(mat, "use_backface_culling"):
            mat.use_backface_culling = False
    if getattr(mat, "use_nodes", False) and mat.node_tree is not None:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = 0.7
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if alpha < 0.999 and "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.35


def reload_pae() -> List[str]:
    """Drop cached ``pae.*`` modules so agent edits take effect without restarting Blender.

    Blender (and Cursor MCP sessions) cache modules across script re-runs —
    without this, boolean/solver fixes appear to do nothing. See Docs §13.7.

    Does **not** unload ``pae.blender_build`` itself (would break an in-flight call);
    subsequent ``from pae...`` imports inside helpers still refresh.
    """
    stale = sorted(
        (name for name in list(sys.modules) if name == "pae" or name.startswith("pae.")),
        key=lambda n: n.count("."),
        reverse=True,
    )
    dropped: List[str] = []
    for name in stale:
        if name == "pae.blender_build":
            continue
        sys.modules.pop(name, None)
        dropped.append(name)
    return dropped


def _repo_root() -> Path:
    return _PAE_ROOT


def _screenshot_path() -> Path:
    out = _repo_root() / SCREENSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _gallery_screenshot_path() -> Path:
    out = _repo_root() / GALLERY_SCREENSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _per_milestone_screenshot_path(label: str) -> Path:
    out = _repo_root() / "Saved" / "Screenshots" / f"gallery_{label}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _m2_stair_proof_screenshot_path() -> Path:
    out = _repo_root() / M2_STAIR_PROOF_SCREENSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _m1_openings_proof_screenshot_path() -> Path:
    out = _repo_root() / M1_OPENINGS_PROOF_SCREENSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _fortress_screenshot_path() -> Path:
    out = _repo_root() / FORTRESS_SCREENSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def resolve_fortress_compound_builder():
    """Return ``pae.compound.build_fortress_compound`` (flat-ground bailey campus)."""
    from pae.compound import build_fortress_compound

    return build_fortress_compound


def assemble_fortress_compound(*, label: str = "fortress") -> Tuple[Any, Any, Any]:
    """``build_fortress_compound`` → validate. Fail-closed on critical failures."""
    from pae.compound import build_fortress_compound
    from pae.validate import validate

    assembly, layout, compound_report = build_fortress_compound()
    if assembly is None or not assembly.placements:
        raise RuntimeError(f"{label}: compound produced no placements ({compound_report})")
    if not compound_report.ok:
        crit = "; ".join(f.message for f in compound_report.critical[:5])
        raise RuntimeError(f"{label}: compound failed — {crit or compound_report}")
    assembly, vreport = validate(assembly)
    if not vreport.ok:
        crit = "; ".join(f.message for f in vreport.critical[:5])
        raise RuntimeError(f"{label}: validate failed — {crit or vreport}")
    return assembly, vreport, layout


def is_stair_proof_placement(p) -> bool:
    """Placements that define the stair + floor-hole proof frame."""
    return p.asset_id in ("stair_straight", "floor_hole") or p.kind == "stair"


def is_stair_proof_visible_asset(
    asset_id: Optional[str],
    piece_id: Optional[str] = None,
    *,
    level: Optional[int] = None,
) -> bool:
    """True when a mesh instance should remain visible in the M2 stair proof shot."""
    tokens = (str(asset_id or ""), str(piece_id or ""))
    combined = " ".join(tokens).lower()
    if "stair" in combined:
        return True
    if "floor_hole" in combined or "hole" in combined:
        return True
    # Show upper floor slabs so the stair exit reads as an opening, not a floating rim.
    if asset_id == "floor" and level is not None and level >= 1:
        return True
    return False


def stair_proof_bounds_cm(assembly) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """World AABB (cm) union of stair + floor_hole placements — import-safe."""
    from pae.contract import placement_world_aabb

    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    count = 0
    for p in assembly.placements:
        if not is_stair_proof_placement(p):
            continue
        count += 1
        bb_min, bb_max = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        mins[0] = min(mins[0], bb_min[0])
        mins[1] = min(mins[1], bb_min[1])
        mins[2] = min(mins[2], bb_min[2])
        maxs[0] = max(maxs[0], bb_max[0])
        maxs[1] = max(maxs[1], bb_max[1])
        maxs[2] = max(maxs[2], bb_max[2])
    if count == 0:
        raise RuntimeError("stair proof: no stair_straight or floor_hole placements")
    return (tuple(mins), tuple(maxs))


def stair_proof_bounds_m(
    assembly,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Stair-proof world AABB (m) after optional gallery/live offset."""
    bb_min, bb_max = stair_proof_bounds_cm(assembly)
    ox, oy, oz = offset_m
    return (
        (
            bb_min[0] * CM_TO_M + ox,
            bb_min[1] * CM_TO_M + oy,
            bb_min[2] * CM_TO_M + oz,
        ),
        (
            bb_max[0] * CM_TO_M + ox,
            bb_max[1] * CM_TO_M + oy,
            bb_max[2] * CM_TO_M + oz,
        ),
    )


def stair_proof_camera_direction_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Unit offset from target: perpendicular to the longer horizontal run axis."""
    sx = max(bb_max[0] - bb_min[0], 1e-6)
    sy = max(bb_max[1] - bb_min[1], 1e-6)
    elev = STAIR_PROOF_CAM_ELEVATION
    if sx >= sy:
        return _normalize_vec3((0.0, STAIR_PROOF_CAM_SIDE_Y, elev))
    return _normalize_vec3((STAIR_PROOF_CAM_SIDE_X, 0.0, elev))


def stair_proof_ortho_scale_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    *,
    margin: float = STAIR_PROOF_CAM_MARGIN,
) -> float:
    """Ortho scale on the face visible when shooting perpendicular to the run."""
    sx = max(bb_max[0] - bb_min[0], 0.5)
    sy = max(bb_max[1] - bb_min[1], 0.5)
    sz = max(bb_max[2] - bb_min[2], 0.5)
    if sx >= sy:
        return max(sx, sz) * margin
    return max(sy, sz) * margin


def stair_proof_camera_pose_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
) -> Dict[str, Any]:
    """Deterministic camera pose for the M2 stair + hole proof shot."""
    direction = stair_proof_camera_direction_from_bounds_m(bb_min, bb_max)
    pose = camera_pose_from_bounds_m(
        bb_min,
        bb_max,
        margin=STAIR_PROOF_CAM_MARGIN,
        direction=direction,
        ortho=GALLERY_CAM_ORTHO,
    )
    pose["ortho_scale"] = stair_proof_ortho_scale_from_bounds_m(
        bb_min, bb_max, margin=STAIR_PROOF_CAM_MARGIN
    )
    return pose


def is_openings_proof_placement(p) -> bool:
    """South + west exterior shell placements that frame door/windows (import-safe)."""
    if p.kind == "ground":
        return True
    if p.kind != "wall":
        return False
    if p.yaw == 270:
        return True
    if p.yaw == 0 and p.cell[0] == 0:
        return True
    return False


def is_openings_proof_aperture_placement(p) -> bool:
    """Door + window wall pieces on the M1 proof shell."""
    return p.asset_id in ("wall_door", "wall_window")


def is_openings_proof_visible_asset(
    asset_id: Optional[str],
    piece_id: Optional[str] = None,
) -> bool:
    """True when a mesh should remain visible in the M1 openings proof shot."""
    asset = str(asset_id or "")
    piece = str(piece_id or "")
    if asset == "ground_plinth" or piece.startswith("ground_"):
        return True
    if asset in ("roof_flat", "floor"):
        return False
    if piece.startswith("wall_east_") or piece.startswith("wall_north_"):
        return False
    if piece.startswith("wall_south_") or piece.startswith("wall_west_"):
        return True
    if asset in ("wall_door", "wall_window", "wall_plain"):
        combined = f"{asset} {piece}".lower()
        if "east" in combined or "north" in combined:
            return False
        if "south" in combined or "west" in combined:
            return True
    return False


def openings_proof_bounds_cm(assembly) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """World AABB (cm) of south + west exterior shell — import-safe."""
    from pae.contract import placement_world_aabb

    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    count = 0
    for p in assembly.placements:
        if not is_openings_proof_placement(p):
            continue
        count += 1
        bb_min, bb_max = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        mins[0] = min(mins[0], bb_min[0])
        mins[1] = min(mins[1], bb_min[1])
        mins[2] = min(mins[2], bb_min[2])
        maxs[0] = max(maxs[0], bb_max[0])
        maxs[1] = max(maxs[1], bb_max[1])
        maxs[2] = max(maxs[2], bb_max[2])
    if count == 0:
        raise RuntimeError("openings proof: no south/west shell placements")
    return (tuple(mins), tuple(maxs))


def openings_proof_bounds_m(
    assembly,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Openings-proof world AABB (m) after optional offset."""
    bb_min, bb_max = openings_proof_bounds_cm(assembly)
    ox, oy, oz = offset_m
    return (
        (
            bb_min[0] * CM_TO_M + ox,
            bb_min[1] * CM_TO_M + oy,
            bb_min[2] * CM_TO_M + oz,
        ),
        (
            bb_max[0] * CM_TO_M + ox,
            bb_max[1] * CM_TO_M + oy,
            bb_max[2] * CM_TO_M + oz,
        ),
    )


def openings_proof_camera_pose_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
) -> Dict[str, Any]:
    """Deterministic SE-elevated camera pose for the M1 door + window proof shot."""
    return camera_pose_from_bounds_m(
        bb_min,
        bb_max,
        margin=OPENINGS_PROOF_CAM_MARGIN,
        direction=OPENINGS_PROOF_CAM_DIRECTION,
        ortho=GALLERY_CAM_ORTHO,
    )


def assembly_bounds_cm(assembly) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """World AABB (cm) union of all placements — used for gallery side-by-side offsets."""
    from pae.contract import placement_world_aabb

    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    for p in assembly.placements:
        bb_min, bb_max = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        mins[0] = min(mins[0], bb_min[0])
        mins[1] = min(mins[1], bb_min[1])
        mins[2] = min(mins[2], bb_min[2])
        maxs[0] = max(maxs[0], bb_max[0])
        maxs[1] = max(maxs[1], bb_max[1])
        maxs[2] = max(maxs[2], bb_max[2])
    if not assembly.placements:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return (tuple(mins), tuple(maxs))


def assembly_footprint_extent_m(assembly) -> Tuple[float, float, float]:
    """Axis extents (m) of the assembly world AABB."""
    bb_min, bb_max = assembly_bounds_cm(assembly)
    return (
        (bb_max[0] - bb_min[0]) * CM_TO_M,
        (bb_max[1] - bb_min[1]) * CM_TO_M,
        (bb_max[2] - bb_min[2]) * CM_TO_M,
    )


def placement_instance_local_size_cm(p) -> Tuple[float, float, float]:
    """Placement dimensions in prototype-local axes before yaw rotation."""
    sx, sy, sz = (float(v) for v in p.size_cm)
    if bool(getattr(p, "rotates_about_center", False)) and int(p.yaw) % 180 == 90:
        # Centred placement size_cm is its world AABB contract. Swap back to
        # prototype-local axes before Blender applies yaw.
        sx, sy = sy, sx
    return (sx, sy, sz)


def placement_instance_scale_cm(p) -> Tuple[float, float, float]:
    """Per-axis scale from catalog prototype ``size_cm`` to placement ``size_cm``.

    Spanning pieces (``roof_flat``, upper-storey floor decks) assemble with
    XY larger than the 1×1 catalog mesh; instances must non-uniformly scale or
    the roof reads as a recessed 4 m slab on a 16×12 m box.
    """
    from pae.primitives.catalog import catalog_by_id

    cat = catalog_by_id()
    desc = cat.get(p.asset_id)
    if desc is None:
        base = tuple(p.size_cm)
    else:
        base = desc.size_cm

    def _ratio(placed: float, proto: float) -> float:
        if proto <= 0.0:
            return 1.0
        return placed / proto

    local_size = placement_instance_local_size_cm(p)
    return tuple(_ratio(local_size[i], base[i]) for i in range(3))


def assembly_world_bounds_m(
    assembly,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """World AABB (m) for an assembly after gallery/live offset."""
    bb_min, bb_max = assembly_bounds_cm(assembly)
    ox, oy, oz = offset_m
    return (
        (
            bb_min[0] * CM_TO_M + ox,
            bb_min[1] * CM_TO_M + oy,
            bb_min[2] * CM_TO_M + oz,
        ),
        (
            bb_max[0] * CM_TO_M + ox,
            bb_max[1] * CM_TO_M + oy,
            bb_max[2] * CM_TO_M + oz,
        ),
    )


def _normalize_vec3(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = v
    length = math.sqrt(x * x + y * y + z * z)
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (x / length, y / length, z / length)


def camera_pose_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    *,
    margin: float = GALLERY_CAM_MARGIN,
    direction: Tuple[float, float, float] = GALLERY_CAM_DIRECTION,
    ortho: bool = GALLERY_CAM_ORTHO,
) -> Dict[str, Any]:
    """Deterministic camera pose from a world AABB in metres (import-safe, no bpy)."""
    cx = (bb_min[0] + bb_max[0]) * 0.5
    cy = (bb_min[1] + bb_max[1]) * 0.5
    cz = (bb_min[2] + bb_max[2]) * 0.5
    sx = max(bb_max[0] - bb_min[0], 0.5)
    sy = max(bb_max[1] - bb_min[1], 0.5)
    sz = max(bb_max[2] - bb_min[2], 0.5)
    radius = max(sx, sy, sz) * margin
    dx, dy, dz = _normalize_vec3(direction)
    location = (cx + dx * radius, cy + dy * radius, cz + dz * radius)
    target = (cx, cy, cz)
    # Ortho scale fits the ground footprint plus height when viewed from SE.
    ortho_scale = max(math.hypot(sx, sy), sz) * margin
    return {
        "location": location,
        "target": target,
        "radius_m": radius,
        "ortho": ortho,
        "ortho_scale": ortho_scale,
        "lens_mm": GALLERY_CAM_LENS_MM,
    }


def _is_gallery_instance_mesh(obj) -> bool:
    return (
        obj.type == "MESH"
        and not obj.hide_get()
        and not obj.hide_render
        and obj.name.startswith("PAE_")
        and "Proto" not in obj.name
    )


def _meshes_in_collection_tree(coll) -> List[Any]:
    """All visible PAE instance meshes under *coll* (not global scene scan)."""
    found: List[Any] = []

    def _walk(node) -> None:
        for obj in node.objects:
            if _is_gallery_instance_mesh(obj):
                found.append(obj)
        for child in node.children:
            _walk(child)

    _walk(coll)
    return found


def mesh_world_bounds_m(objects: Sequence[Any]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Union world AABB (m) for Blender mesh objects using ``bound_box`` corners."""
    from mathutils import Vector

    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    count = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        count += 1
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            mins[0] = min(mins[0], w.x)
            mins[1] = min(mins[1], w.y)
            mins[2] = min(mins[2], w.z)
            maxs[0] = max(maxs[0], w.x)
            maxs[1] = max(maxs[1], w.y)
            maxs[2] = max(maxs[2], w.z)
    if count == 0:
        raise RuntimeError("no PAE mesh instances to frame")
    return (tuple(mins), tuple(maxs))


def _gallery_factories() -> List[Tuple[str, str, Any]]:
    """Return ``(label, collection_name, factory)`` for the M1–M4 + school gallery."""
    from pae import spec as spec_mod

    entries: List[Tuple[str, str, str]] = [
        ("m1", "PAE_M1", "m1_box_house_spec"),
        ("m2", "PAE_M2", "m2_two_storey_stair_spec"),
        ("m3", "PAE_M3", "m3_keep_tower_spec"),
        ("m4_l", "PAE_M4_L", "m4_l_plan_spec"),
        ("m4_u", "PAE_M4_U", "m4_u_plan_spec"),
        ("m4_c", "PAE_M4_C", "m4_courtyard_spec"),
        ("spiral", "PAE_Spiral_Tower", "m_spiral_tower_spec"),
        (
            "tower_rooms",
            "PAE_Habitable_Round_Tower",
            "habitable_round_tower_spec",
        ),
        ("tiny_spire", "PAE_Tiny_Round_Spire", "tiny_round_spire_spec"),
        ("small_square", "PAE_Small_Square_Spire", "small_square_spire_spec"),
        ("square_spire", "PAE_Square_Spire", "square_spire_tower_spec"),
        ("lighthouse", "PAE_Giant_Lighthouse", "giant_lighthouse_spec"),
        ("school", "PAE_School", "school_academy_spec"),
        ("rooms", "PAE_Roomed_House", "roomed_house_structure_spec"),
        ("joined", "PAE_Joined_Wings", "joined_wings_structure_spec"),
        ("fortress", FORTRESS_COLLECTION, None),  # compound — see assemble_fortress_compound
    ]
    factories: List[Tuple[str, str, Any]] = []
    for label, coll_name, attr in entries:
        if label in _COMPOUND_GALLERY_LABELS:
            factories.append((label, coll_name, None))
            continue
        factory = getattr(spec_mod, attr, None)
        if callable(factory):
            factories.append((label, coll_name, factory))
    return factories


def _spec_factories() -> List[Tuple[str, Any]]:
    """Return ``(label, factory)`` for M1, M2, and M3 (if defined)."""
    from pae import spec as spec_mod

    factories: List[Tuple[str, Any]] = []
    m1 = getattr(spec_mod, "m1_box_house_spec", None)
    if callable(m1):
        factories.append(("m1", m1))
    # Optional M2 — do not invent if missing.
    for name in (
        "m2_two_storey_stair_spec",
        "m2_two_storey_spec",
        "m2_box_house_spec",
        "m2_two_storeys_spec",
    ):
        m2 = getattr(spec_mod, name, None)
        if callable(m2):
            factories.append(("m2", m2))
            break
    m3 = getattr(spec_mod, "m3_keep_tower_spec", None)
    if callable(m3):
        factories.append(("m3", m3))
    return factories


def assemble_and_validate(label: str, factory) -> Tuple[Any, Any]:
    """spec → assemble → validate. Raises if validation fails critically.

    School milestone also runs the trim pass after a green validate.
    """
    from pae.pipeline import run_through_assemble, run_through_validate_trim
    from pae.validate import validate

    spec = factory()
    if label == "school":
        _massing, _plan, assembly, stage_report = run_through_validate_trim(spec)
    else:
        _massing, _plan, assembly, stage_report = run_through_assemble(spec)
        if assembly is not None and assembly.placements:
            assembly, stage_report = validate(assembly)
    if assembly is None or not assembly.placements:
        raise RuntimeError(f"{label}: assemble produced no placements ({stage_report})")
    if not stage_report.ok:
        crit = "; ".join(f.message for f in stage_report.critical[:5])
        raise RuntimeError(f"{label}: validate failed — {crit or stage_report}")
    return assembly, stage_report


def _assemble_for_gallery(label: str, factory) -> Tuple[Any, Any]:
    """Spec factory or compound preset — always fail-closed on critical validate."""
    if label in _COMPOUND_GALLERY_LABELS:
        assembly, report, _layout = assemble_fortress_compound(label=label)
        return assembly, report
    return assemble_and_validate(label, factory)


def build_school_showcase(
    *,
    write_png: bool = True,
    skip_scene_clear: bool = False,
) -> Dict[str, Any]:
    """Build the school academy into ``PAE_School`` and write ``school_*.png``."""
    result = build_gallery(
        milestones=("school",),
        write_png=write_png,
        skip_scene_clear=skip_scene_clear,
    )
    # Alias canonical proof path expected by SCHOOL_READINESS / Wave 5.
    per = result.get("per_milestone_screenshots") or {}
    school_shot = per.get("school")
    if school_shot and write_png:
        try:
            import shutil

            dest = _repo_root() / "Saved" / "Screenshots" / "school_academy.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = Path(school_shot)
            if src.is_file():
                shutil.copy2(src, dest)
                result["school_screenshot"] = str(dest)
        except OSError:
            result["school_screenshot"] = school_shot
    else:
        result["school_screenshot"] = school_shot
    result["mode"] = "school"
    return result


def _ensure_collection(name: str, *, parent=None):
    import bpy

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent is None:
            bpy.context.scene.collection.children.link(coll)
        else:
            parent.children.link(coll)
    elif parent is not None and coll.name not in {c.name for c in parent.children}:
        parent.children.link(coll)
    return coll


def _unlink_collection_tree(coll) -> None:
    """Recursively delete a collection tree.

    Blender ``Collection`` has no ``users_collection`` (that is an Object API).
    Parents are found by scanning scene + data collections' ``children``.
    """
    import bpy

    for child in list(coll.children):
        _unlink_collection_tree(child)
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    parents: List[Any] = []
    scene_root = bpy.context.scene.collection
    if coll.name in {c.name for c in scene_root.children}:
        parents.append(scene_root)
    for other in bpy.data.collections:
        if other is coll:
            continue
        if coll.name in {c.name for c in other.children}:
            parents.append(other)
    for parent in parents:
        parent.children.unlink(coll)
    bpy.data.collections.remove(coll)


def _clear_proto_meshes() -> None:
    """Drop cached ``PAE_Proto_*`` objects so mesh authoring edits take effect.

    Without this, gallery rebuilds reuse stale 8-vert box protos for crown/cap/roof.
    """
    import bpy

    for obj in list(bpy.data.objects):
        if obj.name.startswith("PAE_Proto_"):
            mesh = obj.data if obj.type == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and getattr(mesh, "users", 1) == 0:
                bpy.data.meshes.remove(mesh)


def _is_pae_collection_name(name: str) -> bool:
    return name.startswith("PAE_")


def _is_pae_object_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in _PAE_OBJECT_PREFIXES)


def clear_pae_scene() -> Dict[str, int]:
    """Remove all PAE collections/objects and orphan PAE data blocks.

    Clears prior live/gallery/proof builds so the viewport shows only the next
    build. Safe to call before ``build_fortress_live`` or ``build_gallery``.
    """
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    counts = {"collections": 0, "objects": 0, "meshes": 0, "materials": 0, "images": 0}

    scene_root = bpy.context.scene.collection

    # Top-level PAE trees linked under the scene (Gallery, Live, Fortress, proofs, …).
    for coll in list(scene_root.children):
        if _is_pae_collection_name(coll.name):
            _unlink_collection_tree(coll)
            counts["collections"] += 1

    # Orphan PAE collections left unlinked (partial prior clears / nested leftovers).
    for coll in list(bpy.data.collections):
        if _is_pae_collection_name(coll.name):
            _unlink_collection_tree(coll)
            counts["collections"] += 1

    for obj in list(bpy.data.objects):
        if _is_pae_object_name(obj.name):
            bpy.data.objects.remove(obj, do_unlink=True)
            counts["objects"] += 1

    _clear_proto_meshes()

    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
            counts["meshes"] += 1

    for mat in list(bpy.data.materials):
        if mat.name.startswith(_PAE_MATERIAL_PREFIX) and mat.users == 0:
            bpy.data.materials.remove(mat)
            counts["materials"] += 1

    for img in list(bpy.data.images):
        if img.name.startswith("PAE_") and img.users == 0:
            bpy.data.images.remove(img)
            counts["images"] += 1

    return counts


def prepare_fortress_live_scene(*, skip_clear: bool = False) -> Tuple[Any, Dict[str, int]]:
    """Full PAE slate, then an empty ``PAE_Fortress`` collection."""
    cleared = {} if skip_clear else clear_pae_scene()
    coll = _ensure_collection(FORTRESS_COLLECTION)
    return coll, cleared


def prepare_gallery_scene(*, skip_clear: bool = False) -> Tuple[Any, Dict[str, int]]:
    """Full PAE slate, then an empty ``PAE_Gallery`` root collection."""
    cleared = {} if skip_clear else clear_pae_scene()
    coll = _ensure_collection(GALLERY_ROOT_COLLECTION)
    return coll, cleared


def _clear_pae_objects():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    _clear_proto_meshes()
    # Remove prior PAE live objects / orphans.
    for obj in list(bpy.data.objects):
        if obj.name.startswith("PAE_") or obj.name.startswith("m1_") or obj.name.startswith("m2_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    coll = _ensure_collection(PAE_ROOT_COLLECTION)
    return coll


def _clear_gallery_collections():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    coll, _cleared = prepare_gallery_scene()
    return coll


def _clear_fortress_collection():
    """Dedicated fortress live collection — clears entire PAE scene first."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    coll, _cleared = prepare_fortress_live_scene()
    return coll


def _ensure_material(asset_id: str, kind: str = "wall"):
    import bpy

    key = material_key_for_placement(asset_id, kind)
    rgba = material_color_for_placement(asset_id, kind)
    name = f"PAE_Mat_{key}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    apply_material_base_color(mat, rgba)
    return mat


def build_framed_opening_fallback(
    asset_id: str,
    size_cm: Tuple[float, float, float],
    *,
    name: Optional[str] = None,
    aperture=None,
):
    """Solid box (optionally boolean-cut) when ``catalog.build_mesh`` has no builder.

    Used for assemble-only assets such as ``roof_flat``.
    """
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or f"fallback_{asset_id}"
    core = bpy_util.box_mesh(obj_name, size_cm, origin_at_min_corner=True)
    if aperture is None:
        return core
    ap = aperture
    cutter_size = (
        ap.max_cm[0] - ap.min_cm[0],
        ap.max_cm[1] - ap.min_cm[1],
        ap.max_cm[2] - ap.min_cm[2],
    )
    cutter = bpy_util.box_mesh(
        f"{obj_name}_cut",
        cutter_size,
        origin_at_min_corner=True,
        location=tuple(ap.min_cm),
    )
    bpy_util.apply_boolean_difference(core, cutter, solver="EXACT")
    return core


def is_spanning_floor_deck(p) -> bool:
    """True for upper-storey floor decks larger than one module bay on both axes."""
    from pae.contract import MODULE_CM

    return (
        getattr(p, "asset_id", None) == "floor"
        and getattr(p, "kind", None) == "floor"
        and float(p.size_cm[0]) > MODULE_CM + 0.5
        and float(p.size_cm[1]) > MODULE_CM + 0.5
    )


def needs_stair_void_punch(p) -> bool:
    """True when this floor must be meshed with ``floor_hole`` voids cut out.

    Shell assemblies tag spanning decks with ``facade_shell``, which used to send
    them through the solid shell-box path and left stairs buried under a slab.
    """
    if is_spanning_floor_deck(p):
        return True
    tags = getattr(p, "tags", frozenset()) or frozenset()
    if getattr(p, "kind", None) != "floor":
        return False
    if "spanning_floor" not in tags:
        return False
    from pae.contract import MODULE_CM

    return float(p.size_cm[0]) > MODULE_CM + 0.5 and float(p.size_cm[1]) > MODULE_CM + 0.5


def spanning_floor_hole_rects_cm(deck, hole_placements, *, peer_decks=()) -> List[Tuple[float, float, float, float]]:
    """Local hole rectangles for VOID ``floor_hole`` placements on a spanning deck.

    Rule 5.1 / Ledger F-7: use every ``covered_cells`` bay of each hole (full
    ``size_cm`` footprint), never ``h.cell`` alone. A 1×2 / 2×1 stairwell is one
    spanning opening — origin-only punch left stairs buried under half a deck.
    """
    from pae.primitives.floors import spanning_deck_hole_rects_cm

    return spanning_deck_hole_rects_cm(deck, hole_placements, peer_decks=peer_decks)


def _mesh_for_spanning_floor_deck(p, hole_placements, *, peer_decks=(), cache: Dict[str, Any]) -> Any:
    """Full-size spanning floor mesh with stair VOIDs punched open."""
    from pae.primitives import bpy_util
    from pae.primitives.floors import slab_with_rect_holes_verts_faces

    from pae.primitives.floors import spanning_deck_hole_rects_cm

    bpy_util.require_bpy()
    key = f"floor_deck::{p.piece_id}::{tuple(p.size_cm)}"
    if key in cache:
        return cache[key]
    rects = spanning_deck_hole_rects_cm(p, hole_placements, peer_decks=peer_decks)
    sx, sy, sz = tuple(p.size_cm)
    verts, faces = slab_with_rect_holes_verts_faces(sx, sy, sz, rects)
    proto_name = f"PAE_Proto_floor_deck_{p.piece_id}"
    obj = bpy_util.mesh_from_verts_faces(proto_name, verts, faces)
    obj.hide_set(True)
    obj.hide_render = True
    cache[key] = obj
    return obj


def _roof_hole_rects_local_cm(p, roof_hole_placements):
    """Return exact local XY exclusions for one unrotated roof placement.

    Roof/tower junctions used to be cut with Blender's Boolean modifier.  Aside
    from being non-deterministic on coplanar faces, that operation can terminate
    Blender.  The authored roof-hole contract is axis-aligned, so panelizing on
    its boundaries produces the same opening without a runtime boolean.
    """
    from pae.contract import placement_world_aabb
    from pae.export.manifest import placement_loc_cm

    if int(round(float(p.yaw))) % 360 != 0 or p.rotates_about_center:
        return []
    origin = placement_loc_cm(p)
    sx, sy, _sz = (float(v) for v in p.size_cm)
    pmin, pmax = placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )
    rects = []
    for hole in roof_hole_placements:
        hmin, hmax = placement_world_aabb(
            hole.cell[0],
            hole.cell[1],
            hole.level,
            hole.yaw,
            hole.size_cm,
            hole.offset_cm,
            rotates_about_center=hole.rotates_about_center,
        )
        x0 = max(pmin[0], hmin[0]) - origin[0]
        y0 = max(pmin[1], hmin[1]) - origin[1]
        x1 = min(pmax[0], hmax[0]) - origin[0]
        y1 = min(pmax[1], hmax[1]) - origin[1]
        x0, x1 = max(0.0, x0), min(sx, x1)
        y0, y1 = max(0.0, y0), min(sy, y1)
        if x1 - x0 > 0.5 and y1 - y0 > 0.5:
            rects.append((x0, y0, x1, y1))
    return rects


def _notched_roof_verts_faces(asset_id, size_cm, rects):
    """Panelize a flat, double-pitch, or gable roof around rectangular voids."""
    sx, sy, sz = (float(v) for v in size_cm)
    xs = sorted({0.0, sx, *(v for r in rects for v in (r[0], r[2]))})
    ys = sorted({0.0, sy, *(v for r in rects for v in (r[1], r[3]))})

    if asset_id == "roof_gable_infill":
        # Gable prisms use their thin dimension as the extrusion axis.
        if sy >= sx:
            top = lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * y / sy - 1.0))
        else:
            top = lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * x / sx - 1.0))
    elif asset_id == "roof_pitched_slope":
        if sx >= sy:
            top = lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * y / sy - 1.0))
        else:
            top = lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * x / sx - 1.0))
    else:
        top = lambda x, y: sz

    verts = []
    faces = []
    for xa, xb in zip(xs, xs[1:]):
        for ya, yb in zip(ys, ys[1:]):
            cx, cy = (xa + xb) * 0.5, (ya + yb) * 0.5
            if any(rx0 < cx < rx1 and ry0 < cy < ry1 for rx0, ry0, rx1, ry1 in rects):
                continue
            z00, z10 = top(xa, ya), top(xb, ya)
            z11, z01 = top(xb, yb), top(xa, yb)
            base = len(verts)
            verts.extend(
                [
                    (xa, ya, 0.0),
                    (xb, ya, 0.0),
                    (xb, yb, 0.0),
                    (xa, yb, 0.0),
                    (xa, ya, z00),
                    (xb, ya, z10),
                    (xb, yb, z11),
                    (xa, yb, z01),
                ]
            )
            faces.extend(
                [
                    (base, base + 3, base + 2, base + 1),
                    (base + 4, base + 5, base + 6, base + 7),
                    (base, base + 1, base + 5, base + 4),
                    (base + 1, base + 2, base + 6, base + 5),
                    (base + 2, base + 3, base + 7, base + 6),
                    (base + 3, base, base + 4, base + 7),
                ]
            )
    return verts, faces


def _mesh_for_notched_roof(p, roof_hole_placements, *, cache: Dict[str, Any]):
    """Build a placement-sized roof mesh with deterministic tower exclusions."""
    from pae.primitives import bpy_util

    rects = _roof_hole_rects_local_cm(p, roof_hole_placements)
    if not rects:
        return None
    key = f"roof_notched::{p.piece_id}::{tuple(p.size_cm)}::{tuple(rects)}"
    if key in cache:
        return cache[key]
    verts, faces = _notched_roof_verts_faces(p.asset_id, p.size_cm, rects)
    obj = bpy_util.mesh_from_verts_faces(
        f"PAE_Proto_roof_notched_{p.piece_id}", verts, faces
    )
    obj.hide_set(True)
    obj.hide_render = True
    cache[key] = obj
    return obj


def _mesh_for_asset(
    asset_id: str,
    size_cm: Tuple[float, float, float],
    *,
    cache: Dict[str, Any],
) -> Any:
    """Build or reuse a prototype mesh object (hidden) for *asset_id*."""
    if asset_id in cache:
        return cache[asset_id]

    from pae.primitives import bpy_util
    from pae.primitives.catalog import build_mesh, catalog_by_id

    bpy_util.require_bpy()
    import bpy

    proto_name = f"PAE_Proto_{asset_id}"
    existing = bpy.data.objects.get(proto_name)
    if existing is not None:
        cache[asset_id] = existing
        return existing

    obj = None
    catalog = catalog_by_id()
    if asset_id in catalog:
        try:
            obj = build_mesh(asset_id, name=proto_name)
        except Exception as exc:  # pragma: no cover - Blender-only
            print(f"[pae.blender_build] build_mesh({asset_id!r}) failed: {exc}; fallback")
            desc = catalog[asset_id]
            obj = build_framed_opening_fallback(
                asset_id,
                desc.size_cm,
                name=proto_name,
                aperture=desc.aperture,
            )
    else:
        obj = build_framed_opening_fallback(asset_id, size_cm, name=proto_name)

    # Hide prototype; instances carry materials / transforms.
    obj.hide_set(True)
    obj.hide_render = True
    obj.name = proto_name
    cache[asset_id] = obj
    return obj


def _mesh_for_shell_box(p, *, cache: Dict[str, Any]) -> Any:
    """Prototype mesh for ``shell_*`` placements — sized box, no catalog stretch."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    key = f"shell_box::{p.piece_id}::{tuple(p.size_cm)}"
    if key in cache:
        return cache[key]
    proto_name = f"PAE_Proto_{p.piece_id}"
    obj = bpy_util.box_mesh(proto_name, tuple(p.size_cm), origin_at_min_corner=True)
    obj.hide_set(True)
    obj.hide_render = True
    cache[key] = obj
    return obj


def _shell_roof_top_fn(asset_id: str, size_cm, tags: frozenset):
    """Height field for shell pitched roof wedges (single-slope or gable prism)."""
    sx, sy, sz = (float(v) for v in size_cm)
    if asset_id == "shell_roof_slope":
        if "slope_south" in tags:
            return lambda x, y: sz * min(1.0, max(0.0, y / sy)) if sy > 0 else 0.0
        if "slope_north" in tags:
            return lambda x, y: sz * min(1.0, max(0.0, 1.0 - y / sy)) if sy > 0 else 0.0
        if "slope_west" in tags:
            return lambda x, y: sz * min(1.0, max(0.0, x / sx)) if sx > 0 else 0.0
        if "slope_east" in tags:
            return lambda x, y: sz * min(1.0, max(0.0, 1.0 - x / sx)) if sx > 0 else 0.0
    if asset_id == "shell_gable_end":
        if "gable_west" in tags or "gable_east" in tags:
            return (
                lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * y / sy - 1.0))
                if sy > 0
                else 0.0
            )
        return (
            lambda x, y: sz * max(0.0, 1.0 - abs(2.0 * x / sx - 1.0))
            if sx > 0
            else 0.0
        )
    return lambda x, y: sz


def _shell_wedge_verts_faces(size_cm, top_fn):
    """Single rectangular panel with sloped top (no voids)."""
    sx, sy, _ = (float(v) for v in size_cm)
    z00, z10 = top_fn(0.0, 0.0), top_fn(sx, 0.0)
    z11, z01 = top_fn(sx, sy), top_fn(0.0, sy)
    verts = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, sy, 0.0),
        (0.0, sy, 0.0),
        (0.0, 0.0, z00),
        (sx, 0.0, z10),
        (sx, sy, z11),
        (0.0, sy, z01),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return verts, faces


def _mesh_for_shell_roof(p, *, cache: Dict[str, Any]) -> Any:
    """Wedge / gable prism for ``shell_roof_slope`` and ``shell_gable_end``."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    tags = getattr(p, "tags", frozenset()) or frozenset()
    key = f"shell_roof::{p.asset_id}::{p.piece_id}::{tuple(p.size_cm)}::{sorted(tags)}"
    if key in cache:
        return cache[key]
    top_fn = _shell_roof_top_fn(p.asset_id, p.size_cm, tags)
    verts, faces = _shell_wedge_verts_faces(p.size_cm, top_fn)
    proto_name = f"PAE_Proto_{p.piece_id}"
    obj = bpy_util.mesh_from_verts_faces(proto_name, verts, faces)
    obj.hide_set(True)
    obj.hide_render = True
    cache[key] = obj
    return obj


def _mesh_for_shell_placement(p, *, cache: Dict[str, Any]) -> Any:
    """Route shell placements to box, punched wall, or pitched roof wedge."""
    aid = getattr(p, "asset_id", "") or ""
    if aid in ("shell_roof_slope", "shell_gable_end"):
        return _mesh_for_shell_roof(p, cache=cache)
    return _mesh_for_shell_box(p, cache=cache)


def _shell_opening_cutters_by_face_level(assembly) -> Dict[Tuple[str, int], list]:
    """Index declarative opening cutters for glazed shell wall panels."""
    out: Dict[Tuple[str, int], list] = {}
    for p in assembly.placements:
        if getattr(p, "asset_id", None) != "shell_opening_cutter":
            continue
        face = next((t[5:] for t in p.tags if t.startswith("face_")), None)
        if face is None:
            continue
        out.setdefault((face, int(p.level)), []).append(p)
    return out


def _mesh_for_shell_wall_punched(
    wall_p,
    cutters: Sequence[Any],
    *,
    cache: Dict[str, Any],
) -> Any:
    """One cream wall mesh per face/storey — boolean cut, panelize on failure."""
    from pae.facade_shell import _face_offset_extra, shell_cutter_hole_yz_cm
    from pae.primitives import bpy_util
    from pae.primitives.walls import wall_solid_with_yz_holes_verts_faces

    bpy_util.require_bpy()
    key = f"shell_punch::{wall_p.piece_id}::{len(cutters)}"
    if key in cache:
        return cache[key]

    wx, wy, wz = (float(v) for v in wall_p.size_cm)
    proto_name = f"PAE_Proto_{wall_p.piece_id}"
    holes = [
        (y0, z0, y1, z1)
        for y0, y1, z0, z1 in (
            shell_cutter_hole_yz_cm(wall_p, cut) for cut in cutters
        )
    ]

    obj = None
    if cutters:
        try:
            core = bpy_util.box_mesh(
                proto_name, (wx, wy, wz), origin_at_min_corner=True
            )
            face = next(t[5:] for t in wall_p.tags if t.startswith("face_"))
            for idx, cut in enumerate(cutters):
                cut_extra = _face_offset_extra(
                    cut.offset_cm,
                    face,
                    cut.yaw,
                    cut.size_cm,
                    panel_size_cm=wall_p.size_cm,
                )
                cutter = bpy_util.box_mesh(
                    f"{proto_name}_cut_{idx}",
                    tuple(cut.size_cm),
                    origin_at_min_corner=True,
                    location=cut_extra,
                )
                bpy_util.apply_boolean_difference(core, cutter, solver="EXACT")
            obj = core
        except Exception:
            obj = None

    if obj is None:
        if holes:
            verts, faces = wall_solid_with_yz_holes_verts_faces(wx, wy, wz, holes)
            obj = bpy_util.mesh_from_verts_faces(proto_name, verts, faces)
        else:
            obj = bpy_util.box_mesh(proto_name, (wx, wy, wz), origin_at_min_corner=True)

    obj.hide_set(True)
    obj.hide_render = True
    cache[key] = obj
    return obj


def instance_facade_shell(
    assembly,
    *,
    label: str = "facade",
    target_coll=None,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> int:
    """Instance a continuous shell assembly (alias for :func:`instance_assembly`)."""
    return instance_assembly(
        assembly, label=label, target_coll=target_coll, offset_m=offset_m
    )


def instance_assembly(
    assembly,
    *,
    label: str = "m1",
    target_coll=None,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> int:
    """Create linked instances for each placement. Returns instance count."""
    from pae.export.manifest import placement_loc_cm
    from pae.primitives import bpy_util
    from pae.primitives.catalog import catalog_by_id

    bpy_util.require_bpy()
    import bpy
    from mathutils import Vector

    coll = target_coll
    if coll is None:
        coll = bpy.data.collections.get(PAE_ROOT_COLLECTION) or _clear_pae_objects()
    cache: Dict[str, Any] = {}
    catalog = catalog_by_id()
    count = 0
    ox, oy, oz = offset_m
    hole_placements = [
        hp
        for hp in assembly.placements
        if getattr(hp, "asset_id", None) == "floor_hole"
    ]
    spanning_floor_decks = [
        dp for dp in assembly.placements if is_spanning_floor_deck(dp)
    ]
    all_floor_decks = [
        dp
        for dp in assembly.placements
        if getattr(dp, "kind", None) == "floor"
        and (
            getattr(dp, "asset_id", None) == "floor"
            or "spanning_floor" in (getattr(dp, "tags", frozenset()) or frozenset())
        )
        and float(dp.size_cm[0]) > 1.0
        and float(dp.size_cm[1]) > 1.0
    ]
    roof_hole_placements = [
        hp
        for hp in assembly.placements
        if getattr(hp, "asset_id", None) == "roof_hole"
    ]
    shell_cutters = _shell_opening_cutters_by_face_level(assembly)
    for p in assembly.placements:
        # ``floor_hole`` is a declarative void/cutter used above to punch the
        # surrounding floor deck. Instancing its legacy blue frame puts solid
        # geometry back into the opening and blocks the stair.
        # Drum-window wall leaves are likewise logical aperture proxies; the
        # windowed curved arc owns the visible geometry.
        if p.asset_id in ("floor_hole", "roof_hole", "shell_opening_cutter") or (
            "non_rendering_aperture_proxy" in p.tags
        ):
            continue
        from pae.facade_shell import is_shell_placement

        # Stair VOIDs before shell-box path — shell-tagged spanning decks must
        # still get floor_hole punches or the well is sealed shut.
        if needs_stair_void_punch(p):
            peers = [
                d
                for d in all_floor_decks
                if d.level == p.level and d.piece_id != p.piece_id
            ]
            proto = _mesh_for_spanning_floor_deck(
                p, hole_placements, peer_decks=peers, cache=cache
            )
            sx = sy = sz = 1.0
        elif is_shell_placement(p):
            if "boolean_parent" in p.tags:
                face = next(
                    (t[5:] for t in p.tags if t.startswith("face_")), None
                )
                cutters = (
                    shell_cutters.get((face, int(p.level)), [])
                    if face is not None
                    else []
                )
                proto = _mesh_for_shell_wall_punched(
                    p, cutters, cache=cache
                )
            else:
                proto = _mesh_for_shell_placement(p, cache=cache)
            sx = sy = sz = 1.0
        else:
            notched_roof = (
                _mesh_for_notched_roof(p, roof_hole_placements, cache=cache)
                if getattr(p, "kind", None) == "roof" and roof_hole_placements
                else None
            )
            if notched_roof is not None:
                proto = notched_roof
                sx = sy = sz = 1.0
            elif is_spanning_floor_deck(p):
                # Full-size mesh with VOID openings already cut — uniform cm→m only.
                peers = [
                    d
                    for d in all_floor_decks
                    if d.level == p.level and d.piece_id != p.piece_id
                ]
                proto = _mesh_for_spanning_floor_deck(
                    p, hole_placements, peer_decks=peers, cache=cache
                )
                sx = sy = sz = 1.0
            else:
                proto = _mesh_for_asset(p.asset_id, tuple(p.size_cm), cache=cache)
                sx, sy, sz = placement_instance_scale_cm(p)
        loc_cm = placement_loc_cm(p)
        loc_m = (
            loc_cm[0] * CM_TO_M + ox,
            loc_cm[1] * CM_TO_M + oy,
            loc_cm[2] * CM_TO_M + oz,
        )
        # ``rotates_about_center`` makes offset_cm an XY centre. Tower arcs and
        # caps are authored around that centre already, but ordinary wall/floor
        # prototypes start at their min corner. Shift those prototypes back by
        # their rotated local half-extents before instancing.
        desc = catalog.get(p.asset_id)
        if (
            bool(getattr(p, "rotates_about_center", False))
            and desc is not None
            and getattr(desc, "origin", "min_corner") != "center"
        ):
            local_sx, local_sy, _local_sz = placement_instance_local_size_cm(p)
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
        # Linked duplicate shares mesh datablock.
        inst = proto.copy()
        inst.data = proto.data
        inst.name = f"PAE_{label}_{p.piece_id}"
        inst.hide_set(False)
        inst.hide_render = False
        inst.location = Vector(loc_m)
        inst.scale = (sx * CM_TO_M, sy * CM_TO_M, sz * CM_TO_M)
        inst.rotation_euler = (0.0, 0.0, math.radians(float(p.yaw)))
        mat = _ensure_material(p.asset_id, getattr(p, "kind", "wall"))
        if len(inst.data.materials) == 0:
            inst.data.materials.append(mat)
        # Object-linked slot so kind tint does not mutate the shared proto mesh.
        if len(inst.material_slots) == 0:
            inst.data.materials.append(mat)
        try:
            inst.material_slots[0].link = "OBJECT"
            inst.material_slots[0].material = mat
        except Exception:
            pass
        coll.objects.link(inst)
        inst["pae_piece_id"] = p.piece_id
        inst["pae_asset_id"] = p.asset_id
        inst["pae_level"] = int(getattr(p, "level", 0))
        inst["pae_cell_x"] = int(p.cell[0])
        inst["pae_cell_y"] = int(p.cell[1])
        inst["pae_kind"] = str(getattr(p, "kind", ""))
        inst["pae_tags"] = "|".join(sorted(str(tag) for tag in p.tags))
        count += 1
    return count


def _apply_camera_pose(pose: Dict[str, Any]) -> None:
    """Apply a ``camera_pose_from_bounds_m`` dict to the active scene camera."""
    import bpy
    from mathutils import Vector

    target = Vector(pose["target"])
    cam = bpy.context.scene.camera
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        bpy.context.scene.camera = cam
    cam.location = Vector(pose["location"])
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    camera_distance = (target - cam.location).length
    if pose.get("ortho"):
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = float(pose["ortho_scale"])
        # Large campuses can place the framing camera beyond Blender's 100 m
        # default far plane, yielding a perfectly framed but completely blank
        # render. Include the full orthographic depth with generous headroom.
        cam.data.clip_end = max(
            float(cam.data.clip_end),
            camera_distance + float(cam.data.ortho_scale) * 2.0,
        )
    else:
        cam.data.type = "PERSP"
        if hasattr(cam.data, "lens"):
            cam.data.lens = float(pose.get("lens_mm", GALLERY_CAM_LENS_MM))
        cam.data.clip_end = max(float(cam.data.clip_end), camera_distance * 4.0)


def _ensure_gallery_lighting() -> None:
    import bpy

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.60, 0.68, 1.0)
        bg.inputs[1].default_value = 1.0

    sun = next((o for o in bpy.data.objects if o.type == "LIGHT" and o.name.startswith("PAE_Sun")), None)
    if sun is None:
        light_data = bpy.data.lights.new(name="PAE_Sun", type="SUN")
        sun = bpy.data.objects.new("PAE_Sun", light_data)
        bpy.context.scene.collection.objects.link(sun)
    sun.data.energy = GALLERY_SUN_ENERGY
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30))


def _apply_stair_proof_visibility(objects: Sequence[Any]) -> Dict[str, List[str]]:
    """Hide every mesh except stair + floor-hole + upper floor slabs."""
    hidden: List[str] = []
    visible: List[str] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        asset = obj.get("pae_asset_id")
        piece = obj.get("pae_piece_id")
        level = obj.get("pae_level")
        try:
            level_i = int(level) if level is not None else None
        except (TypeError, ValueError):
            level_i = None
        label = f"{asset or '?'}:{piece or obj.name}"
        if is_stair_proof_visible_asset(asset, piece, level=level_i):
            obj.hide_render = False
            obj.hide_set(False)
            visible.append(label)
            continue
        obj.hide_render = True
        obj.hide_set(True)
        hidden.append(label)
    return {"hidden": hidden, "visible": visible}


def _hide_non_stair_proof_collections(*, keep: str = M2_STAIR_PROOF_COLLECTION) -> List[str]:
    """Exclude other PAE collections from viewport/render during the proof shot."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    excluded: List[str] = []
    for coll in bpy.data.collections:
        if coll.name == keep:
            coll.hide_viewport = False
            coll.hide_render = False
            continue
        if coll.name.startswith("PAE_") or coll.name in (GALLERY_ROOT_COLLECTION, PAE_ROOT_COLLECTION):
            coll.hide_viewport = True
            coll.hide_render = True
            excluded.append(coll.name)
    return excluded


def prepare_stair_proof_scene() -> Tuple[Any, Dict[str, int]]:
    """Full PAE slate, then an empty ``PAE_M2_StairProof`` collection."""
    cleared = clear_pae_scene()
    coll = _ensure_collection(M2_STAIR_PROOF_COLLECTION)
    return coll, cleared


def _clear_stair_proof_collection():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    coll, _cleared = prepare_stair_proof_scene()
    return coll


def frame_camera_on_stair_proof(
    assembly,
    *,
    collection: str = M2_STAIR_PROOF_COLLECTION,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Frame camera on stair + floor_hole bounds; hide all other instances."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    bpy.context.view_layer.update()
    target_coll = bpy.data.collections.get(collection)
    if target_coll is None:
        raise RuntimeError(f"collection not found: {collection!r}")
    meshes = _meshes_in_collection_tree(target_coll)
    visibility = _apply_stair_proof_visibility(meshes)
    excluded_colls = _hide_non_stair_proof_collections(keep=collection)
    bb_min, bb_max = stair_proof_bounds_m(assembly, offset_m)
    pose = stair_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    _apply_camera_pose(pose)
    _ensure_gallery_lighting()
    bpy.context.view_layer.update()
    return {
        **pose,
        "stair_proof_hidden": visibility["hidden"],
        "stair_proof_visible": visibility["visible"],
        "excluded_collections": excluded_colls,
    }


def write_m2_stair_proof_screenshot(
    path: Optional[Path] = None,
    *,
    assembly=None,
    collection: str = M2_STAIR_PROOF_COLLECTION,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Optional[Path]:
    """Write ``Saved/Screenshots/m2_stair_proof.png`` when bpy is available."""
    from pae.primitives import bpy_util

    if not bpy_util.HAS_BPY:
        return None
    if assembly is None:
        from pae.spec import m2_two_storey_stair_spec

        assembly, _report = assemble_and_validate("m2", m2_two_storey_stair_spec)
    frame_camera_on_stair_proof(assembly, collection=collection, offset_m=offset_m)
    return write_screenshot(path or _m2_stair_proof_screenshot_path())


def build_m2_stair_proof(*, write_png: bool = True) -> Dict[str, Any]:
    """Build isolated M2 and capture stair + floor-hole proof screenshot."""
    reloaded = reload_pae()
    from pae.primitives import bpy_util
    from pae.spec import m2_two_storey_stair_spec

    assembly, report = assemble_and_validate("m2", m2_two_storey_stair_spec)
    stair_min, stair_max = stair_proof_bounds_cm(assembly)
    stair_placements = sum(1 for p in assembly.placements if is_stair_proof_placement(p))

    if not bpy_util.HAS_BPY:
        pose = stair_proof_camera_pose_from_bounds_m(*stair_proof_bounds_m(assembly))
        return {
            "ok": True,
            "blender": False,
            "mode": "stair_proof",
            "reloaded": len(reloaded),
            "placements": len(assembly.placements),
            "stair_proof_placements": stair_placements,
            "stair_bounds_cm": {"min": stair_min, "max": stair_max},
            "camera_pose": pose,
            "screenshot": None,
            "note": "bpy missing - assemble/validate + camera pose only",
        }

    proof_coll, scene_cleared = prepare_stair_proof_scene()
    n = instance_assembly(assembly, label="m2", target_coll=proof_coll)
    frame = frame_camera_on_stair_proof(assembly, collection=M2_STAIR_PROOF_COLLECTION)
    camera_pose = {k: v for k, v in frame.items() if k not in (
        "stair_proof_hidden",
        "stair_proof_visible",
        "excluded_collections",
    )}
    shot = write_screenshot(_m2_stair_proof_screenshot_path()) if write_png else None
    return {
        "ok": report.ok,
        "blender": True,
        "mode": "stair_proof",
        "reloaded": len(reloaded),
        "collection": M2_STAIR_PROOF_COLLECTION,
        "instances": n,
        "placements": len(assembly.placements),
        "stair_proof_placements": stair_placements,
        "stair_bounds_cm": {"min": stair_min, "max": stair_max},
        "camera_pose": camera_pose,
        "stair_proof_hidden": frame["stair_proof_hidden"],
        "stair_proof_visible": frame["stair_proof_visible"],
        "excluded_collections": frame["excluded_collections"],
        "scene_cleared": scene_cleared,
        "screenshot": str(shot) if shot else None,
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
    }


def _apply_openings_proof_visibility(objects: Sequence[Any]) -> Dict[str, List[str]]:
    """Hide north/east walls, roof, and floor — keep south/west shell + ground."""
    hidden: List[str] = []
    visible: List[str] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        asset = obj.get("pae_asset_id")
        piece = obj.get("pae_piece_id")
        label = f"{asset or '?'}:{piece or obj.name}"
        if is_openings_proof_visible_asset(asset, piece):
            obj.hide_render = False
            obj.hide_set(False)
            visible.append(label)
            continue
        obj.hide_render = True
        obj.hide_set(True)
        hidden.append(label)
    return {"hidden": hidden, "visible": visible}


def _clear_openings_proof_collection():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    _clear_proto_meshes()
    coll = bpy.data.collections.get(M1_OPENINGS_PROOF_COLLECTION)
    if coll is not None:
        _unlink_collection_tree(coll)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return _ensure_collection(M1_OPENINGS_PROOF_COLLECTION)


def frame_camera_on_openings_proof(
    assembly,
    *,
    collection: str = M1_OPENINGS_PROOF_COLLECTION,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Frame SE-elevated camera on south door + west windows; hide interior confusion."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    bpy.context.view_layer.update()
    target_coll = bpy.data.collections.get(collection)
    if target_coll is None:
        raise RuntimeError(f"collection not found: {collection!r}")
    meshes = _meshes_in_collection_tree(target_coll)
    visibility = _apply_openings_proof_visibility(meshes)
    excluded_colls = _hide_non_stair_proof_collections(keep=collection)
    bb_min, bb_max = openings_proof_bounds_m(assembly, offset_m)
    pose = openings_proof_camera_pose_from_bounds_m(bb_min, bb_max)
    _apply_camera_pose(pose)
    _ensure_gallery_lighting()
    bpy.context.view_layer.update()
    return {
        **pose,
        "openings_proof_hidden": visibility["hidden"],
        "openings_proof_visible": visibility["visible"],
        "excluded_collections": excluded_colls,
    }


def write_m1_openings_proof_screenshot(
    path: Optional[Path] = None,
    *,
    assembly=None,
    collection: str = M1_OPENINGS_PROOF_COLLECTION,
    offset_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Optional[Path]:
    """Write ``Saved/Screenshots/m1_openings_proof.png`` when bpy is available."""
    from pae.primitives import bpy_util

    if not bpy_util.HAS_BPY:
        return None
    if assembly is None:
        from pae.spec import m1_box_house_spec

        assembly, _report = assemble_and_validate("m1", m1_box_house_spec)
    frame_camera_on_openings_proof(assembly, collection=collection, offset_m=offset_m)
    return write_screenshot(path or _m1_openings_proof_screenshot_path())


def build_m1_openings_proof(*, write_png: bool = True) -> Dict[str, Any]:
    """Build isolated M1 and capture exterior door + window proof screenshot."""
    reloaded = reload_pae()
    from pae.primitives import bpy_util
    from pae.spec import m1_box_house_spec

    assembly, report = assemble_and_validate("m1", m1_box_house_spec)
    shell_min, shell_max = openings_proof_bounds_cm(assembly)
    shell_placements = sum(1 for p in assembly.placements if is_openings_proof_placement(p))
    aperture_placements = sum(
        1 for p in assembly.placements if is_openings_proof_aperture_placement(p)
    )

    if not bpy_util.HAS_BPY:
        pose = openings_proof_camera_pose_from_bounds_m(*openings_proof_bounds_m(assembly))
        return {
            "ok": True,
            "blender": False,
            "mode": "openings_proof",
            "reloaded": len(reloaded),
            "placements": len(assembly.placements),
            "openings_proof_placements": shell_placements,
            "openings_proof_apertures": aperture_placements,
            "openings_bounds_cm": {"min": shell_min, "max": shell_max},
            "camera_pose": pose,
            "screenshot": None,
            "note": "bpy missing - assemble/validate + camera pose only",
        }

    proof_coll = _clear_openings_proof_collection()
    n = instance_assembly(assembly, label="m1", target_coll=proof_coll)
    frame = frame_camera_on_openings_proof(assembly, collection=M1_OPENINGS_PROOF_COLLECTION)
    camera_pose = {k: v for k, v in frame.items() if k not in (
        "openings_proof_hidden",
        "openings_proof_visible",
        "excluded_collections",
    )}
    shot = write_screenshot(_m1_openings_proof_screenshot_path()) if write_png else None
    return {
        "ok": report.ok,
        "blender": True,
        "mode": "openings_proof",
        "reloaded": len(reloaded),
        "collection": M1_OPENINGS_PROOF_COLLECTION,
        "instances": n,
        "placements": len(assembly.placements),
        "openings_proof_placements": shell_placements,
        "openings_proof_apertures": aperture_placements,
        "openings_bounds_cm": {"min": shell_min, "max": shell_max},
        "camera_pose": camera_pose,
        "openings_proof_hidden": frame["openings_proof_hidden"],
        "openings_proof_visible": frame["openings_proof_visible"],
        "excluded_collections": frame["excluded_collections"],
        "screenshot": str(shot) if shot else None,
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
    }


def frame_camera_on_meshes(*, collection: Optional[str] = None) -> None:
    """Frame visible PAE instances — scoped to *collection* when provided."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    # Linked dupes / just-moved instances have stale matrix_world until depsgraph
    # update — framing on identity matrices treats cm meshes as world metres and
    # parks the camera kilometres away (tiny speck / empty PNGs).
    bpy.context.view_layer.update()

    if collection:
        target_coll = bpy.data.collections.get(collection)
        if target_coll is None:
            raise RuntimeError(f"collection not found: {collection!r}")
        meshes = _meshes_in_collection_tree(target_coll)
    else:
        meshes = [obj for obj in bpy.data.objects if _is_gallery_instance_mesh(obj)]

    if not meshes:
        label = collection or "scene"
        raise RuntimeError(f"no PAE mesh instances to frame in {label}")

    bb_min, bb_max = mesh_world_bounds_m(meshes)
    # Sanity: gallery buildings live in metres after scale=0.01. If bounds look
    # like raw centimetres, force another update and remeasure.
    span = max(bb_max[0] - bb_min[0], bb_max[1] - bb_min[1], bb_max[2] - bb_min[2])
    if span > 250.0:
        bpy.context.view_layer.update()
        bb_min, bb_max = mesh_world_bounds_m(meshes)
    pose = camera_pose_from_bounds_m(bb_min, bb_max)
    _apply_camera_pose(pose)
    _ensure_gallery_lighting()
    # Ensure render camera sees the updated transform.
    bpy.context.view_layer.update()


def write_screenshot(path: Optional[Path] = None) -> Path:
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    out = path or _screenshot_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    configure_workbench_screenshot_scene(scene)
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    return out


def write_gallery_screenshot(
    path: Optional[Path] = None,
    *,
    collection: str = GALLERY_ROOT_COLLECTION,
) -> Optional[Path]:
    """Frame the gallery row and write ``Saved/Screenshots/gallery_m1_m4.png``.

    Returns ``None`` when bpy is unavailable (no-op).
    """
    from pae.primitives import bpy_util

    if not bpy_util.HAS_BPY:
        return None
    frame_camera_on_meshes(collection=collection)
    return write_screenshot(path or _gallery_screenshot_path())


def build_gallery(
    *,
    milestones: Optional[Sequence[str]] = None,
    write_png: bool = True,
    gap_m: float = GALLERY_GAP_M,
    stair_proof: bool = False,
    skip_scene_clear: bool = False,
) -> Dict[str, Any]:
    """Build M1–M4 into side-by-side collections under ``PAE_Gallery``.

    Each milestone gets its own child collection (``PAE_M1`` … ``PAE_M4_C``),
    offset along +X by prior footprint width + *gap_m* metres.

    When *stair_proof* is True, also writes ``Saved/Screenshots/m2_stair_proof.png``
    via :func:`build_m2_stair_proof` (isolated M2 at origin).
    """
    reloaded = reload_pae()

    from pae.primitives import bpy_util

    selected = milestones
    factories = _gallery_factories()
    if selected:
        allowed = {s.lower() for s in selected}
        factories = [(lbl, coll, fn) for lbl, coll, fn in factories if lbl in allowed]

    if not bpy_util.HAS_BPY:
        results = []
        for label, coll_name, factory in factories:
            assembly, report = _assemble_for_gallery(label, factory)
            extent = assembly_footprint_extent_m(assembly)
            results.append(
                {
                    "label": label,
                    "collection": coll_name,
                    "placements": len(assembly.placements),
                    "extent_m": extent,
                    "ok": report.ok,
                    "validation_report": report,
                }
            )
        primary = next((r["validation_report"] for r in results if not r["ok"]), None)
        if primary is None and results:
            primary = results[0]["validation_report"]
        return {
            "ok": True,
            "blender": False,
            "mode": "gallery",
            "reloaded": len(reloaded),
            "milestones": results,
            "screenshot": None,
            "per_milestone_screenshots": {},
            "stair_proof_screenshot": None,
            "note": "bpy missing - assemble/validate only",
            "validation_report": primary,
        }

    gallery_root, scene_cleared = prepare_gallery_scene(skip_clear=skip_scene_clear)
    results = []
    cursor_x_m = 0.0
    per_shots: Dict[str, str] = {}
    import bpy

    for label, coll_name, factory in factories:
        assembly, report = _assemble_for_gallery(label, factory)
        bb_min, bb_max = assembly_bounds_cm(assembly)
        offset_m = (
            cursor_x_m - bb_min[0] * CM_TO_M,
            -bb_min[1] * CM_TO_M,
            -bb_min[2] * CM_TO_M,
        )
        child_coll = _ensure_collection(coll_name, parent=gallery_root)
        n = instance_assembly(
            assembly,
            label=label,
            target_coll=child_coll,
            offset_m=offset_m,
        )
        width_m = (bb_max[0] - bb_min[0]) * CM_TO_M
        extent = assembly_footprint_extent_m(assembly)
        results.append(
            {
                "label": label,
                "collection": coll_name,
                "placements": len(assembly.placements),
                "instances": n,
                "offset_m": offset_m,
                "extent_m": extent,
                "ok": report.ok,
                "validation_report": report,
            }
        )
        if write_png:
            # Hide sibling milestone collections so the render is just this building.
            for other_lbl, other_coll, _fn in factories:
                oc = bpy.data.collections.get(other_coll)
                if oc is None:
                    continue
                oc.hide_render = other_coll != coll_name
                oc.hide_viewport = other_coll != coll_name
            frame_camera_on_meshes(collection=coll_name)
            shot = write_screenshot(_per_milestone_screenshot_path(label))
            per_shots[label] = str(shot)
        cursor_x_m += width_m + gap_m

    # Restore visibility for overview shot.
    for _lbl, other_coll, _fn in factories:
        oc = bpy.data.collections.get(other_coll)
        if oc is not None:
            oc.hide_render = False
            oc.hide_viewport = False
    gallery_shot = write_gallery_screenshot() if write_png else None
    stair_proof_result = None
    if stair_proof and write_png:
        stair_proof_result = build_m2_stair_proof(write_png=True)
    primary = next((r["validation_report"] for r in results if not r.get("ok")), None)
    if primary is None and results:
        primary = results[0].get("validation_report")
    return {
        "ok": True,
        "blender": True,
        "mode": "gallery",
        "reloaded": len(reloaded),
        "milestones": results,
        "gap_m": gap_m,
        "screenshot": str(gallery_shot) if gallery_shot else None,
        "per_milestone_screenshots": per_shots,
        "scene_cleared": scene_cleared,
        "stair_proof_screenshot": (
            stair_proof_result.get("screenshot") if stair_proof_result else None
        ),
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
        "validation_report": primary,
    }


def build_fortress_live(
    *,
    write_png: bool = True,
    skip_scene_clear: bool = False,
) -> Dict[str, Any]:
    """Build ``build_fortress_compound()`` into ``PAE_Fortress`` + ``fortress_live.png``.

    Spec preset: ``fortress_bailey_compound_spec()`` via ``pae.compound``. Fail-closed
    on compound or validate critical failures (export/gallery policy).

    When *skip_scene_clear* is True, :func:`prepare_fortress_live_scene` does not call
    :func:`clear_pae_scene` (caller already cleared or wants to preserve siblings).
    """
    reloaded = reload_pae()
    from pae.primitives import bpy_util

    assembly, report, layout = assemble_fortress_compound()
    builder_name = "build_fortress_compound"
    bb_min, bb_max = assembly_bounds_cm(assembly)
    offset_m = (
        -bb_min[0] * CM_TO_M,
        -bb_min[1] * CM_TO_M,
        -bb_min[2] * CM_TO_M,
    )

    if not bpy_util.HAS_BPY:
        return {
            "ok": report.ok,
            "blender": False,
            "mode": "fortress",
            "reloaded": len(reloaded),
            "collection": FORTRESS_COLLECTION,
            "compound_builder": builder_name,
            "ranges": list(getattr(layout, "ranges", [])),
            "placements": len(assembly.placements),
            "extent_m": assembly_footprint_extent_m(assembly),
            "offset_m": offset_m,
            "screenshot": None,
            "note": "bpy missing - assemble/validate only",
            "validation_report": report,
        }

    fortress_coll, scene_cleared = prepare_fortress_live_scene(skip_clear=skip_scene_clear)
    n = instance_assembly(
        assembly,
        label="fortress",
        target_coll=fortress_coll,
        offset_m=offset_m,
    )
    frame_camera_on_meshes(collection=FORTRESS_COLLECTION)
    shot = write_screenshot(_fortress_screenshot_path()) if write_png else None
    return {
        "ok": report.ok,
        "blender": True,
        "mode": "fortress",
        "reloaded": len(reloaded),
        "collection": FORTRESS_COLLECTION,
        "compound_builder": builder_name,
        "ranges": list(getattr(layout, "ranges", [])),
        "instances": n,
        "placements": len(assembly.placements),
        "extent_m": assembly_footprint_extent_m(assembly),
        "offset_m": offset_m,
        "bounds_cm": {"min": bb_min, "max": bb_max},
        "scene_cleared": scene_cleared,
        "screenshot": str(shot) if shot else None,
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
        "validation_report": report,
    }


def build_live(*, write_png: bool = True, milestones: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Full live build: reload → assemble/validate → meshes → camera → screenshot."""
    reloaded = reload_pae()

    from pae.primitives import bpy_util

    if not bpy_util.HAS_BPY:
        # Headless path: still exercise assemble/validate for CI agents.
        results = []
        for label, factory in _spec_factories():
            if milestones and label not in milestones:
                continue
            assembly, report = assemble_and_validate(label, factory)
            results.append(
                {
                    "label": label,
                    "placements": len(assembly.placements),
                    "ok": report.ok,
                }
            )
        return {
            "ok": True,
            "blender": False,
            "reloaded": len(reloaded),
            "milestones": results,
            "screenshot": None,
            "note": "bpy missing - assemble/validate only",
        }

    _clear_pae_objects()
    results = []
    primary = None
    for label, factory in _spec_factories():
        if milestones and label not in milestones:
            continue
        assembly, report = assemble_and_validate(label, factory)
        n = instance_assembly(assembly, label=label)
        results.append(
            {
                "label": label,
                "placements": len(assembly.placements),
                "instances": n,
                "ok": report.ok,
            }
        )
        if primary is None:
            primary = label

    frame_camera_on_meshes()
    shot = write_screenshot() if write_png else None
    m3_shot = None
    if write_png and any(r.get("label") == "m3" for r in results):
        m3_out = _repo_root() / M3_SCREENSHOT_REL
        m3_out.parent.mkdir(parents=True, exist_ok=True)
        m3_shot = write_screenshot(m3_out)
    return {
        "ok": True,
        "blender": True,
        "reloaded": len(reloaded),
        "milestones": results,
        "primary": primary,
        "screenshot": str(shot) if shot else None,
        "m3_screenshot": str(m3_shot) if m3_shot else None,
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
    }


def main() -> Dict[str, Any]:
    import os

    mode = os.environ.get("PAE_BUILD_MODE", "").lower()
    if mode == "gallery":
        result = build_gallery(write_png=True)
    elif mode == "stair_proof":
        result = build_m2_stair_proof(write_png=True)
    elif mode == "openings_proof":
        result = build_m1_openings_proof(write_png=True)
    elif mode == "fortress":
        result = build_fortress_live(write_png=True)
    else:
        result = build_live(write_png=True)
    print("PAE_BLENDER_BUILD", result)
    return result


if __name__ == "__main__":
    main()

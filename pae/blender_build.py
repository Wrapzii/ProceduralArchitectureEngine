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
PAE_ROOT_COLLECTION = "PAE_Live"
GALLERY_ROOT_COLLECTION = "PAE_Gallery"
M2_STAIR_PROOF_COLLECTION = "PAE_M2_StairProof"
GALLERY_GAP_M = 2.0
# Deterministic gallery camera: SE (+X, −Y) elevated — never random orbit per run.
GALLERY_CAM_DIRECTION = (1.0, -1.0, 0.65)
GALLERY_CAM_MARGIN = 1.38
GALLERY_CAM_LENS_MM = 40.0
GALLERY_CAM_ORTHO = True
# M2 stair proof: tighter SE-elevated view framed on stair + floor_hole AABB only.
STAIR_PROOF_CAM_DIRECTION = (1.0, -0.72, 0.48)
STAIR_PROOF_CAM_MARGIN = 1.18

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
    "plinth": (0.35, 0.34, 0.33, 1.0),  # foundation stone
    "hole": (0.20, 0.20, 0.22, 1.0),  # void rim (rare in gallery)
}
_DEFAULT_KIND_COLOR: Tuple[float, float, float, float] = (0.75, 0.75, 0.75, 1.0)

# Asset-specific tints — placements often share ``kind`` (e.g. door/window ``kind=wall``).
# Higher contrast than kind defaults so gallery/workbench reads openings and variants.
ASSET_MATERIAL_COLORS: Dict[str, Tuple[float, float, float, float]] = {
    "wall_door": (0.55, 0.28, 0.12, 1.0),  # dark oak door
    "wall_window": (0.35, 0.65, 0.92, 1.0),  # bright sky glazing
    "roof_flat": (0.22, 0.35, 0.62, 1.0),  # deep slate deck
    "roof_gable_infill": (0.28, 0.55, 0.42, 1.0),  # green gable triangle
    "roof_pitched_slope": (0.62, 0.28, 0.22, 1.0),  # red clay tile
    "tower_arc_quarter": (0.82, 0.68, 0.45, 1.0),  # warm sandstone drum
    "tower_crown": (0.52, 0.42, 0.68, 1.0),  # purple-gray battlements
    "tower_cap": (0.45, 0.62, 0.38, 1.0),  # mossy stone cone
    "stair_straight": (0.72, 0.42, 0.28, 1.0),  # terracotta treads
    "stair_spiral_quarter": (0.78, 0.52, 0.18, 1.0),  # copper spiral
    "floor_hole": (0.12, 0.12, 0.18, 1.0),  # void rim
}
_TINTED_ASSET_PREFIXES = ("roof_", "tower_", "stair_")
_TINTED_ASSET_EXACT = frozenset(ASSET_MATERIAL_COLORS.keys())


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


def is_stair_proof_placement(p) -> bool:
    """Placements that define the stair + floor-hole proof frame."""
    return p.asset_id in ("stair_straight", "floor_hole") or p.kind == "stair"


def is_stair_proof_visible_asset(
    asset_id: Optional[str],
    piece_id: Optional[str] = None,
) -> bool:
    """True when a mesh instance should remain visible in the M2 stair proof shot."""
    tokens = (str(asset_id or ""), str(piece_id or ""))
    combined = " ".join(tokens).lower()
    if "stair" in combined:
        return True
    if "floor_hole" in combined or "hole" in combined:
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


def stair_proof_camera_pose_from_bounds_m(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
) -> Dict[str, Any]:
    """Deterministic camera pose for the M2 stair + hole proof shot."""
    return camera_pose_from_bounds_m(
        bb_min,
        bb_max,
        margin=STAIR_PROOF_CAM_MARGIN,
        direction=STAIR_PROOF_CAM_DIRECTION,
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

    return (
        _ratio(p.size_cm[0], base[0]),
        _ratio(p.size_cm[1], base[1]),
        _ratio(p.size_cm[2], base[2]),
    )


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
    """Return ``(label, collection_name, factory)`` for the M1–M4 gallery row."""
    from pae import spec as spec_mod

    entries: List[Tuple[str, str, str]] = [
        ("m1", "PAE_M1", "m1_box_house_spec"),
        ("m2", "PAE_M2", "m2_two_storey_stair_spec"),
        ("m3", "PAE_M3", "m3_keep_tower_spec"),
        ("m4_l", "PAE_M4_L", "m4_l_plan_spec"),
        ("m4_u", "PAE_M4_U", "m4_u_plan_spec"),
        ("m4_c", "PAE_M4_C", "m4_courtyard_spec"),
    ]
    factories: List[Tuple[str, str, Any]] = []
    for label, coll_name, attr in entries:
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
    """spec → assemble → validate. Raises if validation fails critically."""
    from pae.pipeline import run_through_assemble
    from pae.validate import validate

    spec = factory()
    _massing, _plan, assembly, stage_report = run_through_assemble(spec)
    if assembly is None or not assembly.placements:
        raise RuntimeError(f"{label}: assemble produced no placements ({stage_report})")
    assembly, report = validate(assembly)
    if not report.ok:
        crit = "; ".join(f.message for f in report.critical[:5])
        raise RuntimeError(f"{label}: validate failed — {crit or report}")
    return assembly, report


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
    import bpy

    _clear_proto_meshes()
    root = bpy.data.collections.get(GALLERY_ROOT_COLLECTION)
    if root is not None:
        _unlink_collection_tree(root)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return _ensure_collection(GALLERY_ROOT_COLLECTION)


def _ensure_material(asset_id: str, kind: str = "wall"):
    import bpy

    key = material_key_for_placement(asset_id, kind)
    rgba = material_color_for_placement(asset_id, kind)
    name = f"PAE_Mat_{key}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.7
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

    bpy_util.require_bpy()
    import bpy
    from mathutils import Vector

    coll = target_coll
    if coll is None:
        coll = bpy.data.collections.get(PAE_ROOT_COLLECTION) or _clear_pae_objects()
    cache: Dict[str, Any] = {}
    count = 0
    ox, oy, oz = offset_m
    for p in assembly.placements:
        proto = _mesh_for_asset(p.asset_id, tuple(p.size_cm), cache=cache)
        loc_cm = placement_loc_cm(p)
        loc_m = (
            loc_cm[0] * CM_TO_M + ox,
            loc_cm[1] * CM_TO_M + oy,
            loc_cm[2] * CM_TO_M + oz,
        )
        # Linked duplicate shares mesh datablock.
        inst = proto.copy()
        inst.data = proto.data
        inst.name = f"PAE_{label}_{p.piece_id}"
        inst.hide_set(False)
        inst.hide_render = False
        inst.location = Vector(loc_m)
        sx, sy, sz = placement_instance_scale_cm(p)
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
    if pose.get("ortho"):
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = float(pose["ortho_scale"])
    else:
        cam.data.type = "PERSP"
        if hasattr(cam.data, "lens"):
            cam.data.lens = float(pose.get("lens_mm", GALLERY_CAM_LENS_MM))


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
        light_data.energy = 3.0
        sun = bpy.data.objects.new("PAE_Sun", light_data)
        bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30))


def _apply_stair_proof_visibility(objects: Sequence[Any]) -> Dict[str, List[str]]:
    """Hide every mesh except stair + floor-hole instances (viewport + render)."""
    hidden: List[str] = []
    visible: List[str] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        asset = obj.get("pae_asset_id")
        piece = obj.get("pae_piece_id")
        label = f"{asset or '?'}:{piece or obj.name}"
        if is_stair_proof_visible_asset(asset, piece):
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


def _clear_stair_proof_collection():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

    _clear_proto_meshes()
    coll = bpy.data.collections.get(M2_STAIR_PROOF_COLLECTION)
    if coll is not None:
        _unlink_collection_tree(coll)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return _ensure_collection(M2_STAIR_PROOF_COLLECTION)


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

    proof_coll = _clear_stair_proof_collection()
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
    scene.render.engine = "BLENDER_WORKBENCH"
    if hasattr(scene.display, "shading"):
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(out)
    scene.render.image_settings.file_format = "PNG"
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
            assembly, report = assemble_and_validate(label, factory)
            extent = assembly_footprint_extent_m(assembly)
            results.append(
                {
                    "label": label,
                    "collection": coll_name,
                    "placements": len(assembly.placements),
                    "extent_m": extent,
                    "ok": report.ok,
                }
            )
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
        }

    gallery_root = _clear_gallery_collections()
    results = []
    cursor_x_m = 0.0
    per_shots: Dict[str, str] = {}
    import bpy

    for label, coll_name, factory in factories:
        assembly, report = assemble_and_validate(label, factory)
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
    return {
        "ok": True,
        "blender": True,
        "mode": "gallery",
        "reloaded": len(reloaded),
        "milestones": results,
        "gap_m": gap_m,
        "screenshot": str(gallery_shot) if gallery_shot else None,
        "per_milestone_screenshots": per_shots,
        "stair_proof_screenshot": (
            stair_proof_result.get("screenshot") if stair_proof_result else None
        ),
        "boolean_solvers": sorted(bpy_util.BOOLEAN_SOLVERS),
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
    else:
        result = build_live(write_png=True)
    print("PAE_BLENDER_BUILD", result)
    return result


if __name__ == "__main__":
    main()

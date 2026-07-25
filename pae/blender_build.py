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
PAE_ROOT_COLLECTION = "PAE_Live"
GALLERY_ROOT_COLLECTION = "PAE_Gallery"
GALLERY_GAP_M = 2.0
# Deterministic gallery camera: SE (+X, −Y) elevated — never random orbit per run.
GALLERY_CAM_DIRECTION = (1.0, -1.0, 0.65)
GALLERY_CAM_MARGIN = 1.38
GALLERY_CAM_LENS_MM = 40.0
GALLERY_CAM_ORTHO = True


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


def _clear_pae_objects():
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy

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

    root = bpy.data.collections.get(GALLERY_ROOT_COLLECTION)
    if root is not None:
        _unlink_collection_tree(root)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return _ensure_collection(GALLERY_ROOT_COLLECTION)


def _ensure_material(kind: str):
    import bpy

    colors = {
        "wall": (0.55, 0.52, 0.48, 1.0),
        "floor": (0.35, 0.32, 0.28, 1.0),
        "ground": (0.25, 0.28, 0.22, 1.0),
        "roof": (0.25, 0.30, 0.45, 1.0),
        "stair": (0.40, 0.38, 0.35, 1.0),
    }
    name = f"PAE_Mat_{kind}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = colors.get(kind, (0.75, 0.75, 0.75, 1.0))
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
        mat = _ensure_material(getattr(p, "kind", "wall"))
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
) -> Dict[str, Any]:
    """Build M1–M4 into side-by-side collections under ``PAE_Gallery``.

    Each milestone gets its own child collection (``PAE_M1`` … ``PAE_M4_L``),
    offset along +X by prior footprint width + *gap_m* metres.
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
    return {
        "ok": True,
        "blender": True,
        "mode": "gallery",
        "reloaded": len(reloaded),
        "milestones": results,
        "gap_m": gap_m,
        "screenshot": str(gallery_shot) if gallery_shot else None,
        "per_milestone_screenshots": per_shots,
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

    if os.environ.get("PAE_BUILD_MODE", "").lower() == "gallery":
        result = build_gallery(write_png=True)
    else:
        result = build_live(write_png=True)
    print("PAE_BLENDER_BUILD", result)
    return result


if __name__ == "__main__":
    main()

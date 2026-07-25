"""Live Blender mesh build for PAE milestones (M1, M2 if present).

Run **inside** Blender (MCP ``execute_blender_code`` / Text Editor / add-on).

Hardening notes
---------------
* Mesh authoring units are **centimetres**; instances use ``scale = 0.01``
  (cm → m) and locations in metres.
* Prefer ``catalog.build_mesh``; unknown assets (e.g. ``roof_flat``) fall back
  to a framed opening / solid box via ``bpy_util``.
* Always ``reload_pae()`` first — Blender caches modules across agent re-runs.

Example (Blender MCP)::

    import runpy
    runpy.run_path(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py"
    )

Or::

    exec(open(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py",
        encoding="utf-8",
    ).read())
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
PAE_ROOT_COLLECTION = "PAE_Live"


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
    coll = bpy.data.collections.get(PAE_ROOT_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(PAE_ROOT_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


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


def instance_assembly(assembly, *, label: str = "m1") -> int:
    """Create linked instances for each placement. Returns instance count."""
    from pae.export.manifest import placement_loc_cm
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy
    from mathutils import Vector

    coll = bpy.data.collections.get(PAE_ROOT_COLLECTION) or _clear_pae_objects()
    cache: Dict[str, Any] = {}
    count = 0
    for p in assembly.placements:
        proto = _mesh_for_asset(p.asset_id, tuple(p.size_cm), cache=cache)
        loc_cm = placement_loc_cm(p)
        loc_m = (loc_cm[0] * CM_TO_M, loc_cm[1] * CM_TO_M, loc_cm[2] * CM_TO_M)
        # Linked duplicate shares mesh datablock.
        inst = proto.copy()
        inst.data = proto.data
        inst.name = f"PAE_{label}_{p.piece_id}"
        inst.hide_set(False)
        inst.hide_render = False
        inst.location = Vector(loc_m)
        inst.scale = (CM_TO_M, CM_TO_M, CM_TO_M)
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


def frame_camera_on_meshes() -> None:
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    import bpy
    from mathutils import Vector

    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    found = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.hide_get():
            continue
        if not obj.name.startswith("PAE_"):
            continue
        if "Proto" in obj.name:
            continue
        found += 1
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, w.x)
            mins.y = min(mins.y, w.y)
            mins.z = min(mins.z, w.z)
            maxs.x = max(maxs.x, w.x)
            maxs.y = max(maxs.y, w.y)
            maxs.z = max(maxs.z, w.z)
    if found == 0:
        raise RuntimeError("no PAE mesh instances to frame")

    center = (mins + maxs) * 0.5
    size = maxs - mins
    radius = max(size.x, size.y, size.z, 1.0) * 1.45
    direction = Vector((1.15, -1.35, 0.75)).normalized()

    cam = bpy.context.scene.camera
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        bpy.context.scene.camera = cam
    cam.location = center + direction * radius
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    if hasattr(cam.data, "lens"):
        cam.data.lens = 35

    # Soft workbench-friendly world.
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.60, 0.68, 1.0)
        bg.inputs[1].default_value = 1.0

    # Sun for depth.
    sun = next((o for o in bpy.data.objects if o.type == "LIGHT" and o.name.startswith("PAE_Sun")), None)
    if sun is None:
        light_data = bpy.data.lights.new(name="PAE_Sun", type="SUN")
        light_data.energy = 3.0
        sun = bpy.data.objects.new("PAE_Sun", light_data)
        bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30))


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
    result = build_live(write_png=True)
    print("PAE_BLENDER_BUILD", result)
    return result


if __name__ == "__main__":
    main()

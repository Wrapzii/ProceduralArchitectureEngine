"""Open-air stair showcase — no enclosing walls, landings only.

Builds three demos side-by-side in Blender so a human can see the full
staircase geometry:

1. **Upstairs connect** — bottom landing → one straight flight → top landing
2. **Long stepped** — three flights with mid landings (3 storeys total rise)
3. **Spiral** — four quarter turns stacked to one storey (open drum)

Run inside Blender::

    from pae.open_stair_showcase import build_open_stair_showcase
    build_open_stair_showcase()

Or::

    python tools/pae_build_in_blender.py --open-stairs
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_PAE_ROOT = Path(__file__).resolve().parent.parent
if str(_PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PAE_ROOT))

CM_TO_M = 0.01
OPEN_STAIR_COLLECTION = "PAE_OpenStairs"
OPEN_STAIR_SHOT = Path("Saved") / "Screenshots" / "open_stairs_showcase.png"
# Side spacing between demos (metres)
_DEMO_GAP_M = 6.0


def _repo_root() -> Path:
    return _PAE_ROOT


def _shot_path() -> Path:
    out = _repo_root() / OPEN_STAIR_SHOT
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def open_stair_demo_plan() -> List[Dict[str, Any]]:
    """Pure description of the three demos (no bpy) — for tests / docs."""
    from pae.contract import MODULE_CM, STOREY_CM

    flight_run_m = 2.0 * MODULE_CM * CM_TO_M
    flight_rise_m = STOREY_CM * CM_TO_M
    landing_m = MODULE_CM * CM_TO_M
    return [
        {
            "id": "upstairs_connect",
            "label": "A — upstairs connect",
            "flights": 1,
            "flight_run_m": flight_run_m,
            "flight_rise_m": flight_rise_m,
            "landing_m": landing_m,
            "notes": "bottom landing + one flight + top landing",
        },
        {
            "id": "long_stepped",
            "label": "B — long stepped (3 storeys)",
            "flights": 3,
            "flight_run_m": flight_run_m,
            "flight_rise_m": flight_rise_m,
            "landing_m": landing_m,
            "notes": "three flights with mid landings, open air",
        },
        {
            "id": "spiral_one_storey",
            "label": "C — spiral one storey",
            "quarters": 4,
            "rise_m": flight_rise_m,
            "notes": "four spiral quarters stacked, open",
        },
    ]


def _ensure_collection(name: str):
    import bpy

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _clear_open_stair_collection():
    import bpy

    # Hide other PAE showcases so the open-stair shot is unobstructed.
    for coll in bpy.data.collections:
        if coll.name.startswith("PAE_") and coll.name != OPEN_STAIR_COLLECTION:
            coll.hide_render = True
            coll.hide_viewport = True
            for obj in coll.objects:
                obj.hide_render = True
                try:
                    obj.hide_set(True)
                except Exception:
                    pass

    for obj in list(bpy.data.objects):
        if obj.name.startswith("PAE_OpenStair_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    coll = bpy.data.collections.get(OPEN_STAIR_COLLECTION)
    if coll is not None:
        for child in list(coll.children):
            coll.children.unlink(child)
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    coll = _ensure_collection(OPEN_STAIR_COLLECTION)
    coll.hide_render = False
    coll.hide_viewport = False
    return coll


def _mat(name: str, rgba: Tuple[float, float, float, float]):
    import bpy

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    mat.diffuse_color = rgba
    if mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = 0.65
    return mat


def _link(obj, coll, mat):
    import bpy

    if obj.name not in coll.objects:
        # Unlink from other collections first
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        coll.objects.link(obj)
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat
    obj.hide_set(False)
    obj.hide_render = False
    return obj


def _place_box(
    coll,
    *,
    name: str,
    size_cm: Tuple[float, float, float],
    loc_m: Tuple[float, float, float],
    mat,
):
    from pae.primitives import bpy_util

    obj = bpy_util.box_mesh(name, size_cm, origin_at_min_corner=True)
    obj.scale = (CM_TO_M, CM_TO_M, CM_TO_M)
    obj.location = loc_m
    return _link(obj, coll, mat)


def _place_straight_stair(
    coll,
    *,
    name: str,
    loc_m: Tuple[float, float, float],
    mat,
    steps: Optional[int] = None,
    size_cm: Optional[Tuple[float, float, float]] = None,
):
    from pae.contract import MODULE_CM, STOREY_CM
    from pae.primitives import bpy_util
    from pae.primitives.stairs import straight_stair_verts_faces, stair_straight

    desc = stair_straight()
    sx, sy, sz = size_cm or desc.size_cm
    n = steps if steps is not None else int(round(sz / (STOREY_CM / 20)))
    n = max(n, 8)
    verts, faces = straight_stair_verts_faces(sx, sy, sz, steps=n)
    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    obj.scale = (CM_TO_M, CM_TO_M, CM_TO_M)
    obj.location = loc_m
    return _link(obj, coll, mat)


def _place_spiral_stack(coll, *, origin_m: Tuple[float, float, float], mat_arc, mat_cap):
    from pae.contract import MODULE_CM, STOREY_CM
    from pae.primitives.catalog import build_mesh

    # Four quarters, same centre, yaw 0/90/180/270, stacked rise via level offset.
    # Quarters already rise STOREY/4 each in descriptor — stack by Z for clarity.
    # Actually each quarter is full? Check - spiral is 0.25 storey height.
    from pae.primitives.stairs import stair_spiral_quarter

    desc = stair_spiral_quarter()
    h = desc.size_cm[2] * CM_TO_M
    cx, cy, cz = origin_m
    objs = []
    for i, yaw in enumerate((0, 90, 180, 270)):
        proto = build_mesh("stair_spiral_quarter", name=f"PAE_OpenStair_SpiralProto_{yaw}")
        inst = proto.copy()
        inst.data = proto.data
        inst.name = f"PAE_OpenStair_Spiral_{yaw}"
        # Centre-authored: place at circle centre
        inst.location = (cx, cy, cz + i * h)
        inst.scale = (CM_TO_M, CM_TO_M, CM_TO_M)
        inst.rotation_euler = (0.0, 0.0, math.radians(float(yaw)))
        _link(inst, coll, mat_arc)
        objs.append(inst)
    # Simple cap pad on top
    pad = _place_box(
        coll,
        name="PAE_OpenStair_SpiralTop",
        size_cm=(MODULE_CM * 1.2, MODULE_CM * 1.2, 20.0),
        loc_m=(cx - 0.6 * MODULE_CM * CM_TO_M, cy - 0.6 * MODULE_CM * CM_TO_M, cz + 4 * h),
        mat=mat_cap,
    )
    objs.append(pad)
    return objs


def _build_upstairs_connect(coll, origin_m: Tuple[float, float, float], mats: Dict[str, Any]) -> List[Any]:
    from pae.contract import MODULE_CM, STOREY_CM

    ox, oy, oz = origin_m
    land = MODULE_CM
    run = 2.0 * MODULE_CM
    rise = STOREY_CM
    objs: List[Any] = []
    # Bottom landing (connection)
    objs.append(
        _place_box(
            coll,
            name="PAE_OpenStair_A_Bottom",
            size_cm=(land, land, 20.0),
            loc_m=(ox, oy, oz),
            mat=mats["landing"],
        )
    )
    # Stair starts at end of bottom landing, rises along +X
    objs.append(
        _place_straight_stair(
            coll,
            name="PAE_OpenStair_A_Flight",
            loc_m=(ox + land * CM_TO_M, oy, oz + 0.2),
            mat=mats["stair"],
        )
    )
    # Top landing (upstairs connection)
    objs.append(
        _place_box(
            coll,
            name="PAE_OpenStair_A_Top",
            size_cm=(land * 1.5, land, 20.0),
            loc_m=(
                ox + (land + run) * CM_TO_M,
                oy,
                oz + 0.2 + rise * CM_TO_M,
            ),
            mat=mats["landing_top"],
        )
    )
    return objs


def _build_long_stepped(coll, origin_m: Tuple[float, float, float], mats: Dict[str, Any]) -> List[Any]:
    from pae.contract import MODULE_CM, STOREY_CM

    ox, oy, oz = origin_m
    land = MODULE_CM
    run = 2.0 * MODULE_CM
    rise = STOREY_CM
    objs: List[Any] = []
    x = ox
    z = oz
    # Bottom pad
    objs.append(
        _place_box(
            coll,
            name="PAE_OpenStair_B_Bottom",
            size_cm=(land, land, 20.0),
            loc_m=(x, oy, z),
            mat=mats["landing"],
        )
    )
    x += land * CM_TO_M
    z += 0.2
    for flight in range(3):
        objs.append(
            _place_straight_stair(
                coll,
                name=f"PAE_OpenStair_B_Flight_{flight}",
                loc_m=(x, oy, z),
                mat=mats["stair"],
            )
        )
        x += run * CM_TO_M
        z += rise * CM_TO_M
        # Mid / top landing
        name = "PAE_OpenStair_B_Top" if flight == 2 else f"PAE_OpenStair_B_Mid_{flight}"
        mat = mats["landing_top"] if flight == 2 else mats["landing"]
        objs.append(
            _place_box(
                coll,
                name=name,
                size_cm=(land, land, 20.0),
                loc_m=(x, oy, z),
                mat=mat,
            )
        )
        x += land * CM_TO_M
    return objs


def _frame_camera_on_collection(coll_name: str) -> None:
    import bpy
    from mathutils import Vector

    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return
    meshes = [o for o in coll.objects if o.type == "MESH" and not o.hide_render]
    if not meshes:
        return
    bpy.context.view_layer.update()
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, w.x)
            mins.y = min(mins.y, w.y)
            mins.z = min(mins.z, w.z)
            maxs.x = max(maxs.x, w.x)
            maxs.y = max(maxs.y, w.y)
            maxs.z = max(maxs.z, w.z)
    center = (mins + maxs) * 0.5
    size = maxs - mins
    # Side view from -Y (perpendicular to +X stair runs), elevated
    dist = max(size.x, size.z) * 1.4 + 4.0
    cam = bpy.context.scene.camera
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        bpy.context.scene.camera = cam
    cam.location = (center.x, center.y - dist, center.z + dist * 0.45)
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(size.x, size.z) * 1.25 + 2.0

    # Bright neutral world + sun
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.58, 0.62, 1.0)
        bg.inputs[1].default_value = 1.2
    sun = next((o for o in bpy.data.objects if o.type == "LIGHT" and o.name.startswith("PAE_Sun")), None)
    if sun is None:
        light_data = bpy.data.lights.new(name="PAE_Sun", type="SUN")
        light_data.energy = 5.0
        sun = bpy.data.objects.new("PAE_Sun", light_data)
        bpy.context.scene.collection.objects.link(sun)
    else:
        sun.data.energy = 5.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-25))


def _write_shot(path: Path) -> Path:
    import bpy

    scene = bpy.context.scene
    try:
        from pae.blender_build import configure_workbench_screenshot_scene

        configure_workbench_screenshot_scene(scene)
    except Exception:
        scene.render.engine = "BLENDER_WORKBENCH"
        if hasattr(scene.display, "shading"):
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return path


def build_open_stair_showcase(*, write_png: bool = True) -> Dict[str, Any]:
    """Build open-air stair demos (landings only) and optional screenshot."""
    # Fresh imports after agent edits
    for key in list(sys.modules):
        if key == "pae" or key.startswith("pae."):
            if key == "pae.open_stair_showcase":
                continue
            sys.modules.pop(key, None)

    from pae.primitives import bpy_util

    plan = open_stair_demo_plan()
    if not bpy_util.HAS_BPY:
        return {
            "ok": True,
            "blender": False,
            "mode": "open_stairs",
            "demos": plan,
            "screenshot": None,
            "note": "bpy missing — plan only",
        }

    coll = _clear_open_stair_collection()
    mats = {
        "stair": _mat("PAE_Mat_OpenStair", (0.78, 0.42, 0.22, 1.0)),
        "landing": _mat("PAE_Mat_OpenLanding", (0.55, 0.50, 0.42, 1.0)),
        "landing_top": _mat("PAE_Mat_OpenLandingTop", (0.35, 0.55, 0.70, 1.0)),
        "spiral": _mat("PAE_Mat_OpenSpiral", (0.82, 0.62, 0.28, 1.0)),
        "spiral_top": _mat("PAE_Mat_OpenSpiralTop", (0.40, 0.55, 0.38, 1.0)),
    }

    cursor_x = 0.0
    built: List[Dict[str, Any]] = []

    # A — upstairs connect
    a_objs = _build_upstairs_connect(coll, (cursor_x, 0.0, 0.0), mats)
    built.append({"id": "upstairs_connect", "instances": len(a_objs), "origin_m": (cursor_x, 0.0, 0.0)})
    cursor_x += 2.0 * 4.0 + _DEMO_GAP_M  # rough width

    # B — long stepped 3 storeys
    b_objs = _build_long_stepped(coll, (cursor_x, 0.0, 0.0), mats)
    built.append({"id": "long_stepped", "instances": len(b_objs), "origin_m": (cursor_x, 0.0, 0.0)})
    cursor_x += 3.0 * 8.0 + 4.0 + _DEMO_GAP_M

    # C — spiral
    c_objs = _place_spiral_stack(coll, origin_m=(cursor_x + 4.0, 4.0, 0.0), mat_arc=mats["spiral"], mat_cap=mats["spiral_top"])
    built.append({"id": "spiral_one_storey", "instances": len(c_objs), "origin_m": (cursor_x + 4.0, 4.0, 0.0)})

    _frame_camera_on_collection(OPEN_STAIR_COLLECTION)
    shot = _write_shot(_shot_path()) if write_png else None

    return {
        "ok": True,
        "blender": True,
        "mode": "open_stairs",
        "collection": OPEN_STAIR_COLLECTION,
        "demos": plan,
        "built": built,
        "screenshot": str(shot) if shot else None,
    }


if __name__ == "__main__":
    print(build_open_stair_showcase(write_png=True))

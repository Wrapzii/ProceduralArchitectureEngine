"""Build PAE M1 box house in live Blender via TCP MCP and screenshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

RE = Path(r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE")
PAE = Path(r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine")
sys.path.insert(0, str(RE))
sys.path.insert(0, str(PAE))

from Content.Python.blender._blender_mcp_client import execute, screenshot  # noqa: E402

PLACEMENTS = PAE / "Saved" / "m1_placements.json"
PNG = PAE / "Saved" / "Screenshots" / "m1_box_house_blender.png"


def ensure_placements() -> None:
    if PLACEMENTS.exists():
        return
    from pae.export.manifest import placement_loc_cm
    from pae.pipeline import run_through_assemble
    from pae.spec import m1_box_house_spec
    from pae.validate import validate

    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    assembly, v = validate(assembly)
    rows = [
        {
            "piece_id": p.piece_id,
            "kind": p.kind,
            "asset_id": p.asset_id,
            "loc_cm": list(placement_loc_cm(p)),
            "yaw": p.yaw,
            "size_cm": list(p.size_cm),
            "cell": list(p.cell),
            "level": p.level,
        }
        for p in assembly.placements
    ]
    PLACEMENTS.parent.mkdir(parents=True, exist_ok=True)
    PLACEMENTS.write_text(
        json.dumps({"ok": v.ok, "n": len(rows), "placements": rows}, indent=2),
        encoding="utf-8",
    )


CODE = r"""
import bpy, json, math
from mathutils import Vector
from pathlib import Path

path = Path(r"C:/Users/WhiteWidow/Documents/GitHub/ProceduralArchitectureEngine/Saved/m1_placements.json")
data = json.loads(path.read_text(encoding="utf-8"))

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.meshes):
    if block.users == 0:
        bpy.data.meshes.remove(block)
for block in list(bpy.data.materials):
    if block.users == 0:
        bpy.data.materials.remove(block)

COLORS = {
    "wall": (0.55, 0.52, 0.48, 1),
    "floor": (0.35, 0.32, 0.28, 1),
    "ground": (0.25, 0.28, 0.22, 1),
    "roof": (0.25, 0.30, 0.45, 1),
}

def mat_for(kind):
    name = f"PAE_{kind}"
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = COLORS.get(kind, (0.8, 0.8, 0.8, 1))
            bsdf.inputs["Roughness"].default_value = 0.7
    return m

def add_box(p):
    sx, sy, sz = [c / 100.0 for c in p["size_cm"]]
    lx, ly, lz = [c / 100.0 for c in p["loc_cm"]]
    yaw = math.radians(p["yaw"])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = p["piece_id"]
    obj.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in obj.data.vertices:
        v.co += Vector((sx * 0.5, sy * 0.5, sz * 0.5))
    obj.location = (lx, ly, lz)
    obj.rotation_euler = (0, 0, yaw)
    obj.data.materials.append(mat_for(p["kind"]))
    return obj

for p in data["placements"]:
    add_box(p)

bpy.ops.object.light_add(type="SUN", location=(8, -6, 12))
sun = bpy.context.active_object
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30))

bpy.ops.object.camera_add(location=(18.0, -14.0, 9.0))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(58), 0, math.radians(48))
bpy.context.scene.camera = cam

world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.62, 0.68, 0.75, 1)
    bg.inputs[1].default_value = 0.85

for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.region_3d.view_perspective = "CAMERA"
                break

print(f"M1_OK pieces={len(data['placements'])} validate_ok={data['ok']}")
"""


def main() -> None:
    ensure_placements()
    PNG.parent.mkdir(parents=True, exist_ok=True)
    r = execute(CODE)
    print(json.dumps(r, indent=2)[:2000])
    s = screenshot(str(PNG), max_size=640)
    print(json.dumps(s, indent=2)[:1500])
    print("png", PNG, "exists", PNG.exists(), "bytes", PNG.stat().st_size if PNG.exists() else 0)


if __name__ == "__main__":
    main()

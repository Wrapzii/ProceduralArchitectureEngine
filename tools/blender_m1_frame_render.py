"""Frame full M1 footprint and re-render."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE")
from Content.Python.blender._blender_mcp_client import execute

PNG = Path(
    r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine\Saved\Screenshots\m1_box_house_clean.png"
)

CODE = r"""
import bpy, math
from mathutils import Vector
from pathlib import Path

# Bounds of all meshes
mins = Vector((1e9, 1e9, 1e9))
maxs = Vector((-1e9, -1e9, -1e9))
count = 0
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    count += 1
    for corner in obj.bound_box:
        w = obj.matrix_world @ Vector(corner)
        mins.x = min(mins.x, w.x); mins.y = min(mins.y, w.y); mins.z = min(mins.z, w.z)
        maxs.x = max(maxs.x, w.x); maxs.y = max(maxs.y, w.y); maxs.z = max(maxs.z, w.z)

center = (mins + maxs) * 0.5
size = maxs - mins
radius = max(size.x, size.y, size.z) * 1.35

# 3/4 elevated view
import mathutils
cam = bpy.context.scene.camera
if cam is None:
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam

direction = Vector((1.15, -1.35, 0.75)).normalized()
cam.location = center + direction * radius
# Look at center
direction_to = center - cam.location
rot = direction_to.to_track_quat("-Z", "Y")
cam.rotation_euler = rot.to_euler()
cam.data.lens = 35

# Soft world
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.55, 0.60, 0.68, 1)
    bg.inputs[1].default_value = 1.0

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
out = Path(r"C:/Users/WhiteWidow/Documents/GitHub/ProceduralArchitectureEngine/Saved/Screenshots/m1_box_house_clean.png")
scene.render.filepath = str(out)
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
print("meshes", count)
print("mins", tuple(mins), "maxs", tuple(maxs))
print("cam", tuple(cam.location), "radius", radius)
print("WROTE", out.exists(), out.stat().st_size)
"""

print(json.dumps(execute(CODE, timeout=180), indent=2)[:2000])
print("bytes", PNG.stat().st_size if PNG.exists() else 0)

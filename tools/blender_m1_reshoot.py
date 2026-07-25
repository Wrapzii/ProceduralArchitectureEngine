"""Dismiss Blender splash and reshoot M1 camera view."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE")
from Content.Python.blender._blender_mcp_client import execute, screenshot

PNG = Path(
    r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine\Saved\Screenshots\m1_box_house_blender.png"
)

CODE = r"""
import bpy

# Close extra windows (splash often lives as a temp window)
wm = bpy.context.window_manager
main = bpy.context.window
for w in list(wm.windows):
    if w != main:
        try:
            with bpy.context.temp_override(window=w):
                bpy.ops.wm.window_close()
        except Exception as e:
            print("close", e)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in bpy.data.objects:
    o.select_set(o.type == "MESH")
if meshes:
    bpy.context.view_layer.objects.active = meshes[0]

for area in bpy.context.screen.areas:
    if area.type != "VIEW_3D":
        continue
    region = next(r for r in area.regions if r.type == "WINDOW")
    for space in area.spaces:
        if space.type == "VIEW_3D":
            space.shading.type = "MATERIAL"
            space.region_3d.view_perspective = "CAMERA"
    with bpy.context.temp_override(window=main, area=area, region=region):
        try:
            bpy.ops.view3d.view_camera()
        except Exception as e:
            print("view_camera", e)
        try:
            bpy.ops.view3d.camera_to_view_selected()
        except Exception as e:
            print("frame", e)

# Nudge camera to a clean 3/4 of the house
cam = bpy.context.scene.camera
if cam is not None:
    import math
    cam.location = (16.0, -12.5, 8.0)
    cam.rotation_euler = (math.radians(55), 0, math.radians(50))

print("meshes", len(meshes), "windows", len(wm.windows))
"""

print(json.dumps(execute(CODE), indent=2)[:1500])
print(json.dumps(screenshot(str(PNG), max_size=640), indent=2))
print("bytes", PNG.stat().st_size if PNG.exists() else 0)

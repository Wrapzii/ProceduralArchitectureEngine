"""Clean Workbench render of M1 camera (no Blender UI / splash)."""

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
import bpy
from pathlib import Path

out = Path(r"C:/Users/WhiteWidow/Documents/GitHub/ProceduralArchitectureEngine/Saved/Screenshots/m1_box_house_clean.png")
out.parent.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.filepath = str(out)
scene.render.image_settings.file_format = "PNG"

bpy.ops.render.render(write_still=True)
print("WROTE", out.exists(), out.stat().st_size if out.exists() else 0)
print("meshes", sum(1 for o in bpy.data.objects if o.type == "MESH"))
print("cam", scene.camera.name if scene.camera else None)
"""

print(json.dumps(execute(CODE, timeout=180), indent=2)[:2000])
print("exists", PNG.exists(), "bytes", PNG.stat().st_size if PNG.exists() else 0)

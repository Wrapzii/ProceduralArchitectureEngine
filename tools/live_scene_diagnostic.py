"""Read-only diagnostic for the current live Blender PAE scene."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


CLIENT = Path(
    r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE\Content\Python"
    r"\blender\_blender_mcp_client.py"
)
REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    spec = importlib.util.spec_from_file_location("_pae_blender_client", CLIENT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Blender client: {CLIENT}")
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    code = f"""
import bpy
import json
import runpy
from pathlib import Path
ns = runpy.run_path(str(Path({str(REPO)!r}) / "pae" / "blender_build.py"))
coll = bpy.data.collections.get("PAE_Fortress")
meshes = [o for o in coll.all_objects if o.type == "MESH" and "Proto" not in o.name]
bb_min, bb_max = ns["mesh_world_bounds_m"](meshes)
cam = bpy.context.scene.camera
print(json.dumps({{
    "mesh_count": len(meshes),
    "bounds": [bb_min, bb_max],
    "camera_location": list(cam.location),
    "camera_rotation": list(cam.rotation_euler),
    "camera_type": cam.data.type,
    "ortho_scale": cam.data.ortho_scale,
    "clip": [cam.data.clip_start, cam.data.clip_end],
    "engine": bpy.context.scene.render.engine,
    "view_layer": bpy.context.view_layer.name,
    "collection_hide": [coll.hide_viewport, coll.hide_render],
    "sample_objects": [
        [o.name, list(o.location), list(o.scale), o.hide_get(), o.hide_render]
        for o in meshes[:3]
    ],
}}))
"""
    print(json.dumps(client.execute(code, timeout=60.0), indent=2))


if __name__ == "__main__":
    main()

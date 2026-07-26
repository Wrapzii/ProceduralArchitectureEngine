"""Render an honest multi-angle audit of the currently loaded reference scene."""

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

repo = Path({str(REPO)!r})
ns = runpy.run_path(str(repo / "pae" / "blender_build.py"))
coll = bpy.data.collections.get("PAE_Fortress")
if coll is None:
    raise RuntimeError("PAE_Fortress is not loaded")
meshes = [
    o for o in coll.all_objects
    if o.type == "MESH" and "Proto" not in o.name and not o.hide_render
]
focus = []
for obj in meshes:
    piece = str(obj.get("pae_piece_id") or "").lower()
    asset = str(obj.get("pae_asset_id") or "").lower()
    if asset == "ground_plinth" or "curtain" in piece or piece.startswith("site_"):
        continue
    focus.append(obj)
bb_min, bb_max = ns["mesh_world_bounds_m"](focus)
directions = {{
    "se": (1.0, -1.0, 0.48),
    "sw": (-1.0, -1.0, 0.48),
    "nw": (-1.0, 1.0, 0.48),
    "ne": (1.0, 1.0, 0.48),
    "top": (0.01, -0.01, 1.0),
}}
outputs = {{}}
for label, direction in directions.items():
    pose = ns["camera_pose_from_bounds_m"](
        bb_min, bb_max, margin=1.08, direction=direction, ortho=True
    )
    ns["_apply_camera_pose"](pose)
    out = repo / "Saved" / "Screenshots" / f"reference_audit_{{label}}.png"
    ns["write_screenshot"](out)
    outputs[label] = str(out)
print(json.dumps({{"mesh_count": len(meshes), "focus_count": len(focus), "outputs": outputs}}))
"""
    print(json.dumps(client.execute(code, timeout=180.0), indent=2))


if __name__ == "__main__":
    main()

"""Build the validated reference-style fortress campus in the live Blender scene."""

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
import json
import runpy
import sys
from pathlib import Path
import bpy

repo = Path({str(REPO)!r})
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))
ns = runpy.run_path(str(repo / "pae" / "blender_build.py"))
result = ns["build_fortress_live"](write_png=True)
coll = bpy.data.collections.get(result["collection"])
if coll is None:
    raise RuntimeError("live fortress collection disappeared after build")

# Earlier cutaway proofs intentionally hide sibling collections and objects.
# Reset both datablock and view-layer visibility before the reference render.
def unhide_collection(node):
    node.hide_render = False
    node.hide_viewport = False
    for obj in node.objects:
        if obj.type == "MESH" and "Proto" not in obj.name:
            obj.hide_set(False)
            obj.hide_render = False
    for child in node.children:
        unhide_collection(child)

def unexclude_layer(node):
    node.exclude = False
    node.hide_viewport = False
    for child in node.children:
        unexclude_layer(child)

unhide_collection(coll)
unexclude_layer(bpy.context.view_layer.layer_collection)
bpy.context.view_layer.update()
ns["frame_camera_on_meshes"](collection=result["collection"])
shot = ns["write_screenshot"](repo / "Saved" / "Screenshots" / "fortress_live.png")
visible = [
    obj
    for obj in coll.all_objects
    if obj.type == "MESH" and "Proto" not in obj.name and not obj.hide_render
]
# A closer architectural view excludes only the oversized terrain/plinth and
# distant curtain-run pieces from camera framing; all geometry stays visible.
focus = []
for obj in visible:
    piece = str(obj.get("pae_piece_id") or "").lower()
    asset = str(obj.get("pae_asset_id") or "").lower()
    if asset == "ground_plinth":
        continue
    if "curtain" in piece or piece.startswith("site_"):
        continue
    focus.append(obj)
fmin, fmax = ns["mesh_world_bounds_m"](focus)
fpose = ns["camera_pose_from_bounds_m"](
    fmin,
    fmax,
    margin=1.12,
    direction=(1.0, -1.0, 0.52),
    ortho=True,
)
ns["_apply_camera_pose"](fpose)
close_shot = ns["write_screenshot"](
    repo / "Saved" / "Screenshots" / "reference_compound_close.png"
)
print(json.dumps({{
    "ok": result["ok"],
    "collection": result["collection"],
    "instances": result["instances"],
    "placements": result["placements"],
    "extent_m": result["extent_m"],
    "visible_meshes": len(visible),
    "screenshot": str(shot),
    "close_screenshot": str(close_shot),
}}))
"""
    print(json.dumps(client.execute(code, timeout=300.0), indent=2))


if __name__ == "__main__":
    main()

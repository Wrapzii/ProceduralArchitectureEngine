"""Render the courtyard-side covered arcade using the live Blender instance."""

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
import sys
from pathlib import Path

repo = Path({str(REPO)!r})
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))
ns = runpy.run_path(str(repo / "pae" / "blender_build.py"))
from pae.pipeline import run_through_assemble
from pae.spec import m4_courtyard_spec
from pae.validate import validate

_m, _p, assembly, stage = run_through_assemble(
    m4_courtyard_spec(),
    apply_trim=True,
    apply_arcade=True,
)
assembly, report = validate(assembly)
if not stage.ok or not report.ok:
    raise RuntimeError([f.message for f in (stage.critical + report.critical)])

coll = ns["_ensure_collection"]("PAE_Covered_Arcade")
for obj in list(coll.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
count = ns["instance_assembly"](
    assembly,
    label="covered_arcade",
    target_coll=coll,
)

# Cut away the south/east outer envelope and roof so the courtyard-facing
# arches, walk floor, rear wall, and corner piers are all visible together.
kept = []
for obj in list(coll.objects):
    if obj.type != "MESH" or "Proto" in obj.name:
        continue
    piece = str(obj.get("pae_piece_id") or "")
    asset = str(obj.get("pae_asset_id") or "")
    hide = (
        asset.startswith("roof_")
        or piece.startswith("roof_")
        or piece.startswith("wall_south_")
        or piece.startswith("wall_east_")
        or piece.startswith("wall_inner_south_")
        or piece.startswith("wall_inner_east_")
    )
    obj.hide_set(hide)
    obj.hide_render = hide
    if not hide:
        kept.append(obj)

for candidate in bpy.data.collections:
    if candidate.name.startswith("PAE_") and candidate != coll:
        candidate.hide_viewport = True
        candidate.hide_render = True
coll.hide_viewport = False
coll.hide_render = False
bpy.context.view_layer.update()

bb_min, bb_max = ns["mesh_world_bounds_m"](kept)
pose = ns["camera_pose_from_bounds_m"](
    bb_min,
    bb_max,
    margin=1.18,
    direction=(1.0, -1.0, 0.72),
    ortho=True,
)
ns["_apply_camera_pose"](pose)
ns["_ensure_gallery_lighting"]()
out = repo / "Saved" / "Screenshots" / "covered_arcade_cutaway.png"
ns["write_screenshot"](out)

# Roofed view: restore the flat cover while retaining the south/east cutaway.
for obj in list(coll.objects):
    if obj.type != "MESH" or "Proto" in obj.name:
        continue
    piece = str(obj.get("pae_piece_id") or "")
    asset = str(obj.get("pae_asset_id") or "")
    if asset.startswith("roof_") or piece.startswith("roof_"):
        obj.hide_set(False)
        obj.hide_render = False
bpy.context.view_layer.update()
roofed = [
    obj
    for obj in coll.objects
    if obj.type == "MESH" and not obj.hide_get() and not obj.hide_render
]
rmin, rmax = ns["mesh_world_bounds_m"](roofed)
rpose = ns["camera_pose_from_bounds_m"](
    rmin,
    rmax,
    margin=1.18,
    direction=(1.0, -1.0, 0.38),
    ortho=True,
)
ns["_apply_camera_pose"](rpose)
roofed_out = repo / "Saved" / "Screenshots" / "covered_arcade_roofed.png"
ns["write_screenshot"](roofed_out)
print(json.dumps({{
    "ok": report.ok,
    "instances": count,
    "arcades": sum(1 for p in assembly.placements if p.asset_id == "wall_arcade"),
    "screenshot": str(out),
    "roofed_screenshot": str(roofed_out),
}}))
"""
    print(json.dumps(client.execute(code, timeout=300.0), indent=2))


if __name__ == "__main__":
    main()

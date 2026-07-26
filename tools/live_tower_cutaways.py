"""Build and render live cutaways for the small round and square stair towers."""

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
build = ns["build_gallery"](
    milestones=("tiny_spire", "small_square"),
    write_png=False,
)

def collection_meshes(coll):
    out = []
    def walk(node):
        out.extend(o for o in node.objects if o.type == "MESH" and "Proto" not in o.name)
        for child in node.children:
            walk(child)
    walk(coll)
    return out

def keep_piece(piece, asset, square):
    piece = str(piece or "")
    asset = str(asset or "")
    if asset.startswith("roof_") or piece.startswith("roof_"):
        return False
    if piece.startswith("ground_") or asset == "ground_plinth":
        return False
    if piece.startswith("tower_win_") or piece.startswith("tower_crenel_"):
        return False
    if piece.startswith("tower_arc_"):
        # Camera is south-east: retain only the north-west quarter as context.
        return "_90_" in piece
    if piece.startswith("square_tower_"):
        # Retain north/west faces, remove south/east faces.
        return "_0_" in piece or "_90_" in piece
    if (
        piece.startswith("tower_")
        or piece.startswith("stair_spiral_")
        or piece.startswith("spiral_newel_")
        or piece.startswith("floor_hole_")
    ):
        return True
    # Host floors show exactly where each tower doorway meets the building.
    if asset in ("floor", "floor_hole"):
        return True
    # Hide the host envelope so it cannot conceal the stair and landings.
    return False

def keep_circulation(piece, asset):
    piece = str(piece or "")
    asset = str(asset or "")
    return (
        piece.startswith("stair_spiral_")
        or piece.startswith("spiral_newel_")
        or piece.startswith("tower_entry_")
        or piece.startswith("tower_core_door_")
        or piece.startswith("tower_floor_hole_")
        or piece.startswith("floor_hole_")
    )

configs = [
    ("PAE_Tiny_Round_Spire", False, "tower_cutaway_tiny_round.png"),
    ("PAE_Small_Square_Spire", True, "tower_cutaway_small_square.png"),
]
outputs = []
gallery = bpy.data.collections.get("PAE_Gallery")
for coll_name, square, filename in configs:
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        raise RuntimeError(f"missing cutaway collection {{coll_name}}")
    if gallery is not None:
        for child in gallery.children:
            child.hide_render = child.name != coll_name
            child.hide_viewport = child.name != coll_name
    kept = []
    hidden = []
    for obj in collection_meshes(coll):
        keep = keep_piece(
            obj.get("pae_piece_id"),
            obj.get("pae_asset_id"),
            square,
        )
        obj.hide_set(not keep)
        obj.hide_render = not keep
        (kept if keep else hidden).append(obj.name)
    bpy.context.view_layer.update()
    visible = [o for o in collection_meshes(coll) if not o.hide_get() and not o.hide_render]
    bb_min, bb_max = ns["mesh_world_bounds_m"](visible)
    pose = ns["camera_pose_from_bounds_m"](
        bb_min,
        bb_max,
        margin=1.22,
        direction=(1.0, -1.0, 0.58),
        ortho=True,
    )
    ns["_apply_camera_pose"](pose)
    ns["_ensure_gallery_lighting"]()
    out = repo / "Saved" / "Screenshots" / filename
    ns["write_screenshot"](out)
    # Second proof removes every slab/shell so all three stair flights and
    # doorway-bearing landings can be inspected without occlusion.
    for obj in collection_meshes(coll):
        keep = keep_circulation(
            obj.get("pae_piece_id"),
            obj.get("pae_asset_id"),
        )
        obj.hide_set(not keep)
        obj.hide_render = not keep
    bpy.context.view_layer.update()
    circulation_visible = [
        o for o in collection_meshes(coll) if not o.hide_get() and not o.hide_render
    ]
    cmin, cmax = ns["mesh_world_bounds_m"](circulation_visible)
    cpose = ns["camera_pose_from_bounds_m"](
        cmin,
        cmax,
        margin=1.32,
        direction=(1.0, -1.0, 0.35),
        ortho=True,
    )
    ns["_apply_camera_pose"](cpose)
    circulation_out = (
        repo
        / "Saved"
        / "Screenshots"
        / filename.replace("tower_cutaway_", "tower_circulation_")
    )
    ns["write_screenshot"](circulation_out)
    outputs.append({{
        "collection": coll_name,
        "kept": len(kept),
        "hidden": len(hidden),
        "screenshot": str(out),
        "circulation_screenshot": str(circulation_out),
    }})

# Leave the small square circulation proof isolated and visible in Blender.
if gallery is not None:
    for child in gallery.children:
        child.hide_render = child.name != "PAE_Small_Square_Spire"
        child.hide_viewport = child.name != "PAE_Small_Square_Spire"
bpy.context.view_layer.update()
print(json.dumps({{"build_ok": build["ok"], "cutaways": outputs}}))
"""
    print(json.dumps(client.execute(code, timeout=300.0), indent=2))


if __name__ == "__main__":
    main()

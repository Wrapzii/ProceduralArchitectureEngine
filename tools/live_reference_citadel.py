"""Build and audit the new reference-image citadel in the live Blender scene."""

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
import importlib
import json
import runpy
import sys
from pathlib import Path

repo = Path({str(REPO)!r})
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))
ns = runpy.run_path(str(repo / "pae" / "blender_build.py"))
ns["clear_pae_scene"]()
ns["reload_pae"]()

import pae.reference_citadel as reference_citadel
importlib.reload(reference_citadel)
from pae.pipeline import run_through_assemble
from pae.validate import validate

root = bpy.data.collections.new("PAE_Reference_Citadel")
bpy.context.scene.collection.children.link(root)
results = []
children = {{}}
child_meshes = {{}}
all_meshes = []
for component in reference_citadel.reference_citadel_components():
    _m, _p, assembly, stage_report = run_through_assemble(
        component.factory(), apply_arcade=component.arcade
    )
    assembly, report = validate(assembly)
    if stage_report.critical or report.critical:
        problems = [
            f"{{f.check}}: {{f.message}}"
            for f in list(stage_report.critical) + list(report.critical)
        ]
        raise RuntimeError(f"{{component.name}} failed: {{problems[:12]}}")
    coll = bpy.data.collections.new(f"PAE_Reference_{{component.name}}")
    root.children.link(coll)
    count = ns["instance_assembly"](
        assembly,
        label=f"reference_{{component.name}}",
        target_coll=coll,
        offset_m=component.offset_m,
    )
    meshes = [
        o for o in coll.all_objects
        if o.type == "MESH" and "Proto" not in o.name
    ]
    all_meshes.extend(meshes)
    children[component.name] = coll
    child_meshes[component.name] = meshes
    results.append({{
        "name": component.name,
        "placements": len(assembly.placements),
        "instances": count,
        "critical": len(report.critical),
    }})

def show_all():
    for name, coll in children.items():
        coll.hide_viewport = False
        coll.hide_render = False
        for obj in child_meshes[name]:
            obj.hide_set(False)
            obj.hide_render = False

def render_bounds(meshes, label, direction, margin=1.10, resolution=None):
    bpy.context.view_layer.update()
    bb_min, bb_max = ns["mesh_world_bounds_m"](meshes)
    pose = ns["camera_pose_from_bounds_m"](
        bb_min, bb_max, margin=margin, direction=direction, ortho=True
    )
    ns["_apply_camera_pose"](pose)
    ns["_ensure_gallery_lighting"]()
    out = repo / "Saved" / "Screenshots" / f"reference_citadel_{{label}}.png"
    if resolution is None:
        ns["write_screenshot"](out)
    else:
        scene = bpy.context.scene
        ns["configure_workbench_screenshot_scene"](scene)
        scene.render.resolution_x, scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
        scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
    return str(out)

show_all()
views = {{}}
for label, direction in {{
    "se": (1.0, -1.0, 0.50),
    "sw": (-1.0, -1.0, 0.50),
    "nw": (-1.0, 1.0, 0.50),
    "ne": (1.0, 1.0, 0.50),
    "top": (0.01, -0.01, 1.0),
}}.items():
    view_margin = 1.38 if label == "top" else 1.08
    views[label] = render_bounds(all_meshes, label, direction, view_margin)

# Gate proof: front-on, with no approach stair placed in either carriage lane.
for name, coll in children.items():
    coll.hide_viewport = name != "gatehouse"
    coll.hide_render = name != "gatehouse"
gate_meshes = list(child_meshes["gatehouse"])
views["gate_front"] = render_bounds(
    gate_meshes, "gate_front", (0.01, -1.0, 0.18), 1.05
)

# Interior proofs deliberately remove roofs and one obscuring exterior face.
# These are diagnostic sections, not flattering exterior views: every landing,
# floor void, connector portal, and gate lane must remain legible.
def section_component(name, hide_predicate):
    for other_name, other_coll in children.items():
        other_coll.hide_viewport = other_name != name
        other_coll.hide_render = other_name != name
    visible = []
    for obj in child_meshes[name]:
        hidden = bool(hide_predicate(obj))
        obj.hide_set(hidden)
        obj.hide_render = hidden
        if not hidden:
            visible.append(obj)
    return visible

gate_section = section_component(
    "gatehouse",
    lambda o: o.get("pae_kind") == "roof"
    or (
        o.get("pae_kind") == "wall"
        and o.get("pae_cell_x") == 4
        and "tower" not in str(o.get("pae_tags") or "")
    ),
)
views["gate_interior"] = render_bounds(
    gate_section, "gate_interior", (1.0, -1.0, 0.65), 1.08
)

for connector_name in ("gate_to_court", "court_to_hall"):
    connector_section = section_component(
        connector_name,
        lambda o: o.get("pae_kind") == "roof"
        or (
            o.get("pae_kind") == "wall"
            and str(o.get("pae_piece_id") or "").startswith("wall_east_")
        ),
    )
    views[f"{{connector_name}}_interior"] = render_bounds(
        connector_section,
        f"{{connector_name}}_interior",
        (1.0, -0.35, 0.35),
        1.16,
    )

court_section = section_component(
    "courtyard",
    lambda o: o.get("pae_kind") == "roof",
)
views["courtyard_open"] = render_bounds(
    court_section, "courtyard_open", (0.2, -0.25, 1.0), 1.12
)

# Gallery bearing proof: retain the north/west roof soffits and remove the
# nearer south/east roof runs so column bases and capitals are both visible.
court_bearing = section_component(
    "courtyard",
    lambda o: (
        o.get("pae_kind") == "roof"
        and (
            (o.get("pae_cell_x"), o.get("pae_cell_y")) == (0, 0)
            or (o.get("pae_cell_x"), o.get("pae_cell_y")) == (10, 2)
        )
    )
    or (
        o.get("pae_kind") == "wall"
        and (
            o.get("pae_cell_y") == 0
            or o.get("pae_cell_x") == 11
        )
    ),
)
views["courtyard_bearing"] = render_bounds(
    court_bearing,
    "courtyard_bearing",
    (1.0, -1.0, 0.18),
    1.08,
    resolution=(1280, 720),
)

hall_section = section_component(
    "great_hall",
    lambda o: "tower" in str(o.get("pae_tags") or "")
    or (
        o.get("pae_kind") == "wall"
        and o.get("pae_cell_x") == 10
        and "interior_arch_rib" not in str(o.get("pae_tags") or "")
    ),
)
views["hall_interior"] = render_bounds(
    hall_section, "hall_interior", (1.0, -0.38, 0.12), 1.05,
    resolution=(1280, 720),
)

# Isolated structural proof for the repeated free-standing hall ribs.
hall_ribs = section_component(
    "great_hall",
    lambda o: not (
        "interior_arch_rib" in str(o.get("pae_tags") or "")
        or (
            o.get("pae_kind") == "floor"
            and o.get("pae_level") == 0
        )
        or (
            o.get("pae_kind") == "wall"
            and o.get("pae_level") == 0
            and o.get("pae_cell_y") == 4
            and "tower" not in str(o.get("pae_tags") or "")
        )
    ),
)
views["hall_ribs"] = render_bounds(
    hall_ribs,
    "hall_ribs",
    (1.0, -1.0, 0.45),
    1.12,
    resolution=(1280, 720),
)

# Honest round-tower circulation cutaway from the great hall's west tower.
for name, coll in children.items():
    coll.hide_viewport = name != "great_hall"
    coll.hide_render = name != "great_hall"
cutaway = []
for obj in child_meshes["great_hall"]:
    cell = (obj.get("pae_cell_x"), obj.get("pae_cell_y"))
    piece = str(obj.get("pae_piece_id") or "")
    asset = str(obj.get("pae_asset_id") or "")
    keep = False
    if cell == (-1, 2):
        keep = (
            asset == "stair_spiral_quarter"
            or asset == "spiral_newel"
            or piece.startswith("tower_entry_")
            or piece.startswith("tower_entry_landing_")
            or piece.startswith("tower_room_floor_")
            or piece.startswith("tower_core_door_")
            or (piece.startswith("tower_arc_") and "_90_" in piece)
        )
    obj.hide_set(not keep)
    obj.hide_render = not keep
    if keep:
        cutaway.append(obj)
views["tower_cutaway"] = render_bounds(
    cutaway,
    "tower_cutaway",
    (1.0, -1.0, 0.18),
    1.25,
    resolution=(720, 1280),
)

# Matching cutaway for the Great Hall square tower that previously retained
# room-floor and core-wall solids through its spiral.
for name, coll in children.items():
    coll.hide_viewport = name != "great_hall"
    coll.hide_render = name != "great_hall"
square_cutaway = []
for obj in child_meshes["great_hall"]:
    cell = (obj.get("pae_cell_x"), obj.get("pae_cell_y"))
    piece = str(obj.get("pae_piece_id") or "")
    tags = str(obj.get("pae_tags") or "")
    keep = False
    if cell == (10, 2):
        keep = (
            obj.get("pae_asset_id") == "stair_spiral_quarter"
            or piece.startswith("tower_entry_")
            or piece.startswith("tower_entry_landing_")
            or piece.startswith("tower_room_floor_")
            or (
                "square_tower" in tags
                and ("face_90" in tags or "face_180" in tags)
            )
        )
    obj.hide_set(not keep)
    obj.hide_render = not keep
    if keep:
        square_cutaway.append(obj)
views["square_tower_cutaway"] = render_bounds(
    square_cutaway,
    "square_tower_cutaway",
    (-1.0, -1.0, 0.18),
    1.18,
    resolution=(720, 1280),
)

# Leave the complete new citadel visible from the southeast.
show_all()
render_bounds(all_meshes, "current", (1.0, -1.0, 0.50), 1.08)
bpy.context.view_layer.update()
print(json.dumps({{
    "ok": True,
    "root": root.name,
    "components": results,
    "total_instances": sum(r["instances"] for r in results),
    "views": views,
}}))
"""
    print(json.dumps(client.execute(code, timeout=300.0), indent=2))


if __name__ == "__main__":
    main()

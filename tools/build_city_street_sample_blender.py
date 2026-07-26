#!/usr/bin/env python3
"""Build RE city street sample in Blender via PAE assembly + kit-scale meshes.

Creates:
  Saved/city_samples/street_sample.blend
  Saved/city_samples/street_sample_validation.json
  Saved/Screenshots/city_street_sample_*.png
  Saved/Screenshots/city_street_sample_opposite_*.png
  Saved/city_samples/renders/*.png (copies)

Usage::

    blender --background --python tools/build_city_street_sample_blender.py
    blender --background --python tools/build_city_street_sample_blender.py -- --side both

Headless validation only (no bpy)::

    python tools/build_city_street_sample_blender.py --dry-run --side both
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

STREET_COLLECTION = "PAE_CityStreet"
COMPOSER_COLLECTION = "Composer"
GROK_COLLECTION = "Grok"
BLEND_PATH = PAE_ROOT / "Saved" / "city_samples" / "street_sample.blend"
VALIDATION_PATH = PAE_ROOT / "Saved" / "city_samples" / "street_sample_validation.json"
SCREENSHOT_DIR = PAE_ROOT / "Saved" / "Screenshots"
RENDER_DIR = PAE_ROOT / "Saved" / "city_samples" / "renders"

# Proof cameras — deterministic, not orbit.
# Overview from SE looking NW: near=south(Grok), far=north(Composer).
OVERVIEW_DIR = (0.85, -0.72, 0.55)
COMMERCE_DIR = (0.35, -1.0, 0.42)
NOBLE_DIR = (1.0, -0.55, 0.48)
DOORWAY_DIR = (0.2, -1.0, 0.18)
# Grok south-lane cams (looking toward −Y frontage from the street)
OPP_OVERVIEW_DIR = (0.75, 0.85, 0.52)
OPP_COMMERCE_DIR = (0.25, 1.0, 0.40)
OPP_NOBLE_DIR = (-0.55, 0.85, 0.48)
OPP_DOORWAY_DIR = (0.15, 1.0, 0.16)


def _ensure_child_collection(parent, name: str):
    import bpy

    child = bpy.data.collections.get(name)
    if child is None:
        child = bpy.data.collections.new(name)
    # Unlink from other parents so the Outliner folder sits under the street root.
    scene_root = bpy.context.scene.collection
    for coll in list(bpy.data.collections):
        if child.name in {c.name for c in coll.children}:
            try:
                coll.children.unlink(child)
            except RuntimeError:
                pass
    if child.name in {c.name for c in scene_root.children}:
        try:
            scene_root.children.unlink(child)
        except RuntimeError:
            pass
    if child.name not in {c.name for c in parent.children}:
        parent.children.link(child)
    return child


def _agent_for_object_name(name: str) -> str:
    """Map PAE instance name → Composer | Grok | Street (site props)."""
    lower = name.lower()
    if "_opp_" in lower or lower.startswith("pae_street_opp_"):
        return GROK_COLLECTION
    if any(
        key in lower
        for key in (
            "sidewalk",
            "lawn",
            "street_slab",
            "paving",
            "boundary",
            "fence",
            "gate",
        )
    ):
        return "Street"
    return COMPOSER_COLLECTION


def _organize_agent_collections(street_coll) -> Dict[str, int]:
    """Move kit instances into Composer / Grok folders (plus Street for paving)."""
    composer = _ensure_child_collection(street_coll, COMPOSER_COLLECTION)
    grok = _ensure_child_collection(street_coll, GROK_COLLECTION)
    street_props = _ensure_child_collection(street_coll, "Street")
    counts = {COMPOSER_COLLECTION: 0, GROK_COLLECTION: 0, "Street": 0}

    for obj in list(street_coll.objects):
        agent = _agent_for_object_name(obj.name)
        target = {
            COMPOSER_COLLECTION: composer,
            GROK_COLLECTION: grok,
            "Street": street_props,
        }[agent]
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        target.objects.link(obj)
        counts[agent] = counts.get(agent, 0) + 1
    return counts


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def build_assembly(side: str = "both"):
    """PAE assemble + site + per-lot validation JSON."""
    from pae.city_street_sample import build_street, write_validation_json

    assembly, report, stats = build_street(side=side)
    if assembly is None:
        raise RuntimeError(f"street assembly failed: {stats.get('failed')}")
    val_path = write_validation_json(stats, VALIDATION_PATH)
    return assembly, report, stats, val_path


def _bounds_for_objects(
    objects: Sequence[Any],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    from pae.blender_build import mesh_world_bounds_m

    if not objects:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return mesh_world_bounds_m(objects)


def _objects_matching(coll, substring: str) -> List[Any]:
    return [
        o
        for o in coll.all_objects
        if substring in o.name and o.type == "MESH" and not o.hide_render
    ]


def _frame_and_shot(
    coll,
    out_path: Path,
    *,
    direction: Tuple[float, float, float],
    margin: float = 1.28,
    filter_sub: Optional[str] = None,
) -> Path:
    from pae.blender_build import (
        _apply_camera_pose,
        camera_pose_from_bounds_m,
        write_screenshot,
    )

    import bpy

    objs = (
        _objects_matching(coll, filter_sub)
        if filter_sub
        else [o for o in coll.all_objects if o.type == "MESH" and not o.hide_render]
    )
    bb_min, bb_max = _bounds_for_objects(objs)
    pose = camera_pose_from_bounds_m(bb_min, bb_max, margin=margin, direction=direction)
    _apply_camera_pose(pose)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.filepath = str(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return out_path


def _copy_shot(path: Path, fname: str, shots: Dict[str, str]) -> None:
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    copy = RENDER_DIR / fname
    try:
        import shutil

        shutil.copy2(path, copy)
        shots[fname.replace(".png", "") + "_renders"] = str(copy)
    except OSError:
        pass


def build_blender_scene(
    assembly,
    *,
    write_blend: bool = True,
    write_shots: bool = True,
    side: str = "both",
) -> Dict[str, Any]:
    """Instance assembly with themed kit meshes, save blend + proof PNGs."""
    from pae.blender_build import (
        CM_TO_M,
        assembly_bounds_cm,
        clear_pae_scene,
        reload_pae,
    )
    from pae.kit_dress import instance_assembly_kit

    reloaded = reload_pae()
    if not _have_bpy():
        return {
            "ok": True,
            "blender": False,
            "reloaded": len(reloaded),
            "note": "bpy missing — assembly/validation only",
        }

    import bpy
    from tools.build_modular_kit_blender import _configure_render, _setup_kit_lighting

    clear_pae_scene()
    coll = bpy.data.collections.get(STREET_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(STREET_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    else:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    bb_min, bb_max = assembly_bounds_cm(assembly)
    offset_m = (
        -bb_min[0] * CM_TO_M,
        -bb_min[1] * CM_TO_M,
        -bb_min[2] * CM_TO_M,
    )
    n, kit_used = instance_assembly_kit(
        assembly,
        label="street",
        target_coll=coll,
        offset_m=offset_m,
    )
    agent_counts = _organize_agent_collections(coll)

    objs = [o for o in coll.all_objects if o.type == "MESH"]
    if objs:
        from mathutils import Vector
        from tools.build_modular_kit_blender import _scene_bounds_m

        mins, maxs, span = _scene_bounds_m(objs)
        center = Vector(
            ((mins[0] + maxs[0]) * 0.5, (mins[1] + maxs[1]) * 0.5, (mins[2] + maxs[2]) * 0.5)
        )
        _setup_kit_lighting(bpy.context.scene, bpy, center, span)
    _configure_render(bpy.context.scene, bpy, width=1280, height=720)

    shots: Dict[str, str] = {}
    if write_shots:
        overview_margin = 1.55 if side in ("both", "opposite") else 1.32
        shot_specs = [
            ("city_street_sample_overview.png", OVERVIEW_DIR, overview_margin, None),
            ("city_street_sample_commerce.png", COMMERCE_DIR, 1.18, "shop_"),
            ("city_street_sample_noble.png", NOBLE_DIR, 1.22, "noble_manor"),
            ("city_street_sample_doorway.png", DOORWAY_DIR, 1.08, "shop_1storey"),
        ]
        if side in ("both", "opposite"):
            shot_specs.extend(
                [
                    (
                        "city_street_sample_opposite_overview.png",
                        OPP_OVERVIEW_DIR,
                        1.35,
                        "opp_",
                    ),
                    (
                        "city_street_sample_opposite_commerce.png",
                        OPP_COMMERCE_DIR,
                        1.18,
                        "opp_shop_",
                    ),
                    (
                        "city_street_sample_opposite_noble.png",
                        OPP_NOBLE_DIR,
                        1.22,
                        "opp_noble_manor",
                    ),
                    (
                        "city_street_sample_opposite_doorway.png",
                        OPP_DOORWAY_DIR,
                        1.08,
                        "opp_shop_1storey",
                    ),
                ]
            )
        for fname, direction, margin, filt in shot_specs:
            primary = SCREENSHOT_DIR / fname
            path = _frame_and_shot(
                coll, primary, direction=direction, margin=margin, filter_sub=filt
            )
            shots[fname.replace(".png", "")] = str(path)
            _copy_shot(path, fname, shots)

    if write_blend:
        BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    return {
        "ok": True,
        "blender": True,
        "reloaded": len(reloaded),
        "collection": STREET_COLLECTION,
        "agent_collections": {
            COMPOSER_COLLECTION: "north (+Y)",
            GROK_COLLECTION: "south (−Y)",
        },
        "agent_object_counts": agent_counts,
        "instances": n,
        "kit_meshes": True,
        "kit_pieces_used": kit_used,
        "placements": len(assembly.placements),
        "offset_m": offset_m,
        "side": side,
        "blend": str(BLEND_PATH),
        "validation": str(VALIDATION_PATH),
        "screenshots": shots,
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Build RE city street sample")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="PAE assemble/validate only (no Blender file or renders)",
    )
    parser.add_argument("--no-blend", action="store_true", help="Skip .blend save")
    parser.add_argument("--no-shots", action="store_true", help="Skip PNG renders")
    parser.add_argument(
        "--side",
        choices=("original", "opposite", "both"),
        default="both",
        help="Which lot plan to build (default: both = original + opposite)",
    )
    args = parser.parse_args(argv)

    assembly, report, stats, val_path = build_assembly(side=args.side)
    print(
        json.dumps(
            {
                "side": args.side,
                "lots": len(stats.get("lots", [])),
                "all_lots_valid": stats.get("all_lots_valid"),
                "opposite_lots_valid": stats.get("opposite_lots_valid"),
                "opposite_building_count": stats.get("opposite_building_count"),
                "site_critical": stats.get("critical"),
                "total_pieces": stats.get("total"),
                "validation_json": str(val_path),
            },
            indent=2,
        )
    )

    if args.dry_run:
        print("dry-run: skipping Blender scene")
        return

    result = build_blender_scene(
        assembly,
        write_blend=not args.no_blend,
        write_shots=not args.no_shots,
        side=args.side,
    )
    stats["kit_meshes"] = result.get("kit_meshes", False)
    stats["kit_instance_count"] = result.get("instances", 0)
    stats["kit_pieces_used"] = result.get("kit_pieces_used", {})
    from pae.city_street_sample import write_validation_json

    write_validation_json(stats, VALIDATION_PATH)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    # Blender forwards its own argv; script args follow ``--`` or the script path.
    _argv = list(sys.argv)
    _script = str(Path(__file__).resolve())
    if "--" in _argv:
        _argv = _argv[_argv.index("--") + 1 :]
    elif _script in _argv:
        _argv = _argv[_argv.index(_script) + 1 :]
    else:
        _script_name = Path(__file__).name
        if _script_name in _argv:
            _argv = _argv[_argv.index(_script_name) + 1 :]
        else:
            _argv = _argv[1:] if not _have_bpy() else []
    main(_argv)

#!/usr/bin/env python3
"""PREVIEW-only Blender material lookdev for style gallery (MP-WS-K2).

Assigns simple procedural PBR materials by export slot family. These are
**temporary lookdev previews only** — final surfacing is Unreal/Nanite via
``MI_*`` slots and masks (see ``pae/export/materials.py``).

Does **not** modify Codex-dirty ``pae/blender_build.py``. Screenshots ≤640px,
one style at a time, Cycles/EEVEE material preview (not Workbench flat).

Usage::

    blender --background --python tools/render_style_material_preview.py -- --seed 7
    blender --background --python tools/render_style_material_preview.py -- --seed 7 --styles rustic,manor,civic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

from tools.style_seed_matrix import (  # noqa: E402
    ALL_BUILTIN_STYLE_IDS,
    GALLERY_SEED,
    matrix_spec,
)

SCREENSHOT_DIR = PAE_ROOT / "Saved" / "Screenshots"
REPORT_PATH = PAE_ROOT / "Saved" / "exports" / "architectural_detail_report.json"
MAX_SIZE = 640

# Explicit preview-only naming — never collide with UE MI_* contract.
PREVIEW_NOTE = (
    "PREVIEW_* Blender procedural materials only. Final materials are Unreal "
    "Nanite MI_* slots + masks from pae.export.materials — do not ship these "
    "as production textures."
)


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def _preview_slot_for_obj(name: str, asset_id: str = "") -> str:
    blob = f"{name} {asset_id}".lower()
    if "window" in blob and "sill" not in blob and "box" not in blob and "hood" not in blob:
        return "PREVIEW_Glass"
    if "door" in blob and "case" not in blob:
        return "PREVIEW_Timber"
    if any(k in blob for k in ("roof", "chimney", "barge")):
        return "PREVIEW_Roof"
    if any(k in blob for k in ("rail", "metal", "gate_iron")):
        return "PREVIEW_Metal"
    if any(k in blob for k in ("planter", "window_box", "soil")):
        return "PREVIEW_Planter"
    if any(k in blob for k in ("sill", "hood", "band", "trim", "pilaster", "jamb", "lintel", "bracket")):
        return "PREVIEW_Timber"
    if any(k in blob for k in ("floor", "deck", "patio", "porch_slab", "plinth", "step")):
        return "PREVIEW_Plinth"
    return "PREVIEW_Wall"


def _make_preview_materials(bpy) -> Dict[str, object]:
    """Cheap procedural Principled BSDF materials — no external textures."""
    specs = {
        "PREVIEW_Wall": {
            "base": (0.55, 0.42, 0.35, 1.0),
            "rough": 0.82,
            "bump": 0.35,
            "brick": True,
        },
        "PREVIEW_Timber": {
            "base": (0.28, 0.18, 0.10, 1.0),
            "rough": 0.55,
            "bump": 0.15,
            "brick": False,
        },
        "PREVIEW_Roof": {
            "base": (0.25, 0.22, 0.20, 1.0),
            "rough": 0.70,
            "bump": 0.25,
            "brick": False,
        },
        "PREVIEW_Metal": {
            "base": (0.45, 0.45, 0.48, 1.0),
            "rough": 0.35,
            "metal": 0.85,
            "bump": 0.05,
            "brick": False,
        },
        "PREVIEW_Glass": {
            "base": (0.75, 0.85, 0.90, 1.0),
            "rough": 0.05,
            "trans": 0.85,
            "bump": 0.0,
            "brick": False,
        },
        "PREVIEW_Planter": {
            "base": (0.22, 0.28, 0.14, 1.0),
            "rough": 0.90,
            "bump": 0.40,
            "brick": False,
        },
        "PREVIEW_Plinth": {
            "base": (0.50, 0.48, 0.44, 1.0),
            "rough": 0.75,
            "bump": 0.20,
            "brick": False,
        },
    }
    out: Dict[str, object] = {}
    for name, cfg in specs.items():
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out_n = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = cfg["base"]
        bsdf.inputs["Roughness"].default_value = cfg["rough"]
        if "metal" in cfg and "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = cfg["metal"]
        if "trans" in cfg:
            # Blender 4+/5: Transmission Weight; older: Transmission
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = cfg["trans"]
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = cfg["trans"]
        nt.links.new(bsdf.outputs["BSDF"], out_n.inputs["Surface"])

        if cfg.get("bump", 0) > 0:
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 18.0 if cfg.get("brick") else 8.0
            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = float(cfg["bump"])
            nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
            if cfg.get("brick"):
                # Cheap brick-ish value variation into base color.
                brick = nt.nodes.new("ShaderNodeTexBrick")
                brick.inputs["Scale"].default_value = 4.5
                brick.inputs["Color1"].default_value = cfg["base"]
                brick.inputs["Color2"].default_value = (
                    cfg["base"][0] * 0.85,
                    cfg["base"][1] * 0.85,
                    cfg["base"][2] * 0.85,
                    1.0,
                )
                nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
        out[name] = mat
    return out


def _assign_preview_materials(bpy, mats: Dict[str, object]) -> int:
    n = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        slot = _preview_slot_for_obj(obj.name)
        mat = mats.get(slot)
        if mat is None:
            continue
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        n += 1
    return n


def _configure_lookdev_scene(bpy, scene) -> None:
    """Neutral lookdev lighting + EEVEE/Cycles material preview (not Workbench)."""
    # Prefer EEVEE for speed/RAM; fall back to CYCLES if needed.
    engine = "BLENDER_EEVEE"
    if hasattr(bpy.types.RenderSettings, "engine"):
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
            engine = "BLENDER_EEVEE_NEXT"
        except Exception:
            try:
                scene.render.engine = "BLENDER_EEVEE"
                engine = "BLENDER_EEVEE"
            except Exception:
                scene.render.engine = "CYCLES"
                engine = "CYCLES"
                scene.cycles.samples = 16
                scene.cycles.use_denoising = False

    scene.render.resolution_x = MAX_SIZE
    scene.render.resolution_y = MAX_SIZE
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.filepath = ""  # set per shot

    # Clear lights; add a simple 3-point lookdev rig.
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)

    def _add_light(name: str, energy: float, loc, color=(1.0, 0.98, 0.94)):
        data = bpy.data.lights.new(name=name, type="AREA")
        data.energy = energy
        data.color = color
        data.size = 4.0
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        return obj

    _add_light("PREVIEW_Key", 450.0, (6.0, -8.0, 7.0))
    _add_light("PREVIEW_Fill", 180.0, (-7.0, -4.0, 5.0), color=(0.85, 0.90, 1.0))
    _add_light("PREVIEW_Rim", 120.0, (0.0, 6.0, 4.0), color=(1.0, 0.95, 0.85))
    # World soft grey — no HDRI download.
    world = scene.world or bpy.data.worlds.new("PREVIEW_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.22, 0.24, 0.26, 1.0)
        bg.inputs[1].default_value = 0.6
    _ = engine


def render_style_material_shot(style_id: str, seed: int) -> Path:
    import bpy
    from mathutils import Vector

    from pae.blender_build import (
        assembly_world_bounds_m,
        camera_pose_from_bounds_m,
        clear_pae_scene,
        instance_assembly,
    )
    from pae.style_pipeline import assemble_with_style_shell_and_detail

    clear_pae_scene()
    spec = matrix_spec(style_id, seed)
    _m, _p, assembly, stage_report = assemble_with_style_shell_and_detail(
        spec,
        seed=seed,
        validate_assembly=True,
    )
    # Gallery still renders if only known assemble debts; refuse K2 criticals.
    k2_crit = [
        f
        for f in stage_report.critical
        if f.check.startswith("balcony_")
        or f.check
        in ("sill_alignment", "planter_clearance", "patio_door_path", "cross_mullion_geometry")
    ]
    if k2_crit:
        raise RuntimeError(f"{style_id} K2 critical: {[f.message for f in k2_crit[:3]]}")

    count = instance_assembly(assembly, label=f"matprev_{style_id}")
    if count <= 0:
        raise RuntimeError(f"no instances for {style_id}")

    mats = _make_preview_materials(bpy)
    assigned = _assign_preview_materials(bpy, mats)

    bpy.context.view_layer.update()
    bmin, bmax = assembly_world_bounds_m(assembly)
    pose = camera_pose_from_bounds_m(bmin, bmax)

    scene = bpy.context.scene
    _configure_lookdev_scene(bpy, scene)

    cam_data = bpy.data.cameras.new(f"PAE_MatPrevCam_{style_id}")
    cam_obj = bpy.data.objects.new(f"PAE_MatPrevCam_{style_id}", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_obj.location = Vector(pose["location"])
    target = Vector(pose["target"])
    cam_obj.rotation_euler = (target - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    if pose.get("ortho"):
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = float(pose["ortho_scale"])

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SCREENSHOT_DIR / f"style_material_preview_{style_id}_s{seed}.png"
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    if not out.is_file():
        raise RuntimeError(f"render produced no file: {out}")
    print(f"[matprev] {style_id}: assigned={assigned} -> {out}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=GALLERY_SEED)
    parser.add_argument(
        "--styles",
        type=str,
        default="rustic,manor,civic",
        help="Comma-separated style ids (default: rustic,manor,civic)",
    )
    args = parser.parse_args(argv)

    if not _have_bpy():
        print(
            "bpy missing — run via Blender:\n"
            "  blender --background --python tools/render_style_material_preview.py "
            f"-- --seed {args.seed}"
        )
        return 2

    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    if styles == ["all"]:
        styles = list(ALL_BUILTIN_STYLE_IDS)

    paths: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    for style_id in styles:
        try:
            path = render_style_material_shot(style_id, args.seed)
            paths[style_id] = str(path.relative_to(PAE_ROOT)).replace("\\", "/")
        except Exception as exc:  # noqa: BLE001 — report per style, continue
            errors[style_id] = str(exc)
            print(f"[matprev] FAIL {style_id}: {exc}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Merge with existing report if present.
    report: Dict = {}
    if REPORT_PATH.is_file():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    report["material_preview"] = {
        "note": PREVIEW_NOTE,
        "seed": args.seed,
        "max_size": MAX_SIZE,
        "paths": paths,
        "errors": errors,
        "status": "ok" if paths and not errors else ("partial" if paths else "fail"),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[matprev] report -> {REPORT_PATH}")
    return 0 if paths else 1


if __name__ == "__main__":
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    raise SystemExit(main(argv))

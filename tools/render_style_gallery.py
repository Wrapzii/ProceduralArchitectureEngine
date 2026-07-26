#!/usr/bin/env python3
"""Render a small style gallery — one image per style pack at a fixed seed.

Uses Blender when ``bpy`` is available. Imports ``pae.blender_build`` **read-only**
(does not edit that dirty Codex file). Screenshots stay small (Workbench, ≤640).

Usage::

    blender --background --python tools/render_style_gallery.py -- --seed 7

When bpy is missing, exits 2 and prints the command for later. Also patches
``Saved/exports/style_seed_matrix.json`` ``renders`` when that file exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

from tools.style_seed_matrix import (  # noqa: E402
    ALL_BUILTIN_STYLE_IDS,
    GALLERY_SEED,
    matrix_spec,
)

SCREENSHOT_DIR = PAE_ROOT / "Saved" / "Screenshots"
MATRIX_PATH = PAE_ROOT / "Saved" / "exports" / "style_seed_matrix.json"
MAX_SIZE = 640


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def render_style_shot(style_id: str, seed: int) -> Path:
    """Build one style via decorate+detail and write a small PNG."""
    import bpy

    # Read-only: call helpers; never modify blender_build.py.
    from pae.blender_build import (
        assembly_world_bounds_m,
        camera_pose_from_bounds_m,
        clear_pae_scene,
        configure_workbench_screenshot_scene,
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
    if not stage_report.ok:
        msgs = [f.message for f in stage_report.critical[:3]]
        raise RuntimeError(f"{style_id} style pipeline failed: {msgs}")

    count = instance_assembly(assembly, label=f"style_{style_id}")
    if count <= 0:
        raise RuntimeError(f"no instances for {style_id}")

    bpy.context.view_layer.update()
    bmin, bmax = assembly_world_bounds_m(assembly)
    pose = camera_pose_from_bounds_m(bmin, bmax)

    scene = bpy.context.scene
    configure_workbench_screenshot_scene(scene)
    scene.render.resolution_x = MAX_SIZE
    scene.render.resolution_y = MAX_SIZE
    scene.render.resolution_percentage = 100

    from mathutils import Vector

    cam_data = bpy.data.cameras.new(f"PAE_StyleCam_{style_id}")
    cam_obj = bpy.data.objects.new(f"PAE_StyleCam_{style_id}", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_obj.location = Vector(pose["location"])
    target = Vector(pose["target"])
    cam_obj.rotation_euler = (target - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    if pose.get("ortho"):
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = float(pose["ortho_scale"])

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SCREENSHOT_DIR / f"style_gallery_{style_id}_s{seed}.png"
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    return out


def render_all(
    *,
    seed: int = GALLERY_SEED,
    styles: Sequence[str] = ALL_BUILTIN_STYLE_IDS,
) -> Dict[str, Any]:
    paths: List[str] = []
    errors: List[str] = []
    for style_id in styles:
        try:
            path = render_style_shot(style_id, seed)
            paths.append(str(path.relative_to(PAE_ROOT)).replace("\\", "/"))
        except Exception as exc:  # noqa: BLE001 — collect per-style failures
            errors.append(f"{style_id}: {exc}")
    status = "ok" if paths and not errors else ("partial" if paths else "failed")
    return {"status": status, "paths": paths, "errors": errors, "seed": seed}


def _patch_matrix_renders(result: Dict[str, Any]) -> None:
    if not MATRIX_PATH.is_file():
        return
    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    cmd = f"blender --background --python tools/render_style_gallery.py -- --seed {result['seed']}"
    data["renders"] = {
        "status": result["status"],
        "paths": result.get("paths", []),
        "errors": result.get("errors", []),
        "seed": result["seed"],
        "command": result.get("command", cmd),
    }
    summary = data.get("human_summary", "")
    lines = [ln for ln in summary.splitlines() if not ln.startswith("Renders:")]
    if result["status"] == "ok":
        lines.append(
            f"Renders: {len(result.get('paths', []))} images under Saved/Screenshots/."
        )
    else:
        lines.append(
            f"Renders: {result['status']} — {data['renders']['command']}"
        )
    data["human_summary"] = "\n".join(lines)
    MATRIX_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    if "--" in raw:
        raw = raw[raw.index("--") + 1 :]

    parser = argparse.ArgumentParser(description="Render style gallery screenshots.")
    parser.add_argument("--seed", type=int, default=GALLERY_SEED)
    parser.add_argument(
        "--styles",
        nargs="+",
        default=list(ALL_BUILTIN_STYLE_IDS),
    )
    args = parser.parse_args(raw)

    cmd = (
        f"blender --background --python tools/render_style_gallery.py "
        f"-- --seed {args.seed}"
    )
    if not _have_bpy():
        print("bpy not available — Blender offline in this process.", file=sys.stderr)
        print(f"Run later: {cmd}")
        stub = {
            "status": "n/a",
            "paths": [],
            "errors": ["bpy missing"],
            "seed": args.seed,
            "command": cmd,
        }
        _patch_matrix_renders(stub)
        return 2

    result = render_all(seed=args.seed, styles=args.styles)
    result["command"] = cmd
    _patch_matrix_renders(result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("ok", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build + prove the fancy manor showpiece (MP-WS-K2).

Writes YAML, JSON report, and (when run inside Blender) multi-view 640px
inspection screenshots proving a solid multi-floor building.

Usage::

    python tools/build_fancy_manor.py
    blender --background --python tools/build_fancy_manor.py -- --render
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

EXPORT_DIR = PAE_ROOT / "Saved" / "exports"
SHOT_DIR = PAE_ROOT / "Saved" / "Screenshots"
YAML_PATH = EXPORT_DIR / "fancy_manor.yaml"
REPORT_PATH = EXPORT_DIR / "fancy_manor_report.json"
MAX_SIZE = 640


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def build_and_report(*, seed: int = 42) -> Dict[str, Any]:
    from pae.fancy_manor import (
        build_fancy_manor,
        fancy_manor_structure,
        summarize_fancy_manor,
    )

    structure = fancy_manor_structure(seed=seed)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    YAML_PATH.write_text(structure.to_yaml(), encoding="utf-8")

    _m, _p, assembly, report = build_fancy_manor(seed=seed, validate_assembly=True)
    summary = summarize_fancy_manor(assembly)
    summary["critical"] = [
        {"check": f.check, "message": f.message} for f in report.critical
    ]
    summary["critical_empty"] = report.critical == []
    summary["warnings"] = len(report.warnings)
    summary["yaml"] = str(YAML_PATH.relative_to(PAE_ROOT)).replace("\\", "/")
    summary["screenshots"] = {}
    summary["note"] = (
        "Fancy manor showpiece. Final UE materials via MI_* slots; "
        "Blender PREVIEW_* mats are lookdev only when rendered."
    )
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"[fancy] placements={summary['total_placements']} "
        f"critical={len(report.critical)} "
        f"stairs={summary['stair_count']} "
        f"balcony_decks={summary['balcony']['decks']} "
        f"door_clear={summary['entrance_approach_clear']}"
    )
    print(f"[fancy] yaml -> {YAML_PATH}")
    print(f"[fancy] report -> {REPORT_PATH}")
    if report.critical:
        for f in report.critical[:8]:
            print(f"  CRITICAL {f.check}: {f.message[:120]}")
    return {"assembly": assembly, "report": report, "summary": summary}


def _bounds_for_levels(assembly, levels: Optional[Sequence[int]] = None):
    from pae.blender_build import assembly_world_bounds_m

    if levels is None:
        return assembly_world_bounds_m(assembly)
    from dataclasses import replace

    keep = {int(l) for l in levels}
    filtered = replace(
        assembly,
        placements=[p for p in assembly.placements if p.level in keep],
    )
    return assembly_world_bounds_m(filtered)


def _hide_kinds(bpy, kinds: Sequence[str]) -> None:
    kind_set = set(kinds)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        name = obj.name.lower()
        if any(k in name for k in kind_set):
            obj.hide_render = True
            obj.hide_viewport = True


def _show_all_meshes(bpy) -> None:
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.hide_render = False
            obj.hide_viewport = False


def _set_camera(bpy, scene, location, target, *, ortho_scale: Optional[float] = None):
    from mathutils import Vector

    cam = scene.camera
    if cam is None:
        data = bpy.data.cameras.new("PAE_FancyCam")
        cam = bpy.data.objects.new("PAE_FancyCam", data)
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.location = Vector(location)
    tgt = Vector(target)
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    if ortho_scale is not None:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = float(ortho_scale)
    else:
        cam.data.type = "PERSP"


def _render_to(bpy, scene, path: Path) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.resolution_x = MAX_SIZE
    scene.render.resolution_y = MAX_SIZE
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"no screenshot at {path}")
    print(f"[fancy] shot -> {path}")
    return path


def render_inspection_views(assembly) -> Dict[str, str]:
    """Multi-view solid-building proof — one shot at a time, ≤640px."""
    import bpy

    from pae.blender_build import (
        camera_pose_from_bounds_m,
        clear_pae_scene,
        configure_workbench_screenshot_scene,
        instance_assembly,
    )

    clear_pae_scene()
    count = instance_assembly(assembly, label="fancy_manor")
    if count <= 0:
        raise RuntimeError("no instances for fancy manor")

    scene = bpy.context.scene
    configure_workbench_screenshot_scene(scene)
    paths: Dict[str, str] = {}

    bmin, bmax = _bounds_for_levels(assembly)
    cx = 0.5 * (bmin[0] + bmax[0])
    cy = 0.5 * (bmin[1] + bmax[1])
    cz = 0.5 * (bmin[2] + bmax[2])
    span = max(bmax[0] - bmin[0], bmax[1] - bmin[1], 8.0)

    # 1) Front (south — -Y) — pull back + elevate so storeys + roof read
    _show_all_meshes(bpy)
    _set_camera(
        bpy,
        scene,
        (cx, bmin[1] - span * 1.85, cz + span * 0.55),
        (cx, cy, cz + span * 0.1),
    )
    paths["front"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_front.png").relative_to(PAE_ROOT)
    ).replace("\\", "/")

    # 2) Back (north — +Y)
    _set_camera(
        bpy,
        scene,
        (cx, bmax[1] + span * 1.85, cz + span * 0.55),
        (cx, cy, cz + span * 0.1),
    )
    paths["back"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_back.png").relative_to(PAE_ROOT)
    ).replace("\\", "/")

    # 3) Roof-off top-down
    _show_all_meshes(bpy)
    _hide_kinds(bpy, ("roof_", "chimney", "barge", "spire"))
    _set_camera(
        bpy,
        scene,
        (cx, cy, bmax[2] + span * 1.4),
        (cx, cy, cz),
        ortho_scale=span * 1.35,
    )
    paths["roofoff"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_roofoff.png").relative_to(PAE_ROOT)
    ).replace("\\", "/")

    # 4) Per-floor plans
    levels = sorted({p.level for p in assembly.placements})
    for lv in levels:
        _show_all_meshes(bpy)
        # Hide roofs always; hide walls/floors above this level.
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            name = obj.name.lower()
            if any(k in name for k in ("roof_", "chimney", "barge")):
                obj.hide_render = True
                obj.hide_viewport = True
                continue
            # Instance names embed level tokens like _L1_ or _1_
            hide = False
            for other in levels:
                if other > lv and (
                    f"_l{other}_" in name
                    or f"_{other}_" in name
                    or f"level{other}" in name
                ):
                    hide = True
            if hide:
                obj.hide_render = True
                obj.hide_viewport = True
        # Rebuild only this level for a clean plan (more reliable than name hacks).
        clear_pae_scene()
        from dataclasses import replace

        floor_asm = replace(
            assembly,
            placements=[
                p
                for p in assembly.placements
                if p.level == lv
                and not (p.kind == "roof" or p.asset_id.startswith("roof_"))
            ],
        )
        instance_assembly(floor_asm, label=f"fancy_floor{lv}")
        configure_workbench_screenshot_scene(scene)
        fbmin, fbmax = _bounds_for_levels(floor_asm)
        fcx = 0.5 * (fbmin[0] + fbmax[0])
        fcy = 0.5 * (fbmin[1] + fbmax[1])
        fspan = max(fbmax[0] - fbmin[0], fbmax[1] - fbmin[1], 6.0)
        _set_camera(
            bpy,
            scene,
            (fcx, fcy, fbmax[2] + fspan * 1.5),
            (fcx, fcy, fbmin[2]),
            ortho_scale=fspan * 1.3,
        )
        key = f"floor{lv}"
        paths[key] = str(
            _render_to(bpy, scene, SHOT_DIR / f"fancy_manor_floor{lv}.png").relative_to(
                PAE_ROOT
            )
        ).replace("\\", "/")

    # 4b) Stair-path top-down — floors + stairs only (all levels, roof off)
    clear_pae_scene()
    from dataclasses import replace

    path_asm = replace(
        assembly,
        placements=[
            p
            for p in assembly.placements
            if p.kind in ("floor", "stair", "wall")
            and not (p.kind == "roof" or str(p.asset_id).startswith("roof_"))
        ],
    )
    instance_assembly(path_asm, label="fancy_stair_path")
    configure_workbench_screenshot_scene(scene)
    pbmin, pbmax = _bounds_for_levels(path_asm)
    pcx = 0.5 * (pbmin[0] + pbmax[0])
    pcy = 0.5 * (pbmin[1] + pbmax[1])
    pspan = max(pbmax[0] - pbmin[0], pbmax[1] - pbmin[1], 6.0)
    _set_camera(
        bpy,
        scene,
        (pcx, pcy, pbmax[2] + pspan * 1.6),
        (pcx, pcy, pbmin[2]),
        ortho_scale=pspan * 1.35,
    )
    paths["stair_path"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_stair_path.png").relative_to(
            PAE_ROOT
        )
    ).replace("\\", "/")

    # 5) Section / stairs — full assembly, side camera looking at stair core
    clear_pae_scene()
    instance_assembly(assembly, label="fancy_section")
    configure_workbench_screenshot_scene(scene)
    _hide_kinds(bpy, ("roof_",))
    _set_camera(
        bpy,
        scene,
        (bmin[0] - span * 0.2, cy, cz + span * 0.15),
        (cx, cy, cz),
    )
    paths["section_stairs"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_section_stairs.png").relative_to(
            PAE_ROOT
        )
    ).replace("\\", "/")

    # 6) Entry close-up — ground door clear of jambs/posts (exterior SE 3/4)
    clear_pae_scene()
    instance_assembly(assembly, label="fancy_entry")
    configure_workbench_screenshot_scene(scene)
    doors = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and p.level == 0
        and ("door" in p.asset_id or "gate" in p.asset_id)
        and "balcony" not in p.tags
    ]
    if doors:
        from pae.contract import placement_world_aabb

        d = doors[0]
        dmn, dmx = placement_world_aabb(
            d.cell[0],
            d.cell[1],
            d.level,
            d.yaw,
            d.size_cm,
            d.offset_cm,
            rotates_about_center=d.rotates_about_center,
        )
        dcx = 0.5 * (dmn[0] + dmx[0]) * 0.01
        dcy = float(dmn[1]) * 0.01
        dcz = min(2.2, 0.35 * (dmx[2] - dmn[2]) * 0.01 + dmn[2] * 0.01)
        # Outside looking north at the leaf — keep the opening centred.
        _set_camera(
            bpy,
            scene,
            (dcx + 1.8, dcy - 5.5, dcz + 1.0),
            (dcx, dcy + 0.3, dcz + 0.6),
        )
    paths["entry_validation"] = str(
        _render_to(bpy, scene, SHOT_DIR / "fancy_manor_entry_validation.png").relative_to(
            PAE_ROOT
        )
    ).replace("\\", "/")

    # 7) Balcony close-up — rails on edges + clear door access (exterior SW elevated)
    clear_pae_scene()
    instance_assembly(assembly, label="fancy_balcony")
    configure_workbench_screenshot_scene(scene)
    # Hide roofs so the deck edge reads; keep L1 walls/rails.
    _hide_kinds(bpy, ("roof_", "chimney", "barge"))
    decks = [
        p
        for p in assembly.placements
        if "balcony_deck" in p.tags or p.asset_id == "balcony_deck"
    ]
    if decks:
        from pae.contract import placement_world_aabb

        deck = decks[0]
        kmn, kmx = placement_world_aabb(
            deck.cell[0],
            deck.cell[1],
            deck.level,
            deck.yaw,
            deck.size_cm,
            deck.offset_cm,
            rotates_about_center=deck.rotates_about_center,
        )
        kcx = 0.5 * (kmn[0] + kmx[0]) * 0.01
        kcy = float(kmn[1]) * 0.01
        kcz = float(kmx[2]) * 0.01
        _set_camera(
            bpy,
            scene,
            (kcx - 3.2, kcy - 3.8, kcz + 2.2),
            (kcx, kcy + 0.5, kcz - 0.2),
        )
    paths["balcony_validation"] = str(
        _render_to(
            bpy, scene, SHOT_DIR / "fancy_manor_balcony_validation.png"
        ).relative_to(PAE_ROOT)
    ).replace("\\", "/")

    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--render",
        action="store_true",
        help="Emit multi-view Blender screenshots (requires bpy)",
    )
    args = parser.parse_args(argv)

    result = build_and_report(seed=args.seed)
    if not result["summary"]["critical_empty"]:
        print("[fancy] refusing render — critical failures present")
        return 1
    if not result["summary"]["entrance_approach_clear"]:
        print("[fancy] refusing render — entrance approach blocked")
        return 1
    if not result["summary"]["floor_deck_solid"]:
        print("[fancy] refusing render — floor decks not solid")
        return 1
    if not result["summary"].get("multi_floor_real", False):
        print("[fancy] refusing render — upper floors look like stubs (floor_cells)")
        return 1
    if result["summary"]["stair_count"] < 1:
        print("[fancy] refusing render — no stairs")
        return 1

    if args.render:
        if not _have_bpy():
            print(
                "bpy missing — run:\n"
                "  blender --background --python tools/build_fancy_manor.py -- --render"
            )
            return 2
        paths = render_inspection_views(result["assembly"])
        summary = result["summary"]
        summary["screenshots"] = paths
        REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[fancy] screenshots: {list(paths)}")
    return 0


if __name__ == "__main__":
    # Blender passes args after `--`
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    raise SystemExit(main(argv))

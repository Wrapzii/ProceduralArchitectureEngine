#!/usr/bin/env python3
"""Build a Georgian merchant townhouse in Blender from slider-like CLI params.

Uses ``pae.facade_grammar.build_from_params`` and ``pae.blender_build`` for
walkable floors/stairs with shared door/stair ids from ``pae.shared_ids``.

Usage::

    python tools/build_georgian_townhouse_blender.py --dry-run --export-json
    blender --background --python tools/build_georgian_townhouse_blender.py -- \\
        --seed 7 --frontage-m 10 --depth-m 8 --storeys 4 --wealth 3 \\
        --out Saved/georgian_townhouse/demo.blend --export-json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

DEFAULT_BLEND = PAE_ROOT / "Saved" / "georgian_townhouse" / "townhouse.blend"
DEFAULT_SUMMARY = PAE_ROOT / "Saved" / "georgian_townhouse" / "townhouse_summary.json"
COLLECTION = "PAE_GeorgianTownhouse"

# Workbench preview tints for shared material tokens (no bpy).
_PREVIEW_RGBA: Dict[str, Tuple[float, float, float, float]] = {
    "mat_cream_render": (0.88, 0.85, 0.78, 1.0),
    "mat_plaster_interior": (0.84, 0.82, 0.76, 1.0),
    "mat_slate": (0.32, 0.38, 0.52, 1.0),
    "mat_timber_oak": (0.55, 0.36, 0.22, 1.0),
    "mat_floor_board": (0.52, 0.40, 0.30, 1.0),
}


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def summarize_assembly(assembly, report, params) -> Dict[str, Any]:
    """Compact stats for CLI / JSON (pure, no bpy)."""
    from pae.facade_grammar import metres_to_bays, resolve_wealth
    from pae.shared_ids import resolve_shared

    wealth = resolve_wealth(params.wealth)
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    doors = [p for p in assembly.placements if "door" in p.asset_id]
    floors = [p for p in assembly.placements if p.kind == "floor"]
    bays_x = metres_to_bays(params.frontage_m) or 3
    bays_y = metres_to_bays(params.depth_m) or 2
    return {
        "archetype": params.archetype,
        "seed": params.seed,
        "bays_x": bays_x,
        "bays_y": bays_y,
        "storeys": params.storeys,
        "frontage_m": params.frontage_m,
        "depth_m": params.depth_m,
        "wealth": params.wealth,
        "resolved_wealth": wealth,
        "weathering": params.weathering,
        "lit_windows": params.lit_windows,
        "row_context": params.row_context,
        "placement_count": len(assembly.placements),
        "stair_count": len(stairs),
        "door_count": len(doors),
        "floor_count": len(floors),
        "report_ok": bool(report.ok),
        "critical_count": len(report.critical),
        "warning_count": len(report.warnings),
        "shared_door_id": resolve_shared("door", wealth, "main"),
        "shared_stair_id": resolve_shared("stair", wealth, "main"),
        "exterior_wall_mat": resolve_shared("material", wealth, "exterior_wall"),
        "interior_wall_mat": resolve_shared("material", wealth, "interior_wall"),
    }


def run_grammar(params, *, validate_assembly: bool = False):
    from pae.facade_grammar import build_from_params

    return build_from_params(params, mode="shell", validate_assembly=validate_assembly)


def preview_rgba_for_placement(asset_id: str, kind: str, wealth: int) -> Tuple[float, float, float, float]:
    from pae.shared_ids import resolve_shared

    if "door" in asset_id:
        token = resolve_shared("material", wealth, "trim")
    elif kind == "floor":
        token = resolve_shared("material", wealth, "floor")
    elif kind in ("stair",):
        token = resolve_shared("material", wealth, "trim")
    elif kind == "roof":
        token = resolve_shared("material", wealth, "roof")
    else:
        token = resolve_shared("material", wealth, "exterior_wall")
    return _PREVIEW_RGBA.get(token, _PREVIEW_RGBA["mat_cream_render"])


def apply_style_preview_materials(objects: Sequence[Any], wealth: int) -> int:
    """Tint instances — cream exterior, plaster/board interior floors."""
    if not _have_bpy():
        return 0
    from pae.blender_build import apply_material_base_color

    import bpy

    touched = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        asset_id = str(obj.get("pae_asset_id", ""))
        kind = str(obj.get("pae_kind", "wall"))
        rgba = preview_rgba_for_placement(asset_id, kind, wealth)
        mat_name = f"PAE_Georgian_{asset_id or kind}"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
        apply_material_base_color(mat, rgba)
        if obj.material_slots:
            obj.material_slots[0].material = mat
        elif obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        touched += 1
    return touched


def build_blender_scene(
    assembly,
    params,
    *,
    out_blend: Path,
    label: str = "georgian",
) -> Dict[str, Any]:
    """Instance assembly into Blender and save .blend."""
    from pae.blender_build import (
        CM_TO_M,
        assembly_bounds_cm,
        clear_pae_scene,
        configure_workbench_screenshot_scene,
        instance_facade_shell,
        reload_pae,
    )
    from pae.facade_grammar import resolve_wealth

    reloaded = reload_pae()
    if not _have_bpy():
        return {
            "ok": True,
            "blender": False,
            "reloaded": len(reloaded),
            "note": "bpy missing — grammar/assembly only",
        }

    import bpy

    clear_pae_scene()
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
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
    count = instance_facade_shell(
        assembly,
        label=label,
        target_coll=coll,
        offset_m=offset_m,
    )
    meshes = [o for o in coll.all_objects if o.type == "MESH"]
    for obj in meshes:
        for p in assembly.placements:
            if p.piece_id in obj.name:
                obj["pae_asset_id"] = p.asset_id
                obj["pae_kind"] = getattr(p, "kind", "wall")
                break
    wealth = resolve_wealth(params.wealth)
    mats_applied = apply_style_preview_materials(meshes, wealth)
    configure_workbench_screenshot_scene(bpy.context.scene)

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))

    return {
        "ok": True,
        "blender": True,
        "reloaded": len(reloaded),
        "collection": COLLECTION,
        "instances": count,
        "placements": len(assembly.placements),
        "materials_applied": mats_applied,
        "offset_m": offset_m,
        "blend": str(out_blend),
    }


def write_summary_json(
    summary: Dict[str, Any],
    params_json: str,
    path: Path,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "params": json.loads(params_json),
        "summary": summary,
    }
    if extra:
        payload["blender"] = extra
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def print_summary(
    summary: Dict[str, Any],
    *,
    report_ok: bool,
    out_path: Optional[Path] = None,
    json_path: Optional[Path] = None,
) -> None:
    print(
        "[georgian] "
        f"bays={summary['bays_x']}x{summary['bays_y']} "
        f"storeys={summary['storeys']} "
        f"placements={summary['placement_count']} "
        f"stairs={summary['stair_count']} "
        f"report.ok={report_ok}"
    )
    print(
        f"[georgian] shared door={summary['shared_door_id']} "
        f"stair={summary['shared_stair_id']} "
        f"row={summary['row_context']}"
    )
    if json_path:
        print(f"[georgian] params JSON -> {json_path}")
    if out_path:
        print(f"[georgian] blend -> {out_path}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1812)
    parser.add_argument("--archetype", default="georgian_merchant")
    parser.add_argument("--frontage-m", type=float, default=10.0)
    parser.add_argument("--depth-m", type=float, default=8.0)
    parser.add_argument("--storeys", type=int, default=2, help="0 = auto (3)")
    parser.add_argument(
        "--wealth",
        type=int,
        default=2,
        help="Wealth tier 1–5 (-1 = auto). Tiers ≥3 need wider footprints for switchback stairs",
    )
    parser.add_argument(
        "--weathering",
        type=float,
        default=-1.0,
        help="0–1 wear amount (-1 = auto from wealth)",
    )
    parser.add_argument("--lit-windows", type=float, default=0.4)
    parser.add_argument(
        "--row-context",
        choices=("freestanding", "end_left", "end_right", "mid"),
        default="freestanding",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_BLEND,
        help="Output .blend path (under Saved/)",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Write assembly summary JSON to Saved/georgian_townhouse/",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=DEFAULT_SUMMARY,
        help="Summary JSON path when --export-json is set",
    )
    parser.add_argument(
        "--strict-validate",
        action="store_true",
        help="Fail closed on assembly validation (default: assemble for demo preview)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Grammar + assemble only (no Blender file)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from pae.facade_grammar import FacadeParams, export_params_json

    args = parse_args(argv)
    params = FacadeParams(
        seed=args.seed,
        archetype=args.archetype,
        frontage_m=args.frontage_m,
        depth_m=args.depth_m,
        storeys=args.storeys,
        wealth=args.wealth,
        weathering=args.weathering,
        lit_windows=args.lit_windows,
        row_context=args.row_context,
    )

    _massing, _plan, assembly, report, _out = run_grammar(
        params, validate_assembly=args.strict_validate
    )
    summary = summarize_assembly(assembly, report, params)
    params_json = export_params_json(params)
    report_ok = bool(report.ok) and summary["placement_count"] > 0
    print_summary(
        summary,
        report_ok=report_ok,
        out_path=None if args.dry_run else args.out,
        json_path=args.summary_json if args.export_json else None,
    )

    if args.export_json:
        write_summary_json(summary, params_json, args.summary_json)

    if args.dry_run:
        if args.export_json:
            print(f"[georgian] dry-run summary -> {args.summary_json}")
        else:
            print("[georgian] dry-run complete (use --export-json to write summary)")
        return 0 if report_ok else 1

    if not _have_bpy():
        print(
            "bpy missing — run:\n"
            "  blender --background --python tools/build_georgian_townhouse_blender.py -- "
            f"--seed {args.seed} --out {args.out}"
        )
        return 2

    result = build_blender_scene(assembly, params, out_blend=args.out)
    if args.export_json:
        write_summary_json(summary, params_json, args.summary_json, extra=result)
    print_summary(
        summary,
        report_ok=report_ok,
        out_path=Path(result["blend"]),
        json_path=args.summary_json if args.export_json else None,
    )
    return 0 if report_ok and result.get("ok") else 1


if __name__ == "__main__":
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
    raise SystemExit(main(_argv))

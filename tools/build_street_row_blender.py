#!/usr/bin/env python3
"""Build an MMO street row (N townhouses along +X) in Blender.

Usage::

    python tools/build_street_row_blender.py --count 5 --dry-run
    blender --background --python tools/build_street_row_blender.py -- \\
        --count 5 --out Saved/street_row/row_5.blend --export-json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

DEFAULT_BLEND = PAE_ROOT / "Saved" / "street_row" / "street_row.blend"
DEFAULT_SUMMARY = PAE_ROOT / "Saved" / "street_row" / "street_row_summary.json"
COLLECTION = "PAE_StreetRow"


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def build_blender_scene(assembly, stats: Dict[str, Any], *, out_blend: Path) -> Dict[str, Any]:
    from pae.blender_build import (
        CM_TO_M,
        assembly_bounds_cm,
        clear_pae_scene,
        configure_workbench_screenshot_scene,
        instance_facade_shell,
        reload_pae,
    )
    from pae.facade_grammar import resolve_wealth
    from tools.build_georgian_townhouse_blender import apply_style_preview_materials

    import bpy

    reload_pae()
    clear_pae_scene()
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    else:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    bb_min, _bb_max = assembly_bounds_cm(assembly)
    offset_m = (
        -bb_min[0] * CM_TO_M,
        -bb_min[1] * CM_TO_M,
        -bb_min[2] * CM_TO_M,
    )
    count = instance_facade_shell(
        assembly,
        label="street_row",
        target_coll=coll,
        offset_m=offset_m,
    )
    meshes = [o for o in coll.all_objects if o.type == "MESH"]
    buildings = stats.get("buildings") or [{}]
    wealth = resolve_wealth(buildings[0].get("wealth", 2))
    mats_applied = apply_style_preview_materials(meshes, wealth)
    configure_workbench_screenshot_scene(bpy.context.scene)

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))

    return {
        "ok": True,
        "collection": COLLECTION,
        "instances": count,
        "placements": len(assembly.placements),
        "materials_applied": mats_applied,
        "blend": str(out_blend),
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="Townhouses along +X")
    parser.add_argument("--seed", type=int, default=1812)
    parser.add_argument("--frontage-m", type=float, default=10.0)
    parser.add_argument("--depth-m", type=float, default=8.0)
    parser.add_argument("--storeys", type=int, default=3)
    parser.add_argument("--wealth", type=int, default=2)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_BLEND,
        help="Output .blend path",
    )
    parser.add_argument("--export-json", action="store_true")
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--strict-validate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from pae.street_row import build_street_row

    args = parse_args(argv)
    assembly, report, stats = build_street_row(
        args.count,
        frontage_m=args.frontage_m,
        depth_m=args.depth_m,
        storeys=args.storeys,
        wealth=args.wealth,
        base_seed=args.seed,
        validate_assembly=args.strict_validate,
    )
    report_ok = bool(report.ok) and stats.get("placement_count", 0) > 0
    print(
        f"[street_row] count={args.count} "
        f"placements={stats.get('placement_count', 0)} "
        f"total_bays_x={stats.get('total_bays_x')} "
        f"report.ok={report_ok}"
    )
    for b in stats.get("buildings", []):
        print(
            f"  {b['name']}: ctx={b['row_context']} "
            f"seed={b['seed']} offset={b['cell_offset']}"
        )

    if args.export_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps({"stats": stats, "report_ok": report_ok}, indent=2),
            encoding="utf-8",
        )
        print(f"[street_row] summary -> {args.summary_json}")

    if args.dry_run:
        return 0 if report_ok else 1

    if not _have_bpy():
        print(
            "bpy missing — run:\n"
            "  blender --background --python tools/build_street_row_blender.py -- "
            f"--count {args.count} --out {args.out}"
        )
        return 2

    result = build_blender_scene(assembly, stats, out_blend=args.out)
    print(f"[street_row] blend -> {result['blend']}")
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

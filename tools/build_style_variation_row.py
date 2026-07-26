#!/usr/bin/env python3
"""Build a side-by-side wealth / seed variation row in Blender (shell path).

Uses ``pae.building_builder.build_building`` — three shells offset in X for
visual comparison (Wealth Sweep companion CLI).

Usage::

    python tools/build_style_variation_row.py --dry-run
    blender --background --python tools/build_style_variation_row.py -- \\
        --seed 42 --archetype georgian_merchant --wealths 1,3,5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

COLLECTION = "PAE_StyleVariationRow"
DEFAULT_SUMMARY = PAE_ROOT / "Saved" / "style_variation_row" / "row_summary.json"


def _have_bpy() -> bool:
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def parse_wealths(text: str) -> List[int]:
    out = []
    for part in text.split(","):
        part = part.strip()
        if part:
            out.append(max(1, min(5, int(part))))
    return out or [1, 3, 5]


def build_row(
    *,
    seed: int,
    archetype: str,
    wealths: Sequence[int],
    frontage_m: float,
    depth_m: float,
    storeys: int,
    row_context: str,
    gap_m: float = 4.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    from pae.building_builder import build_building
    from pae.facade_grammar import (
        FacadeParams,
        params_to_spec,
        params_to_style_overrides,
        party_wall_faces,
    )
    from pae.facade_shell import (
        count_chimney_stubs,
        count_opening_cutters,
        derive_shell_variation,
    )
    from pae.facade_grammar import load_archetype_shell_config

    entries: List[Dict[str, Any]] = []
    offset_x_m = 0.0

    for idx, wealth in enumerate(wealths):
        params = FacadeParams(
            seed=int(seed) + idx,
            archetype=archetype,
            frontage_m=frontage_m,
            depth_m=depth_m,
            storeys=storeys,
            wealth=wealth,
            row_context=row_context,
        )
        _m, _p, assembly, report, _out = build_building(params, validate_assembly=False)
        spec = params_to_spec(params)
        shell_cfg = load_archetype_shell_config(archetype, wealth=wealth)
        style_overrides = params_to_style_overrides(params)
        glazed = tuple(
            f
            for f in ("south", "north", "east", "west")
            if f not in party_wall_faces(row_context)
        )
        variation = derive_shell_variation(
            params,
            bays_x=spec.footprint.bays_x,
            bays_y=spec.footprint.bays_y,
            storeys=spec.storeys,
            glazed_faces=glazed,
            style_overrides=style_overrides,
            shell_cfg=shell_cfg,
        )
        entries.append(
            {
                "seed": params.seed,
                "wealth": wealth,
                "door_bay": variation.door_bay,
                "chimney_count": count_chimney_stubs(assembly),
                "south_cutters": count_opening_cutters(assembly, "south"),
                "placements": len(assembly.placements),
                "offset_x_m": offset_x_m,
                "report_ok": bool(report.ok),
            }
        )
        if not dry_run and _have_bpy():
            from pae.blender_build import CM_TO_M, assembly_bounds_cm, instance_facade_shell
            import bpy

            coll = bpy.data.collections.get(COLLECTION)
            if coll is None:
                coll = bpy.data.collections.new(COLLECTION)
                bpy.context.scene.collection.children.link(coll)
            bb_min, bb_max = assembly_bounds_cm(assembly)
            width_m = (bb_max[0] - bb_min[0]) * CM_TO_M
            offset_m = (
                offset_x_m - bb_min[0] * CM_TO_M,
                -bb_min[1] * CM_TO_M,
                -bb_min[2] * CM_TO_M,
            )
            instance_facade_shell(
                assembly,
                label=f"w{wealth}_s{params.seed}",
                target_coll=coll,
                offset_m=offset_m,
            )
            offset_x_m += width_m + gap_m

    return {"archetype": archetype, "base_seed": seed, "entries": entries}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PAE shell wealth/seed variation row")
    parser.add_argument("--seed", type=int, default=1812)
    parser.add_argument("--archetype", default="georgian_merchant")
    parser.add_argument("--wealths", default="1,3,5", help="Comma-separated wealth tiers")
    parser.add_argument("--frontage-m", type=float, default=10.0)
    parser.add_argument("--depth-m", type=float, default=8.0)
    parser.add_argument("--storeys", type=int, default=3)
    parser.add_argument("--row-context", default="freestanding")
    parser.add_argument("--gap-m", type=float, default=4.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_row(
        seed=args.seed,
        archetype=args.archetype,
        wealths=parse_wealths(args.wealths),
        frontage_m=args.frontage_m,
        depth_m=args.depth_m,
        storeys=args.storeys,
        row_context=args.row_context,
        gap_m=args.gap_m,
        dry_run=args.dry_run or not _have_bpy(),
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

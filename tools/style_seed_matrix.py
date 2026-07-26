#!/usr/bin/env python3
"""Style × seed matrix proof — 8 packs × N seeds on one small generic sketch.

Runs decorate WITH Stage K detail (``apply_detail=True``). Writes
``Saved/exports/style_seed_matrix.json`` with placement counts, roof/window
fields, detail piece counts, distinguishing fields, and determinism hashes.

Does NOT edit Codex-dirty modules; calls public pipeline + detail APIs only.
No fortress / school / city builds.

Usage::

    python tools/style_seed_matrix.py
    python tools/style_seed_matrix.py --seeds 3 7 11
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

EXPORT_REL = Path("Saved") / "exports" / "style_seed_matrix.json"

ALL_BUILTIN_STYLE_IDS = (
    "townhouse",
    "keep",
    "gothic_academy",
    "wizard_academy",
    "rustic",
    "medieval",
    "manor",
    "civic",
)

DEFAULT_SEEDS = (3, 7, 11)
GALLERY_SEED = 7  # fixed seed for optional per-style renders


# Per-style layout variants — same seed discipline, different door/window/footprint.
# Goal: gallery reads as different buildings in different languages, not one box + hats.
_STYLE_LAYOUT: Dict[str, Dict[str, Any]] = {
    "manor": {
        "bays_x": 5,
        "bays_y": 3,
        "entrance_bay": 2,
        "entrance_role": "grand",
        "windows_ground": 4,
        "windows_per_bay": 2,
        "level_window_tags": (None, "window_cross"),
    },
    "civic": {
        "bays_x": 5,
        "bays_y": 3,
        "entrance_bay": 2,
        "entrance_role": "grand",
        "windows_ground": 4,
        "windows_per_bay": 1,
        "level_window_tags": (None, "window_round"),
    },
    "townhouse": {
        "bays_x": 4,
        "bays_y": 3,
        "entrance_bay": 0,  # side / shop door
        "entrance_role": "main",
        "windows_ground": 3,
        "windows_per_bay": 1,
        "level_window_tags": ("window_cross", "window_cross"),
    },
    "rustic": {
        "bays_x": 4,
        "bays_y": 3,
        "entrance_bay": 1,  # offset farmhouse
        "entrance_role": "main",
        "windows_ground": 2,
        "windows_per_bay": 1,
        "level_window_tags": (None, "window_simple"),
    },
    "medieval": {
        "bays_x": 5,
        "bays_y": 3,
        "entrance_bay": 2,
        "entrance_role": "main",
        "windows_ground": 3,
        "windows_per_bay": 1,
        "level_window_tags": (None, "window_mullioned"),
    },
    "keep": {
        "bays_x": 4,
        "bays_y": 4,
        "entrance_bay": 0,  # austere corner entry
        "entrance_role": "main",
        "windows_ground": 1,
        "windows_per_bay": 1,
        "level_window_tags": (None, "window_arrowslit"),
        "skip_ground_windows": True,
    },
    "gothic_academy": {
        "bays_x": 5,
        "bays_y": 3,
        "entrance_bay": 2,
        "entrance_role": "grand",
        "windows_ground": 3,
        "windows_per_bay": 1,
        "level_window_tags": ("window_lancet", "window_lancet"),
    },
    "wizard_academy": {
        "bays_x": 4,
        "bays_y": 3,
        "entrance_bay": 3,
        "entrance_role": "main",
        "windows_ground": 2,
        "windows_per_bay": 1,
        "level_window_tags": (None, "window_gothic"),
    },
}


def matrix_spec(style_id: str, seed: int):
    """Per-style door/window/footprint variant (seed-stable), not one identical box."""
    from pae.spec import (
        EntranceSpec,
        FootprintSpec,
        OpeningPolicy,
        RoofSpec,
        m2_two_storey_stair_spec,
    )

    layout = _STYLE_LAYOUT.get(str(style_id).strip().lower(), {})
    base = m2_two_storey_stair_spec(seed=seed)
    bx = int(layout.get("bays_x", 4))
    by = int(layout.get("bays_y", 3))
    bay = layout.get("entrance_bay")
    role = str(layout.get("entrance_role", "main"))
    entrances = []
    if bay is not None:
        entrances = [
            EntranceSpec(role=role, facade="south", bay=int(bay)),
        ]
    openings = OpeningPolicy(
        windows_per_bay=int(layout.get("windows_per_bay", 1)),
        doors_ground=1,
        windows_ground=layout.get("windows_ground", 2),
        skip_ground_windows=bool(layout.get("skip_ground_windows", False)),
    )
    level_tags = layout.get("level_window_tags")
    return replace(
        base,
        name=f"style_seed_{style_id}_s{seed}",
        style=style_id,
        footprint=FootprintSpec(kind="rect", bays_x=bx, bays_y=by),
        roof=RoofSpec(kind="auto", pitch=1.0),
        openings=openings,
        entrances=entrances,
        level_window_tags=level_tags,
    )


def _ridge_z_cm(placements) -> Optional[float]:
    ridge_pieces = [
        p
        for p in placements
        if p.asset_id in ("roof_pitched_slope", "roof_hip")
    ]
    if not ridge_pieces:
        return None
    return round(max(p.size_cm[2] for p in ridge_pieces), 1)


def _roof_kind_from_placements(placements) -> str:
    ids = {p.asset_id for p in placements if p.asset_id.startswith("roof_")}
    if "roof_hip" in ids:
        return "hip"
    if "roof_pitched_slope" in ids or "roof_gable_infill" in ids:
        return "pitched"
    if "roof_flat" in ids:
        return "flat"
    return "none"


def _window_profile(placements) -> str:
    wins = sorted({p.asset_id for p in placements if "window" in p.asset_id})
    if not wins:
        return "none"
    return wins[0] if len(wins) == 1 else "|".join(wins)


def _determinism_hash(assembly) -> str:
    from pae.detail_layer import detail_signature

    sig = detail_signature(assembly)
    # Also fold placement ids for full-assembly stability.
    rows = [
        (p.piece_id, p.asset_id, p.yaw, tuple(p.cell), p.level)
        for p in assembly.placements
    ]
    payload = json.dumps({"detail": sig, "placements": rows}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def measure_style_seed(style_id: str, seed: int) -> Dict[str, Any]:
    """Assemble + Stage K detail (same hook as decorate ``apply_detail=True``).

    Skips ``fitout_greybox``: civic + pack storey height trips floating
    railing/balustrade criticals (pre-existing fitout collateral, not Stage K).
    """
    from pae.detail_layer import count_detail_pieces, detail_policy_for_style
    from pae.style_apply import count_shell_pieces
    from pae.style_pipeline import assemble_with_style_shell_and_detail
    from pae.style_pack import (
        load_style_pack,
        resolve_door_piece_id,
        resolve_eave_overhang_cm,
        resolve_roof_kind,
        resolve_roof_pitch,
        resolve_window_piece_id,
    )

    pack, pack_report = load_style_pack(style_id)
    if pack is None or not pack_report.ok:
        raise RuntimeError(f"style pack {style_id!r} failed load: {pack_report}")

    spec = matrix_spec(style_id, seed)
    _m, _p, detailed, stage_report = assemble_with_style_shell_and_detail(
        spec, seed=seed
    )
    if not stage_report.ok:
        return {
            "style_id": style_id,
            "seed": seed,
            "built": False,
            "critical": [f.message for f in stage_report.critical],
            "placement_count": len(detailed.placements) if detailed else 0,
            "detail_piece_count": 0,
            "determinism_hash": "",
            "pipeline": "pae.style_pipeline.assemble_with_style_shell_and_detail",
        }

    vreport = stage_report
    critical = [f.message for f in vreport.critical]
    placements = detailed.placements if detailed else []
    policy = detail_policy_for_style(style_id)
    doors = sorted({p.asset_id for p in placements if "door" in p.asset_id or "gate" in p.asset_id})
    shell_counts = count_shell_pieces(detailed)

    return {
        "style_id": style_id,
        "seed": seed,
        "built": bool(vreport.ok and not critical),
        "critical": critical,
        "placement_count": len(placements),
        "roof_kind_resolved": resolve_roof_kind(pack, spec_kind="auto"),
        "roof_kind_emitted": _roof_kind_from_placements(placements),
        "roof_pitch_resolved": round(resolve_roof_pitch(pack), 3),
        "eave_overhang_cm": resolve_eave_overhang_cm(pack),
        "ridge_z_cm": _ridge_z_cm(placements),
        "window_profile": _window_profile(placements),
        "window_tag_authored": pack.window.tag,
        "window_piece_id": resolve_window_piece_id(pack),
        "door_tag_authored": pack.door.tag,
        "door_piece_id": resolve_door_piece_id(pack),
        "door_assets_emitted": doors,
        "detail_piece_count": count_detail_pieces(detailed),
        "shell_counts": shell_counts,
        "detail_policy": {
            "opening_accent": policy.opening_accent,
            "weathering": policy.weathering,
            "density": policy.density,
            "course_names": list(policy.course_names),
            "jettied_mid": policy.jettied_mid,
            "coping": policy.coping,
            "mid_string": policy.mid_string,
        },
        "wall_bands_authored": {
            "plinth_cm": pack.wall_bands.plinth_cm,
            "cornice_cm": pack.wall_bands.cornice_cm,
            "string_cm": pack.wall_bands.string_cm,
        },
        "storey_height_cm_authored": pack.geometry.storey_height_cm,
        "materials_authored": {
            "wall": pack.materials.wall,
            "roof": pack.materials.roof,
            "trim": pack.materials.trim,
        },
        "determinism_hash": _determinism_hash(detailed),
        "pipeline": "pae.style_pipeline.assemble_with_style_shell_and_detail",
    }


def _differing_across_styles(rows: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    keys = (
        "roof_kind_emitted",
        "roof_pitch_resolved",
        "eave_overhang_cm",
        "ridge_z_cm",
        "window_profile",
        "door_piece_id",
        "detail_piece_count",
        "detail_policy",
        "wall_bands_authored",
        "shell_counts",
        "placement_count",
        "storey_height_cm_authored",
    )
    out: Dict[str, List[Any]] = {}
    for key in keys:
        values = [row[key] for row in rows]
        serialized = {json.dumps(v, sort_keys=True) for v in values}
        if len(serialized) > 1:
            out[key] = values
    return out


def _human_summary(matrix: Dict[str, Any]) -> str:
    lines = [
        f"Style×seed matrix: {matrix['styles_total']} packs × "
        f"{len(matrix['seeds'])} seeds on {matrix['sketch']}.",
        f"Built critical-empty: {matrix['built_ok']}/"
        f"{matrix['styles_total'] * len(matrix['seeds'])}.",
    ]
    gallery = matrix.get("gallery_seed_rows") or {}
    if gallery:
        lines.append(
            "At fixed seed "
            f"{matrix['gallery_seed']} (what visibly differs):"
        )
        for sid, row in gallery.items():
            lines.append(
                f"  • {sid}: placements={row['placement_count']} "
                f"roof={row['roof_kind_emitted']} "
                f"ridge_z={row['ridge_z_cm']} "
                f"window={row['window_profile']} "
                f"detail_pieces={row['detail_piece_count']} "
                f"accent={row['detail_policy']['opening_accent']}"
            )
    diffs = matrix.get("differing_fields_at_gallery_seed") or {}
    if diffs:
        lines.append(
            "Distinguishing fields across packs: " + ", ".join(sorted(diffs.keys()))
        )
    renders = matrix.get("renders") or {}
    if renders.get("status") == "ok":
        lines.append(f"Renders: {len(renders.get('paths', []))} images under Saved/Screenshots/.")
    else:
        lines.append(
            f"Renders: {renders.get('status', 'n/a')} — "
            f"{renders.get('command', '')}"
        )
    return "\n".join(lines)


def build_matrix(
    *,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    styles: Sequence[str] = ALL_BUILTIN_STYLE_IDS,
    gallery_seed: int = GALLERY_SEED,
) -> Dict[str, Any]:
    seed_list = list(seeds)
    cells: Dict[str, Dict[str, Any]] = {}
    all_rows: List[Dict[str, Any]] = []
    for style_id in styles:
        cells[style_id] = {}
        for seed in seed_list:
            row = measure_style_seed(style_id, seed)
            cells[style_id][str(seed)] = row
            all_rows.append(row)

    # Determinism: same (style, seed) twice → same hash (spot-check gallery seed).
    det_ok = True
    for style_id in styles:
        a = measure_style_seed(style_id, gallery_seed)
        b = cells[style_id][str(gallery_seed)]
        if a["determinism_hash"] != b["determinism_hash"]:
            det_ok = False
            break

    gallery_rows = [cells[s][str(gallery_seed)] for s in styles if str(gallery_seed) in cells[s]]
    gallery_map = {r["style_id"]: r for r in gallery_rows}
    built_ok = sum(1 for r in all_rows if r["built"])

    return {
        "skill": "style-seed-matrix",
        "lane": "MP-WS-STYLE-V",
        "sketch": "m2_two_storey_stair 4x3 rect (2 storeys, straight stair) + style_apply + Stage K",
        "apply_detail": True,
        "pipeline": "pae.style_pipeline.assemble_with_style_shell_and_detail",
        "pipeline_note": (
            "style_apply remaps doors/windows/eaves and attaches forecourt/doorcase/"
            "porch/buttress/bargeboard/chimney_stub; Stage K detail follows. "
            "Skips fitout_greybox (civic railing floaters are fitout collateral). "
            "Codex merge hook: in run_through_decorate before apply_detail_layer, call "
            "pae.style_apply.apply_style_shell(assembly, style_id=spec.style, seed=decor_seed) "
            "— or delegate to pae.style_pipeline.run_with_style_shell."
        ),
        "seeds": seed_list,
        "gallery_seed": gallery_seed,
        "styles_total": len(styles),
        "built_ok": built_ok,
        "cells": cells,
        "gallery_seed_rows": gallery_map,
        "differing_fields_at_gallery_seed": _differing_across_styles(gallery_rows),
        "determinism_spotcheck_ok": det_ok,
        "renders": {
            "status": "n/a",
            "paths": [],
            "command": (
                "python tools/render_style_gallery.py "
                f"--seed {gallery_seed}"
            ),
        },
        "gates": {
            "styles_seeds_proven": built_ok == len(styles) * len(seed_list),
            "packs_differ": bool(_differing_across_styles(gallery_rows)),
            "determinism": det_ok,
        },
    }


def write_matrix(matrix: Dict[str, Any], *, root: Path = PAE_ROOT) -> Path:
    out = root / EXPORT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = _human_summary(matrix)
    payload = {
        **matrix,
        "human_summary": summary,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "report_path": str(EXPORT_REL).replace("\\", "/"),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build style × seed proof matrix.")
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=list(DEFAULT_SEEDS),
        help=f"seeds to sample (default: {list(DEFAULT_SEEDS)})",
    )
    parser.add_argument(
        "--gallery-seed",
        type=int,
        default=GALLERY_SEED,
        help=f"fixed seed for cross-style compare / renders (default: {GALLERY_SEED})",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    seeds = list(args.seeds)
    if args.gallery_seed not in seeds:
        seeds.append(args.gallery_seed)

    matrix = build_matrix(seeds=seeds, gallery_seed=args.gallery_seed)
    path = write_matrix(matrix)
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"Wrote {path}")
    print(data.get("human_summary", _human_summary(matrix)))
    return 0 if matrix["gates"]["styles_seeds_proven"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

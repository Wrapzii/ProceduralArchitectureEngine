#!/usr/bin/env python3
"""Write Saved/exports/style_variance_report.json — STYLE-V acceptance evidence.

Builds the same M2 sketch × 8 packs at a fixed seed through
``assemble → style_apply → detail_layer``, then asserts packs differ on
≥4 independent silhouette axes (door, roof, proportion, trim/shell, …).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

from tools.style_seed_matrix import (  # noqa: E402
    ALL_BUILTIN_STYLE_IDS,
    GALLERY_SEED,
    measure_style_seed,
)

EXPORT_REL = Path("Saved") / "exports" / "style_variance_report.json"


def _silhouette_signature(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "height_proxy_cm": row.get("storey_height_cm_authored"),
        "roof_kind": row.get("roof_kind_emitted"),
        "roof_pitch": row.get("roof_pitch_resolved"),
        "ridge_z_cm": row.get("ridge_z_cm"),
        "eave_overhang_cm": row.get("eave_overhang_cm"),
        "door_id": row.get("door_piece_id"),
        "window_id": row.get("window_piece_id") or row.get("window_profile"),
        "plinth_cm": (row.get("wall_bands_authored") or {}).get("plinth_cm"),
        "cornice_cm": (row.get("wall_bands_authored") or {}).get("cornice_cm"),
        "shell_keys": sorted((row.get("shell_counts") or {}).keys()),
        "detail_jetty": (row.get("detail_policy") or {}).get("jettied_mid"),
        "detail_coping": (row.get("detail_policy") or {}).get("coping"),
    }


def _axis_sets(rows: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    axes: Dict[str, Set[str]] = {
        "door": set(),
        "roof_kind": set(),
        "roof_pitch": set(),
        "proportion_storey": set(),
        "window": set(),
        "plinth": set(),
        "eave": set(),
        "shell": set(),
        "detail_family": set(),
    }
    for row in rows:
        axes["door"].add(str(row.get("door_piece_id")))
        axes["roof_kind"].add(str(row.get("roof_kind_emitted")))
        axes["roof_pitch"].add(str(row.get("roof_pitch_resolved")))
        axes["proportion_storey"].add(str(row.get("storey_height_cm_authored")))
        axes["window"].add(str(row.get("window_profile")))
        axes["plinth"].add(str((row.get("wall_bands_authored") or {}).get("plinth_cm")))
        axes["eave"].add(str(row.get("eave_overhang_cm")))
        axes["shell"].add(json.dumps(row.get("shell_counts") or {}, sort_keys=True))
        pol = row.get("detail_policy") or {}
        axes["detail_family"].add(
            f"{pol.get('jettied_mid')}|{pol.get('coping')}|{pol.get('mid_string')}|"
            f"{pol.get('opening_accent')}"
        )
    return axes


def build_report(*, seed: int = GALLERY_SEED) -> Dict[str, Any]:
    rows = [measure_style_seed(sid, seed) for sid in ALL_BUILTIN_STYLE_IDS]
    axes = _axis_sets(rows)
    differing = {k: sorted(v) for k, v in axes.items() if len(v) >= 2}
    independent = len(differing)
    per_pack = {}
    for row in rows:
        per_pack[row["style_id"]] = {
            "roof_kind": row.get("roof_kind_emitted"),
            "roof_pitch": row.get("roof_pitch_resolved"),
            "storey_cm": row.get("storey_height_cm_authored"),
            "door_piece_id": row.get("door_piece_id"),
            "door_assets_emitted": row.get("door_assets_emitted"),
            "window_piece_id": row.get("window_piece_id"),
            "window_profile": row.get("window_profile"),
            "plinth_cm": (row.get("wall_bands_authored") or {}).get("plinth_cm"),
            "cornice_cm": (row.get("wall_bands_authored") or {}).get("cornice_cm"),
            "eave_overhang_cm": row.get("eave_overhang_cm"),
            "detail_counts": row.get("detail_piece_count"),
            "shell_counts": row.get("shell_counts"),
            "silhouette_signature": _silhouette_signature(row),
            "built": row.get("built"),
            "critical": row.get("critical"),
        }

    return {
        "skill": "style-variance",
        "lane": "MP-WS-STYLE-V",
        "seed": seed,
        "packs_total": len(ALL_BUILTIN_STYLE_IDS),
        "independent_axes": independent,
        "differing_axes": differing,
        "per_pack": per_pack,
        "gates": {
            "style_variance_strong": independent >= 4,
            "door_differs": len(axes["door"]) >= 3,
            "roof_differs": len(axes["roof_kind"]) >= 2 or len(axes["roof_pitch"]) >= 3,
            "proportion_differs": len(axes["proportion_storey"]) >= 4,
            "shell_differs": len(axes["shell"]) >= 3,
            "packs_emitted": all(r.get("placement_count", 0) > 0 for r in rows),
        },
        "hook_suggestion": (
            "Codex merge: in run_through_decorate before apply_detail_layer, call "
            "pae.style_apply.apply_style_shell(assembly, style_id=spec.style, seed=decor_seed) "
            "— clean interim: pae.style_pipeline.run_with_style_shell / "
            "assemble_with_style_shell_and_detail."
        ),
    }


def write_report(report: Dict[str, Any], *, root: Path = PAE_ROOT) -> Path:
    out = root / EXPORT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {**report, "generated_utc": datetime.now(timezone.utc).isoformat()}
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    report = build_report()
    path = write_report(report)
    print(f"Wrote {path}")
    print(
        f"independent_axes={report['independent_axes']} "
        f"doors={len(report['differing_axes'].get('door', []))} "
        f"gates={report['gates']}"
    )
    return 0 if report["gates"]["style_variance_strong"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

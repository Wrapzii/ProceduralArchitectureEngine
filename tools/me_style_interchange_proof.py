"""M-E style interchange proof — same sketch × eight style packs.

Builds a modest two-storey 4×3 rect (M2 footprint) with ``roof.kind=auto`` so each
pack's default roof kind and window profile apply. Writes
``Saved/exports/me_style_interchange_report.json``.

Usage::

    python tools/me_style_interchange_proof.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

EXPORT_REL = Path("Saved") / "exports" / "me_style_interchange_report.json"

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

# Cheap interchange sketch — M2 footprint, not fortress/city scale.
INTERCHANGE_SEED = 7


def interchange_spec(style_id: str):
    """Same 4×3 two-storey rect; only ``style`` (and auto roof) changes."""
    from pae.spec import RoofSpec, m2_two_storey_stair_spec

    return replace(
        m2_two_storey_stair_spec(seed=INTERCHANGE_SEED),
        name=f"me_interchange_{style_id}",
        style=style_id,
        roof=RoofSpec(kind="auto", pitch=1.0),
    )


def _ridge_z_cm(placements) -> Optional[float]:
    """Top Z of pitched slope or hip ridge proxy (``size_cm[2]``)."""
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


def measure_pack(style_id: str) -> Dict[str, Any]:
    from pae.pipeline import run_through_assemble
    from pae.style_pack import (
        load_style_pack,
        resolve_roof_kind,
        resolve_roof_pitch,
    )
    from pae.validate import validate

    pack, pack_report = load_style_pack(style_id)
    if pack is None or not pack_report.ok:
        raise RuntimeError(f"style pack {style_id!r} failed load: {pack_report}")

    spec = interchange_spec(style_id)
    _massing, _plan, assembly, stage_report = run_through_assemble(spec)
    _, vreport = validate(assembly)
    critical = [f.message for f in vreport.critical]

    placements = assembly.placements if assembly else []
    resolved_kind = resolve_roof_kind(pack, spec_kind="auto")
    resolved_pitch = resolve_roof_pitch(pack, spec_pitch=spec.roof.pitch)
    emitted_kind = _roof_kind_from_placements(placements)

    return {
        "style_id": style_id,
        "built": stage_report.ok and not critical,
        "critical": critical,
        "placement_count": len(placements),
        "roof_kind_resolved": resolved_kind,
        "roof_kind_emitted": emitted_kind,
        "roof_pitch_resolved": round(resolved_pitch, 3),
        "ridge_z_cm": _ridge_z_cm(placements),
        "window_profile": _window_profile(placements),
        "window_tag_authored": pack.window.tag,
        "wall_bands_authored": {
            "plinth_cm": pack.wall_bands.plinth_cm,
            "cornice_cm": pack.wall_bands.cornice_cm,
        },
        "storey_height_cm_authored": pack.geometry.storey_height_cm,
        "materials_authored": {
            "wall": pack.materials.wall,
            "roof": pack.materials.roof,
            "trim": pack.materials.trim,
        },
    }


def _differing_fields(per_pack: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    keys = (
        "roof_kind_resolved",
        "roof_kind_emitted",
        "roof_pitch_resolved",
        "ridge_z_cm",
        "window_profile",
        "wall_bands_authored",
    )
    out: Dict[str, List[Any]] = {}
    for key in keys:
        values = [row[key] for row in per_pack]
        if len({json.dumps(v, sort_keys=True) for v in values}) > 1:
            out[key] = values
    return out


def unconsumed_pack_fields() -> Dict[str, str]:
    """Authored pack fields not yet wired into assemble geometry (honest audit)."""
    return {
        "geometry.wall_thickness_cm": (
            "Schema slot exists; no pack sets it; assemble uses WALL_T_CM."
        ),
        "materials.wall / roof / trim": (
            "Authored per pack; export maps kind/tags to material_slot (MI_*) "
            "via pae.export.materials — UE assigns real MIs (no baked textures)."
        ),
        "tower.cap / crown / finial": (
            "Consumed only when towers are present; interchange sketch has none."
        ),
        "shell.* via style_apply": (
            "Consumed by pae.style_apply.apply_style_shell (gallery/matrix path). "
            "decorate/pipeline still dirty — hook suggestion in style_variance_report."
        ),
    }


def build_report() -> Dict[str, Any]:
    per_pack = [measure_pack(sid) for sid in ALL_BUILTIN_STYLE_IDS]
    built = sum(1 for row in per_pack if row["built"])
    return {
        "skill": "me-style-interchange",
        "milestone": "M-E",
        "lane": "MP-WS6b",
        "sketch": "m2_two_storey_stair 4x3 rect (2 storeys, straight stair)",
        "seed": INTERCHANGE_SEED,
        "roof_spec": "auto",
        "packs_total": len(ALL_BUILTIN_STYLE_IDS),
        "packs_built_critical_empty": built,
        "per_pack": {row["style_id"]: row for row in per_pack},
        "differing_fields": _differing_fields(per_pack),
        "unconsumed_pack_fields": unconsumed_pack_fields(),
        "gates": {
            "m_e_interchange": built == len(ALL_BUILTIN_STYLE_IDS),
            "packs_differ": bool(_differing_fields(per_pack)),
        },
    }


def write_report(report: Dict[str, Any]) -> Path:
    out = PAE_ROOT / EXPORT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **report,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    report = build_report()
    path = write_report(report)
    gates = report["gates"]
    print(
        f"me_style_interchange: built={report['packs_built_critical_empty']}/"
        f"{report['packs_total']} differ={gates['packs_differ']} "
        f"report={path.relative_to(PAE_ROOT)}"
    )
    return 0 if gates["m_e_interchange"] and gates["packs_differ"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

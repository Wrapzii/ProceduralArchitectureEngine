"""City street sample — RE game town block via PAE sketches + specs.

A walkable street corridor with commerce (1/2/3-storey), market hall, inn,
residential longhouse, and a noble manor with corner towers.  Every building is
assembled through the existing PAE pipeline (sketch_to_spec / BuildingSpec →
decorate → validate) and must pass per-building validation before merge.

    python -c "from pae.city_street_sample import report; report()"
    blender --background --python tools/build_city_street_sample_blender.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pae.contract import MODULE_CM, STOREY_CM

# --- sketches (PAE sketch grid: # built, E entrance, S stair, T tower) --------

SHOP_1 = """
######
######
"""

SHOP_2 = """
######
######
######
####S##
######
"""

SHOP_3 = """
########
########
########
####S###
########
"""

MARKET_HALL = """
########
########
########
"""

INN = """
#######
#######
#######
####S##
#######
#######
"""

LONGHOUSE = """
#########
#########
#########
####S####
#########
"""

# Game remembrance (Docs/STYLE_AND_DETAIL_ROADMAP.md, pae/styles/*.json):
# Medieval / anime-fantasy wizarding-school town — timber-framed + stone ranges,
# terracotta tile roofs, slate tower caps, warm plaster/stone walls.


@dataclass(frozen=True)
class StreetLot:
    """One lot on the street grid."""

    name: str
    building_type: str  # commerce_1 | commerce_2 | commerce_3 | market | inn | residential | noble
    storeys: int
    cell_offset: Tuple[int, int]
    # Exactly one of sketch-driven or spec-driven:
    sketch: str = ""
    style: str = "townhouse"
    seed: int = 1
    # Optional BuildingSpec factory name (resolved in _build_lot)
    spec_factory: str = ""


def street_lots() -> List[StreetLot]:
    """Composer lane — entire **north** frontage (+Y), facing the E–W street.

    One agent per side of the road (not west/east). Matching X columns face
    Grok lots on the south (`city_street_sample_opposite.opposite_lots`).
    X starts leave ≥1 empty bay between footprints (sketch max widths).
    """
    y_n = 8
    return [
        StreetLot("shop_1storey", "commerce_1", 1, (0, y_n), SHOP_1, "townhouse", 11),
        StreetLot("shop_2storey", "commerce_2", 2, (7, y_n), SHOP_2, "townhouse", 12),
        # SHOP_2 max width is 7 (stair row); leave a bay before shop_3
        StreetLot("shop_3storey", "commerce_3", 3, (15, y_n), SHOP_3, "keep", 13),
        StreetLot("market_hall", "market", 1, (24, y_n), MARKET_HALL, "civic", 21),
        StreetLot("inn", "inn", 2, (33, y_n), INN, "townhouse", 22),
        StreetLot(
            "longhouse_res",
            "residential",
            2,
            (41, y_n),
            LONGHOUSE,
            "medieval",
            31,
        ),
        StreetLot("shop_corner", "commerce_2", 2, (51, y_n), SHOP_2, "medieval", 32),
        StreetLot(
            "noble_manor",
            "noble",
            4,
            (59, y_n),
            spec_factory="noble_manor_spec",
            style="manor",
            seed=42,
        ),
    ]


def noble_manor_spec():
    """Grand manor — larger footprint, corner towers, steep pitched roof."""
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        OpeningPolicy,
        RoofSpec,
        TowerSpec,
    )

    return BuildingSpec(
        name="noble_manor",
        style="manor",
        footprint=FootprintSpec(kind="rect", bays_x=7, bays_y=5),
        storeys=4,
        storey_use=["hall"] * 4,
        towers=[
            TowerSpec(cell=(0, 0), storeys=4),
            TowerSpec(cell=(6, 4), storeys=5),
        ],
        roof=RoofSpec(kind="pitched", pitch=1.7),
        circulation=CirculationSpec(stair_kind="wide", stair_cells=[(2, 2)]),
        openings=OpeningPolicy(
            windows_per_bay=2,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=42,
        ground_slab=True,
    )


_SPEC_FACTORIES = {
    "noble_manor_spec": noble_manor_spec,
}


def _register_opposite_factories() -> None:
    """Merge opposite-lane noble spec without requiring callers to import it first."""
    try:
        from pae.city_street_sample_opposite import OPPOSITE_SPEC_FACTORIES
    except ImportError:
        return
    for key, factory in OPPOSITE_SPEC_FACTORIES.items():
        _SPEC_FACTORIES.setdefault(key, factory)


def lots_for_side(side: str = "both") -> List[StreetLot]:
    """Return lots for ``original`` | ``opposite`` | ``both`` (default both)."""
    side_n = (side or "both").strip().lower()
    if side_n not in ("original", "opposite", "both"):
        raise ValueError(f"side must be original|opposite|both, got {side!r}")
    _register_opposite_factories()
    original = street_lots()
    if side_n == "original":
        return original
    from pae.city_street_sample_opposite import opposite_lots

    opposite = opposite_lots()
    if side_n == "opposite":
        return opposite
    # both — additive; never drop the first side's buildings
    return list(original) + list(opposite)


def _footprint_bays(lot: StreetLot) -> Tuple[int, int]:
    if lot.spec_factory:
        spec = _SPEC_FACTORIES[lot.spec_factory]()
        return spec.footprint.bays_x, spec.footprint.bays_y
    rows = [r for r in lot.sketch.strip().splitlines() if r.strip()]
    if not rows:
        return 0, 0
    return len(rows[0]), len(rows)


def _with_style_tag(assembly, style: str):
    """Tag placements so kit dress can pick stone/timber/plaster per lot."""
    from dataclasses import replace

    tag = f"style:{style}"
    tagged = [
        replace(p, tags=p.tags | frozenset({tag})) for p in assembly.placements
    ]
    return replace(assembly, placements=tagged)


def _build_lot(lot: StreetLot, seed_offset: int = 0):
    """Assemble one lot (assemble + validate only — no decorate trim/banding)."""
    from pae.pipeline import run_through_assemble
    from pae.sketch import sketch_to_spec
    from pae.validate import validate

    if lot.spec_factory:
        factory = _SPEC_FACTORIES.get(lot.spec_factory)
        if factory is None:
            raise ValueError(f"unknown spec_factory: {lot.spec_factory}")
        spec = factory()
    else:
        spec = sketch_to_spec(
            lot.sketch,
            name=lot.name,
            style=lot.style,
            storeys=lot.storeys,
            seed=lot.seed + seed_offset,
        )

    _massing, _plan, assembly, stage_report = run_through_assemble(spec)
    if assembly is None or not assembly.placements:
        return assembly, stage_report
    assembly = _with_style_tag(assembly, lot.style)
    assembly, report = validate(assembly)
    return assembly, report


def _lot_has_ground_door(assembly) -> bool:
    for p in assembly.placements:
        aid = getattr(p, "asset_id", "") or ""
        if "door" in aid and p.level == 0:
            return True
    return False


def _lot_interior_walkable(assembly) -> bool:
    """Ground floor has floor cells and at least one door opening."""
    floors = {
        (p.cell[0], p.cell[1])
        for p in assembly.placements
        if getattr(p, "kind", None) in ("floor", "ground") and p.level == 0
    }
    return bool(floors) and _lot_has_ground_door(assembly)


def _lot_roof_seated(assembly, *, validate_report) -> bool:
    roof_fail = [
        f
        for f in validate_report.critical
        if "roof" in f.message.lower() or "floating" in f.message.lower()
    ]
    has_roof = any(getattr(p, "kind", None) == "roof" for p in assembly.placements)
    return has_roof and not roof_fail


def _lot_module_snap_ok(validate_report) -> bool:
    snap_fail = [
        f
        for f in validate_report.critical
        if "grid" in f.message.lower() or "module" in f.message.lower()
    ]
    return not snap_fail


def validate_lot(lot: StreetLot, assembly, report) -> Dict[str, Any]:
    """Per-building validation record for street_sample_validation.json."""
    from pae.validate import validate

    bays_x, bays_y = _footprint_bays(lot)
    _, vreport = validate(assembly)
    return {
        "name": lot.name,
        "type": lot.building_type,
        "footprint_bays": f"{bays_x}x{bays_y}",
        "storeys": lot.storeys,
        "style": lot.style,
        "has_ground_door": _lot_has_ground_door(assembly),
        "interior_walk_volume": _lot_interior_walkable(assembly),
        "roof_seated": _lot_roof_seated(assembly, validate_report=vreport),
        "module_snap_ok": _lot_module_snap_ok(vreport),
        "validation_ok": vreport.ok,
        "critical_count": len(vreport.critical),
        "warning_count": len(vreport.warnings),
        "piece_count": len(assembly.placements),
        "critical_messages": [f.message for f in vreport.critical[:5]],
    }


def build_street(
    *,
    seed_offset: int = 0,
    require_per_lot_ok: bool = True,
    side: str = "both",
) -> Tuple[Optional[object], object, Dict[str, Any]]:
    """Build and merge the street sample. Fail-closed when any lot has critical defects.

    ``side``: ``original``, ``opposite`` (opp_* extension), or ``both`` (default).
    """
    from pae.report import Report
    from pae.site import BuildingInstance, SiteOptions, build_site, place_buildings
    from pae.validate import validate

    lots = lots_for_side(side)
    instances: List[BuildingInstance] = []
    stats: Dict[str, Any] = {
        "lots": [],
        "failed": [],
        "side": (side or "both").strip().lower(),
    }

    for lot in lots:
        try:
            assembly, stage_report = _build_lot(lot, seed_offset)
        except Exception as exc:
            stats["failed"].append({"name": lot.name, "error": str(exc)})
            if require_per_lot_ok:
                return None, Report.from_failures([]), stats
            continue

        if assembly is None or not assembly.placements:
            stats["failed"].append({"name": lot.name, "error": "no placements"})
            if require_per_lot_ok:
                return None, stage_report, stats
            continue

        lot_val = validate_lot(lot, assembly, stage_report)
        stats["lots"].append(lot_val)

        if require_per_lot_ok and not lot_val["validation_ok"]:
            stats["failed"].append(
                {
                    "name": lot.name,
                    "error": "validation critical",
                    "messages": lot_val["critical_messages"],
                }
            )
            return None, Report.from_failures([]), stats

        instances.append(BuildingInstance(assembly, lot.cell_offset, lot.name))
        stats[lot.name] = len(assembly.placements)

    if not instances:
        return None, Report.from_failures([]), stats

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, mreport, stats

    sited, _layout, sreport = build_site(
        merged,
        SiteOptions(
            walk_width_bays=2,
            margin_bays=3,
            walk_piece="paving_cobble",
            lawn_piece="sidewalk_slab",
            boundary_fence=False,
            kerbs=True,
        ),
    )
    if not sreport.ok:
        return sited, sreport, stats

    _checked, vreport = validate(sited)
    stats["total"] = len(sited.placements)
    stats["critical"] = len(vreport.critical)
    stats["warnings"] = len(vreport.warnings)
    stats["all_lots_valid"] = all(l["validation_ok"] for l in stats["lots"])
    try:
        from pae.city_street_sample_opposite import opposite_side_names

        opp_name_set = set(opposite_side_names())
    except ImportError:
        opp_name_set = {
            n
            for n in (l.get("name") for l in stats["lots"])
            if str(n).startswith("opp_") and "north" not in str(n)
        }
    opp_lots = [l for l in stats["lots"] if l.get("name") in opp_name_set]
    all_opp = [l for l in stats["lots"] if str(l.get("name", "")).startswith("opp_")]
    stats["opposite_lots_valid"] = (
        all(l["validation_ok"] for l in opp_lots) if opp_lots else True
    )
    stats["opposite_building_count"] = len(opp_lots)
    stats["all_opp_prefixed_valid"] = (
        all(l["validation_ok"] for l in all_opp) if all_opp else True
    )
    return sited, vreport, stats


def write_validation_json(
    stats: Dict[str, Any],
    path: Optional[Path] = None,
) -> Path:
    """Write Saved/city_samples/street_sample_validation.json."""
    root = Path(__file__).resolve().parent.parent
    out = path or root / "Saved" / "city_samples" / "street_sample_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    buildings = stats.get("lots", [])
    try:
        from pae.city_street_sample_opposite import opposite_side_names

        opp_name_set = set(opposite_side_names())
    except ImportError:
        opp_name_set = {
            n
            for n in (b.get("name") for b in buildings)
            if str(n).startswith("opp_") and "north" not in str(n)
        }
    opp = [b for b in buildings if b.get("name") in opp_name_set]
    opp_all = [b for b in buildings if str(b.get("name", "")).startswith("opp_")]
    composer = [b for b in buildings if not str(b.get("name", "")).startswith("opp_")]
    payload = {
        "skill": "pae-city-street-sample",
        "module_snap_cm": MODULE_CM,
        "storey_cm": STOREY_CM,
        "side": stats.get("side", "both"),
        "lane_map": {
            "Composer": "north (+Y)",
            "Grok": "south (−Y)",
            "note": "True across-the-street lanes; matching X columns face each other",
        },
        "all_valid": stats.get("all_lots_valid", False),
        "all_buildings_valid": stats.get("all_lots_valid", False),
        "opposite_all_valid": stats.get("opposite_lots_valid", True),
        "opposite_building_count": stats.get("opposite_building_count", len(opp)),
        "all_opp_prefixed_valid": stats.get("all_opp_prefixed_valid", True),
        "site_merge_valid": stats.get("critical", 0) == 0,
        "kit_meshes": stats.get("kit_meshes", False),
        "kit_pieces_used": stats.get("kit_pieces_used", {}),
        "site_critical": stats.get("critical", 0),
        "site_warnings": stats.get("warnings", 0),
        "total_pieces": stats.get("total", 0),
        "buildings": buildings,
        "composer_buildings": composer,
        "opposite_buildings": opp,
        "opp_prefixed_buildings": opp_all,
        "failed": stats.get("failed", []),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def report(side: str = "both") -> None:
    assembly, rep, stats = build_street(side=side)
    write_validation_json(stats)
    if assembly is None:
        print("STREET FAILED:", stats.get("failed"))
        return
    for lot in stats.get("lots", []):
        print(
            f"  {lot['name']:18s} {lot['type']:12s} "
            f"{lot['footprint_bays']} {lot['storeys']}st "
            f"ok={lot['validation_ok']} door={lot['has_ground_door']}"
        )
    print(f"  TOTAL pieces={stats.get('total')} critical={stats.get('critical')}")
    print(
        f"  opposite_ok={stats.get('opposite_lots_valid')} "
        f"count={stats.get('opposite_building_count')}"
    )


if __name__ == "__main__":
    report()

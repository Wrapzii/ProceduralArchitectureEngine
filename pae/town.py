"""Town — the delivery target: a handful of buildings and a street, ready for Unreal.

WHY THIS EXISTS
---------------
Everything upstream of this file is machinery. This is the thing that was actually
asked for: *"I just want my city and a couple of buildings procedurally generated built
up so I can start throwing them into Unreal."*

It is deliberately NOT another hardcoded scene like the old ``showcase.py``. Every
building here is a **sketch plus a style pack plus a seed** — three lines each. Change
the seed and you get a different but equally legal town; change the style and the same
sketches come out medieval instead of rustic. Adding a building is adding a sketch, not
writing Python.

    from pae.town import build_town, build_catalogue
    assembly, report, stats = build_town(seed=7)

The sketches below are the vocabulary of a small town: cottage, shop, townhouse,
longhouse, courtyard house, gatehouse. They are small on purpose — the solver fills in
stairs, doors, windows, corridors and roof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --- the vocabulary -----------------------------------------------------------------
# '#' built · '.' open/void · 'S' stair · 'E' entrance · 'T' tower · space = outside

# SIZING RULE, learned the hard way: a straight flight is 2 bays long and needs a bay
# to arrive on, so a multi-storey footprint must be at least 4 bays in the stair's
# direction. A 4x3 cottage put the stair against the far wall and produced
# `stair_exit_into_wall`. Anything below 5x4 should be single-storey.

COTTAGE = """
#####
#####
#####
#####
"""

SHOP = """
######
######
######
######
"""

TOWNHOUSE = """
#####
#####
#####
#####
#####
"""

LONGHOUSE = """
#########
#########
#########
#########
"""

COURTYARD_HOUSE = """
#######
#.....#
#.....#
#######
#######
"""

GATEHOUSE = """
T####T
######
##SS##
######
"""

HALL = """
##########
####S#####
##########
##########
"""


@dataclass(frozen=True)
class TownBuilding:
    """One building: a sketch, a style, a place to stand. Nothing else."""

    name: str
    sketch: str
    style: str
    storeys: int
    cell_offset: Tuple[int, int]
    seed: int = 0


def town_plan() -> List[TownBuilding]:
    """A small town: a street of shops and houses, a hall, a gatehouse closing the end.

    Offsets are in CELLS and leave a 3-bay street between the two rows.
    """
    north_y = 7
    south_y = -6
    return [
        # --- north side of the street
        TownBuilding("cottage_a", COTTAGE, "rustic", 2, (0, north_y), 11),
        TownBuilding("shop_a", SHOP, "townhouse", 2, (5, north_y), 12),
        TownBuilding("townhouse_a", TOWNHOUSE, "townhouse", 3, (11, north_y), 13),
        TownBuilding("cottage_b", COTTAGE, "rustic", 2, (16, north_y), 14),
        # --- south side
        TownBuilding("longhouse", LONGHOUSE, "medieval", 2, (1, south_y), 21),
        TownBuilding("courtyard_house", COURTYARD_HOUSE, "manor", 2, (10, south_y), 22),
        TownBuilding("shop_b", SHOP, "townhouse", 2, (17, south_y), 23),
        # --- the hall and the gate, closing the far end
        TownBuilding("guild_hall", HALL, "civic", 2, (23, 0), 31),
        TownBuilding("gatehouse", GATEHOUSE, "keep", 3, (35, 1), 32),
    ]


def catalogue_plan() -> List[TownBuilding]:
    """One of each sketch, in each style — the asset sheet.

    This is the "hundreds of them, placed, each valid" answer: the same six sketches
    across the style packs, laid out on a grid so they can be eyeballed side by side.
    """
    sketches = [
        ("cottage", COTTAGE, 2),
        ("shop", SHOP, 2),
        ("townhouse", TOWNHOUSE, 3),
        ("longhouse", LONGHOUSE, 2),
        ("courtyard", COURTYARD_HOUSE, 2),
    ]
    styles = ["rustic", "medieval", "townhouse", "manor", "civic", "gothic_academy"]
    out: List[TownBuilding] = []
    for sy, style in enumerate(styles):
        for sx, (nm, sk, st) in enumerate(sketches):
            out.append(
                TownBuilding(
                    name=f"{style}_{nm}",
                    sketch=sk,
                    style=style,
                    storeys=st,
                    cell_offset=(sx * 12, sy * 12),
                    seed=100 + sy * 10 + sx,
                )
            )
    return out


def _build_one(b: TownBuilding, seed_offset: int):
    """Sketch -> finished single building. Returns ``(assembly, report)``."""
    from pae.pipeline import run_through_decorate
    from pae.sketch import sketch_to_spec

    spec = sketch_to_spec(
        b.sketch,
        name=b.name,
        style=b.style,
        storeys=b.storeys,
        seed=b.seed + seed_offset,
    )
    result = run_through_decorate(spec)
    assembly = next((r for r in result if hasattr(r, "placements")), None)
    report = next((r for r in reversed(result) if hasattr(r, "ok")), None)
    return assembly, report


def build_group(
    buildings: Sequence[TownBuilding],
    *,
    seed_offset: int = 0,
    site: bool = True,
) -> Tuple[Optional[object], object, Dict[str, int]]:
    """Build and merge a set of buildings onto one site.

    Returns ``(assembly, report, stats)``. Buildings that fail to build are recorded in
    ``stats`` and SKIPPED rather than aborting the town — one bad sketch should not cost
    you the other eight.
    """
    from pae.report import Report
    from pae.site import BuildingInstance, SiteOptions, build_site, place_buildings

    instances: List[BuildingInstance] = []
    stats: Dict[str, int] = {}
    failed: List[str] = []

    for b in buildings:
        try:
            assembly, report = _build_one(b, seed_offset)
        except Exception:  # a sketch that cannot build must not kill the batch
            failed.append(b.name)
            continue
        if assembly is None or not assembly.placements:
            failed.append(b.name)
            continue
        stats[b.name] = len(assembly.placements)
        instances.append(BuildingInstance(assembly, b.cell_offset, b.name))

    stats["failed"] = len(failed)
    if failed:
        stats["failed_names"] = failed  # type: ignore[assignment]
    if not instances:
        return None, Report.from_failures([]), stats

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, mreport, stats

    if not site:
        stats["total"] = len(merged.placements)
        return merged, mreport, stats

    sited, _layout, sreport = build_site(
        merged,
        SiteOptions(
            walk_width_bays=2,
            margin_bays=2,
            boundary_fence=False,
            kerbs=True,
        ),
    )
    if not sreport.ok:
        return sited, sreport, stats

    from pae.validate import validate

    _checked, vreport = validate(sited)
    stats["total"] = len(sited.placements)
    stats["critical"] = len(vreport.critical)
    stats["warnings"] = len(vreport.warnings)
    return sited, vreport, stats


def build_town(*, seed: int = 0):
    """The town. One street, nine buildings, four styles."""
    return build_group(town_plan(), seed_offset=seed)


def build_catalogue(*, seed: int = 0):
    """The asset sheet: every sketch in every style, laid out on a grid."""
    return build_group(catalogue_plan(), seed_offset=seed, site=False)


def report(which: str = "town") -> None:
    """Print what got built. ``python -c "from pae.town import report; report()"``"""
    assembly, rep, stats = build_town() if which == "town" else build_catalogue()
    if assembly is None:
        print("nothing built:", stats)
        return
    for k, v in stats.items():
        if k not in ("total", "critical", "warnings", "failed_names"):
            print(f"  {k:22s} {v}")
    print(f"  {'TOTAL':22s} {stats.get('total')}")
    print(f"  critical={stats.get('critical')}  warnings={stats.get('warnings')}")
    if stats.get("failed_names"):
        print("  FAILED:", stats["failed_names"])

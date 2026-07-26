"""MMO street row — N Georgian townhouses along +X with shared depth.

Each unit uses :func:`pae.building_builder.build_building` (shell path) with
``row_context`` set from position: ``end_left`` / ``mid`` / ``end_right``.
Footprints abut with no empty module gap (party walls on shared east/west faces).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pae.assembly_types import Assembly
from pae.facade_grammar import FacadeParams, metres_to_bays
from pae.report import Report
from pae.site import BuildingInstance, place_buildings


def row_context_for_index(index: int, count: int) -> str:
    """Map row position to facade party-wall context."""
    if count <= 1:
        return "freestanding"
    if index == 0:
        return "end_left"
    if index == count - 1:
        return "end_right"
    return "mid"


def seed_for_row_unit(base_seed: int, index: int) -> int:
    """Alternating seeds along the row (deterministic)."""
    return int(base_seed) + index * 137


def build_street_row(
    count: int = 5,
    *,
    frontage_m: float = 10.0,
    depth_m: float = 8.0,
    storeys: int = 3,
    wealth: int = 2,
    base_seed: int = 1812,
    archetype: str = "georgian_merchant",
    validate_assembly: bool = False,
) -> Tuple[Assembly, Report, Dict[str, Any]]:
    """Build and merge *count* shell townhouses along +X.

    Returns ``(merged_assembly, report, stats)`` where *stats* lists per-unit
    ``row_context``, ``seed``, and ``cell_offset``.
    """
    from pae.building_builder import build_building

    if count < 1:
        return (
            Assembly(placements=[]),
            Report.from_failures([]),
            {"count": 0, "buildings": []},
        )

    instances: List[BuildingInstance] = []
    buildings_meta: List[Dict[str, Any]] = []
    x_offset_bays = 0
    bays_y = metres_to_bays(depth_m) or 2
    failures: List[str] = []

    for i in range(count):
        ctx = row_context_for_index(i, count)
        seed = seed_for_row_unit(base_seed, i)
        wealth_i = wealth if i % 2 == 0 else max(1, min(5, wealth + 1))
        params = FacadeParams(
            seed=seed,
            archetype=archetype,
            frontage_m=frontage_m,
            depth_m=depth_m,
            storeys=storeys,
            wealth=wealth_i,
            row_context=ctx,
        )
        _massing, _plan, assembly, report, _out = build_building(
            params, validate_assembly=validate_assembly
        )
        if assembly is None or not assembly.placements:
            failures.append(f"row_{i:02d}: empty assembly")
            continue
        if not report.ok:
            failures.append(
                f"row_{i:02d}: {len(report.critical)} critical validation issue(s)"
            )

        bays_x = metres_to_bays(frontage_m) or 3
        name = f"row_{i:02d}"
        instances.append(
            BuildingInstance(assembly, (x_offset_bays, 0), name)
        )
        buildings_meta.append(
            {
                "name": name,
                "index": i,
                "row_context": ctx,
                "seed": seed,
                "wealth": wealth_i,
                "cell_offset": (x_offset_bays, 0),
                "bays_x": bays_x,
                "bays_y": bays_y,
            }
        )
        x_offset_bays += bays_x

    if not instances:
        return (
            Assembly(placements=[]),
            Report.from_failures([]),
            {"count": count, "buildings": [], "failed": failures},
        )

    merged, merge_report = place_buildings(instances)
    stats: Dict[str, Any] = {
        "count": count,
        "frontage_m": frontage_m,
        "depth_m": depth_m,
        "storeys": storeys,
        "base_seed": base_seed,
        "total_bays_x": x_offset_bays,
        "depth_bays_y": bays_y,
        "buildings": buildings_meta,
        "placement_count": len(merged.placements),
        "failed": failures,
    }
    if failures:
        from pae.report import Failure

        report = Report.from_failures(
            list(merge_report.failures)
            + [Failure(check="street_row", message=m, world_xyz=None) for m in failures]
        )
    else:
        report = merge_report
    return merged, report, stats


__all__ = [
    "build_street_row",
    "row_context_for_index",
    "seed_for_row_unit",
]

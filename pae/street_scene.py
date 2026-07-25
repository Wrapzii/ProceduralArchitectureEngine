"""Street scene — a medieval town street, built from the existing engine only.

Reference: a timber-framed European street closed by a gate tower with a spire, an arched
gateway through it, shopfronts at ground level, taller stone buildings opposite.

The point of this module is an HONEST capability answer. It uses nothing that does not
already exist: specs, trim, banding, variation, site. Where the reference needs something
the engine cannot do yet, that is recorded in ``MISSING`` rather than faked.

Built with:  python -c "from pae.street_scene import report; report()"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pae.assembly_types import Assembly
from pae.banding import BandingSpec, CourseSpec
from pae.report import Report
from pae.trim import TrimOptions
from pae.variation import VariationSpec

# What the reference has that the engine cannot produce today. Kept here, next to the
# scene, so the gap is visible every time someone builds it.
MISSING: Tuple[Tuple[str, str], ...] = (
    ("jetties", "upper floor projecting past the wall below — roadmap T-013"),
    ("party walls", "buildings sharing a wall in a continuous street front — T-018"),
    ("awnings/signage", "shop awnings, hanging signs, stall canopies — S-091"),
    ("props", "crates, barrels, produce, market stalls — S-081..S-092"),
    ("materials", "plaster, timber, stone, tile — everything is workbench tint — S-102"),
    ("clock face", "the gate tower's clock stage — S-040"),
    ("shopfront glazing", "wide ground-floor openings with counters — S-063"),
    ("cobbles", "paving_cobble exists but street laying is per-cell flat — S-096"),
)

# Timber-framed range: plinth, jettied bressummer line, wall plate, studs and braces.
TIMBER_BANDING = BandingSpec(
    courses=(
        CourseSpec("plinth", 0.02),
        CourseSpec("bressummer", 0.58, piece="band_course_jettied"),
        CourseSpec("plate", 0.93),
    ),
    verticals_every_bays=1,
    braces=True,
)

# Rendered stone/plaster range opposite: plinth and a string course, coping at the head.
STONE_BANDING = BandingSpec(
    courses=(CourseSpec("plinth", 0.03), CourseSpec("string", 0.52)),
    verticals_every_bays=0,
    braces=False,
    coping=True,
)

TOWER_BANDING = BandingSpec(
    courses=(CourseSpec("plinth", 0.02), CourseSpec("stage", 0.86)),
    verticals_every_bays=1,
    braces=False,
    corners_only=True,
)


@dataclass
class StreetBuilding:
    name: str
    bays_x: int
    bays_y: int
    storeys: int
    cell_offset: Tuple[int, int]
    banding: BandingSpec
    trim: TrimOptions
    pitch: float = 1.55
    seed: int = 1
    towers: Optional[List] = None


def _spec(b: StreetBuilding):
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        OpeningPolicy,
        RoofSpec,
    )

    return BuildingSpec(
        name=b.name,
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=b.bays_x, bays_y=b.bays_y),
        storeys=b.storeys,
        storey_use=["hall"] * b.storeys,
        towers=b.towers or [],
        roof=RoofSpec(kind="pitched", pitch=b.pitch),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1, doors_ground=1, windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=b.seed,
        ground_slab=True,
    )


TIMBER_TRIM = TrimOptions(
    buttresses=False, roofline=True, colonnade=False, parapets=False,
    chimney_piece="chimney_stack", dormer_piece="dormer_gabled",
)
STONE_TRIM = TrimOptions(
    buttresses=False, roofline=True, colonnade=False, parapets=True,
    chimney_piece="chimney_stack",
)
TOWER_TRIM = TrimOptions(
    buttresses=True, roofline=True, colonnade=False, parapets=True,
    spire_piece="spire_octagonal",
)


def street() -> List[StreetBuilding]:
    """A street running along X. Timber row north, stone row south, gate tower closing it.

    Depths differ between the rows so the street reads as a place rather than a corridor,
    and each building gets its own seed so no two elevations repeat.
    """
    from pae.spec import TowerSpec

    north_y = 6      # timber row sits north of the street
    south_y = -7     # stone row sits south
    return [
        # --- north side: timber-framed, jettied character, varied heights
        StreetBuilding("timber_a", 4, 4, 3, (0, north_y), TIMBER_BANDING, TIMBER_TRIM,
                       pitch=1.65, seed=21),
        StreetBuilding("timber_b", 3, 4, 2, (5, north_y), TIMBER_BANDING, TIMBER_TRIM,
                       pitch=1.75, seed=22),
        StreetBuilding("timber_c", 5, 4, 3, (9, north_y), TIMBER_BANDING, TIMBER_TRIM,
                       pitch=1.6, seed=23),
        # --- south side: taller rendered stone, arched openings
        StreetBuilding("stone_a", 5, 4, 3, (1, south_y), STONE_BANDING, STONE_TRIM,
                       pitch=1.45, seed=24),
        StreetBuilding("stone_b", 4, 4, 4, (7, south_y), STONE_BANDING, STONE_TRIM,
                       pitch=1.4, seed=25),
        # --- the gate tower closing the far end of the street
        StreetBuilding(
            "gate_tower", 4, 4, 4, (15, 0), TOWER_BANDING, TOWER_TRIM,
            pitch=1.8, seed=26,
            towers=[TowerSpec(cell=(0, 0), storeys=4), TowerSpec(cell=(3, 3), storeys=4)],
        ),
    ]


def build(seed_offset: int = 0) -> Tuple[Optional[Assembly], Report, Dict[str, int]]:
    """Assemble the whole street as ONE site assembly."""
    from pae.banding import band
    from pae.pipeline import run_through_assemble
    from pae.site import BuildingInstance, SiteOptions, build_site, place_buildings
    from pae.trim import trim
    from pae.validate import validate
    from pae.variation import vary

    instances: List[BuildingInstance] = []
    stats: Dict[str, int] = {}

    for b in street():
        _, _, assembly, report = run_through_assemble(_spec(b))
        if assembly is None or not report.ok:
            return None, report, stats

        assembly, vreport = vary(assembly, VariationSpec(seed=b.seed + seed_offset))
        if not vreport.ok:
            return None, vreport, stats

        assembly, treport = trim(assembly, b.trim)
        if not treport.ok:
            return None, treport, stats

        assembly, breport = band(assembly, b.banding)
        if not breport.ok:
            return None, breport, stats

        stats[b.name] = len(assembly.placements)
        instances.append(BuildingInstance(assembly, b.cell_offset, b.name))

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, mreport, stats

    # Pave the street and lay the grounds. No boundary fence — this is a town, not a plot.
    sited, _layout, sreport = build_site(
        merged,
        SiteOptions(
            walk_width_bays=2,
            margin_bays=2,
            walk_piece="paving_cobble",
            lawn_piece="sidewalk_slab",
            boundary_fence=False,
            kerbs=True,
        ),
    )
    if not sreport.ok:
        return sited, sreport, stats

    _, vreport = validate(sited)
    stats["total"] = len(sited.placements)
    stats["critical"] = len(vreport.critical)
    stats["warnings"] = len(vreport.warnings)
    return sited, vreport, stats


def report() -> None:
    assembly, rep, stats = build()
    if assembly is None:
        print("street FAILED to build:", [f.message for f in rep.failures][:3])
        return
    for k, v in stats.items():
        if k not in ("total", "critical", "warnings"):
            print(f"  {k:14s} {v:5d} pieces")
    print(f"  {'TOTAL':14s} {stats['total']:5d} pieces")
    print(f"  critical={stats['critical']}  warnings={stats['warnings']}")
    print("\nWhat the reference has that this cannot:")
    for name, why in MISSING:
        print(f"  - {name:18s} {why}")

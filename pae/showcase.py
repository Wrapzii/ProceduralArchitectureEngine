"""Showcase — ten buildings exercising the whole engine.

Purpose: show what PAE can actually produce today, using every stage in the pipeline
(spec → solve → plan → assemble → trim → banding → site → validate) and every kit family
(walls with real aperture profiles, columns, barriers, roofline, bands, surfaces).

Each entry is a complete, validated building. Nothing here is hand-placed — every piece
comes from a spec plus declarative options, which is the whole point of the engine.

Run headless:  python -c "from pae.showcase import report; report()"
Build in Blender: see tools/pae_showcase_in_blender.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from pae.assembly_types import Assembly
from pae.banding import BandingSpec, CourseSpec, band
from pae.report import Report
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    TowerSpec,
    fortress_keep_spec,
)
from pae.trim import TrimOptions, trim
from pae.variation import VariationSpec, vary


@dataclass
class Build:
    """One showcase building: what it is, and how it is put together."""

    key: str
    title: str
    blurb: str
    spec: BuildingSpec
    trim: TrimOptions
    banding: Optional[BandingSpec] = None
    site: bool = False
    variation: Optional[VariationSpec] = None
    notes: str = ""


def _spec(
    name: str,
    bays_x: int,
    bays_y: int,
    storeys: int,
    *,
    style: str = "townhouse",
    kind: str = "rect",
    roof: str = "pitched",
    pitch: float = 1.3,
    towers: Optional[List[TowerSpec]] = None,
    windows_per_bay: int = 1,
    doors: int = 1,
    ground_windows: Optional[int] = None,
    wing_depth: int = 2,
    seed: int = 1,
) -> BuildingSpec:
    return BuildingSpec(
        name=name,
        style=style,
        footprint=FootprintSpec(
            kind=kind, bays_x=bays_x, bays_y=bays_y, wing_depth=wing_depth
        ),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=towers or [],
        roof=RoofSpec(kind=roof, pitch=pitch),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=windows_per_bay,
            doors_ground=doors,
            windows_ground=ground_windows,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


# Banding presets ------------------------------------------------------------

WEALDEN_BANDING = BandingSpec(
    courses=(
        CourseSpec("plinth", 0.02),
        CourseSpec("bressummer", 0.60, piece="band_course_jettied"),
        CourseSpec("plate", 0.93),
    ),
    verticals_every_bays=1,
    braces=True,
)

STONE_BANDING = BandingSpec(
    courses=(CourseSpec("plinth", 0.03), CourseSpec("string", 0.55)),
    verticals_every_bays=0,
    braces=False,
    coping=True,
)

CIVIC_BANDING = BandingSpec(
    courses=(
        CourseSpec("plinth", 0.02),
        CourseSpec("sill", 0.30),
        CourseSpec("cornice", 0.90),
    ),
    verticals_every_bays=2,
    braces=False,
    corners_only=True,
)


# The ten ---------------------------------------------------------------------


def builds() -> List[Build]:
    return [
        Build(
            "great_hall",
            "Great Hall",
            "Long five-bay hall, steep roof, buttressed flanks, tall lancet range.",
            _spec("great_hall", 7, 3, 2, roof="pitched", pitch=1.7,
                  windows_per_bay=1, doors=2, seed=11),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=False, balustrade_piece="balustrade_stone"),
            STONE_BANDING,
            notes="Steep pitch is the anime-fantasy silhouette lever (S-011).",
        ),
        Build(
            "refectory",
            "Refectory",
            "Wide dining range with mullioned lights and chimney stacks.",
            _spec("refectory", 6, 4, 2, roof="pitched", pitch=1.25,
                  windows_per_bay=1, doors=2, seed=12),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=False, chimney_piece="chimney_stack"),
            CIVIC_BANDING,
        ),
        Build(
            "gatehouse",
            "Gatehouse",
            "Twin-tower gate block with spires over the carriage arch.",
            _spec("gatehouse", 4, 3, 3, roof="pitched", pitch=1.5,
                  towers=[TowerSpec(cell=(0, 0), storeys=3),
                          TowerSpec(cell=(3, 0), storeys=3)],
                  doors=1, seed=13),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=True, spire_piece="spire_needle"),
            STONE_BANDING,
            notes="Tower attachment is Ledger C-5 — watch for freestanding warnings.",
        ),
        Build(
            "brewery",
            "Brewery",
            "Squat working building, wide cart doors, tall flue.",
            _spec("brewery", 4, 3, 2, roof="pitched", pitch=1.15,
                  windows_per_bay=1, doors=2, ground_windows=2, seed=14),
            TrimOptions(buttresses=False, roofline=True, colonnade=False,
                        parapets=False, chimney_piece="chimney_stack",
                        dormer_piece="dormer_gabled"),
            WEALDEN_BANDING,
        ),
        Build(
            "storefront",
            "Storefront Row",
            "Three-storey shop range, wide glazing below, lodgings above.",
            _spec("storefront", 5, 3, 3, roof="pitched", pitch=1.35,
                  windows_per_bay=1, doors=3, seed=15),
            TrimOptions(buttresses=False, roofline=True, colonnade=False,
                        parapets=True, dormer_piece="dormer_gabled"),
            CIVIC_BANDING,
        ),
        Build(
            "wealden_cottage",
            "Wealden Cottage",
            "Timber-framed cottage: plinth, jettied bressummer, studs and braces.",
            _spec("wealden_cottage", 3, 3, 2, roof="pitched", pitch=1.6,
                  windows_per_bay=1, doors=1, seed=16),
            TrimOptions(buttresses=False, roofline=True, colonnade=False,
                        parapets=False, chimney_piece="chimney_stack"),
            WEALDEN_BANDING,
            notes="Direct from the reference photo.",
        ),
        Build(
            "chapel",
            "Chapel",
            "Narrow, tall, steeply roofed, with a needle spire over the crossing.",
            _spec("chapel", 3, 6, 2, roof="pitched", pitch=1.9,
                  towers=[TowerSpec(cell=(0, 0), storeys=3)],
                  windows_per_bay=1, doors=1, seed=17),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=False, spire_piece="spire_octagonal"),
            STONE_BANDING,
        ),
        Build(
            "library_tower",
            "Library Tower",
            "Four-storey book tower, banded stages, spire and finial.",
            _spec("library_tower", 3, 3, 4, roof="pitched", pitch=1.7,
                  towers=[TowerSpec(cell=(2, 2), storeys=4)],
                  windows_per_bay=1, doors=1, seed=18),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=True, spire_piece="spire_octagonal"),
            BandingSpec(
                courses=(CourseSpec("plinth", 0.02), CourseSpec("stage", 0.88)),
                verticals_every_bays=1, braces=False, corners_only=True,
            ),
        ),
        Build(
            "dormitory",
            "Dormitory Range",
            "Three-storey sleeping range, dormered attic, buttressed.",
            _spec("dormitory", 8, 3, 3, roof="pitched", pitch=1.4,
                  windows_per_bay=1, doors=2, seed=19),
            TrimOptions(buttresses=True, roofline=True, colonnade=False,
                        parapets=False, dormer_piece="dormer_gabled"),
            CIVIC_BANDING,
        ),
        Build(
            "cloister_court",
            "Cloister Court",
            "U-plan court with a colonnaded walk and railed upper gallery.",
            _spec("cloister_court", 8, 7, 2, kind="U", roof="pitched", pitch=1.3,
                  wing_depth=3, windows_per_bay=1, doors=2, seed=20),
            TrimOptions(buttresses=True, roofline=True, colonnade=True,
                        parapets=False, arcade_piece="arch_freestanding"),
            STONE_BANDING,
            site=True,
        ),
        Build(
            "fortress_keep",
            "Fortress Keep",
            "Central bailey manor: steep gable, multi-height corner/wall towers, needle spires.",
            fortress_keep_spec(seed=50),
            TrimOptions(
                buttresses=True,
                roofline=True,
                colonnade=False,
                parapets=False,
                dormer_piece="dormer_gabled",
                spire_piece="spire_needle",
                balustrade_piece="balustrade_stone",
            ),
            STONE_BANDING,
            notes="Campus compound: pae.compound.build_fortress_compound().",
        ),
    ]


# Pipeline --------------------------------------------------------------------


def build_one(b: Build) -> Tuple[Optional[Assembly], Report, Dict[str, int]]:
    """Run one showcase entry all the way through, returning stats."""
    from pae.pipeline import run_through_assemble
    from pae.site import build_site
    from pae.validate import validate

    _, _, assembly, report = run_through_assemble(b.spec)
    if not report.ok:
        return None, report, {}

    stats: Dict[str, int] = {"assembled": len(assembly.placements)}

    # Variation runs FIRST: it fixes illegal apertures (upper doors opening onto nothing)
    # and repositions ground doors off the corner, so trim and banding see the final
    # openings and can step around them.
    vspec = b.variation or VariationSpec(seed=b.spec.seed)
    assembly, vreport = vary(assembly, vspec)
    if not vreport.ok:
        return assembly, vreport, stats
    stats["after_variation"] = len(assembly.placements)

    assembly, treport = trim(assembly, b.trim)
    if not treport.ok:
        return assembly, treport, stats
    stats["after_trim"] = len(assembly.placements)

    if b.banding is not None:
        assembly, breport = band(assembly, b.banding)
        if not breport.ok:
            return assembly, breport, stats
        stats["after_banding"] = len(assembly.placements)

    if b.site:
        assembly, _layout, sreport = build_site(assembly)
        if not sreport.ok:
            return assembly, sreport, stats
        stats["after_site"] = len(assembly.placements)

    _, vreport = validate(assembly)
    stats["total"] = len(assembly.placements)
    stats["critical"] = len(vreport.critical)
    stats["warnings"] = len(vreport.warnings)
    return assembly, vreport, stats


def build_all() -> List[Tuple[Build, Optional[Assembly], Report, Dict[str, int]]]:
    out = []
    for b in builds():
        assembly, report, stats = build_one(b)
        out.append((b, assembly, report, stats))
    return out


def report() -> None:
    """Print a table of what built, how big, and whether it validates."""
    rows = build_all()
    print(f"{'building':18s} {'pieces':>7s} {'crit':>5s} {'warn':>5s}  status")
    print("-" * 62)
    ok = 0
    for b, assembly, rep, stats in rows:
        status = "OK" if rep.ok else f"FAIL {rep.failures[0].check}"
        if rep.ok:
            ok += 1
        print(
            f"{b.key:18s} {stats.get('total', 0):7d} "
            f"{stats.get('critical', 0):5d} {stats.get('warnings', 0):5d}  {status}"
        )
    print("-" * 62)
    print(f"{ok}/{len(rows)} validate clean")

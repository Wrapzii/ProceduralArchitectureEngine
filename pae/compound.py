"""Compound — several buildings arranged around a shared open courtyard.

WHY THIS EXISTS: ``site.py`` can merge buildings and pave around them, but a compound is
more than adjacency.  The ranges have to *address* the courtyard: their upper storeys open
onto it as a balcony gallery, their ground storeys open onto it through a colonnade, and
each range should read as its own building rather than four copies of one asset.

This module is the first thing in PAE that composes buildings instead of pieces, and it is
deliberately built out of the existing stages rather than a new assembler:

    assemble (per range)  →  trim (per range, DIFFERENT options)  →  place_buildings
      →  balconies (needs the merged courtyard)  →  build_site  →  validate

Per-range trim is the point of the split.  Trim runs *before* the merge so the north range
can be the chapel range with a spire and gothic arcade while the west range is the service
range with chimneys and a plain parapet — same spec, different building.

BALCONY RULE: a balcony is a deck cantilevered one bay into the courtyard at every upper
level, carried by columns standing on the ground, with a balustrade on its open edge and
railings returning at its ends.  All three are required: a deck with no columns floats, and
a deck with no balustrade is a first-floor drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.boundary import FACE_YAW, boundary_offset_cm
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report
from pae.site import (
    BuildingInstance,
    SiteOptions,
    build_site,
    place_buildings,
    _courtyard_cells,
    _ground_cells,
)
from pae.trim import TrimOptions, covered_cells, trim

Cell = Tuple[int, int]

_NEIGHBOURS = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}
_OPPOSITE = {"south": "north", "north": "south", "west": "east", "east": "west"}


@dataclass(frozen=True)
class RangeStyle:
    """One building in the compound: where it sits and how it is trimmed."""

    name: str
    cell_offset: Cell
    trim: TrimOptions
    label: str = ""


@dataclass
class CompoundLayout:
    courtyard: Set[Cell] = field(default_factory=set)
    balcony_cells: Set[Cell] = field(default_factory=set)
    ranges: List[str] = field(default_factory=list)
    per_range_trim: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trim personalities — this is what stops four ranges reading as one asset ×4.
# ---------------------------------------------------------------------------

CHAPEL_TRIM = TrimOptions(
    railings=True,
    buttresses=True,
    roofline=True,
    colonnade=True,
    parapets=False,
    arcade_piece="arch_freestanding",
    balustrade_piece="balustrade_stone",
    spire_piece="spire_octagonal",
)

HALL_TRIM = TrimOptions(
    railings=True,
    buttresses=True,
    roofline=True,
    colonnade=True,
    parapets=True,
    balustrade_piece="balustrade_stone",
    parapet_piece="parapet_solid",
    chimney_piece="chimney_stack",
)

SERVICE_TRIM = TrimOptions(
    railings=True,
    buttresses=False,
    roofline=True,
    colonnade=False,
    parapets=True,
    balustrade_piece="railing_metal",
    parapet_piece="parapet_solid",
    dormer_piece="dormer_gabled",
)

LODGING_TRIM = TrimOptions(
    railings=True,
    buttresses=False,
    roofline=True,
    colonnade=True,
    parapets=False,
    balustrade_piece="balustrade_stone",
    arcade_piece="arch_freestanding",
    dormer_piece="dormer_gabled",
    chimney_piece="chimney_stack",
)


def default_ranges(span: Tuple[int, int], gap_bays: int) -> List[RangeStyle]:
    """Four ranges round a court: chapel N, hall S, service W, lodging E."""
    w, h = span
    across = w + gap_bays
    up = h + gap_bays
    return [
        RangeStyle("south_hall", (0, 0), HALL_TRIM, "hall range"),
        RangeStyle("north_chapel", (0, up), CHAPEL_TRIM, "chapel range"),
        RangeStyle("west_service", (-across, up // 2), SERVICE_TRIM, "service range"),
        RangeStyle("east_lodging", (across, up // 2), LODGING_TRIM, "lodging range"),
    ]


# ---------------------------------------------------------------------------
# Balconies
# ---------------------------------------------------------------------------


def _building_cells(assembly: Assembly, name: str) -> Set[Cell]:
    out: Set[Cell] = set()
    for p in assembly.placements:
        if name in p.tags and p.kind in ("wall", "floor", "plinth"):
            out |= covered_cells(p)
    return out


def _place(
    piece_id: str,
    cell: Cell,
    level: int,
    *,
    yaw: int = 0,
    offset_cm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    suffix: str,
    tag: str,
) -> SolidPlacement:
    desc = catalog_by_id()[piece_id]
    cx, cy = cell
    return SolidPlacement(
        piece_id=f"{tag}_{piece_id}_{level}_{cx}_{cy}_{suffix}",
        asset_id=piece_id,
        kind=desc.kind,
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"balcony", tag}),
    )


def add_balconies(
    assembly: Assembly,
    courtyard: Set[Cell],
    range_names: Sequence[str],
    *,
    deck_piece: str = "floor",
    post_piece: str = "pier_square",
    balustrade_piece: str = "balustrade_stone",
) -> Tuple[Assembly, Set[Cell], Report]:
    """Cantilever a balcony gallery into the courtyard at every upper level.

    Returns the extended assembly and the balcony cells.  The deck, its supporting posts
    and its balustrade are placed together — a deck without posts is the floating-piece
    defect, and a deck without a balustrade is a hole you can walk off.
    """
    catalog = catalog_by_id()
    missing = [
        p for p in (deck_piece, post_piece, balustrade_piece) if p not in catalog
    ]
    if missing:
        return (
            assembly,
            set(),
            Report.from_failures(
                [
                    Failure(
                        check="balcony_piece_missing",
                        message=f"balcony wants unknown pieces {missing}",
                        world_xyz=None,
                    )
                ]
            ),
        )

    if not courtyard:
        return assembly, set(), Report.from_failures([])

    levels = sorted({p.level for p in assembly.placements if p.level > 0})
    if not levels:
        return assembly, set(), Report.from_failures([])

    extra: List[SolidPlacement] = []
    balcony_cells: Set[Cell] = set()
    deck_t = catalog[deck_piece].size_cm[2]

    # The gallery line is the courtyard PLUS one ring outward, minus anything built.
    # The strict courtyard test needs built cells on all four sides, so the cells directly
    # against each range fail it and the raw courtyard set touches no building at all —
    # dilating by one recovers exactly the band a gallery occupies.
    all_built: Set[Cell] = set()
    for name in range_names:
        all_built |= _building_cells(assembly, name)
    gallery = set(courtyard)
    for cx, cy in sorted(courtyard):
        for dx, dy in _NEIGHBOURS.values():
            gallery.add((cx + dx, cy + dy))
    gallery -= all_built

    for name in range_names:
        built = _building_cells(assembly, name)
        if not built:
            continue
        # Gallery cells directly adjacent to this range.
        for cell in sorted(gallery):
            cx, cy = cell
            faces = [
                face
                for face, (dx, dy) in _NEIGHBOURS.items()
                if (cx + dx, cy + dy) in built
            ]
            if not faces:
                continue
            balcony_cells.add(cell)
            for level in levels:
                extra.append(
                    _place(
                        deck_piece,
                        cell,
                        level,
                        offset_cm=(0.0, 0.0, -deck_t),
                        suffix="deck",
                        tag=name,
                    )
                )
                # Balustrade on every side of the deck that is open courtyard.
                for face, (dx, dy) in _NEIGHBOURS.items():
                    n = (cx + dx, cy + dy)
                    if n in built:
                        continue  # that side is the building itself
                    extra.append(
                        _place(
                            balustrade_piece,
                            cell,
                            level,
                            yaw=FACE_YAW[face],
                            offset_cm=boundary_offset_cm(
                                face, catalog[balustrade_piece].size_cm
                            ),
                            suffix=f"rail_{face}",
                            tag=name,
                        )
                    )
            # Posts carry the gallery from the ground up to the lowest deck.
            for level in range(0, max(levels)):
                extra.append(
                    _place(
                        post_piece,
                        cell,
                        level,
                        suffix="post",
                        tag=name,
                    )
                )

    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    out = Assembly(
        placements=list(assembly.placements) + extra,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    return out, balcony_cells, Report.from_failures([])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_compound(
    spec=None,
    *,
    gap_bays: int = 6,
    ranges: Optional[Sequence[RangeStyle]] = None,
    site_options: Optional[SiteOptions] = None,
    balconies: bool = True,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Assemble one range, trim four copies differently, arrange them round a court."""
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    building_spec = spec if spec is not None else m2_two_storey_stair_spec()
    _, _, base, report = run_through_assemble(building_spec)
    if not report.ok:
        return base, CompoundLayout(), report

    cells = {p.cell for p in base.placements}
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    span = (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    styles = list(ranges) if ranges is not None else default_ranges(span, gap_bays)

    layout = CompoundLayout(ranges=[s.name for s in styles])
    instances: List[BuildingInstance] = []
    for style in styles:
        trimmed, treport = trim(base, style.trim)
        if not treport.ok:
            return base, layout, treport
        layout.per_range_trim[style.name] = sum(
            1 for p in trimmed.placements if "trim" in p.tags
        )
        instances.append(
            BuildingInstance(trimmed, style.cell_offset, style.name)
        )

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, layout, mreport

    layout.courtyard = _courtyard_cells(_ground_cells(merged))

    if balconies:
        merged, balcony_cells, breport = add_balconies(
            merged, layout.courtyard, [s.name for s in styles]
        )
        if not breport.ok:
            return merged, layout, breport
        layout.balcony_cells = balcony_cells

    sited, site_layout, sreport = build_site(merged, site_options)
    if not sreport.ok:
        return sited, layout, sreport
    layout.courtyard = site_layout.courtyard

    return sited, layout, Report.from_failures([])

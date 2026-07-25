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
class BalconySpec:
    """How a balcony gallery is built — every knob you would want to turn.

    A balcony is not a fixed feature; it is a set of choices. Which sides get one, how far
    it projects, how many doors open onto it, whether it is railed, whether the roof covers
    it. Defaults give a court-facing gallery with two doors per range.
    """

    enabled: bool = True
    sides: Tuple[str, ...] = ()          # range names; empty = every range on the court
    depth_bays: int = 1                  # how far the deck projects into the court
    doors_per_range: int = 2             # access doors punched in the wall behind it
    door_piece: str = "wall_door_arched"
    railing: bool = True
    railing_piece: str = "balustrade_stone"
    posts: bool = True                   # columns carrying the deck to the ground
    post_piece: str = "pier_square"
    deck_piece: str = "floor"
    under_roof: bool = True              # extend a roof over the gallery
    roof_piece: str = "roof_flat"
    levels: Tuple[int, ...] = ()         # empty = every upper level

    def wants(self, range_name: str) -> bool:
        return self.enabled and (not self.sides or range_name in self.sides)


@dataclass(frozen=True)
class RangeStyle:
    """One building in the compound: its spec, where it sits, how it is trimmed.

    ``spec`` matters as much as the offset. Four copies of one square pavilion can never
    form a quadrangle no matter where you put them — you get four separate buildings round
    a cross-shaped gap. A quad needs *ranges*: wide bars north and south, deep bars east
    and west, meeting at the corners so the court is genuinely enclosed.
    """

    name: str
    cell_offset: Cell
    trim: TrimOptions
    label: str = ""
    spec: object = None
    balcony: Optional[BalconySpec] = None


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


def range_spec(name: str, bays_x: int, bays_y: int, *, storeys: int = 2, seed: int = 1):
    """A range: a long bar with a stair, sized in bays."""
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        OpeningPolicy,
        RoofSpec,
    )

    return BuildingSpec(
        name=name,
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=bays_x, bays_y=bays_y),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=2,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def default_ranges(
    court_bays_x: int = 7,
    court_bays_y: int = 5,
    *,
    depth_bays: int = 3,
    storeys: int = 2,
    balcony: Optional[BalconySpec] = None,
) -> List[RangeStyle]:
    """Four ranges enclosing a court: hall S, chapel N, service W, lodging E."""
    bal = balcony if balcony is not None else BalconySpec()
    wide = court_bays_x + 2 * depth_bays
    return [
        RangeStyle("south_hall", (-depth_bays, -depth_bays), HALL_TRIM, "hall range",
                   range_spec("range_wide", wide, depth_bays, storeys=storeys, seed=1), bal),
        RangeStyle("north_chapel", (-depth_bays, court_bays_y), CHAPEL_TRIM, "chapel range",
                   range_spec("range_wide", wide, depth_bays, storeys=storeys, seed=2), bal),
        RangeStyle("west_service", (-depth_bays, 0), SERVICE_TRIM, "service range",
                   range_spec("range_deep", depth_bays, court_bays_y, storeys=storeys, seed=3), bal),
        RangeStyle("east_lodging", (court_bays_x, 0), LODGING_TRIM, "lodging range",
                   range_spec("range_deep", depth_bays, court_bays_y, storeys=storeys, seed=4), bal),
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


def _court_facing_walls(
    assembly: Assembly,
    name: str,
    gallery: Set[Cell],
    level: int,
) -> List[SolidPlacement]:
    """Wall placements of ``name`` at ``level`` that face the gallery."""
    out: List[SolidPlacement] = []
    for p in assembly.placements:
        if p.kind != "wall" or name not in p.tags or p.level != level:
            continue
        cells = covered_cells(p)
        touches = any(
            (c[0] + dx, c[1] + dy) in gallery
            for c in cells
            for dx, dy in _NEIGHBOURS.values()
        )
        if touches:
            out.append(p)
    return out


def add_balconies(
    assembly: Assembly,
    courtyard: Set[Cell],
    ranges: Sequence[RangeStyle],
) -> Tuple[Assembly, Set[Cell], Report]:
    """Build a balcony gallery per range, following each range's :class:`BalconySpec`.

    Deck, posts, railing, access doors and roof cover are placed together. The rules that
    matter and why:

      * The railing goes ONLY where the deck meets open air. Putting one on every face that
        is not a building turns the court into a grid of fences.
      * Gallery cells are resolved ONCE globally. A corner cell touches two ranges, and
        claiming it per range gives it a duplicate deck and duplicate posts.
      * A balcony with no door is a balcony you cannot reach. ``doors_per_range`` wall bays
        behind the deck are swapped for door pieces — never left as a blank wall, and never
        left as a hole with no door in it.
    """
    catalog = catalog_by_id()
    if not courtyard:
        return assembly, set(), Report.from_failures([])

    active = [r for r in ranges if r.balcony and r.balcony.wants(r.name)]
    if not active:
        return assembly, set(), Report.from_failures([])

    wanted = {
        piece
        for r in active
        for piece in (
            r.balcony.deck_piece,
            r.balcony.post_piece,
            r.balcony.railing_piece,
            r.balcony.door_piece,
            r.balcony.roof_piece,
        )
    }
    missing = sorted(w for w in wanted if w not in catalog)
    if missing:
        return assembly, set(), Report.from_failures([
            Failure(check="balcony_piece_missing",
                    message=f"balcony wants unknown pieces {missing}", world_xyz=None)
        ])

    all_levels = sorted({p.level for p in assembly.placements if p.level > 0})
    if not all_levels:
        return assembly, set(), Report.from_failures([])

    all_built: Set[Cell] = set()
    for r in ranges:
        all_built |= _building_cells(assembly, r.name)

    # Gallery band: the court dilated outward by the deepest requested projection, minus
    # anything built. The strict courtyard test needs building on all four sides, so cells
    # directly against a range are not "courtyard" and the raw set touches no building.
    depth = max(r.balcony.depth_bays for r in active)
    gallery = set(courtyard)
    for _ in range(max(1, depth)):
        for cx, cy in sorted(gallery):
            for dx, dy in _NEIGHBOURS.values():
                gallery.add((cx + dx, cy + dy))
    gallery -= all_built

    walk_cells = {
        c for c in gallery
        if any((c[0] + dx, c[1] + dy) in all_built for dx, dy in _NEIGHBOURS.values())
    }

    extra: List[SolidPlacement] = []
    drop: Set[str] = set()
    balcony_cells: Set[Cell] = set()

    for style in active:
        bal = style.balcony
        name = style.name
        built = _building_cells(assembly, name)
        if not built:
            continue
        levels = list(bal.levels) or all_levels
        mine = sorted(
            c for c in (walk_cells - balcony_cells)
            if any((c[0] + dx, c[1] + dy) in built for dx, dy in _NEIGHBOURS.values())
        )
        if not mine:
            continue
        balcony_cells.update(mine)
        deck_t = catalog[bal.deck_piece].size_cm[2]

        for cell in mine:
            cx, cy = cell
            for level in levels:
                extra.append(_place(bal.deck_piece, cell, level,
                                    offset_cm=(0.0, 0.0, -deck_t), suffix="deck", tag=name))
                if bal.railing:
                    for face, (dx, dy) in _NEIGHBOURS.items():
                        n = (cx + dx, cy + dy)
                        if n in all_built or n in walk_cells:
                            continue
                        extra.append(_place(
                            bal.railing_piece, cell, level,
                            yaw=FACE_YAW[face],
                            offset_cm=boundary_offset_cm(
                                face, catalog[bal.railing_piece].size_cm),
                            suffix=f"rail_{face}", tag=name))
            if bal.posts:
                # Posts run from the ground to the deck, and CONTINUE to the roof when the
                # gallery is covered — otherwise the roof has nothing under it and floats
                # a storey above the balustrade.
                top_post = max(levels) + (1 if bal.under_roof else 0)
                for level in range(0, top_post):
                    extra.append(_place(bal.post_piece, cell, level,
                                        suffix="post", tag=name))
            if bal.under_roof:
                # Sit the gallery roof on the SAME plane as the range roof (one full
                # storey above the top level datum), not a slab-thickness below it.
                # Offsetting by STOREY - FLOOR_T put the canopy 30 cm low, so it met the
                # range roof edge-on with a step and a gap instead of running into it.
                top = max(all_levels)
                extra.append(_place(bal.roof_piece, cell, top,
                                    offset_cm=(0.0, 0.0, STOREY_CM),
                                    suffix="roof", tag=name))

        # Access doors: swap wall bays behind the gallery for door pieces.
        if bal.doors_per_range > 0:
            for level in levels:
                candidates = _court_facing_walls(assembly, name, set(mine), level)
                if not candidates:
                    continue
                candidates.sort(key=lambda p: (p.cell, p.piece_id))
                count = min(bal.doors_per_range, len(candidates))
                step = max(1, len(candidates) // count)
                chosen = candidates[::step][:count]
                door = catalog[bal.door_piece]
                for w in chosen:
                    drop.add(w.piece_id)
                    extra.append(SolidPlacement(
                        piece_id=f"{w.piece_id}_balcony_door",
                        asset_id=bal.door_piece,
                        kind=door.kind,
                        cell=w.cell,
                        level=w.level,
                        yaw=w.yaw,
                        offset_cm=w.offset_cm,
                        size_cm=door.size_cm,
                        rotates_about_center=door.rotates_about_center,
                        tags=door.tags | frozenset({"balcony", "balcony_door", name}),
                    ))

    # Parapets stranded mid-roof: trim gave each range a parapet on its court-facing
    # edge, which was correct then. Roofing the gallery extends the roof plane past that
    # edge, so the parapet is no longer at a boundary — it is a grey wall standing up
    # through the middle of the blue roof. Drop any parapet now fully surrounded by roof.
    roofed: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind == "roof":
            roofed |= covered_cells(p)
    for p in extra:
        if p.kind == "roof":
            roofed |= covered_cells(p)
    for p in assembly.placements:
        if p.kind != "barrier" or "parapet" not in p.tags:
            continue
        cells = covered_cells(p)
        if all(
            (c[0] + dx, c[1] + dy) in roofed
            for c in cells
            for dx, dy in _NEIGHBOURS.values()
        ):
            drop.add(p.piece_id)

    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    kept = [p for p in assembly.placements if p.piece_id not in drop]
    out = Assembly(
        placements=kept + extra,
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
    ranges: Optional[Sequence[RangeStyle]] = None,
    site_options: Optional[SiteOptions] = None,
    balcony: Optional[BalconySpec] = None,
    balconies: bool = True,
    court_bays_x: int = 7,
    court_bays_y: int = 5,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Assemble each range, trim them differently, arrange them round a court."""
    from pae.pipeline import run_through_assemble
    from pae.spec import m2_two_storey_stair_spec

    bal = balcony if balcony is not None else BalconySpec(enabled=balconies)
    if not balconies:
        bal = BalconySpec(enabled=False)
    styles = list(ranges) if ranges is not None else default_ranges(
        court_bays_x, court_bays_y, balcony=bal
    )
    fallback = spec if spec is not None else m2_two_storey_stair_spec()

    layout = CompoundLayout(ranges=[s.name for s in styles])
    instances: List[BuildingInstance] = []
    for style in styles:
        _, _, assembled, report = run_through_assemble(style.spec or fallback)
        if not report.ok:
            return assembled, layout, report
        trimmed, treport = trim(assembled, style.trim)
        if not treport.ok:
            return assembled, layout, treport
        layout.per_range_trim[style.name] = sum(
            1 for p in trimmed.placements if "trim" in p.tags
        )
        instances.append(BuildingInstance(trimmed, style.cell_offset, style.name))

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, layout, mreport

    layout.courtyard = _courtyard_cells(_ground_cells(merged))

    merged, balcony_cells, breport = add_balconies(merged, layout.courtyard, styles)
    if not breport.ok:
        return merged, layout, breport
    layout.balcony_cells = balcony_cells

    sited, site_layout, sreport = build_site(merged, site_options)
    if not sreport.ok:
        return sited, layout, sreport
    layout.courtyard = site_layout.courtyard
    return sited, layout, Report.from_failures([])

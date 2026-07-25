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
from pae.contract import EAVE_OVERHANG_CM, FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.catalog import catalog_by_id
from pae.primitives.roofs import roof_eave_offset_cm, roof_flat_span_size_cm
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

# Castle curtain + gatehouse (Phase 4.1–4.2 greybox).
CURTAIN_TRIM = TrimOptions(
    railings=False,
    buttresses=False,
    roofline=True,
    colonnade=False,
    parapets=True,
    parapet_piece="parapet_solid",
)

GATEHOUSE_TRIM = TrimOptions(
    railings=False,
    buttresses=False,
    roofline=False,
    colonnade=False,
    parapets=False,
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


def _gallery_roof_overhangs(
    mine: Set[Cell],
    *,
    balcony_cells: Set[Cell],
) -> Tuple[float, float, float, float]:
    """Eave overhang (west, east, south, north) for one range's gallery roof span.

    WHY: per-cell ``roof_flat`` decks stop at the cell boundary.  The range roof spans its
    full footprint with ``EAVE_OVERHANG_CM`` on exterior faces; the gallery canopy must do
    the same or it meets the range roof only along part of its edge and stops short of the
    balustrade on the open court side.  Interior seams where two gallery runs meet get zero
    overhang so the slabs butt cleanly.
    """
    min_x = min(c[0] for c in mine)
    max_x = max(c[0] for c in mine)
    min_y = min(c[1] for c in mine)
    max_y = max(c[1] for c in mine)
    oh = EAVE_OVERHANG_CM

    def side_overhang(face: str) -> float:
        dx, dy = _NEIGHBOURS[face]
        if face == "west":
            edge = {(min_x, cy) for cy in range(min_y, max_y + 1)}
        elif face == "east":
            edge = {(max_x, cy) for cy in range(min_y, max_y + 1)}
        elif face == "south":
            edge = {(cx, min_y) for cx in range(min_x, max_x + 1)}
        else:
            edge = {(cx, max_y) for cx in range(min_x, max_x + 1)}
        outside = {(cx + dx, cy + dy) for cx, cy in edge}
        if outside & balcony_cells:
            return 0.0
        return oh

    return (
        side_overhang("west"),
        side_overhang("east"),
        side_overhang("south"),
        side_overhang("north"),
    )


def _place_gallery_roof(
    piece: str,
    mine: Set[Cell],
    level: int,
    *,
    balcony_cells: Set[Cell],
    tag: str,
) -> SolidPlacement:
    """One spanning flat roof covering every gallery cell claimed by ``tag``."""
    desc = catalog_by_id()[piece]
    min_x = min(c[0] for c in mine)
    min_y = min(c[1] for c in mine)
    max_x = max(c[0] for c in mine)
    max_y = max(c[1] for c in mine)
    modules_x = max_x - min_x + 1
    modules_y = max_y - min_y + 1
    west, east, south, north = _gallery_roof_overhangs(
        mine, balcony_cells=balcony_cells,
    )
    eave_ox, eave_oy, _ = roof_eave_offset_cm(overhang_west=west, overhang_south=south)
    return SolidPlacement(
        piece_id=f"{tag}_{piece}_{level}_{min_x}_{min_y}_roof",
        asset_id=piece,
        kind=desc.kind,
        cell=(min_x, min_y),
        level=level,
        yaw=0,
        offset_cm=(eave_ox, eave_oy, STOREY_CM),
        size_cm=roof_flat_span_size_cm(
            modules_x,
            modules_y,
            overhang_west=west,
            overhang_east=east,
            overhang_south=south,
            overhang_north=north,
        ),
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"balcony", tag, "gallery_roof"}),
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
            # Span the full gallery run in one slab with eave overhang like the range roof,
            # not one module per cell — otherwise the canopy stops at the cell line and 7 of
            # 16 outer pieces met no wall and no range roof (roadmap 0.4 / C-2).
            top = max(all_levels)
            extra.append(_place_gallery_roof(
                bal.roof_piece,
                set(mine),
                top,
                balcony_cells=balcony_cells,
                tag=name,
            ))

        # Access doors: swap wall bays behind the gallery for door pieces.
        # Only walls that already touch a deck cell at this level — never punch a
        # doorway onto open air (aperture_reachability critical, roadmap 0.5).
        if bal.doors_per_range > 0:
            deck_at = set(mine)
            for level in levels:
                candidates = _court_facing_walls(assembly, name, deck_at, level)
                if not candidates:
                    continue
                candidates.sort(key=lambda p: (p.cell, p.piece_id))
                count = min(bal.doors_per_range, len(candidates))
                step = max(1, len(candidates) // count)
                chosen = candidates[::step][:count]
                door = catalog[bal.door_piece]
                for w in chosen:
                    # Refuse a door whose covered cells have no orthogonal neighbour
                    # in the deck set (guards against stale gallery membership).
                    wcells = covered_cells(w)
                    if not any(
                        (c[0] + dx, c[1] + dy) in deck_at
                        for c in wcells
                        for dx, dy in _NEIGHBOURS.values()
                    ):
                        continue
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


# ---------------------------------------------------------------------------
# Castle curtain + gatehouse (Phase 4.1–4.2)
# ---------------------------------------------------------------------------


def castle_curtain_ranges(
    bailey=None,
) -> List[RangeStyle]:
    """West + east curtain runs and a south gatehouse block."""
    from pae.spec import (
        CastleBaileySpec,
        castle_bailey_spec,
        castle_curtain_wall_spec,
        castle_gatehouse_spec,
    )

    cfg = bailey if bailey is not None else castle_bailey_spec()
    if not isinstance(cfg, CastleBaileySpec):
        cfg = CastleBaileySpec()

    length = cfg.curtain_length_bays
    gh_width = castle_gatehouse_spec(seed=cfg.gatehouse_seed).footprint.bays_x
    return [
        RangeStyle(
            "west_curtain",
            (0, 0),
            CURTAIN_TRIM,
            "west curtain",
            castle_curtain_wall_spec(
                "west_curtain",
                length,
                storeys=cfg.curtain_storeys,
                seed=cfg.west_curtain_seed,
            ),
            BalconySpec(enabled=False),
        ),
        RangeStyle(
            "gatehouse",
            (length, 0),
            GATEHOUSE_TRIM,
            "gatehouse",
            castle_gatehouse_spec(seed=cfg.gatehouse_seed),
            BalconySpec(enabled=False),
        ),
        RangeStyle(
            "east_curtain",
            (length + gh_width, 0),
            CURTAIN_TRIM,
            "east curtain",
            castle_curtain_wall_spec(
                "east_curtain",
                length,
                storeys=cfg.curtain_storeys,
                seed=cfg.east_curtain_seed,
            ),
            BalconySpec(enabled=False),
        ),
    ]


def _add_curtain_battlements(
    assembly: Assembly,
    range_names: Set[str],
) -> Assembly:
    """Crenellated caps along exterior wall-walks on curtain ranges."""
    catalog = catalog_by_id()
    if "battlement" not in catalog:
        return assembly

    batt_desc = catalog["battlement"]
    walls = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and p.asset_id == "wall_plain"
        and any(name in p.tags for name in range_names)
    ]
    if not walls:
        return assembly

    top_level = max(p.level for p in walls)
    top_walls = [p for p in walls if p.level == top_level]
    built: Set[Cell] = set()
    for p in assembly.placements:
        if any(name in p.tags for name in range_names) and p.kind in (
            "wall",
            "floor",
            "plinth",
            "ground",
        ):
            built |= covered_cells(p)

    extra: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
    for wall in top_walls:
        wall_top = wall.offset_cm[2] + wall.size_cm[2]
        for cell in covered_cells(wall):
            cx, cy = cell
            for face, (dx, dy) in _NEIGHBOURS.items():
                if (cx + dx, cy + dy) in built:
                    continue
                key = (cell, face)
                if key in seen:
                    continue
                seen.add(key)
                extra.append(
                    SolidPlacement(
                        piece_id=f"curtain_battlement_{top_level}_{cx}_{cy}_{face}",
                        asset_id="battlement",
                        kind=batt_desc.kind,
                        cell=cell,
                        level=top_level,
                        yaw=FACE_YAW[face],
                        offset_cm=boundary_offset_cm(
                            face, batt_desc.size_cm, z_cm=wall_top
                        ),
                        size_cm=batt_desc.size_cm,
                        rotates_about_center=batt_desc.rotates_about_center,
                        tags=batt_desc.tags
                        | frozenset({"trim", "curtain", "battlement"}),
                    )
                )

    if not extra:
        return assembly

    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    return Assembly(
        placements=list(assembly.placements) + extra,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )


def _range_ground_footprint(assembly: Assembly, range_name: str) -> Set[Cell]:
    """Level-0 built cells for one compound range tag."""
    out: Set[Cell] = set()
    for p in assembly.placements:
        if range_name not in p.tags:
            continue
        if p.level == 0 and p.kind in ("wall", "floor", "plinth", "ground"):
            out |= covered_cells(p)
    return out


def check_range_chain_connection(
    assembly: Assembly,
    range_names: Sequence[str],
) -> List[Failure]:
    """Adjacent compound ranges must meet at a 4-connected ground-cell edge."""
    footprints = {name: _range_ground_footprint(assembly, name) for name in range_names}
    failures: List[Failure] = []
    deltas = ((0, 1), (0, -1), (1, 0), (-1, 0))
    for left, right in zip(range_names, range_names[1:]):
        fa, fb = footprints[left], footprints[right]
        if not fa:
            failures.append(
                Failure(
                    check="range_connection",
                    message=f"range {left!r} has no level-0 footprint",
                    world_xyz=None,
                )
            )
            continue
        if not fb:
            failures.append(
                Failure(
                    check="range_connection",
                    message=f"range {right!r} has no level-0 footprint",
                    world_xyz=None,
                )
            )
            continue
        touches = any(
            (cx + dx, cy + dy) in fb for cx, cy in fa for dx, dy in deltas
        )
        if not touches:
            failures.append(
                Failure(
                    check="range_connection",
                    message=(
                        f"compound ranges {left!r} and {right!r} do not meet at any "
                        f"4-connected ground cell (gap between curtain segments)"
                    ),
                    world_xyz=None,
                )
            )
    return failures


def check_castle_curtain_compound(assembly: Assembly) -> List[Failure]:
    """Gate entrance role + west→gatehouse→east connectivity (Phase 4.1–4.2)."""
    from pae.existence import check_entrance_existence
    from pae.spec import castle_gatehouse_spec

    failures = check_range_chain_connection(
        assembly, ["west_curtain", "gatehouse", "east_curtain"]
    )
    failures.extend(check_entrance_existence(castle_gatehouse_spec().entrances, assembly))
    return failures


def build_castle_curtain_compound(
    *,
    bailey=None,
    site_options: Optional[SiteOptions] = None,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Assemble west/east curtain runs and a twin-tower south gatehouse."""
    from pae.pipeline import run_through_assemble
    from pae.site import CASTLE_BAILEY_SITE

    styles = castle_curtain_ranges(bailey)
    curtain_names = {s.name for s in styles if s.name != "gatehouse"}

    layout = CompoundLayout(ranges=[s.name for s in styles])
    instances: List[BuildingInstance] = []
    for style in styles:
        _, _, assembled, report = run_through_assemble(style.spec)
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

    compound_failures = check_castle_curtain_compound(merged)
    if compound_failures:
        return merged, layout, Report.from_failures(compound_failures)

    merged = _add_curtain_battlements(merged, curtain_names)

    opts = site_options if site_options is not None else CASTLE_BAILEY_SITE
    sited, site_layout, sreport = build_site(merged, opts)
    if not sreport.ok:
        return sited, layout, sreport
    layout.courtyard = site_layout.courtyard
    return sited, layout, Report.from_failures([])


def build_gatehouse_curtain(
    *,
    bailey=None,
    site_options: Optional[SiteOptions] = None,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Alias for :func:`build_castle_curtain_compound`."""
    return build_castle_curtain_compound(bailey=bailey, site_options=site_options)

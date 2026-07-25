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
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.boundary import FACE_YAW, boundary_offset_cm
from pae.contract import EAVE_OVERHANG_CM, FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM
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


class ConnectionPolicy(str, Enum):
    """How adjacent compound ranges relate along a shared edge.

    * ``separate`` — distinct buildings; may touch but stay sealed until a doorway
      is authored.
    * ``connect`` — one circulation graph: strip back-to-back exterior skins and
      punch a walkable link (door / arcade) on the shared interface.
    * ``merge`` — single inhabited mass: retag to a shared ``building:*`` identity
      and remove party walls on the interface (continuous floors).
    """

    SEPARATE = "separate"
    CONNECT = "connect"
    MERGE = "merge"


@dataclass(frozen=True)
class CompoundConnections:
    """Per-range-pair adjacency policy for compound unification."""

    pair_policy: Dict[Tuple[str, str], ConnectionPolicy] = field(default_factory=dict)
    default: ConnectionPolicy = ConnectionPolicy.CONNECT
    campus_id: str = "fortress_campus"
    # Declared structure identity (Roadmap 10.1). When set, all compound pieces are
    # stamped ``structure:<structure_id>`` and freestanding partitions on it.
    structure_id: Optional[str] = None
    # Range that owns the one vertical circulation core for the structure (D3-1).
    primary_circulation_mass: Optional[str] = None
    # Multi-storey subsidiary masses that keep their own hall stair well (e.g. gatehouse).
    auxiliary_circulation_masses: Tuple[str, ...] = ()

    def policy_for(self, range_a: str, range_b: str) -> ConnectionPolicy:
        key = tuple(sorted((range_a, range_b)))
        return self.pair_policy.get(key, self.default)


def school_compound_connections(
    styles: Sequence[RangeStyle],
) -> CompoundConnections:
    """School quad — court-facing ranges connect, never merge."""
    return CompoundConnections(default=ConnectionPolicy.CONNECT, campus_id="school_campus")


def fortress_compound_connections() -> CompoundConnections:
    """Fortress bailey — south curtain chain merges; cloisters connect into keep."""
    south = ("west_curtain", "gatehouse", "east_curtain")
    pair: Dict[Tuple[str, str], ConnectionPolicy] = {}
    for i in range(len(south) - 1):
        pair[tuple(sorted((south[i], south[i + 1])))] = ConnectionPolicy.MERGE
    for curtain, cloister in (
        ("west_curtain", "west_cloister"),
        ("east_curtain", "east_cloister"),
    ):
        pair[tuple(sorted((curtain, cloister)))] = ConnectionPolicy.CONNECT
    for cloister in ("west_cloister", "east_cloister"):
        pair[tuple(sorted((cloister, "north_keep")))] = ConnectionPolicy.CONNECT
    return CompoundConnections(
        pair_policy=pair,
        default=ConnectionPolicy.CONNECT,
        campus_id="fortress_campus",
        structure_id="fortress_bailey",
        primary_circulation_mass="north_keep",
        auxiliary_circulation_masses=("gatehouse",),
    )


def castle_curtain_connections() -> CompoundConnections:
    """South curtain chain — west | gate | east merges into one barbican mass."""
    chain = ("west_curtain", "gatehouse", "east_curtain")
    pair: Dict[Tuple[str, str], ConnectionPolicy] = {}
    for i in range(len(chain) - 1):
        pair[tuple(sorted((chain[i], chain[i + 1])))] = ConnectionPolicy.MERGE
    return CompoundConnections(
        pair_policy=pair,
        default=ConnectionPolicy.CONNECT,
        campus_id="castle_curtain",
        structure_id="castle_curtain",
    )


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
    connection: ConnectionPolicy = ConnectionPolicy.CONNECT


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
    arcade_piece="wall_arcade",
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
    arcade_piece="wall_arcade",
    dormer_piece="dormer_gabled",
    chimney_piece="chimney_stack",
)

# Castle curtain + gatehouse (Phase 4.1–4.2 greybox).
CURTAIN_TRIM = TrimOptions(
    railings=False,
    buttresses=False,
    roofline=True,
    colonnade=False,
    parapets=False,  # crenels via _add_curtain_battlements — not parapet_solid (D3-4)
)

GATEHOUSE_TRIM = TrimOptions(
    railings=False,
    buttresses=False,
    roofline=False,
    colonnade=False,
    parapets=False,
    exterior_steps=True,
    steps_piece="steps_grand",
)

# Fortress / bailey campus — keep dormers + needle spires, cloister arcade,
# buttressed curtains with parapets. Battlements added post-merge.
# ``buttress_outward`` orientation is owned by @CASTLE_FORTRESS_KIT / trim — do
# not disable emit here just to skip the check.
FORTRESS_KEEP_TRIM = TrimOptions(
    railings=True,
    buttresses=True,
    roofline=True,
    colonnade=False,
    parapets=True,
    parapet_piece="parapet_solid",
    dormer_piece="dormer_gabled",
    chimney_piece="chimney_stack",
    spire_piece="spire_needle",
    balustrade_piece="balustrade_stone",
)

FORTRESS_CLOISTER_TRIM = TrimOptions(
    railings=True,
    buttresses=False,
    roofline=True,
    colonnade=False,  # arcade placed post-merge (rect ranges have no COURTYARD cells)
    parapets=False,
    arcade_piece="wall_arcade",
    arcade_pier_piece="pier_square",
    balustrade_piece="balustrade_stone",
    dormer_piece="dormer_gabled",
)

FORTRESS_CURTAIN_TRIM = TrimOptions(
    railings=False,
    buttresses=True,
    roofline=True,
    colonnade=False,
    parapets=False,  # crenels via _add_curtain_battlements (not parapet_solid — D3-4)
)

FORTRESS_GATEHOUSE_TRIM = TrimOptions(
    railings=False,
    buttresses=True,
    roofline=True,
    colonnade=False,
    parapets=True,
    parapet_piece="parapet_solid",
    spire_piece="spire_needle",
    exterior_steps=True,
    steps_piece="steps_grand",
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
    building_cells: Set[Cell],
) -> Tuple[float, float, float, float]:
    """Eave overhang (west, east, south, north) for one range's gallery roof span.

    WHY: per-cell ``roof_flat`` decks stop at the cell boundary.  The range roof spans its
    full footprint with ``EAVE_OVERHANG_CM`` on exterior faces; the gallery canopy must do
    the same or it meets the range roof only along part of its edge and stops short of the
    balustrade on the open court side.  Interior seams where two gallery runs meet get zero
    overhang so the slabs butt cleanly.

    Building-facing sides use ``WALL_T_CM`` (not mere eave): ``roof_bears_on_wall`` needs
    >35 cm XY overlap with the wall-head strip.  ``EAVE_OVERHANG_CM`` is only half a wall
    (30 cm), so a canopy that stops at the eave line fails bearing while still touching the
    wall face sideways (``canopy_attachment``).  Posts carry the free edge; the wall head
    still has to carry the eaves — do not exempt ``gallery_roof`` from that check.
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
        if outside & building_cells:
            return WALL_T_CM
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
    building_cells: Set[Cell],
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
        mine, balcony_cells=balcony_cells, building_cells=building_cells,
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
                building_cells=all_built,
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
    connections = school_compound_connections(styles)
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
        instances.append(
            BuildingInstance(
                trimmed,
                style.cell_offset,
                style.name,
                structure=connections.structure_id,
            )
        )

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, layout, mreport

    # Unify sealed party walls between touching ranges (one circulation graph).
    from pae.compound_unify import unify_compound_assembly
    from pae.stair_occupancy import repair_stair_landing_walls

    merged = unify_compound_assembly(merged, connections=connections)
    merged = repair_stair_landing_walls(merged)

    layout.courtyard = _courtyard_cells(_ground_cells(merged))

    merged, balcony_cells, breport = add_balconies(merged, layout.courtyard, styles)
    if not breport.ok:
        return merged, layout, breport
    layout.balcony_cells = balcony_cells

    sited, site_layout, sreport = build_site(merged, site_options)
    if not sreport.ok:
        return sited, layout, sreport
    layout.courtyard = site_layout.courtyard
    # Re-unify after balconies/site in case new skins sealed an interface.
    sited = unify_compound_assembly(sited, connections=connections)
    sited = repair_stair_landing_walls(sited)
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


def _trim_run_along_x(
    cell: Cell,
    level: int,
    yaw: int,
    size_cm: Tuple[float, float, float],
    offset_cm: Tuple[float, float, float],
    trim_lo: float,
    trim_hi: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Shorten a yawed run at its low-X and/or high-X end, keeping it in place.

    The run's length lives in ``size_cm[1]`` and yaw maps it onto world X, so the offset
    has to move as the length changes. Rather than hand-derive that per yaw — the exact
    class of arithmetic that produced Ledger A-1..A-4 — build the trimmed piece, measure
    where it landed, and correct the offset by the difference.
    """
    from pae.contract import placement_world_aabb

    want_min, want_max = placement_world_aabb(
        cell[0], cell[1], level, yaw, size_cm, offset_cm
    )
    new_size = (size_cm[0], size_cm[1] - trim_lo - trim_hi, size_cm[2])
    if new_size[1] <= 0.0:
        return size_cm, offset_cm  # nothing left to lay; keep the original
    got_min, _got_max = placement_world_aabb(
        cell[0], cell[1], level, yaw, new_size, offset_cm
    )
    target_min_x = want_min[0] + trim_lo
    return new_size, (
        offset_cm[0] + (target_min_x - got_min[0]),
        offset_cm[1] + (want_min[1] - got_min[1]),
        offset_cm[2],
    )


def _add_curtain_battlements(
    assembly: Assembly,
    range_names: Set[str],
) -> Assembly:
    """Crenellated caps along exterior wall-walks on curtain ranges."""
    from pae.existence import is_door_or_gate_asset
    from pae.roof_edging import claimed_roof_edges, edge_is_claimed

    catalog = catalog_by_id()
    if "battlement" not in catalog:
        return assembly

    def _matches_range(p: SolidPlacement) -> bool:
        pid = p.piece_id or ""
        for name in range_names:
            if name in p.tags or f"building:{name}" in p.tags or name in pid:
                return True
        return False

    batt_desc = catalog["battlement"]
    walls = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and not is_door_or_gate_asset(p.asset_id or "")
        and _matches_range(p)
    ]
    if not walls:
        return assembly

    top_level = max(p.level for p in walls)
    top_walls = [p for p in walls if p.level == top_level]
    built: Set[Cell] = set()
    for p in assembly.placements:
        if _matches_range(p) and p.kind in (
            "wall",
            "floor",
            "plinth",
            "ground",
        ):
            built |= covered_cells(p)

    extra: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
    claimed = claimed_roof_edges(assembly)

    def _wants(cell: Cell, face: str) -> bool:
        cx, cy = cell
        dx, dy = _NEIGHBOURS[face]
        if (cx + dx, cy + dy) in built:
            return False
        return not edge_is_claimed(claimed, level=top_level, cell=cell, face=face)

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
                if edge_is_claimed(claimed, level=top_level, cell=cell, face=face):
                    continue
                seen.add(key)
                range_tags = frozenset(
                    t
                    for t in wall.tags
                    if t in range_names or t.startswith("building:")
                )
                # CORNER MITRE. A corner cell has TWO unbuilt faces, and laying a full
                # module run on each drives both through the same corner square — 532
                # interpenetration warnings on the fortress and visibly doubled masonry
                # at every corner. Ledger A-10 again: the corner is claimed once per run
                # instead of being resolved once. Resolution: the north-south runs own
                # the corner; an east-west run is trimmed back by the piece thickness
                # wherever it meets one, so the two BUTT instead of crossing.
                size = batt_desc.size_cm
                offset = boundary_offset_cm(face, size, z_cm=wall_top)
                if face in ("south", "north"):
                    thick = size[0]
                    trim_lo = thick if _wants(cell, "west") else 0.0
                    trim_hi = thick if _wants(cell, "east") else 0.0
                    if trim_lo or trim_hi:
                        size, offset = _trim_run_along_x(
                            cell, top_level, FACE_YAW[face], size, offset,
                            trim_lo, trim_hi,
                        )
                extra.append(
                    SolidPlacement(
                        piece_id=f"curtain_battlement_{top_level}_{cx}_{cy}_{face}",
                        asset_id="battlement",
                        kind=batt_desc.kind,
                        cell=cell,
                        level=top_level,
                        yaw=FACE_YAW[face],
                        offset_cm=offset,
                        size_cm=size,
                        rotates_about_center=batt_desc.rotates_about_center,
                        tags=batt_desc.tags
                        | frozenset({"trim", "curtain", "battlement"})
                        | range_tags,
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
    curtain_connections = castle_curtain_connections()
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
        instances.append(
            BuildingInstance(
                trimmed,
                style.cell_offset,
                style.name,
                structure=curtain_connections.structure_id,
            )
        )

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, layout, mreport

    from pae.compound_unify import unify_compound_assembly
    from pae.stair_occupancy import repair_stair_landing_walls

    merged = unify_compound_assembly(merged, connections=curtain_connections)
    merged = repair_stair_landing_walls(merged)

    compound_failures = check_castle_curtain_compound(merged)
    if compound_failures:
        return merged, layout, Report.from_failures(compound_failures)

    merged = _add_curtain_battlements(merged, curtain_names)
    merged = _add_approach_causeway(
        merged,
        gatehouse_name="gatehouse",
        steps_piece="steps_grand",
    )

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


# ---------------------------------------------------------------------------
# Fortress / bailey campus (nested courts on flat ground)
# ---------------------------------------------------------------------------


def fortress_bailey_ranges(
    bailey=None,
) -> List[RangeStyle]:
    """Nested bailey: south curtains+gate, cloisters around a court, north keep."""
    from pae.spec import (
        FortressBaileySpec,
        castle_curtain_wall_spec,
        fortress_bailey_compound_spec,
        fortress_cloister_range_spec,
        fortress_gatehouse_spec,
        fortress_keep_spec,
    )

    cfg = bailey if bailey is not None else fortress_bailey_compound_spec()
    if not isinstance(cfg, FortressBaileySpec):
        cfg = FortressBaileySpec()

    depth = cfg.range_depth
    court_x = cfg.court_bays_x
    court_y = cfg.court_bays_y
    wide = court_x + 2 * depth
    curtain_len = cfg.curtain_length_bays
    gh = fortress_gatehouse_spec(seed=cfg.gatehouse_seed)
    gh_w = gh.footprint.bays_x
    # South front spans the bailey width: curtain | gate | curtain.
    # If curtain lengths undershoot, pad the east run so the north keep meets.
    south_span = curtain_len + gh_w + curtain_len
    east_len = curtain_len + max(0, wide - south_span)
    # Three-storey curtains need a deeper bar for plan stair_graph (measured depth≥5).
    curtain_depth = max(depth, cfg.curtain_storeys + 2)
    # Origin: SW of west curtain / west cloister column (x = -depth).
    ox = -depth
    # South wall line sits one range-depth below the court (y = -depth).
    sy = -depth
    # Keep sits on the north edge of the court (closes the campus like a manor).
    keep_y = court_y
    keep_depth = max(4, depth + 1)

    no_balcony = BalconySpec(enabled=False)
    court_balcony = BalconySpec(
        enabled=True,
        sides=("west_cloister", "east_cloister", "north_keep"),
        doors_per_range=1,
        under_roof=True,
    )

    return [
        RangeStyle(
            "west_curtain",
            (ox, sy),
            FORTRESS_CURTAIN_TRIM,
            "west curtain",
            castle_curtain_wall_spec(
                "west_curtain",
                curtain_len,
                storeys=cfg.curtain_storeys,
                depth_bays=curtain_depth,
                seed=cfg.west_curtain_seed,
            ),
            no_balcony,
        ),
        RangeStyle(
            "gatehouse",
            (ox + curtain_len, sy),
            FORTRESS_GATEHOUSE_TRIM,
            "gatehouse",
            gh,
            no_balcony,
        ),
        RangeStyle(
            "east_curtain",
            (ox + curtain_len + gh_w, sy),
            FORTRESS_CURTAIN_TRIM,
            "east curtain",
            castle_curtain_wall_spec(
                "east_curtain",
                east_len,
                storeys=cfg.curtain_storeys,
                depth_bays=curtain_depth,
                seed=cfg.east_curtain_seed,
            ),
            no_balcony,
        ),
        RangeStyle(
            "west_cloister",
            (ox, 0),
            FORTRESS_CLOISTER_TRIM,
            "west cloister",
            fortress_cloister_range_spec(
                "west_cloister",
                depth,
                court_y,
                storeys=2,
                seed=cfg.west_cloister_seed,
            ),
            court_balcony,
        ),
        RangeStyle(
            "east_cloister",
            (court_x, 0),
            FORTRESS_CLOISTER_TRIM,
            "east cloister",
            fortress_cloister_range_spec(
                "east_cloister",
                depth,
                court_y,
                storeys=2,
                seed=cfg.east_cloister_seed,
            ),
            court_balcony,
        ),
        RangeStyle(
            "north_keep",
            (ox, keep_y),
            FORTRESS_KEEP_TRIM,
            "great hall / keep",
            fortress_keep_spec(
                bays_x=wide,
                bays_y=keep_depth,
                storeys=3,
                seed=cfg.keep_seed,
            ),
            court_balcony,
        ),
    ]


def _strip_trim_tower_helixes(assembly: Assembly) -> Assembly:
    """Drop spiral treads/newels that fail headroom under *any* roof AABB.

    Habitable keeps keep their drum climbs, but after compound merge a neighbour
    range roof can graze a gatehouse/keep helix (east curtain × gate drum). Those
    quarters are not climbable — strip them rather than demote headroom /
    stair_exit_clearance. Caps, crowns, spires, and clear spirals stay.
    """
    from pae.contract import placement_world_aabb
    from pae.trim import covered_cells

    _HEADROOM_CM = 210.0
    roof_bottom: Dict[Cell, float] = {}
    for p in assembly.placements:
        if p.kind not in ("roof", "roofline"):
            continue
        mn, _mx = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        for c in covered_cells(p):
            roof_bottom[c] = min(roof_bottom.get(c, mn[2]), mn[2])
    if not roof_bottom:
        return assembly

    drop: Set[str] = set()
    blocked_cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.asset_id != "stair_spiral_quarter":
            continue
        # Assemble-owned habitable keep/gate drum climbs — do not strip here.
        if "habitable_drum" in p.tags:
            continue
        mn, mx = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        ceil = min(
            (roof_bottom[c] for c in covered_cells(p) if c in roof_bottom),
            default=None,
        )
        if ceil is not None and ceil - mx[2] < _HEADROOM_CM:
            drop.add(p.piece_id)
            blocked_cells.add(p.cell)
    # Orphan newels on a level where every quarter was stripped.
    for p in assembly.placements:
        if p.asset_id != "spiral_newel":
            continue
        if p.cell not in blocked_cells:
            continue
        siblings = [
            q
            for q in assembly.placements
            if q.asset_id == "stair_spiral_quarter"
            and q.cell == p.cell
            and q.level == p.level
            and q.piece_id not in drop
        ]
        if not siblings:
            drop.add(p.piece_id)
    if not drop:
        return assembly
    kept = [p for p in assembly.placements if p.piece_id not in drop]
    return Assembly(
        placements=kept,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", None) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
    )


def _placement_matches_range(p: SolidPlacement, range_name: str) -> bool:
    """Match compound range after merge retags ``building:*`` to campus ids."""
    pid = p.piece_id or ""
    return (
        range_name in p.tags
        or f"building:{range_name}" in p.tags
        or range_name in pid
    )


def repair_shell_wall_level_support(assembly: Assembly) -> Assembly:
    """Remove upper-storey walls whose plan cells lost L0 wall support after unify.

    ``unify_compound_interfaces`` CONNECT/MERGE strips L0 party skins; when upper
    storeys were assembled per-level the remaining L1+ shells float (Handbook
    §7.5). Idempotent.
    """
    from pae.trim import covered_cells

    l0_wall_cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind == "wall" and p.level == 0:
            l0_wall_cells.update(covered_cells(p))

    drop: Set[str] = set()
    for p in assembly.placements:
        if p.kind != "wall" or p.level <= 0:
            continue
        cells = set(covered_cells(p))
        if cells and cells.isdisjoint(l0_wall_cells):
            drop.add(p.piece_id)

    if not drop:
        return assembly

    kept = [p for p in assembly.placements if p.piece_id not in drop]
    return Assembly(
        placements=kept,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def repair_junction_deck_headroom(assembly: Assembly) -> Assembly:
    """Trim upper spanning decks so junction bays under neighbour roofs stay non-walkable.

    After compound merge, a curtain L2 ``floor_deck`` can share plan cells with a
    cloister L1 hip roof (zero headroom at the interface). Split the deck so only
    interior bays remain — do not demote ``headroom``.
    """
    from pae.assemble import _rect_cover
    from pae.contract import FLOOR_T_CM, MODULE_CM, TOL_CM
    from pae.trim import covered_cells

    roof_cells_by_level: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "roof":
            continue
        for cell in covered_cells(p):
            roof_cells_by_level.setdefault(p.level, set()).add(cell)

    if not roof_cells_by_level:
        return assembly

    drop_ids: Set[str] = set()
    add: List[SolidPlacement] = []
    seq = 0

    for p in assembly.placements:
        if p.kind != "floor" or "hole" in (p.asset_id or ""):
            continue
        if float(p.size_cm[0]) <= MODULE_CM + TOL_CM and float(p.size_cm[1]) <= (
            MODULE_CM + TOL_CM
        ):
            continue
        deck_cells = set(covered_cells(p))
        under_roof: Set[Cell] = set()
        for roof_level, cells in roof_cells_by_level.items():
            if roof_level >= p.level:
                continue
            under_roof |= deck_cells & cells
        if not under_roof:
            continue
        keep = deck_cells - under_roof
        if not keep:
            drop_ids.add(p.piece_id)
            continue
        drop_ids.add(p.piece_id)
        floor_z_off = p.offset_cm[2] if p.offset_cm else -FLOOR_T_CM
        for x0, y0, w, h in _rect_cover(keep):
            seq += 1
            add.append(
                SolidPlacement(
                    piece_id=f"{p.piece_id}_jh_{seq}",
                    asset_id=p.asset_id,
                    kind=p.kind,
                    cell=(x0, y0),
                    level=p.level,
                    yaw=p.yaw,
                    offset_cm=(0.0, 0.0, floor_z_off),
                    size_cm=(w * MODULE_CM, h * MODULE_CM, p.size_cm[2]),
                    rotates_about_center=p.rotates_about_center,
                    tags=p.tags,
                )
            )

    if not drop_ids:
        return assembly

    kept = [p for p in assembly.placements if p.piece_id not in drop_ids]
    kept.extend(add)
    return Assembly(
        placements=kept,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def _add_cloister_arcade(
    assembly: Assembly,
    courtyard: Set[Cell],
    range_names: Sequence[str],
    *,
    arcade_piece: str = "wall_arcade",
    pier_piece: str = "pier_square",
) -> Assembly:
    """Cloister arcade along court-facing ground walls of cloister ranges.

    ``wall_arcade`` bays are cut into the courtyard-facing wall (openings under the
    upper roof). ``arch_freestanding`` remains supported for legacy colonnade paths.
    Corner court cells where two cloister walls meet get a shared ``pier_square``.
    """
    from pae.wall_faces import (
        claimed_wall_arcade_faces,
        face_is_claimed_for_arcade,
        repair_wall_face_stacks,
    )

    catalog = catalog_by_id()
    if not courtyard or arcade_piece not in catalog:
        return assembly
    desc = catalog[arcade_piece]
    pier_desc = catalog.get(pier_piece)
    names = set(range_names)
    wall_cells: Dict[str, Set[Cell]] = {n: set() for n in names}
    all_cloister_walls: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind != "wall" or p.level != 0:
            continue
        for name in names:
            if _placement_matches_range(p, name):
                wall_cells[name] |= covered_cells(p)
                all_cloister_walls |= covered_cells(p)

    extra: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
    wall_mode = arcade_piece.startswith("wall_")
    claimed = claimed_wall_arcade_faces(assembly)

    for name in names:
        walls = wall_cells.get(name, set())
        if not walls:
            continue
        for cx, cy in sorted(courtyard):
            for face, (dx, dy) in _NEIGHBOURS.items():
                wall_cell = (cx + dx, cy + dy)
                if wall_cell not in walls:
                    continue
                key = (wall_cell, face)
                if key in seen:
                    continue
                seen.add(key)
                if wall_mode:
                    place_cell = wall_cell
                    outward = _OPPOSITE[face]
                    if face_is_claimed_for_arcade(
                        claimed, level=0, cell=place_cell, face=outward
                    ):
                        continue
                    yaw = FACE_YAW[outward]
                    off = boundary_offset_cm(outward, desc.size_cm)
                else:
                    place_cell = (cx, cy)
                    yaw = FACE_YAW[face]
                    off = boundary_offset_cm(face, desc.size_cm)
                extra.append(
                    SolidPlacement(
                        piece_id=f"cloister_arcade_{name}_{cx}_{cy}_{face}",
                        asset_id=arcade_piece,
                        kind=desc.kind,
                        cell=place_cell,
                        level=0,
                        yaw=yaw,
                        offset_cm=off,
                        size_cm=desc.size_cm,
                        rotates_about_center=desc.rotates_about_center,
                        tags=desc.tags
                        | frozenset(
                            {
                                "cloister",
                                "arcade",
                                "trim",
                                name,
                                f"building:{name}",
                            }
                        ),
                    )
                )

    # Corner piers: court cell touches cloister walls on two perpendicular faces.
    if pier_desc is not None:
        pier_seen: Set[Cell] = set()
        for cx, cy in sorted(courtyard):
            wall_neighbors = sorted(
                (cx + dx, cy + dy)
                for face, (dx, dy) in _NEIGHBOURS.items()
                if (cx + dx, cy + dy) in all_cloister_walls
            )
            if len(wall_neighbors) < 2:
                continue
            cell = wall_neighbors[0]
            if cell in pier_seen:
                continue
            pier_seen.add(cell)
            extra.append(
                SolidPlacement(
                    piece_id=f"cloister_pier_{cell[0]}_{cell[1]}",
                    asset_id=pier_piece,
                    kind=pier_desc.kind,
                    cell=cell,
                    level=0,
                    yaw=0,
                    offset_cm=(0.0, 0.0, 0.0),
                    size_cm=pier_desc.size_cm,
                    rotates_about_center=pier_desc.rotates_about_center,
                    tags=pier_desc.tags
                    | frozenset({"cloister", "arcade", "trim", "arcade_pier"}),
                )
            )

    if not extra:
        return assembly
    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    merged = Assembly(
        placements=list(assembly.placements) + extra,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    return repair_wall_face_stacks(merged)


def _gate_leaf_cells(
    assembly: Assembly,
    *,
    gatehouse_name: str = "gatehouse",
) -> Set[Cell]:
    """Cells occupied by gatehouse gate / arch leaves (passage columns)."""
    cells: Set[Cell] = set()
    for p in assembly.placements:
        if gatehouse_name not in p.tags and f"building:{gatehouse_name}" not in p.tags:
            continue
        if p.level != 0:
            continue
        aid = (p.asset_id or "").lower()
        if "gate" in aid or "entrance_role_gate" in p.tags:
            cells |= covered_cells(p)
    return cells


def _add_approach_causeway(
    assembly: Assembly,
    *,
    gatehouse_name: str = "gatehouse",
    rows: int = 3,
    width_bays: int = 5,
    clearance_bays: int = 1,
    steps_piece: str = "steps_grand",
) -> Assembly:
    """Grand approach south of the gatehouse — one flanking pair per gate arch.

    Replaces the old rectangular apron grid (``rows`` × ``width_bays``) that
    scattered 9–12 misaligned ``steps_grand``. Heights mate to gate / L0 floor Z.
    ``rows`` / ``width_bays`` are kept for API compat but ignored.
    """
    from pae.approach_stairs import repair_approach_stairs

    del rows, width_bays  # legacy knobs — per-gate flanking only
    return repair_approach_stairs(
        assembly,
        steps_piece=steps_piece,
        clearance_bays=clearance_bays,
        building_name=gatehouse_name,
        extra_tags=frozenset(
            {
                "causeway",
                "grand_approach",
                gatehouse_name,
                f"building:{gatehouse_name}",
            }
        ),
    )


def _tag_post_merge_buttresses(
    assembly: Assembly,
    range_names: Set[str],
) -> Assembly:
    """Attach ``building:*`` / range tags to post-merge buttress piers.

    ``apply_buttresses`` places sound outward piers but does not stamp range
    markers. Without ``building:`` tags, ``freestanding`` treats each pier stack
    as an orphan island. Copy markers from the wall bay the pier shares.
    """
    if not range_names:
        return assembly

    wall_tags_by_cell: Dict[Cell, Set[str]] = {}
    for p in assembly.placements:
        if p.kind != "wall" or p.level != 0:
            continue
        markers = {
            t
            for t in p.tags
            if t in range_names or t.startswith("building:")
        }
        if not markers:
            continue
        for cell in covered_cells(p):
            wall_tags_by_cell.setdefault(cell, set()).update(markers)

    if not wall_tags_by_cell:
        return assembly

    updated: List[SolidPlacement] = []
    changed = False
    for p in assembly.placements:
        if p.asset_id != "buttress" or "trim" not in p.tags:
            updated.append(p)
            continue
        if any(t.startswith("building:") for t in p.tags):
            updated.append(p)
            continue
        markers: Set[str] = set()
        for cell in covered_cells(p):
            markers |= wall_tags_by_cell.get(cell, set())
        if not markers:
            # Fall back to the placement cell (pier often sits in the wall cell).
            markers |= wall_tags_by_cell.get(p.cell, set())
        if not markers:
            updated.append(p)
            continue
        changed = True
        updated.append(
            SolidPlacement(
                piece_id=p.piece_id,
                asset_id=p.asset_id,
                kind=p.kind,
                cell=p.cell,
                level=p.level,
                yaw=p.yaw,
                offset_cm=p.offset_cm,
                size_cm=p.size_cm,
                rotates_about_center=p.rotates_about_center,
                tags=p.tags | frozenset(markers),
            )
        )

    if not changed:
        return assembly
    return Assembly(
        placements=updated,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def _stamp_fortress_validate_tags(assembly: Assembly) -> Assembly:
    """Stamp markers so ``pae.fortress_validate`` existence checks activate.

    Massing already places gate / towers / approach geometry; validate looks for
    ``fortress_compound`` (and ``grand_approach`` on the causeway). Minimal tag
    wiring only — does not redesign layout or trim.
    """
    marker = "fortress_compound"
    stamped: List[SolidPlacement] = []
    for p in assembly.placements:
        if marker in p.tags:
            stamped.append(p)
            continue
        stamped.append(
            SolidPlacement(
                piece_id=p.piece_id,
                asset_id=p.asset_id,
                kind=p.kind,
                cell=p.cell,
                level=p.level,
                yaw=p.yaw,
                offset_cm=p.offset_cm,
                size_cm=p.size_cm,
                rotates_about_center=p.rotates_about_center,
                tags=p.tags | frozenset({marker}),
            )
        )
    return Assembly(
        placements=stamped,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def check_fortress_compound(assembly: Assembly) -> List[Failure]:
    """South curtain chain + twin gate arches + keep presence."""
    from pae.existence import check_entrance_existence
    from pae.spec import fortress_gatehouse_spec

    failures = check_range_chain_connection(
        assembly, ["west_curtain", "gatehouse", "east_curtain"]
    )
    failures.extend(
        check_entrance_existence(fortress_gatehouse_spec().entrances, assembly)
    )
    gates = [
        p
        for p in assembly.placements
        if "gatehouse" in p.tags
        and (
            p.asset_id in ("wall_gate_arch", "wall_gate_arch_grand")
            or "gate" in (p.asset_id or "").lower()
        )
        and p.kind == "wall"
    ]
    if len(gates) < 2:
        failures.append(
            Failure(
                check="fortress_twin_gate",
                message=(
                    f"fortress gatehouse needs ≥2 gate arch leaves "
                    f"(wall_gate_arch / wall_gate_arch_grand); got {len(gates)}"
                ),
                world_xyz=None,
            )
        )
    keep_pieces = [p for p in assembly.placements if "north_keep" in p.tags]
    if not keep_pieces:
        failures.append(
            Failure(
                check="fortress_keep",
                message="fortress compound missing north_keep range",
                world_xyz=None,
            )
        )
    return failures


def build_fortress_compound(
    *,
    bailey=None,
    site_options: Optional[SiteOptions] = None,
    balconies: bool = False,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Assemble a flat-ground fortress / bailey campus approximating a castle plan.

    Composition (reuses curtain + compound patterns):
      * south curtain walls with buttresses + parapets + battlements
      * twin-arch gatehouse with needle-spired drums
      * west/east cloister ranges with court-facing arcade around an open court
      * north multi-storey keep/manor with steep hip roof + dormers + buttresses
      * grand exterior approach stairs (``steps_grand`` flanking causeway, ``grand_approach``)

    Stamps ``fortress_compound`` (+ ``grand_approach`` on the causeway) for
    ``pae.fortress_validate``. Balcony galleries default off — court-facing
    gallery roofs currently fail ``roof_bears_on_wall``; cloister arcade carries
    the walkway read.
    """
    from pae.pipeline import run_through_assemble
    from pae.site import FORTRESS_BAILEY_SITE
    from pae.spec import FortressBaileySpec, fortress_bailey_compound_spec

    cfg = bailey if bailey is not None else fortress_bailey_compound_spec()
    if not isinstance(cfg, FortressBaileySpec):
        cfg = FortressBaileySpec()

    styles = fortress_bailey_ranges(cfg)
    if not balconies:
        styles = [
            RangeStyle(
                s.name,
                s.cell_offset,
                s.trim,
                s.label,
                s.spec,
                BalconySpec(enabled=False),
            )
            for s in styles
        ]

    layout = CompoundLayout(ranges=[s.name for s in styles])
    fortress_connections = fortress_compound_connections()
    instances: List[BuildingInstance] = []
    for style in styles:
        _, _, assembled, report = run_through_assemble(style.spec)
        if not report.ok:
            return assembled, layout, report
        trimmed, treport = trim(assembled, style.trim)
        if not treport.ok:
            return assembled, layout, treport
        from pae.anchors import apply_light_anchors
        from pae.fitout import fitout_greybox

        if style.name in {
            "north_keep",
            "gatehouse",
            "west_cloister",
            "east_cloister",
        }:
            decor_seed = int(getattr(style.spec, "seed", 0)) + sum(
                ord(c) for c in style.name
            )
            trimmed, _ = fitout_greybox(trimmed, seed=decor_seed)
            trimmed, _ = apply_light_anchors(trimmed)
        layout.per_range_trim[style.name] = sum(
            1 for p in trimmed.placements if "trim" in p.tags
        )
        instances.append(
            BuildingInstance(
                trimmed,
                style.cell_offset,
                style.name,
                structure=fortress_connections.structure_id,
            )
        )

    merged, mreport = place_buildings(instances)
    if not mreport.ok:
        return merged, layout, mreport

    from pae.compound_unify import unify_compound_assembly
    from pae.stair_occupancy import repair_stair_landing_walls

    # After merge: drop helix quarters that a neighbour roof now blocks.
    merged = unify_compound_assembly(merged, connections=fortress_connections)
    merged = repair_shell_wall_level_support(merged)
    merged = _strip_trim_tower_helixes(merged)
    merged = repair_stair_landing_walls(merged)
    merged = repair_junction_deck_headroom(merged)

    compound_failures = check_fortress_compound(merged)
    if compound_failures:
        return merged, layout, Report.from_failures(compound_failures)

    curtain_names = {s.name for s in styles if "curtain" in s.name}
    merged = _add_curtain_battlements(merged, curtain_names)
    merged = _add_approach_causeway(
        merged,
        rows=cfg.approach_rows,
        width_bays=cfg.approach_width_bays,
        clearance_bays=getattr(cfg, "approach_clearance_bays", 1),
        steps_piece="steps_grand",
    )

    layout.courtyard = _courtyard_cells(_ground_cells(merged))
    cloister_names = [s.name for s in styles if "cloister" in s.name]
    merged = _add_cloister_arcade(
        merged,
        layout.courtyard,
        cloister_names,
        arcade_piece=FORTRESS_CLOISTER_TRIM.arcade_piece,
        pier_piece=FORTRESS_CLOISTER_TRIM.arcade_pier_piece,
    )

    from pae.trim import TrimOptions as _TrimOptions, apply_buttresses

    # Post-merge re-place so buttress_outward sees the full campus interior
    # (kit contract). Per-range trim still has buttresses=True so pre-merge
    # emit works for single-range paths; apply_buttresses strips + re-places.
    buttress_names = curtain_names | {"north_keep", "gatehouse"}
    merged, _ = apply_buttresses(
        merged,
        _TrimOptions(buttresses=True, buttress_piece="buttress"),
        range_names=buttress_names,
    )
    merged = _tag_post_merge_buttresses(merged, buttress_names)

    if balconies:
        merged, balcony_cells, breport = add_balconies(
            merged, layout.courtyard, styles
        )
        if not breport.ok:
            return merged, layout, breport
        layout.balcony_cells = balcony_cells

    opts = site_options if site_options is not None else FORTRESS_BAILEY_SITE
    sited, site_layout, sreport = build_site(merged, opts)
    if not sreport.ok:
        return sited, layout, sreport
    layout.courtyard = site_layout.courtyard
    sited = _stamp_fortress_validate_tags(sited)
    # Final unify after arcade/buttress/site stamps — sealed interfaces stay illegal.
    sited = unify_compound_assembly(sited, connections=fortress_connections)
    sited = repair_shell_wall_level_support(sited)
    sited = _strip_trim_tower_helixes(sited)
    sited = repair_stair_landing_walls(sited)
    sited = repair_junction_deck_headroom(sited)
    return sited, layout, Report.from_failures([])


def build_fortress_bailey_compound(
    *,
    bailey=None,
    site_options: Optional[SiteOptions] = None,
    balconies: bool = False,
) -> Tuple[Assembly, CompoundLayout, Report]:
    """Alias for :func:`build_fortress_compound`."""
    return build_fortress_compound(
        bailey=bailey, site_options=site_options, balconies=balconies
    )

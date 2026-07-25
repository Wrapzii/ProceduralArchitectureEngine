"""Trim stage — places the kit pieces the assembler never reaches for.

WHY THIS EXISTS: 32 of the kit's 49 pieces were unreachable from any spec.  Railings,
buttresses, dormers, chimneys, spires and colonnades existed as geometry, passed their unit
tests, and could never appear in a building.  The gallery therefore read as sheds with lids.

Trim is a **pure, additive** pass over a finished assembly: it reads placements, works out
where trim belongs, and returns a new assembly with extra placements.  It never moves or
deletes anything the assembler produced, which is why it can live outside ``assemble.py``
and be developed without fighting the solver.

Ordering: assemble → **trim** → decorate → validate.  Trim runs before decorate so props
can be scattered onto terraces the trim pass created.

What it places, and the rule each follows:

  RAILINGS    every open edge of an upper deck, and every floor_hole perimeter, gets a
              railing. This is a safety rule in the real world and a "you can walk off the
              building" bug in ours.
  BUTTRESSES  exterior walls of buildings ≥ 3 storeys get buttresses on a regular bay
              rhythm — the taller the range, the more it needs them to read as masonry.
  ROOFLINE    flat decks get parapets; pitched roofs get chimneys on the gable ends and
              dormers on the long slopes; towers get a spire and a finial.
  COLONNADE   faces onto a courtyard get a free-standing arcade at ground level — the
              cloister walk that makes a courtyard read as a courtyard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.boundary import FACE_YAW, boundary_offset_cm, outward_offset_cm
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    placement_world_aabb,
)
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report

Cell = Tuple[int, int]

# Rhythm / threshold constants — all in bays or storeys, never centimetres.
#: Mirror of ``validate.HEADROOM_CLEARANCE_CM``; imported lazily there to avoid a cycle.
_HEADROOM_CM = 210.0
BUTTRESS_MIN_STOREYS = 3
BUTTRESS_CASTLE_MIN_STOREYS = 2
BUTTRESS_EVERY_BAYS = 2
DORMER_EVERY_BAYS = 2
CHIMNEY_EVERY_BAYS = 4
SPIRE_MIN_TOWER_PIECES = 2
_STEEP_ROOF_HEIGHT_FRAC = 0.55  # of STOREY — pitched slope taller than flat deck


@dataclass(frozen=True)
class TrimOptions:
    """Which trim families to place. Off switches exist so a bare massing test can
    assert on the assembler's output without trim noise."""

    railings: bool = True
    buttresses: bool = True
    roofline: bool = True
    colonnade: bool = True
    parapets: bool = True
    railing_piece: str = "railing_metal"
    balustrade_piece: str = "balustrade_stone"
    parapet_piece: str = "parapet_solid"
    buttress_piece: str = "buttress"
    dormer_piece: str = "dormer_gabled"
    chimney_piece: str = "chimney_stack"
    spire_piece: str = "spire_octagonal"
    finial_piece: str = "finial"
    arcade_piece: str = "wall_arcade"
    arcade_pier_piece: str = "pier_square"
    exterior_steps: bool = False
    steps_piece: str = "steps_external"
    buttress_min_storeys: Optional[int] = None


def _buttress_min_storeys(assembly: Assembly, opts: TrimOptions) -> int:
    if opts.buttress_min_storeys is not None:
        return opts.buttress_min_storeys
    if getattr(assembly, "building_class", "generic") == "castle":
        return BUTTRESS_CASTLE_MIN_STOREYS
    if any(
        "curtain" in p.tags
        for p in assembly.placements
        if p.kind == "wall"
    ):
        return BUTTRESS_CASTLE_MIN_STOREYS
    return BUTTRESS_MIN_STOREYS


def _effective_dormer_piece(opts: TrimOptions, roof: SolidPlacement) -> str:
    """Steep roof planes warrant the taller dormer variant when registered."""
    if opts.dormer_piece != "dormer_gabled":
        return opts.dormer_piece
    steep_h = STOREY_CM * _STEEP_ROOF_HEIGHT_FRAC
    if roof.size_cm[2] >= steep_h - TOL_CM and "dormer_steep" in catalog_by_id():
        return "dormer_steep"
    return opts.dormer_piece


def _placement(
    piece_id: str,
    cell: Cell,
    level: int,
    *,
    yaw: int = 0,
    offset_cm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    suffix: str = "",
) -> SolidPlacement:
    """Build a placement from the catalog, so size and tags are never re-declared."""
    desc = catalog_by_id()[piece_id]
    cx, cy = cell
    pid = f"{piece_id}_{level}_{cx}_{cy}"
    if suffix:
        pid = f"{pid}_{suffix}"
    return SolidPlacement(
        piece_id=pid,
        asset_id=piece_id,
        kind=desc.kind,
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"trim"}),
    )


# ---------------------------------------------------------------------------
# Reading the assembly
# ---------------------------------------------------------------------------


def _by_kind(assembly: Assembly, *kinds: str) -> List[SolidPlacement]:
    want = set(kinds)
    return [p for p in assembly.placements if p.kind in want]


def covered_cells(p: SolidPlacement) -> Set[Cell]:
    """Every grid cell a placement actually covers.

    Floors, roofs and ground slabs are emitted as ONE spanning placement per wing (the
    GROUND_SKIRT / roof-span rule), so ``p.cell`` is only its origin.  Reasoning per
    ``p.cell`` puts a parapet on the corner of a 5-bay roof and leaves the other four bays
    bare — which is exactly the floating-parapet defect the validator caught here.
    """
    mn, mx = placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )
    # The inset must never exceed HALF THE PIECE, or a thin piece flush against a cell's
    # far boundary is pushed into the NEXT cell: a 60 cm wall on the east edge of cell 9,
    # inset by 100 cm, reports as cell 10. That inflated every range by one cell, which
    # pushed the balcony gallery a full bay inward and left decks 4 m short of the wall.
    eps_x = min(MODULE_CM * 0.25, (mx[0] - mn[0]) * 0.5)
    eps_y = min(MODULE_CM * 0.25, (mx[1] - mn[1]) * 0.5)
    x0 = int(math.floor((mn[0] + eps_x) / MODULE_CM))
    x1 = int(math.ceil((mx[0] - eps_x) / MODULE_CM))
    y0 = int(math.floor((mn[1] + eps_y) / MODULE_CM))
    y1 = int(math.ceil((mx[1] - eps_y) / MODULE_CM))
    cells = {(x, y) for x in range(x0, max(x1, x0 + 1)) for y in range(y0, max(y1, y0 + 1))}
    return cells or {p.cell}


def _cells_of(placements: Sequence[SolidPlacement]) -> Set[Cell]:
    out: Set[Cell] = set()
    for p in placements:
        out |= covered_cells(p)
    return out


def _levels(assembly: Assembly) -> List[int]:
    return sorted({p.level for p in assembly.placements})


def _wall_cells_by_level(assembly: Assembly) -> Dict[int, Set[Cell]]:
    """Cells blocked for open-edge railings: façade walls and tower drum arcs.

    ``tower_arc`` must count — otherwise a rampart ``tower_deck`` whose
    ``covered_cells`` spill into peripheral bays looks like an open terrace and
    grows floating balustrades mid-drum.
    """
    out: Dict[int, Set[Cell]] = {}
    for p in _by_kind(assembly, "wall", "tower_arc"):
        out.setdefault(p.level, set()).update(covered_cells(p))
    return out


def _deck_cells_by_level(assembly: Assembly) -> Dict[int, Set[Cell]]:
    """Floor cells per level, excluding holes (you do not railing over a hole's slab).

    Tower rampart decks (``tower_deck`` / ``tower_top``) are excluded: they sit above
    the storey datum (junction plate) and are already guarded by battlements/crenels.
    Treating them as ordinary decks plants ``balustrade_stone`` at level*STOREY with
    nothing underneath — the floating-balustrade defect on gatehouse/chapel/library.
    """
    out: Dict[int, Set[Cell]] = {}
    for p in _by_kind(assembly, "floor"):
        if "hole" in p.asset_id:
            continue
        if "tower_deck" in p.tags or "tower_top" in p.tags:
            continue
        out.setdefault(p.level, set()).update(covered_cells(p))
    return out


def _hole_cells_by_level(assembly: Assembly) -> Dict[int, Set[Cell]]:
    out: Dict[int, Set[Cell]] = {}
    for p in _by_kind(assembly, "floor"):
        if "hole" in p.asset_id:
            out.setdefault(p.level, set()).update(covered_cells(p))
    return out


_NEIGHBOURS = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}

# Boundary-line placement (rotation compensation + far-edge rule) lives in pae.boundary
# so trim, site and the assembler cannot drift apart on it.
_FACE_YAW = FACE_YAW
_OPPOSITE = {"south": "north", "north": "south", "west": "east", "east": "west"}


def _face_offset(
    face: str,
    size_cm: Tuple[float, float, float],
    z_cm: float = 0.0,
) -> Tuple[float, float, float]:
    return boundary_offset_cm(face, size_cm, z_cm=z_cm)


def _open_edges(cells: Set[Cell], blocked: Set[Cell]) -> List[Tuple[Cell, str]]:
    """Edges of the cell set with neither a neighbouring deck cell nor a wall."""
    edges: List[Tuple[Cell, str]] = []
    for cx, cy in sorted(cells):
        for face, (dx, dy) in _NEIGHBOURS.items():
            n = (cx + dx, cy + dy)
            if n in cells or n in blocked:
                continue
            if (cx, cy) in blocked:
                continue
            edges.append(((cx, cy), face))
    return edges


# ---------------------------------------------------------------------------
# Trim families
# ---------------------------------------------------------------------------


def _stair_landing_edges(assembly: Assembly) -> Set[Tuple[int, Cell, Cell]]:
    """``(deck_level, hole_cell, deck_cell)`` triples a stair run arrives through.

    A straight run climbs along its long axis, so the cell it steps off onto is one bay
    past its top end in that direction. Both that cell and the well cell it leaves are
    needed, because the railing loop works per (hole cell, neighbouring deck cell) pair
    and only that ONE pair may be left unguarded — every other edge of the well is still
    a fall and still gets a rail.
    """
    edges: Set[Tuple[int, Cell, Cell]] = set()
    for p in _by_kind(assembly, "stair"):
        cells = sorted(covered_cells(p))
        if len(cells) < 2:
            continue
        (x0, y0), (x1, y1) = cells[0], cells[-1]
        sx = (x1 > x0) - (x1 < x0)
        sy = (y1 > y0) - (y1 < y0)
        if sx == 0 and sy == 0:
            continue
        # Either end may be the head — the run's yaw decides which way it climbs, and
        # yaw is not reliably recoverable here, so open BOTH ends of the well. An extra
        # open edge is a missing rail on one side; a wrong closed edge is a dead end.
        for tail, step in (((x1, y1), (sx, sy)), ((x0, y0), (-sx, -sy))):
            edges.add((p.level + 1, tail, (tail[0] + step[0], tail[1] + step[1])))
    return edges


def _courtyard_cells_from_plan(assembly: Assembly) -> Set[Cell]:
    """Ground-level courtyard cells from the floor plan (open court void)."""
    from pae.plan import CellRole

    layer = assembly.floor_plan.get(0)
    if layer is None:
        return set()
    court: Set[Cell] = set()
    ox, oy = layer.origin_cell
    role = getattr(CellRole, "COURTYARD", None)
    for ly in range(layer.height):
        for lx in range(layer.width):
            if layer.cells[ly][lx] == role:
                court.add((ox + lx, oy + ly))
    return court


def _barrier_edges_by_level(assembly: Assembly) -> Dict[int, Set[Tuple[Cell, str]]]:
    """``(cell, face)`` pairs already guarded by a barrier piece."""
    out: Dict[int, Set[Tuple[Cell, str]]] = {}
    for p in _by_kind(assembly, "barrier"):
        cell = p.cell
        face = {0: "south", 90: "west", 180: "north", 270: "east"}.get(p.yaw, "")
        if face:
            out.setdefault(p.level, set()).add((cell, face))
    return out


def _gallery_court_railings(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Balustrades on upper decks that overlook the open courtyard (gallery walk).

    Generic ``_open_edges`` misses some cloister galleries when interior walls
    register on the court face; this pass keys off the ground court footprint.
    """
    court = _courtyard_cells_from_plan(assembly)
    if not court:
        return []
    decks = _deck_cells_by_level(assembly)
    walls = _wall_cells_by_level(assembly)
    guarded = _barrier_edges_by_level(assembly)
    bal_desc = catalog_by_id()[opts.balustrade_piece]
    thick = bal_desc.size_cm
    out: List[SolidPlacement] = []

    for level, cells in decks.items():
        if level <= 0:
            continue
        wall_cells = walls.get(level, set())
        for cx, cy in sorted(cells):
            for face, (dx, dy) in _NEIGHBOURS.items():
                n = (cx + dx, cy + dy)
                if n not in court:
                    continue
                if n in cells or n in wall_cells:
                    continue
                if ((cx, cy), face) in guarded.get(level, set()):
                    continue
                out.append(
                    _placement(
                        opts.balustrade_piece,
                        (cx, cy),
                        level,
                        yaw=_FACE_YAW[face],
                        offset_cm=_face_offset(face, thick),
                        suffix=f"gallery_{face}",
                    )
                )
    return out


def _railings(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Railings on open upper-deck edges and around every floor hole."""
    out: List[SolidPlacement] = []
    decks = _deck_cells_by_level(assembly)
    walls = _wall_cells_by_level(assembly)
    holes = _hole_cells_by_level(assembly)
    thick = catalog_by_id()[opts.railing_piece].size_cm

    for level, cells in decks.items():
        if level <= 0:
            continue  # ground deck has no drop to guard
        wall_cells = walls.get(level, set())
        for cell, face in _open_edges(cells, wall_cells):
            out.append(
                _placement(
                    opts.balustrade_piece,
                    cell,
                    level,
                    yaw=_FACE_YAW[face],
                    offset_cm=_face_offset(
                        face, catalog_by_id()[opts.balustrade_piece].size_cm
                    ),
                    suffix=face,
                )
            )

    # Floor holes: guard the void, but stand the railing on the DECK cell beside it, not
    # on the hole cell. A railing placed in the hole has nothing under it — the validator
    # correctly reports it as floating, because you would be bolting a handrail to air.
    # Where a stair ARRIVES on the deck, the guarding must stop. Railing all four sides
    # of a well fences the person climbing it in at the top — user: "the top of that
    # staircase has the railing blocking you from exiting it." The landing edge is the
    # one pair (hole cell, deck cell) the run travels through as it reaches the deck.
    landings = _stair_landing_edges(assembly)

    for level, hole_cells in holes.items():
        # The upper deck is emitted as ONE spanning slab covering the hole cells too, so
        # "is there deck beside this hole" is only meaningful after subtracting the holes.
        # Without this a railing gets planted in the neighbouring half of the same void.
        deck = decks.get(level, set()) - hole_cells
        for cx, cy in sorted(hole_cells):
            for face, (dx, dy) in _NEIGHBOURS.items():
                n = (cx + dx, cy + dy)
                if n not in deck:
                    continue  # no deck beside it — nothing to stand on
                if (level, (cx, cy), n) in landings:
                    continue  # the way out — leave it open
                out.append(
                    _placement(
                        opts.railing_piece,
                        n,
                        level,
                        yaw=_FACE_YAW[_OPPOSITE[face]],
                        offset_cm=_face_offset(_OPPOSITE[face], thick),
                        suffix=f"hole_{face}",
                    )
                )
    out.extend(_gallery_court_railings(assembly, opts))
    return out


def _interior_deck_cells(assembly: Assembly) -> Set[Cell]:
    """Walkable / structural deck cells — must match ``fortress_validate.check_buttress_outward``."""
    interior: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("floor", "ground", "plinth"):
            interior |= covered_cells(p)
    return interior


def _building_tags(p: SolidPlacement) -> Set[str]:
    return {t for t in p.tags if t.startswith("building:")}


def _inherit_buttress_tags(wall: SolidPlacement, base: frozenset) -> frozenset:
    """Copy range identity from the braced wall so freestanding groups by building."""
    extra = {t for t in wall.tags if t.startswith("building:")}
    for t in wall.tags:
        if t.endswith("_curtain") or t in ("north_keep", "gatehouse", "curtain"):
            extra.add(t)
    return base | extra


def _buttress_placement(
    wall: SolidPlacement,
    opts: TrimOptions,
    cell: Cell,
    *,
    level: int,
    yaw: int,
    offset_cm: Tuple[float, float, float],
    suffix: str,
) -> SolidPlacement:
    p = _placement(
        opts.buttress_piece,
        cell,
        level,
        yaw=yaw,
        offset_cm=offset_cm,
        suffix=suffix,
    )
    return SolidPlacement(
        piece_id=p.piece_id,
        asset_id=p.asset_id,
        kind=p.kind,
        cell=p.cell,
        level=p.level,
        yaw=p.yaw,
        offset_cm=p.offset_cm,
        size_cm=p.size_cm,
        rotates_about_center=p.rotates_about_center,
        tags=_inherit_buttress_tags(wall, p.tags),
    )


def _buttresses(
    assembly: Assembly,
    opts: TrimOptions,
    *,
    range_names: Optional[Set[str]] = None,
) -> List[SolidPlacement]:
    """Buttresses on the exterior faces of tall ranges, on a bay rhythm.

    Works from WALL PLACEMENTS, not from the set of cells that contain walls. The first
    version picked a face by "this neighbour is not interior", which says nothing about
    whether a wall exists on that face — so buttresses were planted against thin air on
    corner cells. The freestanding check caught five of them in the school.
    """
    out: List[SolidPlacement] = []
    min_storeys = _buttress_min_storeys(assembly, opts)
    if assembly.storeys < min_storeys:
        return out

    # A round tower has no flat face to brace and no thrust to take: buttressing a drum
    # plants piers inside the tower and across its door. User: "there's buttresses inside
    # of the spire." Exclude every cell the drum occupies, at any level.
    drum_cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("tower_arc", "tower_cap") or "tower_arc" in p.asset_id:
            drum_cells |= covered_cells(p)

    walls = [
        p for p in _by_kind(assembly, "wall")
        if p.level == 0
        and not (covered_cells(p) & drum_cells)
        and (
            range_names is None
            or any(f"building:{n}" in p.tags for n in range_names)
        )
    ]
    if not walls:
        return out

    # Global deck footprint — same source as ``buttress_outward``. Per-range trim cannot
    # see neighbouring ranges; post-merge ``apply_buttresses`` re-runs with this set so
    # piers never land on cloister/court slabs (fortress campus defect).
    interior = _interior_deck_cells(assembly)
    depth = catalog_by_id()[opts.buttress_piece].size_cm

    for i, wall in enumerate(sorted(walls, key=lambda p: (p.cell, p.piece_id))):
        if i % BUTTRESS_EVERY_BAYS:
            continue
        bb_min, bb_max = placement_world_aabb(
            wall.cell[0], wall.cell[1], wall.level, wall.yaw, wall.size_cm,
            wall.offset_cm, rotates_about_center=wall.rotates_about_center,
        )
        cell = wall.cell
        cx0, cy0 = cell[0] * MODULE_CM, cell[1] * MODULE_CM
        near = MODULE_CM * 0.5
        if (bb_max[0] - bb_min[0]) < (bb_max[1] - bb_min[1]):
            face = "west" if (bb_min[0] - cx0) < near else "east"
        else:
            face = "south" if (bb_min[1] - cy0) < near else "north"
        cand: Optional[SolidPlacement] = None
        for f in [face] + [g for g in _NEIGHBOURS if g != face]:
            dx, dy = _NEIGHBOURS[f]
            outward = (cell[0] + dx, cell[1] + dy)
            if outward in interior:
                continue  # pier would stand on a deck slab
            if outward in drum_cells:
                continue  # projecting into the tower drum
            yaw, off = _pier_pose(f, depth)
            trial = _buttress_placement(
                wall,
                opts,
                cell,
                level=0,
                yaw=yaw,
                offset_cm=off,
                suffix=f,
            )
            if not _buttress_is_sound(trial, (bb_min, bb_max), interior):
                continue
            cand = trial
            break
        if cand is None:
            continue  # no sound face on this bay — a missing buttress beats a wrong one
        out.append(cand)
        for lvl in range(1, max(1, assembly.storeys - 1)):
            out.append(
                _buttress_placement(
                    wall,
                    opts,
                    cand.cell,
                    level=lvl,
                    yaw=cand.yaw,
                    offset_cm=cand.offset_cm,
                    suffix=f"{cand.piece_id.rsplit('_', 1)[-1]}_l{lvl}",
                )
            )
    return out


def _strip_buttress_trim(assembly: Assembly, piece_id: str = "buttress") -> Assembly:
    """Remove prior buttress trim so a post-merge pass can re-place outward piers."""
    kept = [
        p
        for p in assembly.placements
        if not (p.asset_id == piece_id and "trim" in p.tags)
    ]
    if len(kept) == len(assembly.placements):
        return assembly
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


def apply_buttresses(
    assembly: Assembly,
    opts: TrimOptions,
    *,
    range_names: Optional[Set[str]] = None,
) -> Tuple[Assembly, List[SolidPlacement]]:
    """Post-merge buttress pass — global interior, optional per-range filter.

    Per-range ``trim(..., buttresses=True)`` runs before ``place_buildings`` and cannot
    see adjacent ranges; merged campuses must call this after merge so
    ``buttress_outward`` stays green.
    """
    if not opts.buttresses:
        return assembly, []
    base = _strip_buttress_trim(assembly, opts.buttress_piece)
    extra = _buttresses(base, opts, range_names=range_names)
    if not extra:
        return base, []
    merged = Assembly(
        placements=list(base.placements) + extra,
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
        aperture_policy=base.aperture_policy,
        room_specs=list(getattr(base, "room_specs", []) or []),
        building_class=getattr(base, "building_class", "generic"),
        stair_kind=getattr(base, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            base, "wide_stair_well_available", False
        ),
    )
    return merged, extra


#: Which yaw puts a piece's local +X face against the wall on each face. A buttress
#: mates to the wall with its BACK (``buttress()``'s socket sits at ``pos_cm=(depth,..)``
#: with normal ``+X``), so it needs the OPPOSITE yaw to ``FACE_OUTWARD_YAW`` — that table
#: is for pieces whose +X points away. Getting this backwards mounted every buttress with
#: its battered face buried in the masonry and its flat back to the street, which is why
#: they read as blocks that "aren't even facing the buildings".
_PIER_BACK_YAW = {"west": 0, "east": 180, "south": 90, "north": 270}


def _pier_pose(
    face: str,
    size_cm: Tuple[float, float, float],
) -> Tuple[int, Tuple[float, float, float]]:
    """Yaw + offset for a pier that BEARS on ``face`` with its back and projects out.

    Takes the target footprint from :func:`outward_offset_cm` — which gets the position
    right — then re-solves the offset for the yaw that actually points the piece's back
    at the wall, so the piece lands in the same slot the right way round.
    """
    ref_yaw, ref_off = outward_offset_cm(face, size_cm)
    want_min, _ = placement_world_aabb(0, 0, 0, ref_yaw, size_cm, ref_off)
    yaw = _PIER_BACK_YAW[face]
    got_min, _ = placement_world_aabb(0, 0, 0, yaw, size_cm, (0.0, 0.0, 0.0))
    return yaw, (
        want_min[0] - got_min[0],
        want_min[1] - got_min[1],
        0.0,
    )


def _buttress_is_sound(
    butt: SolidPlacement,
    wall_box: Tuple[Tuple[float, float, float], Tuple[float, float, float]],
    interior: Set[Cell],
) -> bool:
    """A buttress must bear on its wall, and must not stand inside the building.

    This is the orientation check the Validation Handbook's seven questions owe for any
    piece that attaches to a face: *what does it attach to* (this wall) and *which way
    does it face* (away from the interior).
    """
    bmn, bmx = placement_world_aabb(
        butt.cell[0], butt.cell[1], butt.level, butt.yaw, butt.size_cm,
        butt.offset_cm, rotates_about_center=butt.rotates_about_center,
    )
    wmn, wmx = wall_box
    # Bearing: share real extent on every axis, not merely graze a corner.
    for i in (0, 1, 2):
        if min(bmx[i], wmx[i]) - max(bmn[i], wmn[i]) < -TOL_CM:
            return False
    return not (covered_cells(butt) & interior)


def _roofline(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Parapets on flat decks, chimneys and dormers on pitched roofs, spires on towers."""
    from pae.roof_edging import claimed_roof_edges, edge_is_claimed

    out: List[SolidPlacement] = []
    roofs = _by_kind(assembly, "roof")
    if not roofs:
        return out

    flat = [p for p in roofs if "flat" in p.asset_id]
    pitched = [p for p in roofs if "flat" not in p.asset_id]

    if opts.parapets and flat:
        cells = _cells_of(flat)
        # Never plant parapets inside a round drum — crown/rampart owns that rim.
        drum_cells: Set[Cell] = set()
        for p in assembly.placements:
            if p.kind in ("tower_arc", "tower_cap") or "tower_arc" in p.asset_id:
                drum_cells |= covered_cells(p)
        cells -= drum_cells
        claimed = claimed_roof_edges(assembly)
        thick = catalog_by_id()[opts.parapet_piece].size_cm
        level = max(p.level for p in flat)
        # Stand the parapet on the roof's TOP surface. Using the level datum puts it at
        # the storey floor instead — a parapet round the ankles of the building.
        deck_top = max(p.offset_cm[2] + p.size_cm[2] for p in flat if p.level == level)
        for cell, face in _open_edges(cells, set()):
            if cell in drum_cells:
                continue
            if edge_is_claimed(claimed, level=level, cell=cell, face=face):
                continue
            out.append(
                _placement(
                    opts.parapet_piece,
                    cell,
                    level,
                    yaw=_FACE_YAW[face],
                    offset_cm=_face_offset(face, thick, z_cm=deck_top),
                    suffix=f"parapet_{face}",
                )
            )

    for i, p in enumerate(sorted(pitched, key=lambda q: (q.cell, q.level))):
        if "gable" in p.asset_id:
            if i % CHIMNEY_EVERY_BAYS == 0:
                out.append(
                    _placement(
                        opts.chimney_piece,
                        p.cell,
                        p.level,
                        offset_cm=(0.0, 0.0, p.size_cm[2] * 0.5),
                        suffix="stack",
                    )
                )

    slopes = [
        p for p in pitched
        if "gable" not in p.asset_id and "valley" not in p.asset_id
    ]
    for i, p in enumerate(sorted(slopes, key=lambda q: (q.cell, q.level))):
        if i % DORMER_EVERY_BAYS != 0:
            continue
        dormer_id = _effective_dormer_piece(opts, p)
        dormer_h = catalog_by_id()[dormer_id].size_cm[2]
        z_seat = p.offset_cm[2] + p.size_cm[2] * 0.42 - dormer_h * 0.05
        out.append(
            _placement(
                dormer_id,
                p.cell,
                p.level,
                offset_cm=(0.0, 0.0, z_seat),
                suffix="dormer",
            )
        )

    # Towers: spire on the cap, finial on the spire.
    caps = [p for p in assembly.placements if p.kind == "tower_cap"]
    if len(caps) >= 1 and len(_by_kind(assembly, "tower_arc")) >= SPIRE_MIN_TOWER_PIECES:
        for cap in caps:
            top = cap.offset_cm[2] + cap.size_cm[2]
            # Centred tower caps carry an XY offset to the drum centre; spires must
            # inherit it or they land on the cell origin and fail the touch graph.
            cap_xy = (cap.offset_cm[0], cap.offset_cm[1])
            out.append(
                _placement(
                    opts.spire_piece,
                    cap.cell,
                    cap.level,
                    offset_cm=(cap_xy[0], cap_xy[1], top),
                    suffix="spire",
                )
            )
            spire_h = catalog_by_id()[opts.spire_piece].size_cm[2]
            out.append(
                _placement(
                    opts.finial_piece,
                    cap.cell,
                    cap.level,
                    offset_cm=(cap_xy[0], cap_xy[1], top + spire_h),
                    suffix="finial",
                )
            )
        out.extend(_tower_spiral_stairs(assembly, caps))
    return out


def _tower_spiral_stairs(
    assembly: Assembly,
    caps: Sequence[SolidPlacement],
) -> List[SolidPlacement]:
    """A helix up every spired tower that does not already have one.

    WHY: a tower got a drum, a cap, a spire and a finial, and nothing inside it. User:
    "still no actual helix spiral staircase inside of the spires." The tower read as a
    solid ornament rather than as something you climb.

    The helix is ``stair_spiral_quarter`` at yaw 0/90/180/270, each lifted by its own
    rise so the treads WIND rather than stack. The quarters share a cell by design —
    that is what a helix is, and why the co-occupancy rule exempts them.
    """
    out: List[SolidPlacement] = []
    catalog = catalog_by_id()
    if "stair_spiral_quarter" not in catalog:
        return out
    rise = catalog["stair_spiral_quarter"].size_cm[2]
    per_storey = max(1, int(round(STOREY_CM / rise)))
    # Clear bore of the drum: the module less the masonry on both sides.
    inner_d = MODULE_CM - 2.0 * WALL_T_CM

    already = {
        p.cell
        for p in assembly.placements
        if p.kind == "stair" and "spiral" in p.asset_id
    }
    # Decks the helix has to pass THROUGH. A stair that climbs into a solid slab is a
    # ceiling, not a stair, so every deck the helix crosses gets opened at that cell.
    # EVERY slab, including tower decks. ``_deck_cells_by_level`` skips the tower-top
    # platform, which is exactly the slab a tower helix arrives at — the stair climbed
    # into the underside of the viewing deck with no hatch through it.
    decks_at: Dict[int, Set[Cell]] = {}
    open_at: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "floor":
            continue
        bucket = open_at if p.asset_id == "floor_hole" else decks_at
        bucket.setdefault(p.level, set()).update(covered_cells(p))
    hole = catalog.get("floor_hole")

    # Lowest roof underside over each cell. A helix may not climb into a roof — the
    # chapel's tower sits under a gable and the top flights had no headroom at all.
    roof_bottom: Dict[Cell, float] = {}
    for p in assembly.placements:
        if p.kind not in ("roof", "roofline"):
            continue
        mn, _mx = placement_world_aabb(
            p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        for c in covered_cells(p):
            roof_bottom[c] = min(roof_bottom.get(c, mn[2]), mn[2])

    for cap in caps:
        if cap.cell in already:
            continue  # the assembler already built one — do not double it
        cap_xy = (cap.offset_cm[0], cap.offset_cm[1])
        # Stop BELOW the cap. Climbing to cap.level inclusive ran the top quarter into
        # the underside of the tower roof — 50 headroom criticals. The helix delivers
        # you onto the top deck; the roof above it is not somewhere you walk.
        for level in range(max(0, cap.level)):
            # Only build a flight whose EXIT is genuinely clear. ``stair_exit_clearance``
            # rejects any solid module floor over a run's top, and a tower deck spans the
            # whole drum — a hole cannot open it, because the check reads the slab itself
            # as the blockage. Emitting the flight anyway would ship a stair that climbs
            # into the underside of the viewing platform. A helix that stops one storey
            # short is honest; one that dead-ends into a slab is not.
            probe = _placement(
                "stair_spiral_quarter", cap.cell, level,
                offset_cm=(cap_xy[0], cap_xy[1], 0.0), suffix="probe",
            )
            reach = covered_cells(probe)
            if any(
                s.level == level + 1
                and s.kind == "floor"
                and s.asset_id != "floor_hole"
                and covered_cells(s) & reach
                # Mirror ``validate._is_module_solid_floor``: only a 1x1 PAD is an
                # unopenable blockage. A spanning deck can be punched with a hole; a
                # pad cannot, which is what "use floor_hole, not a pad" means.
                and max(s.size_cm[0], s.size_cm[1]) <= MODULE_CM + TOL_CM
                for s in assembly.placements
            ):
                continue
            # The NEWEL. A helix is not self-supporting — every tread is cantilevered
            # off the central post, and without it the quarters read as floating steps
            # winding round thin air. One post per storey, at the drum centre.
            if "spiral_newel" in catalog:
                # SAME offset as the treads. spiral_newel has origin="center" and
                # rotates_about_center, so cap_xy already puts it on the drum axis —
                # adding a half-module corner shift on top pushed the post off to one
                # side and the helix appeared to wind around nothing.
                out.append(
                    _placement(
                        "spiral_newel",
                        cap.cell,
                        level,
                        offset_cm=(cap_xy[0], cap_xy[1], 0.0),
                        suffix=f"newel{level}",
                    )
                )
            for q in range(per_storey):
                step = _placement(
                    "stair_spiral_quarter",
                    cap.cell,
                    level,
                    yaw=(q * 90) % 360,
                    offset_cm=(cap_xy[0], cap_xy[1], q * rise),
                    suffix=f"helix{level}_{q}",
                )
                # FIT THE TREADS INSIDE THE DRUM. Both the arc and the stair quarter are
                # nominally one module square, but the arc is a RING with WALL_T of
                # masonry at its outer radius — so a full-module tread runs straight
                # through the tower wall. On the fortress that was 213 of 524
                # interpenetrations, by far the largest single cause. The treads land on
                # the drum's inner face instead.
                step = SolidPlacement(
                    piece_id=step.piece_id,
                    asset_id=step.asset_id,
                    kind=step.kind,
                    cell=step.cell,
                    level=step.level,
                    yaw=step.yaw,
                    offset_cm=step.offset_cm,
                    size_cm=(inner_d, inner_d, step.size_cm[2]),
                    rotates_about_center=step.rotates_about_center,
                    tags=step.tags,
                )
                # Headroom, measured. Anything that would tuck under a roof slope is
                # dropped rather than shipped as a tread you cannot stand on.
                mn, mx = placement_world_aabb(
                    step.cell[0], step.cell[1], step.level, step.yaw, step.size_cm,
                    step.offset_cm, rotates_about_center=step.rotates_about_center,
                )
                ceil = min(
                    (roof_bottom[c] for c in covered_cells(step) if c in roof_bottom),
                    default=None,
                )
                if ceil is not None and ceil - mx[2] < _HEADROOM_CM:
                    continue
                out.append(step)

    # Open every deck the helix passes THROUGH. Punching only the cap cell missed the
    # rest of the drum: a centred quarter spans more than one bay, so part of the slab
    # stayed solid and the stair climbed into a ceiling. Punch by the run's real
    # footprint, not by the cell it is nominally anchored to.
    if hole is not None:
        under: Dict[int, Set[Cell]] = {}
        for p in out:
            if p.kind != "stair":
                continue
            under.setdefault(p.level, set()).update(covered_cells(p))

        # Open the ceiling directly over each flight. ``stair_exit_clearance`` looks for
        # a floor_hole at EXACTLY stair.level + 1 covering every cell the run occupies,
        # so the opening is keyed to the run, not to whichever slab happens to be up
        # there — matching the slab's own level put the hole on the wrong storey.
        opened: Set[Tuple[int, Cell]] = {
            (lvl, c) for lvl, cs in open_at.items() for c in cs
        }
        for lvl, cells in sorted(under.items()):
            top = lvl + 1
            for c in sorted(cells):
                if (top, c) in opened:
                    continue
                opened.add((top, c))
                out.append(
                    _placement(
                        "floor_hole",
                        c,
                        top,
                        offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                        suffix="helix_well",
                    )
                )
    return out


def _colonnade(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Free-standing arcade along ground-level faces that look onto a courtyard."""
    from pae.plan import CellRole
    from pae.wall_faces import claimed_wall_arcade_faces, face_is_claimed_for_arcade

    layer = assembly.floor_plan.get(0)
    if layer is None:
        return []

    court: Set[Cell] = set()
    ox, oy = layer.origin_cell
    for ly in range(layer.height):
        for lx in range(layer.width):
            if layer.cells[ly][lx] == getattr(CellRole, "COURTYARD", None):
                court.add((ox + lx, oy + ly))
    if not court:
        return []

    walls = _wall_cells_by_level(assembly).get(0, set())
    piece_id = opts.arcade_piece
    catalog = catalog_by_id()
    if piece_id not in catalog:
        return []
    thick = catalog[piece_id].size_cm
    out: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
    claimed = claimed_wall_arcade_faces(assembly)

    # ``wall_arcade`` mates to the courtyard-facing wall cell (cloister walk language).
    pier_id = opts.arcade_pier_piece
    pier_desc = catalog.get(pier_id) if pier_id else None
    if piece_id.startswith("wall_"):
        for cx, cy in sorted(court):
            for face, (dx, dy) in _NEIGHBOURS.items():
                wall_cell = (cx + dx, cy + dy)
                if wall_cell not in walls:
                    continue
                key = (wall_cell, face)
                if key in seen:
                    continue
                seen.add(key)
                outward = _OPPOSITE[face]
                if face_is_claimed_for_arcade(
                    claimed, level=0, cell=wall_cell, face=outward
                ):
                    continue
                out.append(
                    _placement(
                        piece_id,
                        wall_cell,
                        0,
                        yaw=_FACE_YAW[outward],
                        offset_cm=_face_offset(outward, thick),
                        suffix=f"cloister_{face}",
                    )
                )
        if pier_desc is not None:
            pier_seen: Set[Cell] = set()
            for cx, cy in sorted(court):
                wall_neighbors = sorted(
                    (cx + dx, cy + dy)
                    for face, (dx, dy) in _NEIGHBOURS.items()
                    if (cx + dx, cy + dy) in walls
                )
                if len(wall_neighbors) < 2:
                    continue
                cell = wall_neighbors[0]
                if cell in pier_seen:
                    continue
                pier_seen.add(cell)
                out.append(
                    _placement(
                        pier_id,
                        cell,
                        0,
                        suffix="arcade_corner",
                    )
                )
        return out

    for cx, cy in sorted(court):
        for face, (dx, dy) in _NEIGHBOURS.items():
            n = (cx + dx, cy + dy)
            if n not in walls:
                continue
            key = ((cx, cy), face)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                _placement(
                    piece_id,
                    (cx, cy),
                    0,
                    yaw=_FACE_YAW[face],
                    offset_cm=_face_offset(face, thick),
                    suffix=f"walk_{face}",
                )
            )
    return out


def _exterior_steps(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Grand approach steps outside ground-level entrance doors.

    Gate / arch leaves get **flanking** flights beside the opening (never a solid
    apron in the passage column — ``gate_passage_clear``). Heights mate to the
    gate / L0 floor threshold, not a fixed catalog rise.
    """
    from pae.approach_stairs import plan_gate_approach_steps

    return plan_gate_approach_steps(
        assembly,
        steps_piece=opts.steps_piece,
        clearance_bays=1,
    )


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def trim(
    assembly: Assembly,
    options: Optional[TrimOptions] = None,
) -> Tuple[Assembly, Report]:
    """Additive trim pass. Returns a new assembly; the input is not mutated."""
    opts = options or TrimOptions()
    extra: List[SolidPlacement] = []
    failures: List[Failure] = []

    catalog = catalog_by_id()
    for piece in (
        opts.railing_piece,
        opts.balustrade_piece,
        opts.parapet_piece,
        opts.buttress_piece,
        opts.dormer_piece,
        opts.chimney_piece,
        opts.spire_piece,
        opts.finial_piece,
        opts.arcade_piece,
        opts.steps_piece,
    ):
        if piece not in catalog:
            failures.append(
                Failure(
                    check="trim_piece_missing",
                    message=f"trim wants unknown piece {piece!r}",
                    world_xyz=None,
                )
            )
    if failures:
        return assembly, Report.from_failures(failures)

    if opts.railings:
        extra.extend(_railings(assembly, opts))
    if opts.buttresses:
        extra.extend(_buttresses(assembly, opts))
    if opts.roofline:
        extra.extend(_roofline(assembly, opts))
    if opts.colonnade:
        extra.extend(_colonnade(assembly, opts))

    # Deterministic order — the assembly hash must not depend on dict iteration.
    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))

    out = Assembly(
        placements=list(assembly.placements) + extra,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, 'room_specs', []) or []),
        building_class=getattr(assembly, 'building_class', 'generic'),
        stair_kind=getattr(assembly, 'stair_kind', 'straight'),
        wide_stair_well_available=getattr(
            assembly, 'wide_stair_well_available', False
        ),
    )
    if opts.colonnade and opts.arcade_piece.startswith("wall_"):
        from pae.wall_faces import repair_wall_face_stacks

        out = repair_wall_face_stacks(out)
    if opts.exterior_steps:
        from pae.approach_stairs import repair_approach_stairs

        out = repair_approach_stairs(
            out,
            steps_piece=opts.steps_piece,
            clearance_bays=1,
        )
    return out, Report.from_failures([])

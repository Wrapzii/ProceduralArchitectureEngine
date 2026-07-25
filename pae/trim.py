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
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, placement_world_aabb
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report

Cell = Tuple[int, int]

# Rhythm / threshold constants — all in bays or storeys, never centimetres.
BUTTRESS_MIN_STOREYS = 3
BUTTRESS_EVERY_BAYS = 2
DORMER_EVERY_BAYS = 2
CHIMNEY_EVERY_BAYS = 4
SPIRE_MIN_TOWER_PIECES = 2


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
    arcade_piece: str = "arch_freestanding"


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
    return out


def _buttresses(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Buttresses on the exterior faces of tall ranges, on a bay rhythm.

    Works from WALL PLACEMENTS, not from the set of cells that contain walls. The first
    version picked a face by "this neighbour is not interior", which says nothing about
    whether a wall exists on that face — so buttresses were planted against thin air on
    corner cells. The freestanding check caught five of them in the school.
    """
    out: List[SolidPlacement] = []
    if assembly.storeys < BUTTRESS_MIN_STOREYS:
        return out

    walls = [p for p in _by_kind(assembly, "wall") if p.level == 0]
    if not walls:
        return out

    interior = _deck_cells_by_level(assembly).get(0, set())
    depth = catalog_by_id()[opts.buttress_piece].size_cm

    for i, wall in enumerate(sorted(walls, key=lambda p: (p.cell, p.piece_id))):
        if i % BUTTRESS_EVERY_BAYS:
            continue
        bb_min, bb_max = placement_world_aabb(
            wall.cell[0], wall.cell[1], wall.level, wall.yaw, wall.size_cm,
            wall.offset_cm, rotates_about_center=wall.rotates_about_center,
        )
        # Which boundary line does this wall actually SIT on? Deriving the face from the
        # cell's neighbours instead put a west buttress against a wall standing on the
        # cell's east edge — 340 cm of masonry braced against thin air.
        cell = wall.cell
        cx0, cy0 = cell[0] * MODULE_CM, cell[1] * MODULE_CM
        near = MODULE_CM * 0.5
        if (bb_max[0] - bb_min[0]) < (bb_max[1] - bb_min[1]):
            face = "west" if (bb_min[0] - cx0) < near else "east"
        else:
            face = "south" if (bb_min[1] - cy0) < near else "north"
        dx, dy = _NEIGHBOURS[face]
        if (cell[0] + dx, cell[1] + dy) in interior:
            continue  # that face looks inward — bracing there would be inside a room
        chosen = face
        yaw, off = outward_offset_cm(chosen, depth)
        out.append(
            _placement(
                opts.buttress_piece,
                cell,
                0,
                yaw=yaw,
                offset_cm=off,
                suffix=chosen,
            )
        )
    return out


def _roofline(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Parapets on flat decks, chimneys and dormers on pitched roofs, spires on towers."""
    out: List[SolidPlacement] = []
    roofs = _by_kind(assembly, "roof")
    if not roofs:
        return out

    flat = [p for p in roofs if "flat" in p.asset_id]
    pitched = [p for p in roofs if "flat" not in p.asset_id]

    if opts.parapets and flat:
        cells = _cells_of(flat)
        thick = catalog_by_id()[opts.parapet_piece].size_cm
        level = max(p.level for p in flat)
        # Stand the parapet on the roof's TOP surface. Using the level datum puts it at
        # the storey floor instead — a parapet round the ankles of the building.
        deck_top = max(p.offset_cm[2] + p.size_cm[2] for p in flat if p.level == level)
        for cell, face in _open_edges(cells, set()):
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
        elif i % DORMER_EVERY_BAYS == 0:
            out.append(
                _placement(
                    opts.dormer_piece,
                    p.cell,
                    p.level,
                    offset_cm=(0.0, 0.0, p.size_cm[2] * 0.35),
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
    return out


def _colonnade(assembly: Assembly, opts: TrimOptions) -> List[SolidPlacement]:
    """Free-standing arcade along ground-level faces that look onto a courtyard."""
    from pae.plan import CellRole

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
    thick = catalog_by_id()[opts.arcade_piece].size_cm
    out: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
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
                    opts.arcade_piece,
                    (cx, cy),
                    0,
                    yaw=_FACE_YAW[face],
                    offset_cm=_face_offset(face, thick),
                    suffix=f"walk_{face}",
                )
            )
    return out


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
    return out, Report.from_failures([])

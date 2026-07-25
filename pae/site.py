"""Site stage — everything outside the building envelope.

WHY THIS EXISTS: PAE could generate *a building*.  A school is a site: two or three ranges
placed in relation to each other, a courtyard between them, walks connecting the doors, a
kerbed sidewalk round the boundary, lawn filling the rest, a fence and a gate at the edge.
None of that was expressible, so every render was one object on nothing.

The site stage works in the same cell grid as the building — it is not a separate
coordinate system — which is what lets a walk meet a door sill exactly instead of
approximately.

Two capabilities:

  ``place_buildings``  merges several assemblies into one, each shifted by a cell offset.
                       This is how you get past single buildings: a spec per range, then a
                       campus layout that positions them.
  ``build_site``       reads the merged footprint and lays courtyard paving, perimeter
                       walks, kerbs, lawn, boundary fence and gates around it.

Surfaces are laid with their **top** at ground level (z = 0), following the same
``−FLOOR_T`` rule the assembler uses for floors.  A walk you step up onto is a bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
from pae.boundary import FACE_YAW, boundary_offset_cm
from pae.contract import MODULE_CM
from pae.primitives.catalog import catalog_by_id
from pae.trim import covered_cells
from pae.report import Failure, Report

Cell = Tuple[int, int]

DEFAULT_WALK_WIDTH_BAYS = 1
DEFAULT_MARGIN_BAYS = 3  # lawn/grounds ring outside the walk
GATE_EVERY_BAYS = 8


@dataclass(frozen=True)
class SiteOptions:
    """Site layout in bays — never centimetres."""

    walk_width_bays: int = DEFAULT_WALK_WIDTH_BAYS
    margin_bays: int = DEFAULT_MARGIN_BAYS
    courtyard_paving: str = "paving_flagstone"
    walk_piece: str = "sidewalk_slab"
    kerb_piece: str = "kerb_edge"
    lawn_piece: str = "lawn_patch"
    fence_piece: str = "fence_picket"
    gate_piece: str = "gate_iron"
    pave_courtyards: bool = True
    walks: bool = True
    kerbs: bool = True
    lawn: bool = True
    boundary_fence: bool = True


# Castle bailey — cobbled approach walk, wider grounds margin, no interior courtyard paving.
CASTLE_BAILEY_SITE = SiteOptions(
    walk_piece="paving_cobble",
    margin_bays=4,
    pave_courtyards=False,
)


@dataclass
class BuildingInstance:
    """One assembled building and where it sits on the site, in cells."""

    assembly: Assembly
    cell_offset: Cell = (0, 0)
    name: str = "building"


@dataclass
class SiteLayout:
    """What the site stage worked out — useful for tests and for the UI."""

    footprint: Set[Cell] = field(default_factory=set)
    courtyard: Set[Cell] = field(default_factory=set)
    walk: Set[Cell] = field(default_factory=set)
    lawn: Set[Cell] = field(default_factory=set)
    boundary: List[Tuple[Cell, str]] = field(default_factory=list)


_NEIGHBOURS = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}
# Boundary placement comes from pae.boundary. site.py used to carry its own copy that
# applied the far-edge rule but NOT the yaw rotation compensation, so every south/north
# fence — which is yawed 90 deg — landed a full module out. It read as fences and gates
# being off by one at the corners.
_FACE_YAW = FACE_YAW


def _face_offset(
    face: str,
    size_cm: Tuple[float, float, float],
    z_cm: float = 0.0,
) -> Tuple[float, float, float]:
    return boundary_offset_cm(face, size_cm, z_cm=z_cm)


# ---------------------------------------------------------------------------
# Multiple buildings
# ---------------------------------------------------------------------------


def _shift_placement(p: SolidPlacement, dx: int, dy: int, tag: str) -> SolidPlacement:
    return SolidPlacement(
        piece_id=f"{tag}_{p.piece_id}",
        asset_id=p.asset_id,
        kind=p.kind,
        cell=(p.cell[0] + dx, p.cell[1] + dy),
        level=p.level,
        yaw=p.yaw,
        offset_cm=p.offset_cm,
        size_cm=p.size_cm,
        rotates_about_center=p.rotates_about_center,
        tags=p.tags | frozenset({tag}),
    )


def place_buildings(instances: Sequence[BuildingInstance]) -> Tuple[Assembly, Report]:
    """Merge several assemblies into one site-wide assembly.

    Each building keeps its own geometry; only its cells move.  Piece ids are prefixed
    with the instance name so two copies of the same range do not collide in the manifest.
    """
    if not instances:
        return Assembly(placements=[]), Report.from_failures(
            [
                Failure(
                    check="site_empty",
                    message="place_buildings called with no buildings",
                    world_xyz=None,
                )
            ]
        )

    names = [b.name for b in instances]
    if len(set(names)) != len(names):
        return Assembly(placements=[]), Report.from_failures(
            [
                Failure(
                    check="site_duplicate_name",
                    message=f"building names must be unique, got {names}",
                    world_xyz=None,
                )
            ]
        )

    placements: List[SolidPlacement] = []
    floor_plan: Dict[int, FloorPlanLayer] = {}
    circulation: List = []
    storeys = 1

    for inst in instances:
        dx, dy = inst.cell_offset
        for p in inst.assembly.placements:
            placements.append(_shift_placement(p, dx, dy, inst.name))
        circulation.extend(inst.assembly.circulation)
        storeys = max(storeys, inst.assembly.storeys)
        # Keep the first building's plan layers as the site reference frame; per-building
        # plans are preserved on the instances themselves.
        for level, layer in inst.assembly.floor_plan.items():
            floor_plan.setdefault(
                level,
                FloorPlanLayer(
                    level=layer.level,
                    width=layer.width,
                    height=layer.height,
                    origin_cell=(
                        layer.origin_cell[0] + dx,
                        layer.origin_cell[1] + dy,
                    ),
                    cells=layer.cells,
                ),
            )

    merged = Assembly(
        placements=placements,
        floor_plan=floor_plan,
        circulation=circulation,
        storeys=storeys,
    )
    return merged, Report.from_failures([])


# ---------------------------------------------------------------------------
# Site surfaces
# ---------------------------------------------------------------------------


def _footprint_cells(assembly: Assembly) -> Set[Cell]:
    """Every cell any building piece occupies at any level."""
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("surface", "barrier"):
            continue
        out |= covered_cells(p)
    return out


def _ground_cells(assembly: Assembly) -> Set[Cell]:
    """Cells with a ground slab, floor or wall at level 0 — the built area.

    Must use covered cells, not ``p.cell``. Ground slabs and floors are emitted as one
    spanning placement per wing, so reading the origin cell alone leaves the whole interior
    of every building looking unbuilt — which made the courtyard detector classify rooms as
    courtyard and cantilever a balcony deck over a stairwell.
    """
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.level == 0 and p.kind in ("wall", "floor", "plinth", "ground"):
            out |= covered_cells(p)
    return out


def _ring(cells: Set[Cell], depth: int) -> Set[Cell]:
    """Cells within ``depth`` of the set, excluding the set itself (Chebyshev ring)."""
    out: Set[Cell] = set()
    for cx, cy in cells:
        for dx in range(-depth, depth + 1):
            for dy in range(-depth, depth + 1):
                n = (cx + dx, cy + dy)
                if n not in cells:
                    out.add(n)
    return out


def _courtyard_cells(cells: Set[Cell]) -> Set[Cell]:
    """Open cells framed by building on all four sides — the courtyard.

    Deliberately NOT a flood fill.  A quadrangle is four ranges with gaps at the corners,
    so a flood leaks straight out through them and reports no courtyard at all — which is
    exactly what the first version did.  Instead each empty cell is ray-tested along ±X and
    ±Y: if built cells lie in all four directions, you are standing in a courtyard, corner
    gaps or not.  That matches what a person means by the word.
    """
    if not cells:
        return set()
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    by_row: Dict[int, List[int]] = {}
    by_col: Dict[int, List[int]] = {}
    for cx, cy in cells:
        by_row.setdefault(cy, []).append(cx)
        by_col.setdefault(cx, []).append(cy)

    court: Set[Cell] = set()
    for y in range(y0, y1 + 1):
        row = by_row.get(y, [])
        for x in range(x0, x1 + 1):
            if (x, y) in cells:
                continue
            col = by_col.get(x, [])
            if not row or not col:
                continue
            if (
                any(v < x for v in row)
                and any(v > x for v in row)
                and any(v < y for v in col)
                and any(v > y for v in col)
            ):
                court.add((x, y))
    return court


def _enclosed_holes(cells: Set[Cell]) -> Set[Cell]:
    """Empty cells fully surrounded by the footprint (strict 4-connected flood).

    Kept for callers that need true topological enclosure; :func:`_courtyard_cells` is what
    the site stage uses for paving.
    """
    if not cells:
        return set()
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    x0, x1 = min(xs) - 1, max(xs) + 1
    y0, y1 = min(ys) - 1, max(ys) + 1

    outside: Set[Cell] = set()
    stack: List[Cell] = []
    for x in range(x0, x1 + 1):
        for y in (y0, y1):
            if (x, y) not in cells:
                stack.append((x, y))
    for y in range(y0, y1 + 1):
        for x in (x0, x1):
            if (x, y) not in cells:
                stack.append((x, y))
    while stack:
        c = stack.pop()
        if c in outside or c in cells:
            continue
        if not (x0 <= c[0] <= x1 and y0 <= c[1] <= y1):
            continue
        outside.add(c)
        for dx, dy in _NEIGHBOURS.values():
            stack.append((c[0] + dx, c[1] + dy))

    holes: Set[Cell] = set()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            c = (x, y)
            if c not in cells and c not in outside:
                holes.add(c)
    return holes


def _surface_placement(piece_id: str, cell: Cell, *, suffix: str = "") -> SolidPlacement:
    """Lay a surface with its TOP at z = 0 — never a step up onto a path."""
    desc = catalog_by_id()[piece_id]
    cx, cy = cell
    pid = f"{piece_id}_{cx}_{cy}"
    if suffix:
        pid = f"{pid}_{suffix}"
    return SolidPlacement(
        piece_id=pid,
        asset_id=piece_id,
        kind=desc.kind,
        cell=cell,
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, -desc.size_cm[2]),
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"site"}),
    )


def build_site(
    assembly: Assembly,
    options: Optional[SiteOptions] = None,
) -> Tuple[Assembly, SiteLayout, Report]:
    """Lay courtyard paving, walks, kerbs, lawn and a boundary fence around a building."""
    opts = options or SiteOptions()
    catalog = catalog_by_id()
    failures: List[Failure] = []
    for piece in (
        opts.courtyard_paving,
        opts.walk_piece,
        opts.kerb_piece,
        opts.lawn_piece,
        opts.fence_piece,
        opts.gate_piece,
    ):
        if piece not in catalog:
            failures.append(
                Failure(
                    check="site_piece_missing",
                    message=f"site wants unknown piece {piece!r}",
                    world_xyz=None,
                )
            )
    if failures:
        return assembly, SiteLayout(), Report.from_failures(failures)

    built = _ground_cells(assembly) or _footprint_cells(assembly)
    layout = SiteLayout(footprint=set(built))
    extra: List[SolidPlacement] = []

    # Courtyards: enclosed voids inside the footprint.
    if opts.pave_courtyards:
        layout.courtyard = _courtyard_cells(built)
        for cell in sorted(layout.courtyard):
            extra.append(_surface_placement(opts.courtyard_paving, cell))

    # Perimeter walk: a ring of walk_width_bays hugging the building.
    occupied = built | layout.courtyard
    if opts.walks:
        layout.walk = _ring(occupied, opts.walk_width_bays) - occupied
        for cell in sorted(layout.walk):
            extra.append(_surface_placement(opts.walk_piece, cell))

    # Lawn fills the margin outside the walk.
    inner = occupied | layout.walk
    if opts.lawn and opts.margin_bays > 0:
        layout.lawn = _ring(inner, opts.margin_bays) - inner
        for cell in sorted(layout.lawn):
            extra.append(_surface_placement(opts.lawn_piece, cell))

    # Kerbs on the outer edge of the walk, where it meets lawn.
    if opts.kerbs and layout.walk:
        kerb_size = catalog[opts.kerb_piece].size_cm
        for cx, cy in sorted(layout.walk):
            for face, (dx, dy) in _NEIGHBOURS.items():
                n = (cx + dx, cy + dy)
                if n in inner:
                    continue
                extra.append(
                    SolidPlacement(
                        piece_id=f"{opts.kerb_piece}_{cx}_{cy}_{face}",
                        asset_id=opts.kerb_piece,
                        kind=catalog[opts.kerb_piece].kind,
                        cell=(cx, cy),
                        level=0,
                        yaw=_FACE_YAW[face],
                        offset_cm=_face_offset(face, kerb_size),
                        size_cm=catalog[opts.kerb_piece].size_cm,
                        tags=catalog[opts.kerb_piece].tags | frozenset({"site"}),
                    )
                )

    # Boundary fence around the whole site, with a gate on a regular rhythm.
    if opts.boundary_fence:
        site_cells = inner | layout.lawn
        fence_size = catalog[opts.fence_piece].size_cm
        edges: List[Tuple[Cell, str]] = []
        for cx, cy in sorted(site_cells):
            for face, (dx, dy) in _NEIGHBOURS.items():
                if (cx + dx, cy + dy) not in site_cells:
                    edges.append(((cx, cy), face))
        layout.boundary = edges
        for i, (cell, face) in enumerate(edges):
            piece = opts.gate_piece if i % GATE_EVERY_BAYS == 0 else opts.fence_piece
            desc = catalog[piece]
            cx, cy = cell
            extra.append(
                SolidPlacement(
                    piece_id=f"{piece}_{cx}_{cy}_{face}",
                    asset_id=piece,
                    kind=desc.kind,
                    cell=cell,
                    level=0,
                    yaw=_FACE_YAW[face],
                    offset_cm=_face_offset(face, desc.size_cm),
                    size_cm=desc.size_cm,
                    tags=desc.tags | frozenset({"site", "boundary"}),
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
    return out, layout, Report.from_failures([])


def courtyard_quad(
    assembly: Assembly,
    *,
    gap_bays: int = 6,
    name_prefix: str = "range",
) -> Tuple[Assembly, Report]:
    """Four copies of one range arranged around a courtyard.

    The quickest way to get a school-shaped site out of a single building spec: north and
    south ranges, east and west ranges, a courtyard between them.
    """
    span = _span_bays(assembly)
    if span is None:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="site_span",
                    message="cannot arrange an empty assembly into a quad",
                    world_xyz=None,
                )
            ]
        )
    w, h = span
    off = w + gap_bays
    instances = [
        BuildingInstance(assembly, (0, 0), f"{name_prefix}_s"),
        BuildingInstance(assembly, (0, h + gap_bays), f"{name_prefix}_n"),
        BuildingInstance(assembly, (-off, (h + gap_bays) // 2), f"{name_prefix}_w"),
        BuildingInstance(assembly, (off, (h + gap_bays) // 2), f"{name_prefix}_e"),
    ]
    return place_buildings(instances)


def _span_bays(assembly: Assembly) -> Optional[Tuple[int, int]]:
    cells = _footprint_cells(assembly)
    if not cells:
        return None
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

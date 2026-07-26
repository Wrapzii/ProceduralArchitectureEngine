"""Floor slabs — solid and with stair/light-well hole."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set, Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM
from pae.primitives.types import (
    ApertureDesc,
    PrimitiveDescriptor,
    SocketDesc,
    module_tag,
)

Vec3 = Tuple[float, float, float]
Face = Tuple[int, ...]
Cell = Tuple[int, int]

# Thin rim; inner void ≈ full module bay (stair footprint per cell).
_HOLE_MARGIN_CM = 10.0


def floor_hole_margin_cm() -> float:
    """Slab rim left around the stair void opening."""
    return _HOLE_MARGIN_CM


def _box_verts_faces(
    ox: float, oy: float, oz: float, sx: float, sy: float, sz: float
) -> Tuple[List[Vec3], List[Face]]:
    verts: List[Vec3] = [
        (ox, oy, oz),
        (ox + sx, oy, oz),
        (ox + sx, oy + sy, oz),
        (ox, oy + sy, oz),
        (ox, oy, oz + sz),
        (ox + sx, oy, oz + sz),
        (ox + sx, oy + sy, oz + sz),
        (ox, oy + sy, oz + sz),
    ]
    faces: List[Face] = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return verts, faces


def _merge_verts_faces(
    parts: Sequence[Tuple[List[Vec3], List[Face]]],
) -> Tuple[List[Vec3], List[Face]]:
    verts: List[Vec3] = []
    faces: List[Face] = []
    for part_verts, part_faces in parts:
        base = len(verts)
        verts.extend(part_verts)
        faces.extend(tuple(i + base for i in f) for f in part_faces)
    return verts, faces


def floor_hole_frame_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    *,
    margin: Optional[float] = None,
) -> Tuple[List[Vec3], List[Face]]:
    """Perimeter frame with a rectangular void — import-safe (no bpy)."""
    m = _HOLE_MARGIN_CM if margin is None else margin
    if m * 2.0 >= min(sx, sy):
        raise ValueError("hole margin too large for slab footprint")
    hole_x0, hole_y0 = m, m
    hole_x1, hole_y1 = sx - m, sy - m
    parts: List[Tuple[List[Vec3], List[Face]]] = [
        _box_verts_faces(0.0, 0.0, 0.0, sx, hole_y0, sz),
        _box_verts_faces(0.0, hole_y1, 0.0, sx, sy - hole_y1, sz),
        _box_verts_faces(0.0, hole_y0, 0.0, hole_x0, hole_y1 - hole_y0, sz),
        _box_verts_faces(hole_x1, hole_y0, 0.0, sx - hole_x1, hole_y1 - hole_y0, sz),
    ]
    return _merge_verts_faces(parts)


def floor_hole_inner_aabb_cm(
    sx: float = MODULE_CM,
    sy: float = MODULE_CM,
    *,
    margin: Optional[float] = None,
) -> Tuple[Vec3, Vec3]:
    """Inner void min/max in slab-local cm (XY opening; Z is full thickness)."""
    m = _HOLE_MARGIN_CM if margin is None else margin
    return ((m, m, 0.0), (sx - m, sy - m, FLOOR_T_CM))


def slab_with_rect_holes_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    holes: Sequence[Tuple[float, float, float, float]],
) -> Tuple[List[Vec3], List[Face]]:
    """Solid slab with axis-aligned rectangular holes (x0,y0,x1,y1) in local cm.

    Used to punch stair VOIDs out of a spanning upper-floor deck so the stair
    top is an opening, not a solid ceiling/roof pad.
    """
    if not holes:
        return _box_verts_faces(0.0, 0.0, 0.0, sx, sy, sz)

    xs: List[float] = [0.0, sx]
    ys: List[float] = [0.0, sy]
    cleaned: List[Tuple[float, float, float, float]] = []
    for x0, y0, x1, y1 in holes:
        xa, xb = (x0, x1) if x0 <= x1 else (x1, x0)
        ya, yb = (y0, y1) if y0 <= y1 else (y1, y0)
        xa = max(0.0, min(sx, xa))
        xb = max(0.0, min(sx, xb))
        ya = max(0.0, min(sy, ya))
        yb = max(0.0, min(sy, yb))
        if xb - xa < 1e-6 or yb - ya < 1e-6:
            continue
        cleaned.append((xa, ya, xb, yb))
        xs.extend((xa, xb))
        ys.extend((ya, yb))
    if not cleaned:
        return _box_verts_faces(0.0, 0.0, 0.0, sx, sy, sz)

    xs = sorted(set(xs))
    ys = sorted(set(ys))

    def _inside_hole(cx: float, cy: float) -> bool:
        for x0, y0, x1, y1 in cleaned:
            if x0 < cx < x1 and y0 < cy < y1:
                return True
        return False

    parts: List[Tuple[List[Vec3], List[Face]]] = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
                continue
            if _inside_hole(0.5 * (x0 + x1), 0.5 * (y0 + y1)):
                continue
            parts.append(_box_verts_faces(x0, y0, 0.0, x1 - x0, y1 - y0, sz))
    if not parts:
        raise ValueError("slab_with_rect_holes: holes consumed the entire slab")
    return _merge_verts_faces(parts)


def rect_cover_cells(cells: Iterable[Cell]) -> List[Tuple[int, int, int, int]]:
    """Cover a cell set with maximal axis-aligned rectangles ``(x0, y0, w, h)``.

    Same greedy cover as assemble stairwell merge: one spanning opening per well,
    never a rib of floor between adjacent VOID bays.
    """
    remaining: Set[Cell] = set(cells)
    out: List[Tuple[int, int, int, int]] = []
    while remaining:
        x0, y0 = min(remaining, key=lambda c: (c[1], c[0]))
        w = 1
        while (x0 + w, y0) in remaining:
            w += 1
        h = 1
        while all((x0 + i, y0 + h) in remaining for i in range(w)):
            h += 1
        for i in range(w):
            for j in range(h):
                remaining.discard((x0 + i, y0 + j))
        out.append((x0, y0, w, h))
    return out


def hole_rects_for_deck_cm(
    deck_cell: Tuple[int, int],
    hole_cells: Sequence[Tuple[int, int]],
    *,
    margin: Optional[float] = None,
) -> List[Tuple[float, float, float, float]]:
    """Local (x0,y0,x1,y1) hole rectangles — one 1×1 bay per cell (may leave ribs).

    Prefer :func:`hole_rects_merged_for_deck_cm` for stairwells so a multi-bay run
    is a single opening (Ledger F-7).
    """
    m = _HOLE_MARGIN_CM if margin is None else margin
    dx0, dy0 = deck_cell
    rects: List[Tuple[float, float, float, float]] = []
    for cx, cy in hole_cells:
        ox = (cx - dx0) * MODULE_CM
        oy = (cy - dy0) * MODULE_CM
        rects.append((ox + m, oy + m, ox + MODULE_CM - m, oy + MODULE_CM - m))
    return rects


def hole_cells_for_deck_punch(
    deck_cells: Set[Cell],
    hole_cells: Iterable[Cell],
) -> Set[Cell]:
    """Map exterior VOID bays to the deck border cell that shares an edge.

    Used only for single-wing gutters (M2): the well sits west of one spanning
    deck and the east border column must open. Split-wing manor gutters already
    have ``floor_hole`` rim pieces in the between-wing column — do not call this
  for those (see :func:`hole_in_split_wing_gutter`).
    """
    out: Set[Cell] = set()
    for x, y in hole_cells:
        if (x, y) in deck_cells:
            out.add((x, y))
            continue
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in deck_cells:
                out.add((nx, ny))
                break
    return out


def hole_in_split_wing_gutter(
    hole_cells: Set[Cell],
    peer_deck_cell_sets: Sequence[Set[Cell]],
) -> bool:
    """True when separate wing decks flank the well column (manor gutter).

    In that layout the ``floor_hole`` placements live in the between-wing column;
    spanning wing slabs must not neighbour-punch inward or they delete whole border
    bays and leave skeletal floors.
    """
    if not hole_cells or not peer_deck_cell_sets:
        return False
    hx0 = min(c[0] for c in hole_cells)
    hx1 = max(c[0] for c in hole_cells)
    hy0 = min(c[1] for c in hole_cells)
    hy1 = max(c[1] for c in hole_cells)
    west = any(max(c[0] for c in ds) < hx0 for ds in peer_deck_cell_sets if ds)
    east = any(min(c[0] for c in ds) > hx1 for ds in peer_deck_cell_sets if ds)
    if west and east:
        return True
    north = any(max(c[1] for c in ds) < hy0 for ds in peer_deck_cell_sets if ds)
    south = any(min(c[1] for c in ds) > hy1 for ds in peer_deck_cell_sets if ds)
    return north and south


def _hole_inner_world_xy(hole) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Inner stair void min/max XY in world cm (hole placement, yaw 0)."""
    local_min, local_max = floor_hole_inner_aabb_cm(
        float(hole.size_cm[0]), float(hole.size_cm[1])
    )
    ox = hole.cell[0] * MODULE_CM + hole.offset_cm[0]
    oy = hole.cell[1] * MODULE_CM + hole.offset_cm[1]
    return (
        (ox + local_min[0], oy + local_min[1]),
        (ox + local_max[0], oy + local_max[1]),
    )


def hole_rects_merged_for_deck_cm(
    deck_cell: Tuple[int, int],
    hole_cells: Sequence[Tuple[int, int]],
    *,
    margin: Optional[float] = None,
) -> List[Tuple[float, float, float, float]]:
    """Local hole rects after merging adjacent VOID cells into spanning openings.

    Punching one 1×1 per cell (or only the hole's origin cell) leaves a solid rib /
    half-run of floor over the stair — the live Blender defect F-7.
    """
    m = _HOLE_MARGIN_CM if margin is None else margin
    dx0, dy0 = deck_cell
    rects: List[Tuple[float, float, float, float]] = []
    for x0, y0, w, h in rect_cover_cells(hole_cells):
        ox = (x0 - dx0) * MODULE_CM
        oy = (y0 - dy0) * MODULE_CM
        rects.append(
            (
                ox + m,
                oy + m,
                ox + w * MODULE_CM - m,
                oy + h * MODULE_CM - m,
            )
        )
    return rects


def spanning_deck_hole_rects_cm(
    deck,
    hole_placements,
    *,
    peer_decks: Sequence = (),
) -> List[Tuple[float, float, float, float]]:
    """Local VOID punch rects for one spanning upper-floor deck (Blender + validate).

    Implemented here (not in ``blender_build``) so ``reload_pae()`` refreshes the
    contract after agent edits — ``pae.blender_build`` itself stays cached in Blender.

    Uses world→local intersection of each hole's inner void with the deck AABB
    (same contract as roof notches). Single-wing gutters (M2) may neighbour-map
    exterior VOID bays onto the abutting deck border; split-wing manor gutters must
    not — the rim ``floor_hole`` pieces own the between-wing opening.
    """
    from pae.contract import placement_world_aabb
    from pae.export.manifest import placement_loc_cm
    from pae.trim import covered_cells

    deck_cells = covered_cells(deck)
    deck_level = getattr(deck, "level", None)
    peer_cell_sets = [
        covered_cells(d)
        for d in peer_decks
        if getattr(d, "level", None) == deck_level
    ]
    dmin, dmax = placement_world_aabb(
        deck.cell[0],
        deck.cell[1],
        deck.level,
        deck.yaw,
        deck.size_cm,
        deck.offset_cm,
        rotates_about_center=deck.rotates_about_center,
    )
    origin = placement_loc_cm(deck)
    sx, sy = float(deck.size_cm[0]), float(deck.size_cm[1])

    cells: Set[Cell] = set()
    world_rects: List[Tuple[float, float, float, float]] = []
    for h in hole_placements:
        if getattr(h, "asset_id", None) != "floor_hole":
            continue
        if getattr(h, "level", None) != deck_level:
            continue
        hole_cells = set(covered_cells(h))
        on_deck = hole_cells & deck_cells
        cells |= on_deck

        all_deck_sets = peer_cell_sets + [deck_cells]
        in_gutter = hole_in_split_wing_gutter(hole_cells, all_deck_sets)
        if not on_deck:
            # Split-wing gutters: the well sits between wing slabs. World→local
            # intersection still nibbles the abutting border column and leaves thin
            # rim beams beside a shaft that has no solid panels — the live defect.
            # The gutter opening is owned by ``floor_hole`` / landing decks, not a
            # neighbour punch on the wing.
            if not in_gutter:
                hmin, hmax = _hole_inner_world_xy(h)
                x0 = max(dmin[0], hmin[0]) - origin[0]
                y0 = max(dmin[1], hmin[1]) - origin[1]
                x1 = min(dmax[0], hmax[0]) - origin[0]
                y1 = min(dmax[1], hmax[1]) - origin[1]
                x0, x1 = max(0.0, x0), min(sx, x1)
                y0, y1 = max(0.0, y0), min(sy, y1)
                if x1 - x0 > 0.5 and y1 - y0 > 0.5:
                    world_rects.append((x0, y0, x1, y1))
                cells |= hole_cells_for_deck_punch(deck_cells, hole_cells)

    rects = hole_rects_merged_for_deck_cm(tuple(deck.cell), cells) if cells else []
    rects.extend(world_rects)
    return rects


def _edge_sockets() -> tuple:
    tag = frozenset({module_tag(), "floor"})
    mid = MODULE_CM * 0.5
    t = FLOOR_T_CM
    return (
        SocketDesc("edge_x0", (0.0, mid, t), (-1.0, 0.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_x1", (MODULE_CM, mid, t), (1.0, 0.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_y0", (mid, 0.0, t), (0.0, -1.0, 0.0), "floor_edge", tag),
        SocketDesc("edge_y1", (mid, MODULE_CM, t), (0.0, 1.0, 0.0), "floor_edge", tag),
    )


def floor_slab() -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id="floor",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=_edge_sockets(),
        tags=frozenset({"floor", "slab", module_tag()}),
        origin="min_corner",
        notes="Place at level_z − FLOOR_T so top lands on the storey (§2.4).",
    )


def floor_with_hole() -> PrimitiveDescriptor:
    margin = _HOLE_MARGIN_CM
    hole = MODULE_CM - 2.0 * margin
    pad_z = FLOOR_T_CM * 0.25
    return PrimitiveDescriptor(
        id="floor_hole",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=_edge_sockets(),
        tags=frozenset({"floor", "hole", "stairwell", module_tag()}),
        origin="min_corner",
        aperture=ApertureDesc(
            kind="hole",
            min_cm=(margin, margin, -pad_z),
            max_cm=(margin + hole, margin + hole, FLOOR_T_CM + pad_z),
        ),
        notes="Full-bay stair void; thin rim for slab edge.",
    )


def all_floors() -> tuple:
    return (floor_slab(), floor_with_hole())


def build_floor_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    if desc.aperture is None:
        return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)
    sx, sy, sz = desc.size_cm
    verts, faces = floor_hole_frame_verts_faces(sx, sy, sz)
    return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)

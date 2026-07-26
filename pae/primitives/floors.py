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

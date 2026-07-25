"""Floor slabs — solid and with stair/light-well hole."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM
from pae.primitives.types import (
    ApertureDesc,
    PrimitiveDescriptor,
    SocketDesc,
    module_tag,
)

Vec3 = Tuple[float, float, float]
Face = Tuple[int, ...]

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

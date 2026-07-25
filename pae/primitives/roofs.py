"""Pitched roof kit — slope bays plus gable-end infill prisms.

Prior failure mode: walls stopped at the eaves and nothing filled the gable
triangle → 8 m holes. Assembly places per-bay ``roof_pitched_slope`` deck
pieces and ``roof_gable_infill`` triangular prisms on the gable ends.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from pae.contract import EAVE_OVERHANG_CM, FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

# Default pitch rise/run from gothic_academy style (not a grid dimension).
DEFAULT_ROOF_PITCH = 1.05

Vec3 = Tuple[float, float, float]


def roof_rise_cm(pitch: float = DEFAULT_ROOF_PITCH, span_cm: float = MODULE_CM) -> float:
    """Rise for a gable spanning ``span_cm`` (ridge at mid-span)."""
    return pitch * (span_cm * 0.5)


def roof_pitched_height_cm(
    pitch: float = DEFAULT_ROOF_PITCH,
    *,
    span_modules: int = 1,
) -> float:
    """Peak height above eave plane for a roof spanning *span_modules* bays."""
    span_cm = max(1, span_modules) * MODULE_CM
    return roof_rise_cm(pitch, span_cm) + FLOOR_T_CM


def roof_gable_infill(
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
) -> PrimitiveDescriptor:
    """One-module gable-end triangular prism (solid infill, not an open hole)."""
    height = roof_pitched_height_cm(pitch, span_modules=1)
    rise = height - FLOOR_T_CM
    tag = frozenset({module_tag(), "roof"})
    sockets = (
        SocketDesc(
            name="eave_x0",
            pos_cm=(0.0, MODULE_CM * 0.5, 0.0),
            normal=(-1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_x1",
            pos_cm=(MODULE_CM, MODULE_CM * 0.5, 0.0),
            normal=(1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="gable_face",
            pos_cm=(MODULE_CM * 0.5, 0.0, rise * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="roof_gable",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_gable_infill",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=height / STOREY_CM,
        size_cm=(MODULE_CM, MODULE_CM, height),
        sockets=sockets,
        tags=frozenset({"roof", "pitched", "gable", "gable_infill", module_tag()}),
        origin="min_corner",
        notes=(
            f"Pitch={pitch}: triangular gable prism rise={rise:.1f} cm over one bay. "
            "Fills the historical 8 m gable hole above the eaves."
        ),
    )


def roof_pitched_slope(
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
) -> PrimitiveDescriptor:
    """One-module pitched slope bay (deck between gable ends)."""
    height = roof_pitched_height_cm(pitch, span_modules=1)
    rise = height - FLOOR_T_CM
    tag = frozenset({module_tag(), "roof"})
    sockets = (
        SocketDesc(
            name="eave_x0",
            pos_cm=(0.0, MODULE_CM * 0.5, 0.0),
            normal=(-1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_x1",
            pos_cm=(MODULE_CM, MODULE_CM * 0.5, 0.0),
            normal=(1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="ridge_y1",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM, rise),
            normal=(0.0, 1.0, 0.0),
            type="roof_ridge",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_pitched_slope",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=height / STOREY_CM,
        size_cm=(MODULE_CM, MODULE_CM, height),
        sockets=sockets,
        tags=frozenset({"roof", "pitched", "slope", module_tag()}),
        origin="min_corner",
        notes=(
            f"Pitch={pitch}: wedge deck rise={rise:.1f} cm (local height scaled at assemble)."
        ),
    )


def roof_eave_offset_cm(
    *,
    overhang_west: float | None = None,
    overhang_south: float | None = None,
) -> Tuple[float, float, float]:
    """Min-corner shift so deck overhangs footprint on exterior sides."""
    oh = EAVE_OVERHANG_CM
    ox = -(overhang_west if overhang_west is not None else oh)
    oy = -(overhang_south if overhang_south is not None else oh)
    return (ox, oy, 0.0)


def roof_eave_overhang_per_side(
    rx0: int,
    ry0: int,
    rx1: int,
    ry1: int,
    spans: Sequence[Tuple[int, int, int, int]],
) -> Tuple[float, float, float, float]:
    """(west, east, south, north) eave overhang in cm — zero on interior wing seams."""
    oh = EAVE_OVERHANG_CM
    west, east, south, north = oh, oh, oh, oh
    if len(spans) <= 1:
        return west, east, south, north
    for ox0, oy0, ox1, oy1 in spans:
        if (ox0, oy0, ox1, oy1) == (rx0, ry0, rx1, ry1):
            continue
        if not (oy1 < ry0 or oy0 > ry1):
            if ox1 + 1 == rx0:
                west = 0.0
            if ox0 == rx1 + 1:
                east = 0.0
        if not (ox1 < rx0 or ox0 > rx1):
            if oy1 + 1 == ry0:
                south = 0.0
            if oy0 == ry1 + 1:
                north = 0.0
    return west, east, south, north


def roof_flat_span_size_cm(
    modules_x: int,
    modules_y: int,
    *,
    overhang_west: float | None = None,
    overhang_east: float | None = None,
    overhang_south: float | None = None,
    overhang_north: float | None = None,
) -> tuple[float, float, float]:
    """Axis-aligned flat roof slab spanning *modules_x* × *modules_y* bays plus eaves."""
    if modules_x < 1 or modules_y < 1:
        raise ValueError(f"roof span must be ≥ 1×1 modules, got {modules_x}×{modules_y}")
    oh = EAVE_OVERHANG_CM
    west = overhang_west if overhang_west is not None else oh
    east = overhang_east if overhang_east is not None else oh
    south = overhang_south if overhang_south is not None else oh
    north = overhang_north if overhang_north is not None else oh
    return (
        modules_x * MODULE_CM + west + east,
        modules_y * MODULE_CM + south + north,
        FLOOR_T_CM,
    )


def roof_pitched_span_size_cm(span_x_cm: float, span_y_cm: float) -> Tuple[float, float]:
    """Footprint XY for a full-span pitched deck including eave overhang."""
    oh = EAVE_OVERHANG_CM
    return span_x_cm + 2.0 * oh, span_y_cm + 2.0 * oh


def roof_gable_end_size_cm(
    *,
    ridge_along_x: bool,
    span_x_cm: float,
    span_y_cm: float,
    gable_height: float,
) -> Tuple[float, float, float]:
    """Gable-end prism sized to match pitched deck eaves on ridge and cross axes."""
    oh = EAVE_OVERHANG_CM
    if ridge_along_x:
        return (MODULE_CM + oh, span_y_cm + 2.0 * oh, gable_height)
    return (span_x_cm + 2.0 * oh, MODULE_CM + oh, gable_height)


def roof_gable_end_offset_cm(*, ridge_along_x: bool, is_low_end: bool) -> Tuple[float, float, float]:
    """Local offset for a gable cap — extends outward on the ridge axis low/high end only."""
    oh = EAVE_OVERHANG_CM
    if ridge_along_x:
        return (-oh if is_low_end else 0.0, -oh, 0.0)
    return (-oh, -oh if is_low_end else 0.0, 0.0)


def roof_flat() -> PrimitiveDescriptor:
    """One-module flat roof deck (assemble scales XY via ``roof_flat_span_size_cm``)."""
    tag = frozenset({module_tag(), "roof"})
    sockets = (
        SocketDesc(
            name="eave_x0",
            pos_cm=(0.0, MODULE_CM * 0.5, 0.0),
            normal=(-1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_x1",
            pos_cm=(MODULE_CM, MODULE_CM * 0.5, 0.0),
            normal=(1.0, 0.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_y0",
            pos_cm=(MODULE_CM * 0.5, 0.0, 0.0),
            normal=(0.0, -1.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
        SocketDesc(
            name="eave_y1",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM, 0.0),
            normal=(0.0, 1.0, 0.0),
            type="roof_eave",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_flat",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=0.0,
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        sockets=sockets,
        tags=frozenset({"roof", "flat", module_tag()}),
        origin="min_corner",
        notes="Deck thickness FLOOR_T; place top at level_z + STOREY (§6 flat roof).",
    )


def local_slope_rise_cm(
    *,
    pitch: float,
    cell_index: int,
    span_start: int,
    span_end: int,
    ridge_axis: str,
    along_index: int,
) -> float:
    """Rise above eave for an interior slope cell (not a gable-end row/column)."""
    del ridge_axis, along_index
    span_modules = span_end - span_start + 1
    full_rise = roof_rise_cm(pitch, span_modules * MODULE_CM)
    if span_modules <= 1:
        return 0.0
    max_dist = (span_modules - 1) * 0.5
    cell_center = cell_index + 0.5
    span_center = span_start + span_modules * 0.5
    dist_from_eave = max_dist - abs(cell_center - span_center)
    if dist_from_eave <= 0.0:
        return 0.0
    return full_rise * (dist_from_eave / max_dist)


def all_roofs() -> tuple:
    return (roof_gable_infill(), roof_pitched_slope(), roof_flat())


def _gable_infill_verts_faces(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Triangular prism sized for the gable *end* wall.

    * If ``sy >= sx`` (span along Y): triangle in Y–Z, extruded along X — faces ±X
      (ridge-along-X buildings).
    * Else: triangle in X–Z, extruded along Y — faces ±Y (ridge-along-Y buildings).

    Prior bug: always X–Z triangles along the long eaves → sawtooth / wrong facing.
    """
    if sy >= sx:
        # Thickness X, span Y, peak at mid-Y.
        verts: List[Vec3] = [
            (0.0, 0.0, 0.0),
            (0.0, sy, 0.0),
            (0.0, sy * 0.5, sz),
            (sx, 0.0, 0.0),
            (sx, sy, 0.0),
            (sx, sy * 0.5, sz),
        ]
        faces: List[Sequence[int]] = [
            (0, 2, 1),
            (3, 4, 5),
            (0, 1, 4, 3),
            (0, 3, 5, 2),
            (1, 2, 5, 4),
        ]
        return verts, faces
    verts = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx * 0.5, 0.0, sz),
        (0.0, sy, 0.0),
        (sx, sy, 0.0),
        (sx * 0.5, sy, sz),
    ]
    faces = [
        (0, 1, 2),
        (3, 5, 4),
        (0, 3, 4, 1),
        (0, 2, 5, 3),
        (1, 4, 5, 2),
    ]
    return verts, faces


def _double_pitch_verts_faces(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Full-footprint double-pitch roof: eaves at y=0/sy, ridge at mid-Y, height *sz*."""
    mid = sy * 0.5
    verts: List[Vec3] = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, sy, 0.0),
        (0.0, sy, 0.0),
        (0.0, mid, sz),
        (sx, mid, sz),
    ]
    faces: List[Sequence[int]] = [
        (0, 1, 5, 4),  # south slope
        (4, 5, 2, 3),  # north slope
        (0, 4, 3),  # west gable fill (thin)
        (1, 2, 5),  # east gable fill (thin)
        (0, 3, 2, 1),  # underside
    ]
    return verts, faces


def _double_pitch_verts_faces_ridge_y(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Double-pitch with ridge along Y (eaves at x=0/sx)."""
    mid = sx * 0.5
    verts: List[Vec3] = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, sy, 0.0),
        (0.0, sy, 0.0),
        (mid, 0.0, sz),
        (mid, sy, sz),
    ]
    faces: List[Sequence[int]] = [
        (0, 4, 5, 3),  # west slope
        (4, 1, 2, 5),  # east slope
        (0, 1, 4),
        (3, 5, 2),
        (0, 3, 2, 1),
    ]
    return verts, faces


def _single_slope_wedge_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    *,
    ridge_toward_positive_y: bool,
) -> Tuple[List[Vec3], List[Sequence[int]]]:
    if not ridge_toward_positive_y:
        verts, faces = _single_slope_wedge_verts_faces(
            sx, sy, sz, ridge_toward_positive_y=True
        )
        flipped = [(v[0], sy - v[1], v[2]) for v in verts]
        return flipped, faces
    verts: List[Vec3] = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, sy, 0.0),
        (0.0, sy, 0.0),
        (0.0, sy, sz),
        (sx, sy, sz),
    ]
    faces: List[Sequence[int]] = [
        (0, 1, 2, 3),
        (0, 3, 4),
        (0, 4, 5, 1),
        (1, 5, 2),
        (2, 5, 4, 3),
    ]
    return verts, faces


def _slope_wedge_verts_faces(
    sx: float,
    sy: float,
    sz: float,
    *,
    ridge_toward_positive_y: bool = True,
) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Full A-frame for square/rect decks; one-sided wedge only when explicitly thin."""
    # Catalog proto is MODULE×MODULE — always author as double-pitch so non-uniform
    # instance scale produces a closed hall roof.
    if sx >= MODULE_CM * 0.9 and sy >= MODULE_CM * 0.9:
        if sx >= sy:
            return _double_pitch_verts_faces(sx, sy, sz)
        return _double_pitch_verts_faces_ridge_y(sx, sy, sz)
    return _single_slope_wedge_verts_faces(
        sx, sy, sz, ridge_toward_positive_y=ridge_toward_positive_y
    )


def build_roof_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Author roof meshes — gable prism / slope wedge / flat deck."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    sx, sy, sz = desc.size_cm
    obj_name = name or desc.id
    if desc.id == "roof_gable_infill":
        verts, faces = _gable_infill_verts_faces(sx, sy, sz)
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
    if desc.id == "roof_pitched_slope":
        verts, faces = _slope_wedge_verts_faces(sx, sy, sz, ridge_toward_positive_y=True)
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
    return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)

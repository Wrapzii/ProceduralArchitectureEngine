"""Pitched roof kit — slope bays plus gable-end infill prisms.

Prior failure mode: walls stopped at the eaves and nothing filled the gable
triangle → 8 m holes. Assembly places per-bay ``roof_pitched_slope`` deck
pieces and ``roof_gable_infill`` triangular prisms on the gable ends.

S-012 adds four-slope ``roof_hip``. S-019 places ``roof_valley`` stubs along
L/U wing abutments (full diagonal valley merge remains S-021).

Stage C (Master Plan / D3-9): ridge height comes from a **structure height
field** (topmost built level per XY column), not from ``rect_cover`` / wing
decomposition. Plates may still split for mesh placement; one band shares one
ridge family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from pae.contract import EAVE_OVERHANG_CM, FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

# Default pitch rise/run from gothic_academy style (not a grid dimension).
DEFAULT_ROOF_PITCH = 1.05
# S-011 steep anime-fantasy silhouette — specs/styles may request pitch ≥ this.
STEEP_PITCH_MIN = 1.6
ROOF_PITCH_MIN = 0.5
ROOF_PITCH_MAX = 2.5
# S-019 valley stub cross-section — half-module trough centred on the wing seam.
VALLEY_WIDTH_CM = MODULE_CM * 0.5

Vec3 = Tuple[float, float, float]
Cell = Tuple[int, int]
RoofSpan = Tuple[int, int, int, int]  # x0, y0, x1, y1 inclusive


@dataclass(frozen=True)
class ValleySeam:
    """Shared edge between two wing roof spans (S-019).

    ``axis=="x"``: seam runs along X (wings abut in Y); ``cross_hi`` is the
    northern wing's ``y0``. ``axis=="y"``: seam along Y; ``cross_hi`` is the
    eastern wing's ``x0``.
    """

    axis: str
    run0: int
    run1: int
    cross_hi: int


@dataclass(frozen=True)
class RoofHeightBand:
    """One eaves-height plate of a structure roof (Master Plan Stage C).

    Columns that share the same eaves height (topmost built level + cumulative
    height_units) form one band. ``spans`` are rect_cover of that mask for mesh
    placement only — ridge height is ``structure_ridge_span_modules(spans)``.
    """

    top_level: int
    eaves_height_units: float
    cells: FrozenSet[Cell]
    spans: Tuple[RoofSpan, ...]


def column_top_levels(
    level_cells: Sequence[Iterable[Cell]],
) -> Dict[Cell, int]:
    """For each XY column, index of the topmost level that includes the cell."""
    top: Dict[Cell, int] = {}
    for level, cells in enumerate(level_cells):
        for cell in cells:
            c = (int(cell[0]), int(cell[1]))
            prev = top.get(c)
            if prev is None or level > prev:
                top[c] = level
    return top


def eaves_height_units_at_level(
    level: int,
    height_units: Optional[Sequence[float]] = None,
) -> float:
    """Cumulative height units from ground up through ``level`` (inclusive)."""
    if not height_units:
        return float(level + 1)
    total = 0.0
    for i in range(level + 1):
        if i < len(height_units):
            total += float(max(1.0, float(height_units[i])))
        else:
            total += 1.0
    return total


def structure_ridge_span_modules(spans: Sequence[RoofSpan]) -> int:
    """One ridge family for a height band — max short-span, not per-slice.

    D3-9: ``rect_cover`` / wing splits must not invent different ridge heights
    on one eaves plane. The tallest short-span in the band wins so a sketched U
    bridge rises with the legs.
    """
    if not spans:
        return 1
    shorts = [max(1, min(x1 - x0 + 1, y1 - y0 + 1)) for x0, y0, x1, y1 in spans]
    return max(shorts)


def roof_height_field_bands(
    level_cells: Sequence[Iterable[Cell]],
    *,
    height_units: Optional[Sequence[float]] = None,
    exclude: Optional[Set[Cell]] = None,
) -> List[RoofHeightBand]:
    """Derive roof plates from the column height field (Stage C).

    For each XY column, take the topmost built level → eaves height. Group by
    eaves height; ``rect_cover`` each group for placement spans. Valleys follow
    abutting spans inside a band (same as S-019), not massing wing roles.
    """
    from pae.sketch import rect_cover

    skip = exclude or set()
    top = column_top_levels(level_cells)
    by_eaves: Dict[Tuple[float, int], Set[Cell]] = {}
    for cell, level in top.items():
        if cell in skip:
            continue
        eaves = eaves_height_units_at_level(level, height_units)
        key = (eaves, level)
        by_eaves.setdefault(key, set()).add(cell)

    bands: List[RoofHeightBand] = []
    for (eaves, level), cells in sorted(by_eaves.items(), key=lambda kv: kv[0][0]):
        if not cells:
            continue
        spans = tuple(rect_cover(cells))
        bands.append(
            RoofHeightBand(
                top_level=level,
                eaves_height_units=float(eaves),
                cells=frozenset(cells),
                spans=spans,
            )
        )
    return bands


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


def roof_hip_rise_cm(
    pitch: float = DEFAULT_ROOF_PITCH,
    *,
    span_modules_x: int = 1,
    span_modules_y: int = 1,
) -> float:
    """Rise above eave for a hip roof — driven by the shorter span dimension."""
    short_modules = max(1, min(span_modules_x, span_modules_y))
    return roof_rise_cm(pitch, short_modules * MODULE_CM)


def roof_hip_height_cm(
    pitch: float = DEFAULT_ROOF_PITCH,
    *,
    span_modules_x: int = 1,
    span_modules_y: int = 1,
) -> float:
    """Peak height above eave plane for a hip roof spanning *modules_x* × *modules_y*."""
    return roof_hip_rise_cm(
        pitch, span_modules_x=span_modules_x, span_modules_y=span_modules_y
    ) + FLOOR_T_CM


def roof_hip(
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
) -> PrimitiveDescriptor:
    """One-module hip roof proto (assemble scales XY + peak Z per wing span)."""
    height = roof_hip_height_cm(pitch, span_modules_x=1, span_modules_y=1)
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
        SocketDesc(
            name="ridge",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM * 0.5, rise),
            normal=(0.0, 0.0, 1.0),
            type="roof_ridge",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_hip",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=height / STOREY_CM,
        size_cm=(MODULE_CM, MODULE_CM, height),
        sockets=sockets,
        tags=frozenset({"roof", "hip", "pitched", module_tag()}),
        origin="min_corner",
        notes=(
            f"Pitch={pitch}: four-slope hip rise={rise:.1f} cm over one bay; "
            "assemble spans per wing like roof_flat."
        ),
    )


def roof_hip_span_size_cm(
    modules_x: int,
    modules_y: int,
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
    overhang_west: float | None = None,
    overhang_east: float | None = None,
    overhang_south: float | None = None,
    overhang_north: float | None = None,
    ridge_span_modules: int | None = None,
) -> tuple[float, float, float]:
    """Axis-aligned hip roof spanning *modules_x* × *modules_y* bays plus eaves.

    ``ridge_span_modules`` (Stage C) overrides the short-span used for peak Z so
    every plate in a height band shares one ridge family.
    """
    if modules_x < 1 or modules_y < 1:
        raise ValueError(f"roof span must be ≥ 1×1 modules, got {modules_x}×{modules_y}")
    oh = EAVE_OVERHANG_CM
    west = overhang_west if overhang_west is not None else oh
    east = overhang_east if overhang_east is not None else oh
    south = overhang_south if overhang_south is not None else oh
    north = overhang_north if overhang_north is not None else oh
    if ridge_span_modules is not None:
        rs = max(1, int(ridge_span_modules))
        peak = roof_hip_height_cm(pitch, span_modules_x=rs, span_modules_y=rs)
    else:
        peak = roof_hip_height_cm(
            pitch, span_modules_x=modules_x, span_modules_y=modules_y
        )
    return (
        modules_x * MODULE_CM + west + east,
        modules_y * MODULE_CM + south + north,
        peak,
    )


def roof_valley_seams(
    spans: Sequence[Tuple[int, int, int, int]],
) -> List[ValleySeam]:
    """Detect abutting wing spans that need a valley stub (S-019).

    Spans abut when one range's high edge is exactly one cell below the other's
    low edge and their intervals overlap on the shared axis — the same rule
    ``roof_eave_overhang_per_side`` uses to suppress interior eaves.
    """
    seams: List[ValleySeam] = []
    seen: set[Tuple[str, int, int, int]] = set()
    n = len(spans)
    for i in range(n):
        ax0, ay0, ax1, ay1 = spans[i]
        for j in range(i + 1, n):
            bx0, by0, bx1, by1 = spans[j]
            # Abut in Y — shared edge runs along X.
            if ay1 + 1 == by0 or by1 + 1 == ay0:
                run0 = max(ax0, bx0)
                run1 = min(ax1, bx1)
                if run0 <= run1:
                    cross_hi = by0 if ay1 + 1 == by0 else ay0
                    key = ("x", run0, run1, cross_hi)
                    if key not in seen:
                        seen.add(key)
                        seams.append(
                            ValleySeam(axis="x", run0=run0, run1=run1, cross_hi=cross_hi)
                        )
            # Abut in X — shared edge runs along Y.
            if ax1 + 1 == bx0 or bx1 + 1 == ax0:
                run0 = max(ay0, by0)
                run1 = min(ay1, by1)
                if run0 <= run1:
                    cross_hi = bx0 if ax1 + 1 == bx0 else ax0
                    key = ("y", run0, run1, cross_hi)
                    if key not in seen:
                        seen.add(key)
                        seams.append(
                            ValleySeam(axis="y", run0=run0, run1=run1, cross_hi=cross_hi)
                        )
    return seams


def roof_valley_height_cm(pitch: float = DEFAULT_ROOF_PITCH) -> float:
    """Stub valley depth — rise over half a module plus deck thickness."""
    return roof_rise_cm(pitch, MODULE_CM * 0.5) + FLOOR_T_CM


def roof_valley_span_size_cm(
    run_modules: int,
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
    axis: str = "x",
) -> tuple[float, float, float]:
    """Valley trough sized to the shared wing seam (S-019 stub)."""
    if run_modules < 1:
        raise ValueError(f"valley run must be ≥ 1 module, got {run_modules}")
    run_cm = run_modules * MODULE_CM
    height = roof_valley_height_cm(pitch)
    if axis == "y":
        return (VALLEY_WIDTH_CM, run_cm, height)
    return (run_cm, VALLEY_WIDTH_CM, height)


def roof_valley(
    *,
    pitch: float = DEFAULT_ROOF_PITCH,
) -> PrimitiveDescriptor:
    """One-module valley trough proto (assemble scales along the wing seam)."""
    height = roof_valley_height_cm(pitch)
    tag = frozenset({module_tag(), "roof"})
    sockets = (
        SocketDesc(
            name="seam_y0",
            pos_cm=(MODULE_CM * 0.5, 0.0, height * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="roof_valley",
            tags=tag,
        ),
        SocketDesc(
            name="seam_y1",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM, height * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="roof_valley",
            tags=tag,
        ),
        SocketDesc(
            name="gutter",
            pos_cm=(MODULE_CM * 0.5, MODULE_CM * 0.5, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="roof_valley",
            tags=tag,
        ),
    )
    return PrimitiveDescriptor(
        id="roof_valley",
        kind="roof",
        footprint_modules=(1, 1),
        height_storeys=height / STOREY_CM,
        size_cm=(MODULE_CM, MODULE_CM, height),
        sockets=sockets,
        tags=frozenset({"roof", "valley", "pitched", "stub", module_tag()}),
        origin="min_corner",
        notes=(
            f"Pitch={pitch}: V-trough valley stub height={height:.1f} cm; "
            "assemble places one per L/U wing abutment (S-019). "
            f"Cross-section width at place={VALLEY_WIDTH_CM:.0f} cm "
            f"(~{VALLEY_WIDTH_CM / WALL_T_CM:.1f}× WALL_T)."
        ),
    )


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
    return (
        roof_gable_infill(),
        roof_pitched_slope(),
        roof_hip(),
        roof_valley(),
        roof_flat(),
    )


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
    """Full-footprint double-pitch deck: eaves at y=0/sy, ridge at mid-Y, height *sz*.

    Gable ends are **not** closed here — assemble pairs this mesh with separate
    ``roof_gable_infill`` prisms. Baking gable caps into the slope caused triple
    overlapping extruded triangles on fortress / hall roofs.
    """
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
        (0, 3, 2, 1),  # underside
    ]
    return verts, faces


def _valley_verts_faces(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """V-trough valley stub — gutter along the long axis, lips at *sz*.

    Long-X (``sx >= sy``): gutter along mid-Y. Long-Y: gutter along mid-X.
    """
    if sx >= sy:
        mid = sy * 0.5
        verts: List[Vec3] = [
            (0.0, 0.0, sz),
            (sx, 0.0, sz),
            (sx, sy, sz),
            (0.0, sy, sz),
            (0.0, mid, 0.0),
            (sx, mid, 0.0),
        ]
        faces: List[Sequence[int]] = [
            (0, 1, 5, 4),
            (4, 5, 2, 3),
            (0, 4, 3),
            (1, 2, 5),
        ]
        return verts, faces
    mid = sx * 0.5
    verts = [
        (0.0, 0.0, sz),
        (sx, 0.0, sz),
        (sx, sy, sz),
        (0.0, sy, sz),
        (mid, 0.0, 0.0),
        (mid, sy, 0.0),
    ]
    faces = [
        (0, 4, 5, 3),
        (4, 1, 2, 5),
        (0, 1, 4),
        (3, 5, 2),
    ]
    return verts, faces


def hip_roof_slope_face_count(verts: Sequence[Vec3], faces: Sequence[Sequence[int]]) -> int:
    """Count sloped roof plates — faces with at least one vertex above the eave plane."""
    count = 0
    for face in faces:
        zs = [verts[i][2] for i in face]
        if max(zs) <= 1e-6:
            continue
        if all(z <= 1e-6 for z in zs):
            continue
        count += 1
    return count


def hip_roof_verts_faces(
    sx: float, sy: float, sz: float
) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Public wrapper for hip mesh topology tests and Blender build."""
    return _hip_roof_verts_faces(sx, sy, sz)


def _hip_roof_verts_faces(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Four-slope hip on a rectangular footprint. *sz* is peak height above eave plane.

    Always authors exactly four sloped plates (square: four triangles; rectangle:
    two main slopes + two hip-end triangles). Underside is optional deck closure.
    """
    if sx >= sy:
        hip = sy * 0.5
        mid_y = sy * 0.5
        if sx <= sy + 1e-6:
            apex = (sx * 0.5, mid_y, sz)
            verts: List[Vec3] = [
                (0.0, 0.0, 0.0),
                (sx, 0.0, 0.0),
                (sx, sy, 0.0),
                (0.0, sy, 0.0),
                apex,
            ]
            faces: List[Sequence[int]] = [
                (0, 1, 4),
                (1, 2, 4),
                (2, 3, 4),
                (3, 0, 4),
                (0, 3, 2, 1),
            ]
            return verts, faces
        rw = (hip, mid_y, sz)
        re = (sx - hip, mid_y, sz)
        verts = [
            (0.0, 0.0, 0.0),
            (sx, 0.0, 0.0),
            (sx, sy, 0.0),
            (0.0, sy, 0.0),
            rw,
            re,
        ]
        faces = [
            (0, 1, 5, 4),
            (3, 4, 5, 2),
            (0, 4, 3),
            (1, 2, 5),
            (0, 3, 2, 1),
        ]
        return verts, faces
    hip = sx * 0.5
    mid_x = sx * 0.5
    if sy <= sx + 1e-6:
        apex = (mid_x, sy * 0.5, sz)
        verts = [
            (0.0, 0.0, 0.0),
            (sx, 0.0, 0.0),
            (sx, sy, 0.0),
            (0.0, sy, 0.0),
            apex,
        ]
        faces = [
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (3, 0, 4),
            (0, 3, 2, 1),
        ]
        return verts, faces
    rs = (mid_x, hip, sz)
    rn = (mid_x, sy - hip, sz)
    verts = [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, sy, 0.0),
        (0.0, sy, 0.0),
        rs,
        rn,
    ]
    faces = [
        (0, 4, 5, 3),
        (4, 1, 2, 5),
        (0, 1, 4),
        (3, 5, 2),
        (0, 3, 2, 1),
    ]
    return verts, faces


def _double_pitch_verts_faces_ridge_y(sx: float, sy: float, sz: float) -> Tuple[List[Vec3], List[Sequence[int]]]:
    """Double-pitch with ridge along Y (eaves at x=0/sx); open ends for gable infill."""
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
        (0, 3, 2, 1),  # underside
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
    if desc.id == "roof_hip":
        verts, faces = _hip_roof_verts_faces(sx, sy, sz)
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
    if desc.id == "roof_valley":
        verts, faces = _valley_verts_faces(sx, sy, sz)
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
    return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)

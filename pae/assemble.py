"""Assembly stage (§6) — WP-5. Placement math only; geometry lives in primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union

from pae.assembly_types import (
    Assembly,
    Aperture,
    CirculationEdge,
    FloorPlanLayer,
    SolidPlacement,
    StyleAperturePolicy,
    WallRun,
)
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotation_offset_cm,
)
from pae.plan import CellRole, FloorPlan, StoreyGrid
from pae.primitives.catalog import catalog_by_id, get as get_primitive
from pae.primitives.roofs import roof_flat_span_size_cm
from pae.primitives.types import PrimitiveDescriptor
from pae.report import Failure, Report

AssetDBLike = Any
StyleLike = Union[Mapping[str, Any], None]


@dataclass
class Placement:
    """Serializable placement record (§6) — used by determinism hashing."""

    asset_id: str
    cell: Tuple[int, int]
    level: int
    yaw: int
    offset_cm: Tuple[float, float, float]


@dataclass(frozen=True)
class _ResolvedPiece:
    asset_id: str
    kind: str
    size_cm: Tuple[float, float, float]
    rotates_about_center: bool
    tags: frozenset[str]
    aperture: Any = None


def _descriptor_to_piece(desc: PrimitiveDescriptor) -> _ResolvedPiece:
    return _ResolvedPiece(
        asset_id=desc.id,
        kind=desc.kind,
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags,
        aperture=desc.aperture,
    )


def _asset_db_to_piece(asset: Any) -> _ResolvedPiece:
    return _ResolvedPiece(
        asset_id=asset.id,
        kind=asset.kind,
        size_cm=asset.size_cm,
        rotates_about_center=asset.rotates_about_center,
        tags=frozenset(asset.tags),
        aperture=None,
    )


class _PieceCatalog:
    """Resolve kit pieces from AssetDB first, then parametric primitives."""

    def __init__(self, asset_db: AssetDBLike | None) -> None:
        self._db = asset_db
        self._primitives = catalog_by_id()

    def get(self, asset_id: str) -> _ResolvedPiece:
        if self._db is not None:
            getter = getattr(self._db, "get_asset", None)
            if callable(getter):
                row = getter(asset_id)
                if row is not None:
                    return _asset_db_to_piece(row)
        if asset_id in self._primitives:
            return _descriptor_to_piece(self._primitives[asset_id])
        return _descriptor_to_piece(get_primitive(asset_id))

    def pick_wall(
        self,
        *,
        is_door: bool,
        is_window: bool,
        style: StyleLike,
    ) -> _ResolvedPiece:
        if is_door:
            return self.get("wall_door")
        if is_window:
            return self.get("wall_window")
        return self.get("wall_plain")


def _layer_from_grid(grid: StoreyGrid) -> FloorPlanLayer:
    ox, oy = grid.origin
    width, height = grid.size
    cells: List[List[CellRole]] = []
    for ly in range(height):
        row: List[CellRole] = []
        for lx in range(width):
            row.append(grid.get(ox + lx, oy + ly))
        cells.append(row)
    return FloorPlanLayer(
        level=grid.level,
        width=width,
        height=height,
        origin_cell=(ox, oy),
        cells=cells,
    )


_ENCLOSED_ROLES = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.WALL_LINE,
        CellRole.DOOR,
        CellRole.STAIR,
        CellRole.VOID,
    }
)

_FLOOR_ROLES = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.WALL_LINE,
        CellRole.DOOR,
        CellRole.STAIR,
    }
)


def _boundary_wall_cells(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> Dict[str, List[Tuple[int, int]]]:
    """§2.3 boundary-line wall cells with single corner ownership.

    East/north runs sit on ``x1+1`` / ``y1+1`` (not ``x1`` / ``y1``).

    Corner ownership — vertical runs (west/east) own perimeter corner cells;
    horizontal runs (south/north) omit the shared endpoint so each grid cell
    gets at most one wall piece:

    - **SW** ``(x0, y0)``: west keeps it; south starts at ``x0+1``.
    - East/north boundary lines are orthogonal (``x1+1`` column vs ``y1+1`` row),
      so they do not share grid cells; only west+south meet at one cell today.
    """
    return {
        "west": [(x0, y) for y in range(y0, y1 + 1)],
        "east": [(x1 + 1, y) for y in range(y0, y1 + 1)],
        "south": [(x, y0) for x in range(x0 + 1, x1 + 1)],
        "north": [(x, y1 + 1) for x in range(x0, x1 + 1)],
    }


def _footprint_bbox(grid: StoreyGrid) -> Tuple[int, int, int, int]:
    """Inclusive enclosed footprint (x0, y0, x1, y1) for §2.3 wall runs.

    WALL_LINE cells are part of the volume footprint — do **not** use INTERIOR
    alone or east/north land one module too far in.
    """
    enclosed = [
        (x, y)
        for (x, y), role in grid.cells.items()
        if role in _ENCLOSED_ROLES
    ]
    if not enclosed:
        ox, oy = grid.origin
        w, h = grid.size
        return ox, oy, ox + w - 1, oy + h - 1
    xs = [c[0] for c in enclosed]
    ys = [c[1] for c in enclosed]
    return min(xs), min(ys), max(xs), max(ys)


def _boundary_wall_offset_cm(
    face: str,
    yaw: int,
    piece: _ResolvedPiece,
) -> Tuple[float, float, float]:
    """§2.2 yaw offset + roof-tuck for east/north.

    West/south keep the stock rotation table — thickness sits under a footprint-
    sized roof (``[0, T]`` from the low edges).

    East/north sit on the ``x1+1`` / ``y1+1`` boundary *lines* but their
    thickness must go *inward* under the roof (``[edge − T, edge]``), not
    outward past it. Otherwise one pair of walls is tucked and the other
    sticks out past a footprint-exact roof slab.
    """
    from pae.contract import WALL_T_CM

    sx, sy, _ = piece.size_cm
    ox, oy = rotation_offset_cm(
        yaw,
        sx,
        sy,
        rotates_about_center=piece.rotates_about_center,
    )
    face = face.lower()
    if face == "east":
        # Stock yaw-180 offset is (sx, sy) → thickness [edge, edge+T] (outside).
        # Drop sx so thickness is [edge − T, edge] under the roof.
        ox = ox - WALL_T_CM
    elif face == "north":
        # Stock yaw-90 offset is (sy, 0) → thickness [edge, edge+T] (outside).
        # Pull back by wall thickness in Y.
        oy = oy - WALL_T_CM
    return (ox, oy, 0.0)


def _next_piece_id(
    counters: Dict[str, int],
    prefix: str,
    cell: Tuple[int, int],
    level: int,
) -> str:
    key = f"{prefix}_{level}_{cell[0]}_{cell[1]}"
    counters[key] = counters.get(key, 0) + 1
    n = counters[key]
    return key if n == 1 else f"{key}_{n}"


def _wall_asset_for_cell(
    fp: FloorPlan,
    cell: Tuple[int, int],
    face: str,
    catalog: _PieceCatalog,
    style: StyleLike,
) -> _ResolvedPiece:
    """Pick wall kit piece; map boundary-line cells back to footprint for openings."""
    x, y = cell
    face = face.lower()
    # East/north walls sit on x1+1 / y1+1 — openings are authored on footprint cells.
    if face == "east":
        probe = (x - 1, y)
    elif face == "north":
        probe = (x, y - 1)
    else:
        probe = cell
    is_door = probe in fp.door_cells or any(
        grid.get(probe[0], probe[1]) == CellRole.DOOR for grid in fp.storeys
    )
    is_window = probe in fp.window_cells
    return catalog.pick_wall(is_door=is_door, is_window=is_window, style=style)


def _interior_exterior_cells(
    face: str,
    cell: Tuple[int, int],
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    x, y = cell
    face = face.lower()
    if face == "west":
        return (x + 1, y), (x, y)
    if face == "east":
        return (x - 1, y), (x, y)
    if face == "south":
        return (x, y + 1), (x, y)
    if face == "north":
        return (x, y - 1), (x, y)
    raise ValueError(f"unknown face {face!r}")


def _aperture_world(
    piece: SolidPlacement,
    ap_kind: str,
) -> Tuple[float, float, float]:
    desc = get_primitive(piece.asset_id)
    if desc.aperture is None:
        bb_min, bb_max = placement_world_aabb(
            piece.cell[0],
            piece.cell[1],
            piece.level,
            piece.yaw,
            piece.size_cm,
            piece.offset_cm,
            rotates_about_center=piece.rotates_about_center,
        )
        return (
            (bb_min[0] + bb_max[0]) * 0.5,
            (bb_min[1] + bb_max[1]) * 0.5,
            bb_min[2],
        )
    ap = desc.aperture
    mid_local = (
        (ap.min_cm[0] + ap.max_cm[0]) * 0.5,
        (ap.min_cm[1] + ap.max_cm[1]) * 0.5,
        ap.min_cm[2],
    )
    from pae.contract import rotate_local_xy

    sx, sy, _ = piece.size_cm
    rx, ry = rotate_local_xy(mid_local[0], mid_local[1], piece.yaw, sx, sy)
    wx, wy, wz = piece.offset_cm
    cx, cy = piece.cell
    world_x = cx * MODULE_CM + wx + rx
    world_y = cy * MODULE_CM + wy + ry
    world_z = piece.level * STOREY_CM + wz + mid_local[2]
    return (world_x, world_y, world_z)


def _place_wall_run(
    *,
    face: str,
    cells: List[Tuple[int, int]],
    level: int,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    piece_ids: List[str],
    counters: Dict[str, int],
) -> None:
    yaw_by_face = {"west": 0, "east": 180, "south": 270, "north": 90}
    yaw = yaw_by_face[face]
    for cell in cells:

        piece_def = _wall_asset_for_cell(fp, cell, face, catalog, style)
        offset = _boundary_wall_offset_cm(face, yaw, piece_def)
        pid = _next_piece_id(counters, f"wall_{face}", cell, level)
        sp = SolidPlacement(
            piece_id=pid,
            asset_id=piece_def.asset_id,
            kind="wall",
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=piece_def.size_cm,
            rotates_about_center=piece_def.rotates_about_center,
            tags=piece_def.tags,
        )
        placements.append(sp)
        piece_ids.append(pid)

        if piece_def.asset_id == "wall_door":
            interior, exterior = _interior_exterior_cells(face, cell)
            floor_z = level * STOREY_CM
            sill = _aperture_world(sp, "door")[2]
            apertures.append(
                Aperture(
                    piece_id=f"door_{pid}",
                    kind="door",
                    wall_piece_id=pid,
                    level=level,
                    sill_z_cm=sill,
                    floor_z_cm=floor_z,
                    interior_cell=interior,
                    exterior_cell=exterior,
                    world_xyz=_aperture_world(sp, "door"),
                )
            )
        elif piece_def.asset_id == "wall_window":
            interior, exterior = _interior_exterior_cells(face, cell)
            floor_z = level * STOREY_CM
            sill = _aperture_world(sp, "window")[2]
            apertures.append(
                Aperture(
                    piece_id=f"win_{pid}",
                    kind="window",
                    wall_piece_id=pid,
                    level=level,
                    sill_z_cm=sill,
                    floor_z_cm=floor_z,
                    interior_cell=interior,
                    exterior_cell=exterior,
                    world_xyz=_aperture_world(sp, "window"),
                )
            )


def _build_wall_runs(
    *,
    wx0: int,
    wy0: int,
    wx1: int,
    wy1: int,
    ex: int,
    ny: int,
    level: int,
    piece_map: Dict[str, List[str]],
) -> List[WallRun]:
    runs: List[WallRun] = []
    face_meta = {
        "west": ("y", wx0 * MODULE_CM, wy0 * MODULE_CM, (wy1 + 1) * MODULE_CM),
        "east": ("y", ex * MODULE_CM, wy0 * MODULE_CM, (wy1 + 1) * MODULE_CM),
        "south": ("x", wy0 * MODULE_CM, wx0 * MODULE_CM, (wx1 + 1) * MODULE_CM),
        "north": ("x", ny * MODULE_CM, wx0 * MODULE_CM, (wx1 + 1) * MODULE_CM),
    }
    for face, ids in piece_map.items():
        if not ids:
            continue
        axis, plane, start, end = face_meta[face]
        runs.append(
            WallRun(
                run_id=f"run_{face}_L{level}",
                level=level,
                axis=axis,
                plane_cm=plane,
                piece_ids=ids,
                start_cm=start,
                end_cm=end,
            )
        )
    return runs


def _stair_run_anchor_and_yaw(
    cells: List[Tuple[int, int]],
) -> Tuple[Tuple[int, int], int]:
    """Bottom-left anchor and yaw for a straight 2-module run (§5.3)."""
    if not cells:
        raise ValueError("stair run requires at least one cell")
    ordered = sorted(cells)
    ax, ay = ordered[0]
    if len(ordered) == 1:
        return (ax, ay), 0
    bx, by = ordered[1]
    if ax == bx:
        return (ax, min(ay, by)), 90
    return (min(ax, bx), ay), 0


def _stair_occupied_cells(fp: FloorPlan) -> Set[Tuple[int, int, int]]:
    """(level, x, y) cells covered by a stair flight — skip floor slabs there."""
    occupied: Set[Tuple[int, int, int]] = set()
    run_cells = list(fp.stair_cells)
    if len(run_cells) < 2:
        return occupied
    for level in range(len(fp.storeys) - 1):
        grid = fp.storeys[level]
        if all(grid.get(*c) == CellRole.STAIR for c in run_cells):
            for cx, cy in run_cells:
                occupied.add((level, cx, cy))
    return occupied


def _place_stairs(
    *,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Emit one ``stair_straight`` per climbed storey (2 modules, 1 rise)."""
    run_cells = list(fp.stair_cells)
    if len(run_cells) < 2:
        return
    anchor, yaw = _stair_run_anchor_and_yaw(run_cells)
    stair_def = catalog.get("stair_straight")
    sx, sy, _ = stair_def.size_cm
    ox, oy = rotation_offset_cm(
        yaw,
        sx,
        sy,
        rotates_about_center=stair_def.rotates_about_center,
    )
    for level in range(len(fp.storeys) - 1):
        grid = fp.storeys[level]
        if not all(grid.get(*c) == CellRole.STAIR for c in run_cells):
            continue
        pid = _next_piece_id(counters, "stair", anchor, level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=stair_def.asset_id,
                kind="stair",
                cell=anchor,
                level=level,
                yaw=yaw,
                offset_cm=(ox, oy, 0.0),
                size_cm=stair_def.size_cm,
                rotates_about_center=stair_def.rotates_about_center,
                tags=stair_def.tags,
            )
        )


def _circulation_edges(fp: FloorPlan) -> List[CirculationEdge]:
    edges: List[CirculationEdge] = []
    seen: Set[Tuple[int, int, int, int]] = set()
    for u, v in fp.circulation.edges:
        key = (u[0], u[1], v[0], v[1])
        rev = (v[0], v[1], u[0], u[1])
        if key in seen or rev in seen:
            continue
        seen.add(key)
        edges.append(
            CirculationEdge(
                piece_id=f"stair_{u[0]}_{u[1]}_to_{v[0]}_{v[1]}",
                from_level=u[0],
                to_level=v[0],
            )
        )
    return edges


def _tower_cells(fp: FloorPlan) -> Set[Tuple[int, int]]:
    """Cells owned by tower volumes (cap/arcs, not pitched roof)."""
    cells: Set[Tuple[int, int]] = set()
    if fp.massing is None:
        return cells
    for vol in fp.massing.volumes:
        if vol.role == "tower":
            cells |= vol.cells()
    return cells


def _place_pitched_roof(
    *,
    grid: StoreyGrid,
    level: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    catalog: _PieceCatalog,
    tower_cells: Set[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Place ``roof_pitched_gable`` over the top storey (gable infill in-piece).

    Prior failure: walls stopped at the eaves and nothing filled the gable
    triangle → 8 m holes. The pitched kit piece includes solid gable faces.

    Spans the enclosed footprint (same pattern as flat roof) so the deck rests
    on the wall ring for §7.2 vertical support. Tower cells are excluded from
    the span when they sit outside the main bbox min/max — tower uses its own
    crown/cap instead.
    """
    del grid  # footprint bbox is authoritative for the deck span
    roof_piece = catalog.get("roof_pitched_gable")
    roof_z = STOREY_CM
    # Shrink bbox away from tower-only cells when tower expands the ring.
    cells = [
        (x, y)
        for x in range(x0, x1 + 1)
        for y in range(y0, y1 + 1)
        if (x, y) not in tower_cells
    ]
    if not cells:
        return
    rx0 = min(c[0] for c in cells)
    ry0 = min(c[1] for c in cells)
    rx1 = max(c[0] for c in cells)
    ry1 = max(c[1] for c in cells)
    modules_x = rx1 - rx0 + 1
    modules_y = ry1 - ry0 + 1
    span_x = modules_x * MODULE_CM
    span_y = modules_y * MODULE_CM
    _, _, hz = roof_piece.size_cm
    pid = _next_piece_id(counters, "roof_pitched", (rx0, ry0), level)
    placements.append(
        SolidPlacement(
            piece_id=pid,
            asset_id=roof_piece.asset_id,
            kind="roof",
            cell=(rx0, ry0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, roof_z),
            size_cm=(span_x, span_y, hz),
            rotates_about_center=roof_piece.rotates_about_center,
            tags=roof_piece.tags,
        )
    )


def _place_tower_arcs(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Place 4× ``tower_arc_quarter`` at the *same* tower cell (§2.2 centred).

    Prior failure: offsetting quarters to four cells scattered the drum and
    left no curved wall. Quarters share the circle centre; yaw only.
    """
    if floor_plan.massing is None:
        return
    arc = catalog.get("tower_arc_quarter")
    crown = catalog.get("tower_crown")
    cap = catalog.get("tower_cap")
    for vol in floor_plan.massing.volumes:
        if vol.role != "tower":
            continue
        # 1×1 tower footprint — all quarters share (x0, y0).
        cell = (vol.x0, vol.y0)
        for level in range(vol.storeys):
            for yaw in (0, 90, 180, 270):
                # §2.2 centred exception — no min-corner yaw offset, same cell.
                pid = _next_piece_id(counters, f"tower_arc_{yaw}", cell, level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=arc.asset_id,
                        kind="tower_arc",
                        cell=cell,
                        level=level,
                        yaw=yaw,
                        offset_cm=(0.0, 0.0, 0.0),
                        size_cm=arc.size_cm,
                        rotates_about_center=True,
                        tags=arc.tags,
                    )
                )
        # Crown + cap on the drum top (centred, same cell).
        top = vol.storeys - 1
        crown_z = STOREY_CM
        for piece, kind, z_off in (
            (crown, "tower_crown", crown_z),
            (cap, "tower_cap", crown_z + crown.size_cm[2]),
        ):
            pid = _next_piece_id(counters, kind, cell, top)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=piece.asset_id,
                    kind=kind,
                    cell=cell,
                    level=top,
                    yaw=0,
                    offset_cm=(0.0, 0.0, z_off),
                    size_cm=piece.size_cm,
                    rotates_about_center=True,
                    tags=piece.tags,
                )
            )


def assemble(
    floor_plan: FloorPlan,
    asset_db: AssetDBLike | None,
    style: StyleLike,
) -> Tuple[Assembly, Report]:
    """Pure function: FloorPlan + assets + style → Assembly (§6)."""
    failures: List[Failure] = []
    if floor_plan is None or not floor_plan.storeys:
        return Assembly(placements=[]), Report.from_failures(
            [
                Failure(
                    check="assemble_empty",
                    message="floor plan has no storeys",
                    world_xyz=None,
                )
            ]
        )

    catalog = _PieceCatalog(asset_db)
    placements: List[SolidPlacement] = []
    apertures: List[Aperture] = []
    counters: Dict[str, int] = {}
    floor_layers: Dict[int, FloorPlanLayer] = {}

    storeys = len(floor_plan.storeys)
    stair_occupied = _stair_occupied_cells(floor_plan)

    for grid in floor_plan.storeys:
        level = grid.level
        floor_layers[level] = _layer_from_grid(grid)
        x0, y0, x1, y1 = _footprint_bbox(grid)

        run_piece_ids: Dict[str, List[str]] = {
            "west": [],
            "east": [],
            "south": [],
            "north": [],
        }

        # §2.3 boundary-line cells — corner ownership via _boundary_wall_cells.
        wall_cells = _boundary_wall_cells(x0, y0, x1, y1)

        for face, cells in (
            ("west", wall_cells["west"]),
            ("east", wall_cells["east"]),
            ("south", wall_cells["south"]),
            ("north", wall_cells["north"]),
        ):
            before = len(placements)
            _place_wall_run(
                face=face,
                cells=cells,
                level=level,
                fp=floor_plan,
                catalog=catalog,
                style=style,
                placements=placements,
                apertures=apertures,
                piece_ids=run_piece_ids[face],
                counters=counters,
            )
            run_piece_ids[face] = [p.piece_id for p in placements[before:]]

        floor_piece = catalog.get("floor")
        floor_z_off = -FLOOR_T_CM
        if level == 0:
            for (cx, cy), role in grid.cells.items():
                if (level, cx, cy) in stair_occupied:
                    continue
                if role in _FLOOR_ROLES:
                    pid = _next_piece_id(counters, "floor", (cx, cy), level)
                    placements.append(
                        SolidPlacement(
                            piece_id=pid,
                            asset_id=floor_piece.asset_id,
                            kind="floor",
                            cell=(cx, cy),
                            level=level,
                            yaw=0,
                            offset_cm=(0.0, 0.0, floor_z_off),
                            size_cm=floor_piece.size_cm,
                            tags=floor_piece.tags,
                        )
                    )
        else:
            # Upper storeys: one spanning deck (perimeter walls carry the span).
            modules_x = x1 - x0 + 1
            modules_y = y1 - y0 + 1
            pid = _next_piece_id(counters, "floor_deck", (x0, y0), level)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=floor_piece.asset_id,
                    kind="floor",
                    cell=(x0, y0),
                    level=level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, floor_z_off),
                    size_cm=roof_flat_span_size_cm(modules_x, modules_y),
                    tags=floor_piece.tags,
                )
            )
            for (cx, cy), role in grid.cells.items():
                if role != CellRole.VOID:
                    continue
                hole = catalog.get("floor_hole")
                pid = _next_piece_id(counters, "floor_hole", (cx, cy), level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=hole.asset_id,
                        kind="floor",
                        cell=(cx, cy),
                        level=level,
                        yaw=0,
                        offset_cm=(0.0, 0.0, floor_z_off),
                        size_cm=hole.size_cm,
                        tags=hole.tags,
                    )
                )

        if level == storeys - 1:
            if floor_plan.roof_kind == "flat":
                roof_piece = catalog.get("roof_flat")
                roof_z = STOREY_CM
                modules_x = x1 - x0 + 1
                modules_y = y1 - y0 + 1
                pid = _next_piece_id(counters, "roof", (x0, y0), level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=roof_piece.asset_id,
                        kind="roof",
                        cell=(x0, y0),
                        level=level,
                        yaw=0,
                        offset_cm=(0.0, 0.0, roof_z),
                        size_cm=roof_flat_span_size_cm(modules_x, modules_y),
                        tags=roof_piece.tags,
                    )
                )
            elif floor_plan.roof_kind == "pitched":
                _place_pitched_roof(
                    grid=grid,
                    level=level,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    catalog=catalog,
                    tower_cells=_tower_cells(floor_plan),
                    placements=placements,
                    counters=counters,
                )

    _place_stairs(
        fp=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    # Round towers: 4 arc quarters × same cell (§2.2 centred exception).
    _place_tower_arcs(
        floor_plan=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    if floor_plan.ground_slab:
        plinth = catalog.get("ground_plinth")
        ground_z = ground_plinth_z_cm()
        for grid in floor_plan.storeys:
            if grid.level != 0:
                continue
            for (cx, cy), role in grid.cells.items():
                if role not in _FLOOR_ROLES:
                    continue
                pid = _next_piece_id(counters, "ground", (cx, cy), 0)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=plinth.asset_id,
                        kind="ground",
                        cell=(cx, cy),
                        level=0,
                        yaw=0,
                        offset_cm=(0.0, 0.0, ground_z),
                        size_cm=plinth.size_cm,
                        tags=plinth.tags,
                    )
                )

    wall_runs: List[WallRun] = []
    for grid in floor_plan.storeys:
        level = grid.level
        x0, y0, x1, y1 = _footprint_bbox(grid)
        ex = x1 + 1
        ny = y1 + 1
        ids_by_face: Dict[str, List[str]] = {
            "west": [],
            "east": [],
            "south": [],
            "north": [],
        }
        for p in placements:
            if p.level != level or p.kind != "wall":
                continue
            cx, cy = p.cell
            if cx == x0 and y0 <= cy <= y1:
                ids_by_face["west"].append(p.piece_id)
            elif cx == ex and y0 <= cy <= y1:
                ids_by_face["east"].append(p.piece_id)
            elif cy == y0 and x0 <= cx <= x1:
                ids_by_face["south"].append(p.piece_id)
            elif cy == ny and x0 <= cx <= x1:
                ids_by_face["north"].append(p.piece_id)
        wall_runs.extend(
            _build_wall_runs(
                wx0=x0,
                wy0=y0,
                wx1=x1,
                wy1=y1,
                ex=ex,
                ny=ny,
                level=level,
                piece_map=ids_by_face,
            )
        )

    assembly = Assembly(
        placements=placements,
        floor_plan=floor_layers,
        circulation=_circulation_edges(floor_plan),
        wall_runs=wall_runs,
        apertures=apertures,
        storeys=storeys,
        aperture_policy=StyleAperturePolicy(),
    )
    return assembly, Report.from_failures(failures)


def placements_from_assembly(assembly: Assembly) -> List[Placement]:
    """Extract hash-friendly Placement rows from an Assembly."""
    rows: List[Placement] = []
    for p in assembly.placements:
        rows.append(
            Placement(
                asset_id=p.asset_id,
                cell=p.cell,
                level=p.level,
                yaw=p.yaw,
                offset_cm=p.offset_cm,
            )
        )
    return rows


__all__ = ["Placement", "assemble", "placements_from_assembly"]

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
    floor_placement_z_cm,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotation_offset_cm,
)
from pae.plan import CellRole, FloorPlan, StoreyGrid
from pae.primitives.catalog import catalog_by_id, get as get_primitive
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


def _interior_bbox(grid: StoreyGrid) -> Tuple[int, int, int, int]:
    """Inclusive interior cell bounds (§2.3 room coordinates)."""
    interior = [
        (x, y) for (x, y), role in grid.cells.items() if role == CellRole.INTERIOR
    ]
    if not interior:
        ox, oy = grid.origin
        w, h = grid.size
        return ox, oy, ox + w - 1, oy + h - 1
    xs = [c[0] for c in interior]
    ys = [c[1] for c in interior]
    return min(xs), min(ys), max(xs), max(ys)


def _wall_ring_from_interior(ix0: int, iy0: int, ix1: int, iy1: int) -> Tuple[int, int, int, int]:
    """Perimeter span for wall modules: west/east x and south/north y (§2.3)."""
    return ix0 - 1, iy0 - 1, ix1 + 1, iy1 + 1


def _boundary_wall_offset_cm(
    face: str,
    yaw: int,
    piece: _ResolvedPiece,
) -> Tuple[float, float, float]:
    """§2.2 offset via contract; §2.3 boundary cells absorb E/S/N table shift."""
    sx, sy, _ = piece.size_cm
    if face == "west":
        ox, oy = rotation_offset_cm(
            yaw,
            sx,
            sy,
            rotates_about_center=piece.rotates_about_center,
        )
    else:
        # East/north/south runs sit on x1+1 / y1+1 boundary-line cells — the
        # rotation-offset table is satisfied by cell index + yaw, not extra XY.
        ox, oy = 0.0, 0.0
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
    catalog: _PieceCatalog,
    style: StyleLike,
) -> _ResolvedPiece:
    x, y = cell
    is_door = cell in fp.door_cells or any(
        grid.get(x, y) == CellRole.DOOR for grid in fp.storeys
    )
    is_window = cell in fp.window_cells
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

        piece_def = _wall_asset_for_cell(fp, cell, catalog, style)
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

    for grid in floor_plan.storeys:
        level = grid.level
        floor_layers[level] = _layer_from_grid(grid)
        ix0, iy0, ix1, iy1 = _interior_bbox(grid)
        wx0, wy0, ex, ny = _wall_ring_from_interior(ix0, iy0, ix1, iy1)
        wx1 = ex
        wy1 = ny

        run_piece_ids: Dict[str, List[str]] = {
            "west": [],
            "east": [],
            "south": [],
            "north": [],
        }

        west_cells = [(wx0, y) for y in range(wy0, wy1 + 1)]
        east_cells = [(ex, y) for y in range(wy0, wy1 + 1)]
        south_cells = [(x, wy0) for x in range(wx0, wx1 + 1)]
        north_cells = [(x, ny) for x in range(wx0, wx1 + 1)]

        for face, cells in (
            ("west", west_cells),
            ("east", east_cells),
            ("south", south_cells),
            ("north", north_cells),
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
        floor_z_off = floor_placement_z_cm(level)
        for (cx, cy), role in grid.cells.items():
            if role == CellRole.INTERIOR:
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
            elif role == CellRole.VOID:
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

        if floor_plan.roof_kind == "flat" and level == storeys - 1:
            roof_z = STOREY_CM
            span_x = (wx1 - wx0 + 1) * MODULE_CM
            span_y = (wy1 - wy0 + 1) * MODULE_CM
            pid = _next_piece_id(counters, "roof", (wx0, wy0), level)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id="roof_flat",
                    kind="roof",
                    cell=(wx0, wy0),
                    level=level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, roof_z),
                    size_cm=(span_x, span_y, FLOOR_T_CM),
                    tags=frozenset({"roof", "flat"}),
                )
            )

    if floor_plan.ground_slab:
        plinth = catalog.get("ground_plinth")
        ground_z = ground_plinth_z_cm()
        for grid in floor_plan.storeys:
            if grid.level != 0:
                continue
            for (cx, cy), role in grid.cells.items():
                if role == CellRole.EXTERIOR:
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
        ix0, iy0, ix1, iy1 = _interior_bbox(grid)
        wx0, wy0, ex, ny = _wall_ring_from_interior(ix0, iy0, ix1, iy1)
        wx1 = ex
        wy1 = ny
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
            if cx == wx0 and wy0 <= cy <= wy1:
                ids_by_face["west"].append(p.piece_id)
            elif cx == ex and wy0 <= cy <= wy1:
                ids_by_face["east"].append(p.piece_id)
            elif cy == wy0 and wx0 <= cx <= wx1:
                ids_by_face["south"].append(p.piece_id)
            elif cy == ny and wx0 <= cx <= wx1:
                ids_by_face["north"].append(p.piece_id)
        wall_runs.extend(
            _build_wall_runs(
                wx0=wx0,
                wy0=wy0,
                wx1=wx1,
                wy1=wy1,
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

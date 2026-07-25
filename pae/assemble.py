"""Assembly stage (§6) — WP-5. Placement math only; geometry lives in primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

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
    WALL_T_CM,
    cell_to_world_cm,
    ground_plinth_z_cm,
    placement_world_aabb,
    rotation_offset_cm,
)
from pae.solver import Volume

# Soft separation between stacked tower roof pieces (visual only; junction owns the joint).
_TOWER_STACK_GAP_CM = 0.5
_TOWER_QUARTER_YAWS = (0, 90, 180, 270)
# Drum-rim window overlays (Phase 0.6). ``placement_world_aabb`` with
# ``rotates_about_center=True`` does **not** rotate the XY box — thin/long axes
# must be baked per yaw. Outer drum half-extent is ``MODULE/2`` (arc size MODULE).
# Push to the rim and bias away from the attach kiss so overlays do not slice the
# hall wall (interpenetration / headroom / roof_penetration). Rim thickness = WALL_T_CM.
_TOWER_WIN_CHORD_CM = MODULE_CM * 0.45
_TOWER_WIN_HEIGHT_CM = 160.0  # under storey / roof; aperture sill stays on the piece
from pae.plan import CellRole, FloorPlan, StoreyGrid
from pae.solver import WING_ROLES
from pae.primitives.catalog import catalog_by_id, get as get_primitive
from pae.primitives.plinth import ground_plinth_span_size_cm
from pae.primitives.roofs import (
    VALLEY_WIDTH_CM,
    roof_eave_offset_cm,
    roof_eave_overhang_per_side,
    roof_flat_span_size_cm,
    roof_gable_end_offset_cm,
    roof_gable_end_size_cm,
    roof_hip_span_size_cm,
    roof_rise_cm,
    roof_valley_seams,
    roof_valley_span_size_cm,
)
from pae.existence import check_entrance_existence
from pae.entrance_ensemble import (
    check_entrance_ensemble_existence,
    expand_entrance_ensembles,
)
from pae.primitives.types import PrimitiveDescriptor
from pae.report import Failure, Report
from pae.style_pack import resolve_piece_id
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
        entrance_role: Optional[str] = None,
    ) -> _ResolvedPiece:
        if is_door:
            asset_id = _door_asset_for_role(entrance_role, style)
            return self.get(asset_id)
        if is_window:
            return self.get(_style_window_asset(style))
        return self.get("wall_plain")


def _style_window_tag(style: StyleLike) -> str:
    if style is None:
        return "window_plain"
    if isinstance(style, dict):
        win = style.get("window") or {}
        if isinstance(win, dict):
            return str(win.get("tag") or "window_plain")
    return "window_plain"


def _style_window_asset(style: StyleLike) -> str:
    """Map style window tags onto existing aperture wall piece ids."""
    tag = _style_window_tag(style)
    return resolve_piece_id(style if isinstance(style, dict) else None, role="window", tag=tag)


def _style_is_gothic(style: StyleLike) -> bool:
    if style is None:
        return False
    if isinstance(style, dict):
        win = style.get("window") or {}
        if isinstance(win, dict):
            tag = str(win.get("tag") or "").lower()
            return "gothic" in tag or "lancet" in tag
    return False


def _style_door_asset(style: StyleLike) -> str:
    if style is None:
        return "wall_door"
    if _style_is_gothic(style):
        return "wall_door_gothic"
    return "wall_door"


def _door_asset_for_role(role: Optional[str], style: StyleLike) -> str:
    """Map entrance role → wall kit piece (§1.1)."""
    if not role:
        return _style_door_asset(style)
    role = role.lower()
    gothic = _style_is_gothic(style)
    if role in ("grand", "gate"):
        return "wall_door_gothic" if gothic else "wall_gate_arch"
    if role == "main":
        return "wall_door_gothic" if gothic else "wall_door"
    if role in ("service", "postern"):
        return "wall_door_plain"
    if role == "side":
        return "wall_door"
    if role == "balcony":
        return "wall_door"
    if role == "upper_exterior":
        return "wall_door"
    if role == "internal":
        return "wall_door_plain"
    return _style_door_asset(style)


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
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
    }
)

_FLOOR_ROLES = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.WALL_LINE,
        CellRole.DOOR,
        CellRole.STAIR,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
    }
)

_VOID_FACING_ROLES = frozenset({CellRole.EXTERIOR, CellRole.COURTYARD})

_FACE_DELTA: Dict[str, Tuple[int, int]] = {
    "west": (-1, 0),
    "east": (1, 0),
    "south": (0, -1),
    "north": (0, 1),
}

_INWARD_DELTA: Dict[str, Tuple[int, int]] = {
    "west": (1, 0),
    "east": (-1, 0),
    "south": (0, 1),
    "north": (0, -1),
}

_OUTWARD_DELTA: Dict[str, Tuple[int, int]] = {
    face: (-dx, -dy) for face, (dx, dy) in _INWARD_DELTA.items()
}

_PERIMETER_WALL_FACES = frozenset({"west", "east", "south", "north"})

_WALKABLE_INTERIOR_ROLES = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.STAIR,
        CellRole.DOOR,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
    }
)

_YAW_FOR_VOID_FACE: Dict[str, int] = {
    "west": 0,
    "east": 180,
    "south": 270,
    "north": 90,
}


def _inner_wall_faces(
    grid: StoreyGrid,
    cx: int,
    cy: int,
    bbox: Tuple[int, int, int, int],
) -> List[str]:
    """Faces of a WALL_LINE cell toward EXTERIOR/COURTYARD not covered by §2.3 runs."""
    x0, y0, x1, y1 = bbox
    faces: List[str] = []
    for face, (dx, dy) in _FACE_DELTA.items():
        if grid.get(cx + dx, cy + dy) not in _VOID_FACING_ROLES:
            continue
        if face == "west" and cx == x0:
            continue
        if face == "east" and cx == x1:
            continue
        if face == "south" and cy == y0:
            continue
        if face == "north" and cy == y1:
            continue
        # Perpendicular perimeter runs already close corner bands (§2.3).
        if face == "north" and cy == y0:
            continue
        if face == "south" and cy == y1:
            continue
        if face == "east" and cx == x0:
            continue
        if face == "west" and cx == x1:
            continue
        faces.append(face)
    return faces


def _massing_wing_roof_spans(
    floor_plan: FloorPlan,
    grid: StoreyGrid,
) -> Optional[List[Tuple[int, int, int, int]]]:
    """Per main/wing volume roofs when courtyard or multi-wing (§11 M4).

    Avoids a single bbox deck over a courtyard hole. Towers keep their own caps.
    """
    has_courtyard = any(
        role == CellRole.COURTYARD for role in grid.cells.values()
    )
    if floor_plan.massing is None:
        return None
    wings = [
        v
        for v in floor_plan.massing.enclosed_volumes()
        if v.role in WING_ROLES
    ]
    if has_courtyard:
        return [(v.x0, v.y0, v.x1, v.y1) for v in wings]
    if len(wings) > 1:
        return [(v.x0, v.y0, v.x1, v.y1) for v in wings]
    return None


def _ground_spans(
    floor_plan: FloorPlan,
    grid: StoreyGrid,
) -> List[Tuple[int, int, int, int]]:
    """Inclusive cell spans for continuous ground slabs (§2.5).

    Main/wing massing volumes only — tower attach cells can be DOOR roles that
    widen ``_footprint_bbox`` without a walkable slab. Courtyard / multi-wing
    uses the same per-wing splits as roofs.
    """
    wing_spans = _massing_wing_roof_spans(floor_plan, grid)
    if wing_spans:
        return wing_spans
    if floor_plan.massing is not None:
        wings = [
            v
            for v in floor_plan.massing.enclosed_volumes()
            if v.role in WING_ROLES
        ]
        if wings:
            return [(v.x0, v.y0, v.x1, v.y1) for v in wings]
    x0, y0, x1, y1 = _footprint_bbox(grid)
    return [(x0, y0, x1, y1)]


def _place_inhabited_inner_walls(
    *,
    grid: StoreyGrid,
    bbox: Tuple[int, int, int, int],
    level: int,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Inhabited wall ranges on re-entrant / courtyard boundaries (§11 M4)."""
    for (cx, cy), role in grid.cells.items():
        if role != CellRole.WALL_LINE:
            continue
        for face in _inner_wall_faces(grid, cx, cy, bbox):
            yaw = _YAW_FOR_VOID_FACE[face]
            piece_def = catalog.get("wall_plain")
            sx, sy, _ = piece_def.size_cm
            offset = rotation_offset_cm(
                yaw,
                sx,
                sy,
                rotates_about_center=piece_def.rotates_about_center,
            )
            pid = _next_piece_id(counters, f"wall_inner_{face}", (cx, cy), level)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=piece_def.asset_id,
                    kind="wall",
                    cell=(cx, cy),
                    level=level,
                    yaw=yaw,
                    offset_cm=(offset[0], offset[1], 0.0),
                    size_cm=piece_def.size_cm,
                    rotates_about_center=piece_def.rotates_about_center,
                    tags=piece_def.tags,
                )
            )


def _boundary_wall_cells(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> Dict[str, List[Tuple[int, int]]]:
    """§2.3 boundary-line wall cells.

    East/north on ``x1+1`` / ``y1+1``. Corner cells are placed on **both**
    meeting runs (overlap by ``WALL_T``) so the perimeter never leaves a
    one-bay hole — omitting SW from south previously opened the south face
    between the west corner piece and ``(x0+1, y0)``.
    """
    return {
        "west": [(x0, y) for y in range(y0, y1 + 1)],
        "east": [(x1 + 1, y) for y in range(y0, y1 + 1)],
        "south": [(x, y0) for x in range(x0, x1 + 1)],
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


_OPENING_FACE_PRIORITY: Dict[str, Tuple[str, ...]] = {
    # Plan places ground doors on the south run first (§plan._place_doors_windows).
    "door": ("south", "north", "east", "west"),
    # Windows on west/east wall-line cells must not bleed onto north/south corners.
    "window": ("west", "east", "south", "north"),
}


def _perimeter_faces_for_footprint_cell(
    cx: int,
    cy: int,
    bbox: Tuple[int, int, int, int],
) -> Tuple[str, ...]:
    """Exterior faces owned by a footprint wall-line cell (1 or 2 at corners)."""
    x0, y0, x1, y1 = bbox
    faces: List[str] = []
    if cx == x0:
        faces.append("west")
    if cx == x1:
        faces.append("east")
    if cy == y0:
        faces.append("south")
    if cy == y1:
        faces.append("north")
    return tuple(faces)


def _primary_opening_face(
    cell: Tuple[int, int],
    bbox: Tuple[int, int, int, int],
    kind: str,
) -> Optional[str]:
    """Single perimeter face that carries a door/window on *cell* (corner-safe)."""
    faces = _perimeter_faces_for_footprint_cell(cell[0], cell[1], bbox)
    if not faces:
        return None
    if len(faces) == 1:
        return faces[0]
    for face in _OPENING_FACE_PRIORITY[kind]:
        if face in faces:
            return face
    return faces[0]


def _window_cells_for_level(fp: FloorPlan, level: int) -> Set[Tuple[int, int]]:
    """Per-storey window bays.

    Ground openings come from the plan. Upper storeys always recompute exterior
    glazing via ``_upper_storey_window_cells`` — copying ``fp.window_cells`` stamped
    plan bays that only receive an *inner* wall (no ``_wall_asset_for_cell`` pass),
    so storey_egress VOLUME stayed critical even when a window cell was "planned".
    """
    if level == 0:
        return set(fp.window_cells)
    if fp.massing is None:
        return set(fp.window_cells)
    return _upper_storey_window_cells(fp, level)


def _upper_storey_window_cells(fp: FloorPlan, level: int) -> Set[Tuple[int, int]]:
    """Mirror plan._place_doors_windows glazing for levels above ground.

    Candidates are exterior south-face bays first (same preference as the plan
    stage). Walking *all* WALL_LINE cells used to pick west-edge cells whose only
    placed piece was an inner south-facing wall — primary face ``west`` never
    received a window, so storey_egress VOLUME stayed critical on random specs.
    """
    from pae.plan import _enclosed_cells_at_level

    massing = fp.massing
    assert massing is not None
    grid = fp.storeys[level]
    interior = _enclosed_cells_at_level(massing, level)
    wall_cells = sorted(
        (x, y) for (x, y), role in grid.cells.items() if role == CellRole.WALL_LINE
    )
    south = sorted(
        (x, y)
        for x, y in wall_cells
        if (x, y - 1) not in interior and (x, y + 1) in interior
    )
    # Other exterior faces as fallback when the south run is all door bays.
    exterior = south + sorted(
        c
        for c in wall_cells
        if c not in south
        and (
            (c[0] - 1, c[1]) not in interior
            or (c[0] + 1, c[1]) not in interior
            or (c[0], c[1] + 1) not in interior
        )
    )
    candidates = exterior if exterior else wall_cells
    n_win = max(0, massing.openings_windows_per_bay * max(1, len(south) or 1))
    if n_win == 0 and candidates:
        # Upper storeys need >=1 aperture for storey_egress VOLUME when per_bay is
        # zero or ground glazing was suppressed.
        n_win = 1
    door_bays = set(fp.door_cells)
    out: List[Tuple[int, int]] = []
    placed = 0
    for cell in candidates:
        if placed >= n_win:
            break
        if cell in door_bays:
            continue
        out.append(cell)
        placed += 1
    return set(out)


def _opening_probe_cell(cell: Tuple[int, int], face: str) -> Tuple[int, int]:
    """Map boundary-line cell back to footprint cell for openings (§2.3)."""
    x, y = cell
    face = face.lower()
    if face == "east":
        return (x - 1, y)
    if face == "north":
        return (x, y - 1)
    return cell


def _wall_asset_for_cell(
    fp: FloorPlan,
    cell: Tuple[int, int],
    face: str,
    catalog: _PieceCatalog,
    style: StyleLike,
    bbox: Tuple[int, int, int, int],
    level: int,
) -> _ResolvedPiece:
    """Pick wall kit piece; map boundary-line cells back to footprint for openings."""
    probe = _opening_probe_cell(cell, face)
    # Openings are per-storey. A ground DOOR role must not stamp a door on every
    # upper perimeter wall at the same bay (tower attach / stacked elevations).
    grid = fp.storeys[level]
    is_door = (
        (level == 0 and probe in fp.door_cells)
        or grid.get(probe[0], probe[1]) == CellRole.DOOR
    )
    is_window = probe in _window_cells_for_level(fp, level)
    if is_door:
        primary = _primary_opening_face(probe, bbox, "door")
        if primary is not None and face != primary:
            is_door = False
    if is_window:
        primary = _primary_opening_face(probe, bbox, "window")
        if primary is not None and face != primary:
            is_window = False
    entrance_role = fp.entrance_by_cell.get(probe) if is_door else None
    return catalog.pick_wall(
        is_door=is_door,
        is_window=is_window,
        style=style,
        entrance_role=entrance_role,
    )


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


def _perimeter_wall_face(piece_id: str) -> Optional[str]:
    parts = piece_id.split("_")
    if len(parts) >= 3 and parts[0] == "wall" and parts[1] in _PERIMETER_WALL_FACES:
        return parts[1]
    return None


def _resolve_walkable_interior(
    face: str,
    cell: Tuple[int, int],
    layer: FloorPlanLayer,
) -> Tuple[int, int]:
    """Step through WALL_LINE corners to the inhabited cell behind a door."""
    inward = _INWARD_DELTA[face.lower()]
    perp = (-inward[1], inward[0])
    seeds = {
        (cell[0] + inward[0], cell[1] + inward[1]),
        (cell[0] + inward[0] + perp[0], cell[1] + inward[1] + perp[1]),
        (cell[0] + inward[0] - perp[0], cell[1] + inward[1] - perp[1]),
    }
    for seed in seeds:
        if layer.role_at(*seed) in _WALKABLE_INTERIOR_ROLES:
            return seed
    queue: List[Tuple[int, int]] = list(seeds)
    seen = set(seeds)
    while queue:
        cx, cy = queue.pop(0)
        if layer.role_at(cx, cy) in _WALKABLE_INTERIOR_ROLES:
            return (cx, cy)
        if layer.role_at(cx, cy) not in (
            CellRole.WALL_LINE,
            CellRole.DOOR,
            CellRole.VOID,
            CellRole.DOUBLE_VOID,
            CellRole.EXTERIOR,
        ):
            continue
        for dx, dy in (inward, perp, (-perp[0], -perp[1])):
            nxt = (cx + dx, cy + dy)
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    naive_int, _ = _interior_exterior_cells(face, cell)
    return naive_int


def _resolve_exterior_cell(
    face: str,
    cell: Tuple[int, int],
    layer: FloorPlanLayer,
) -> Tuple[int, int]:
    """Step outward from a perimeter wall cell to EXTERIOR / outside the grid."""
    outward = _OUTWARD_DELTA[face.lower()]
    cx, cy = cell
    cx += outward[0]
    cy += outward[1]
    for _ in range(16):
        role = layer.role_at(cx, cy)
        if role in (CellRole.EXTERIOR, CellRole.COURTYARD):
            return (cx, cy)
        if role is None:
            return (cx, cy)
        if role == CellRole.DOOR:
            return (cx, cy)
        if role in _WALKABLE_INTERIOR_ROLES:
            return (cx, cy)
        if role in (CellRole.WALL_LINE, CellRole.VOID, CellRole.DOUBLE_VOID):
            cx += outward[0]
            cy += outward[1]
            continue
        return (cx, cy)
    return (cx, cy)


def _resolved_aperture_cells(
    face: str,
    cell: Tuple[int, int],
    layer: FloorPlanLayer,
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    return (
        _resolve_walkable_interior(face, cell, layer),
        _resolve_exterior_cell(face, cell, layer),
    )


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
    bbox: Tuple[int, int, int, int],
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    piece_ids: List[str],
    counters: Dict[str, int],
) -> None:
    yaw_by_face = {"west": 0, "east": 180, "south": 270, "north": 90}
    yaw = yaw_by_face[face]
    for cell in cells:

        piece_def = _wall_asset_for_cell(
            fp, cell, face, catalog, style, bbox, level
        )
        offset = _boundary_wall_offset_cm(face, yaw, piece_def)
        pid = _next_piece_id(counters, f"wall_{face}", cell, level)
        tags = piece_def.tags
        probe = _opening_probe_cell(cell, face)
        entrance_role = fp.entrance_by_cell.get(probe)
        aid = piece_def.asset_id
        if entrance_role and ("door" in aid or "gate" in aid):
            from pae.existence import entrance_role_tag

            tags = tags | frozenset({entrance_role_tag(entrance_role)})
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
            tags=tags,
        )
        placements.append(sp)
        piece_ids.append(pid)

        aid = piece_def.asset_id
        if "door" in aid or "gate" in aid:
            layer = _layer_from_grid(next(g for g in fp.storeys if g.level == level))
            interior, exterior = _resolved_aperture_cells(face, cell, layer)
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
        elif "window" in aid or aid == "wall_arrowslit":
            layer = _layer_from_grid(next(g for g in fp.storeys if g.level == level))
            interior, exterior = _resolved_aperture_cells(face, cell, layer)
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


def _partition_aperture_cells(
    face: str,
    cell: Tuple[int, int],
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Classroom cell (interior) and corridor neighbor (exterior) for a partition door."""
    cx, cy = cell
    dx, dy = _FACE_DELTA[face.lower()]
    return (cx, cy), (cx + dx, cy + dy)


def _place_interior_partitions(
    *,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    counters: Dict[str, int],
) -> None:
    """Place classroom↔corridor partition walls / doors from the plan carve."""
    for cx, cy, level, face, is_door in fp.interior_partitions:
        yaw = _YAW_FOR_VOID_FACE[face]
        piece_def = catalog.pick_wall(
            is_door=is_door, is_window=False, style=style
        )
        sx, sy, _ = piece_def.size_cm
        offset = rotation_offset_cm(
            yaw,
            sx,
            sy,
            rotates_about_center=piece_def.rotates_about_center,
        )
        pid = _next_piece_id(
            counters,
            f"wall_partition_{face}",
            (cx, cy),
            level,
        )
        tags = piece_def.tags | frozenset(
            {"interior", "partition", f"face_{face.lower()}"}
        )
        if is_door:
            tags = tags | frozenset({"door"})
        sp = SolidPlacement(
            piece_id=pid,
            asset_id=piece_def.asset_id,
            kind="wall",
            cell=(cx, cy),
            level=level,
            yaw=yaw,
            offset_cm=(offset[0], offset[1], 0.0),
            size_cm=piece_def.size_cm,
            rotates_about_center=piece_def.rotates_about_center,
            tags=tags,
        )
        placements.append(sp)

        if is_door:
            interior, exterior = _partition_aperture_cells(face, (cx, cy))
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


def _assembly_wide_well_available(fp: FloorPlan) -> bool:
    """True when massing/footprint can host a 2×2 monumental stair well."""
    if fp.massing is None:
        if not fp.storeys:
            return False
        grid = fp.storeys[0]
        w, h = grid.size
        return w >= 4 and h >= 4
    bodies = [v for v in fp.massing.volumes if v.role in WING_ROLES]
    if not bodies:
        bodies = list(fp.massing.enclosed_volumes())
    for v in bodies:
        if (v.x1 - v.x0) >= 3 and (v.y1 - v.y0) >= 3:
            return True
    return False


def _stair_occupied_cells(fp: FloorPlan) -> Set[Tuple[int, int, int]]:
    """(level, x, y) cells covered by a stair flight — skip floor slabs there."""
    occupied: Set[Tuple[int, int, int]] = set()
    run_cells = list(fp.stair_cells)
    if not run_cells:
        return occupied
    kind = "straight"
    if fp.massing is not None:
        kind = str(getattr(fp.massing, "stair_kind", "straight") or "straight").lower()
    if kind == "spiral" and len(run_cells) == 1:
        cell = run_cells[0]
        for level in range(len(fp.storeys) - 1):
            grid = fp.storeys[level]
            if grid.get(*cell) == CellRole.STAIR:
                occupied.add((level, cell[0], cell[1]))
        return occupied
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
    failures: List[Failure],
) -> None:
    """Emit stair pieces per climbed storey (straight / switchback / wide / spiral)."""
    run_cells = list(fp.stair_cells)
    if not run_cells:
        return
    kind = "straight"
    if fp.massing is not None:
        kind = str(getattr(fp.massing, "stair_kind", "straight") or "straight").lower()

    if kind == "spiral":
        if len(run_cells) != 1:
            failures.append(
                Failure(
                    check="stair_spiral_cells",
                    message=(
                        f"spiral stair requires exactly one stair cell, got {len(run_cells)}"
                    ),
                    world_xyz=cell_to_world_cm(run_cells[0][0], run_cells[0][1], 0),
                    critical=True,
                )
            )
            return
        spiral_def = catalog.get("stair_spiral_quarter")
        cell = run_cells[0]
        quarter_rise = spiral_def.size_cm[2]
        xy_offset = (0.0, 0.0)
        if fp.massing is not None:
            bodies = [v for v in fp.massing.volumes if v.role in WING_ROLES]
            for vol in fp.massing.volumes:
                if vol.role == "tower" and (vol.x0, vol.y0) == cell:
                    xy_offset = _tower_drum_xy_offset_cm(vol, bodies)
                    break
        for level in range(len(fp.storeys) - 1):
            grid = fp.storeys[level]
            if grid.get(*cell) != CellRole.STAIR:
                continue
            for qi, yaw in enumerate((0, 90, 180, 270)):
                pid = _next_piece_id(counters, f"stair_spiral_{yaw}", cell, level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=spiral_def.asset_id,
                        kind="stair",
                        cell=cell,
                        level=level,
                        yaw=yaw,
                        offset_cm=(xy_offset[0], xy_offset[1], qi * quarter_rise),
                        size_cm=spiral_def.size_cm,
                        rotates_about_center=True,
                        tags=spiral_def.tags,
                    )
                )
            # Central newel on the spiral axis (@VAL_SPIRAL_SHELL). Drum quarters
            # come from _place_tower_arcs; door bay ownership stays @VAL_TOWER_DOOR.
            from pae.spiral_shell import place_spiral_newels

            place_spiral_newels(
                placements=placements,
                counters=counters,
                cell=cell,
                levels=(level,),
                xy_offset=xy_offset,
                next_piece_id=_next_piece_id,
            )
        return

    if len(run_cells) < 2:
        return

    asset_id = "stair_straight"
    if kind == "switchback":
        asset_id = "stair_switchback"
    elif kind == "wide":
        asset_id = "stair_wide"

    # Switchback / wide need a 2×2 stairwell; expand from the run AABB min corner.
    place_cells = list(run_cells)
    if asset_id in ("stair_switchback", "stair_wide"):
        xs = [c[0] for c in run_cells]
        ys = [c[1] for c in run_cells]
        x0, y0 = min(xs), min(ys)
        place_cells = [(x0 + i, y0 + j) for i in range(2) for j in range(2)]

    if asset_id == "stair_straight":
        anchor, yaw = _stair_run_anchor_and_yaw(run_cells)
    else:
        anchor = (min(c[0] for c in place_cells), min(c[1] for c in place_cells))
        yaw = 0

    stair_def = catalog.get(asset_id)
    sx, sy, _ = stair_def.size_cm
    ox, oy = rotation_offset_cm(
        yaw,
        sx,
        sy,
        rotates_about_center=stair_def.rotates_about_center,
    )
    for level in range(len(fp.storeys) - 1):
        grid = fp.storeys[level]
        # Straight: every listed cell must be STAIR. Switchback/wide: require the
        # full 2×2 stairwell as STAIR before placing the kit mesh.
        check_cells = place_cells
        if not all(grid.get(*c) == CellRole.STAIR for c in check_cells):
            if asset_id in ("stair_switchback", "stair_wide") and len(fp.storeys) > 1:
                missing = [
                    c for c in check_cells if grid.get(*c) != CellRole.STAIR
                ]
                failures.append(
                    Failure(
                        check="stair_well_cells",
                        message=(
                            f"{asset_id} requires 2×2 STAIR on level {level}; "
                            f"missing or wrong role at {missing}"
                        ),
                        world_xyz=(
                            anchor[0] * MODULE_CM + MODULE_CM * 0.5,
                            anchor[1] * MODULE_CM + MODULE_CM * 0.5,
                            float(level * STOREY_CM),
                        ),
                        critical=True,
                    )
                )
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


def _punch_stair_exit_holes(
    *,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Open upper decks at stair exit bays (drum-offset / yawed runs)."""
    from pae.trim import covered_cells

    hole_piece = catalog.get("floor_hole")
    existing: Set[Tuple[int, Tuple[int, int]]] = set()
    for p in placements:
        if p.asset_id != "floor_hole":
            continue
        for cell in covered_cells(p):
            existing.add((p.level, cell))
    for stair in placements:
        if stair.kind != "stair":
            continue
        top_level = stair.level + 1
        if top_level >= len(fp.storeys):
            continue
        for cell in covered_cells(stair):
            key = (top_level, cell)
            if key in existing:
                continue
            existing.add(key)
            pid = _next_piece_id(counters, "floor_hole", cell, top_level)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=hole_piece.asset_id,
                    kind="floor",
                    cell=cell,
                    level=top_level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                    size_cm=hole_piece.size_cm,
                    tags=hole_piece.tags,
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


def _tower_abuts_body(tower: Volume, body: Volume) -> bool:
    """True when *tower* sits on a wall run or corner of *body* (solver parity)."""
    body_cells = body.cells()
    t_cells = tower.cells()
    if t_cells & body_cells:
        return True
    for tx, ty in t_cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if (tx + dx, ty + dy) in body_cells:
                    return True
    return False


def _tower_attached_body(tower: Volume, bodies: List[Volume]) -> Optional[Volume]:
    mains = [v for v in bodies if v.role in WING_ROLES]
    for body in mains:
        if _tower_abuts_body(tower, body):
            return body
    return None


def _shared_edge_mid_cm(
    tower: Volume,
    body: Volume,
    *,
    axis: str,
) -> float:
    """Midpoint (cm) along the shared cell span on *axis* ('x' or 'y')."""
    if axis == "y":
        y0 = max(tower.y0, body.y0)
        y1 = min(tower.y1, body.y1)
        if y0 > y1:
            return (tower.y0 + tower.y1 + 1) * 0.5 * MODULE_CM
        return (y0 * MODULE_CM + (y1 + 1) * MODULE_CM) * 0.5
    x0 = max(tower.x0, body.x0)
    x1 = min(tower.x1, body.x1)
    if x0 > x1:
        return (tower.x0 + tower.x1 + 1) * 0.5 * MODULE_CM
    return (x0 * MODULE_CM + (x1 + 1) * MODULE_CM) * 0.5


def _tower_drum_xy_offset_cm(
    tower: Volume,
    bodies: List[Volume],
) -> Tuple[float, float]:
    """Drum-centre XY offset from the attach-cell min corner (§2.2 centred).

    Annulus outer radius = one MODULE (diameter 2×MODULE).  Default placement
    puts the rotation centre on the cell min-corner, which swings half the drum
    through the hall footprint.  Offset outward along the abutment normal so the
    drum clears the hall envelope or only kisses the exterior wall.
    """
    cell_corner_x = tower.x0 * MODULE_CM
    cell_corner_y = tower.y0 * MODULE_CM
    body = _tower_attached_body(tower, bodies)
    if body is None:
        return (0.0, 0.0)

    r = MODULE_CM
    west = tower.x1 < body.x0
    east = tower.x0 > body.x1
    south = tower.y1 < body.y0
    north = tower.y0 > body.y1

    # Push one MODULE outward from the default centred pose so the drum AABB
    # kisses the hall exterior (2×r left a full-module air gap → freestanding).
    cx = cell_corner_x + r
    cy = cell_corner_y + r
    if west:
        cx = body.x0 * MODULE_CM - r
    elif east:
        cx = (body.x1 + 1) * MODULE_CM + r
    if south:
        cy = body.y0 * MODULE_CM - r
    elif north:
        cy = (body.y1 + 1) * MODULE_CM + r

    # Wall attach (single-axis abut): centre on the shared edge midline.
    if (west or east) and not (south or north):
        cy = _shared_edge_mid_cm(tower, body, axis="y")
    elif (south or north) and not (west or east):
        cx = _shared_edge_mid_cm(tower, body, axis="x")

    return (cx - cell_corner_x, cy - cell_corner_y)


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
    pitch: float,
    catalog: _PieceCatalog,
    tower_cells: Set[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    floor_plan: Optional[FloorPlan] = None,
) -> None:
    """Place slope decks plus gable-end infill prisms (§6 pitched roof).

    Ridge along X (``modules_x >= modules_y``): gable infill only at the two
    ridge ends (``x=rx0`` and ``x=rx1``), spanning full Y; slope wedges run
    every Y row across full X.  Mirror when the ridge runs along Y.

    L/U/courtyard plans get one pitched span per wing (S-019) plus valley stubs
    on abutments — same wing split as hip/flat.

    Tower cells are excluded from the roof footprint — tower uses crown/cap.
    """
    gable_piece = catalog.get("roof_gable_infill")
    slope_piece = catalog.get("roof_pitched_slope")
    roof_z = STOREY_CM
    wing_spans = (
        _massing_wing_roof_spans(floor_plan, grid) if floor_plan is not None else None
    )
    roof_spans = wing_spans if wing_spans else [(x0, y0, x1, y1)]
    for rx0, ry0, rx1, ry1 in roof_spans:
        west, east, south, north = roof_eave_overhang_per_side(
            rx0, ry0, rx1, ry1, roof_spans
        )
        eave_ox, eave_oy, _ = roof_eave_offset_cm(
            overhang_west=west, overhang_south=south
        )
        cells = [
            (x, y)
            for x in range(rx0, rx1 + 1)
            for y in range(ry0, ry1 + 1)
            if (x, y) not in tower_cells
        ]
        if not cells:
            continue
        sx0 = min(c[0] for c in cells)
        sy0 = min(c[1] for c in cells)
        sx1 = max(c[0] for c in cells)
        sy1 = max(c[1] for c in cells)
        modules_x = sx1 - sx0 + 1
        modules_y = sy1 - sy0 + 1
        ridge_along_x = modules_x >= modules_y
        span_x = modules_x * MODULE_CM
        span_y = modules_y * MODULE_CM
        deck_x = span_x + west + east
        deck_y = span_y + south + north
        if ridge_along_x:
            span_modules = modules_y
            full_rise = roof_rise_cm(pitch, span_modules * MODULE_CM)
            gable_height = full_rise + FLOOR_T_CM
            for x in (sx0, sx1):
                placements.append(
                    SolidPlacement(
                        piece_id=_next_piece_id(counters, "roof_gable", (x, sy0), level),
                        asset_id=gable_piece.asset_id,
                        kind="roof",
                        cell=(x, sy0),
                        level=level,
                        yaw=0,
                        offset_cm=(
                            *roof_gable_end_offset_cm(
                                ridge_along_x=True, is_low_end=(x == sx0)
                            )[:2],
                            roof_z,
                        ),
                        size_cm=roof_gable_end_size_cm(
                            ridge_along_x=True,
                            span_x_cm=span_x,
                            span_y_cm=span_y,
                            gable_height=gable_height,
                        ),
                        rotates_about_center=gable_piece.rotates_about_center,
                        tags=gable_piece.tags,
                    )
                )
            placements.append(
                SolidPlacement(
                    piece_id=_next_piece_id(counters, "roof_slope", (sx0, sy0), level),
                    asset_id=slope_piece.asset_id,
                    kind="roof",
                    cell=(sx0, sy0),
                    level=level,
                    yaw=0,
                    offset_cm=(eave_ox, eave_oy, roof_z),
                    size_cm=(deck_x, deck_y, gable_height),
                    rotates_about_center=slope_piece.rotates_about_center,
                    tags=slope_piece.tags,
                )
            )
        else:
            span_modules = modules_x
            full_rise = roof_rise_cm(pitch, span_modules * MODULE_CM)
            gable_height = full_rise + FLOOR_T_CM
            for y in (sy0, sy1):
                placements.append(
                    SolidPlacement(
                        piece_id=_next_piece_id(counters, "roof_gable", (sx0, y), level),
                        asset_id=gable_piece.asset_id,
                        kind="roof",
                        cell=(sx0, y),
                        level=level,
                        yaw=0,
                        offset_cm=(
                            *roof_gable_end_offset_cm(
                                ridge_along_x=False, is_low_end=(y == sy0)
                            )[:2],
                            roof_z,
                        ),
                        size_cm=roof_gable_end_size_cm(
                            ridge_along_x=False,
                            span_x_cm=span_x,
                            span_y_cm=span_y,
                            gable_height=gable_height,
                        ),
                        rotates_about_center=gable_piece.rotates_about_center,
                        tags=gable_piece.tags,
                    )
                )
            placements.append(
                SolidPlacement(
                    piece_id=_next_piece_id(counters, "roof_slope", (sx0, sy0), level),
                    asset_id=slope_piece.asset_id,
                    kind="roof",
                    cell=(sx0, sy0),
                    level=level,
                    yaw=0,
                    offset_cm=(eave_ox, eave_oy, roof_z),
                    size_cm=(deck_x, deck_y, gable_height),
                    rotates_about_center=slope_piece.rotates_about_center,
                    tags=slope_piece.tags,
                )
            )
    _place_valley_stubs(
        level=level,
        pitch=pitch,
        catalog=catalog,
        roof_spans=roof_spans,
        placements=placements,
        counters=counters,
    )


def _place_valley_stubs(
    *,
    level: int,
    pitch: float,
    catalog: _PieceCatalog,
    roof_spans: Sequence[Tuple[int, int, int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Place V-trough valley strips on L/U wing abutments (S-019 stub).

    Does not resolve a single watertight multi-wing surface (S-021) — only
    marks the shared eave seams so adjacent hips/slopes no longer collide bare.
    """
    if len(roof_spans) < 2:
        return
    valley_piece = catalog.get("roof_valley")
    roof_z = STOREY_CM
    for seam in roof_valley_seams(roof_spans):
        run_modules = seam.run1 - seam.run0 + 1
        size = roof_valley_span_size_cm(
            run_modules, pitch=pitch, axis=seam.axis
        )
        if seam.axis == "x":
            cell = (seam.run0, seam.cross_hi)
            # Centre the trough on the world seam at cross_hi * MODULE.
            offset = (0.0, -VALLEY_WIDTH_CM * 0.5, roof_z)
        else:
            cell = (seam.cross_hi, seam.run0)
            offset = (-VALLEY_WIDTH_CM * 0.5, 0.0, roof_z)
        pid = _next_piece_id(counters, "roof_valley", cell, level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=valley_piece.asset_id,
                kind="roof",
                cell=cell,
                level=level,
                yaw=0,
                offset_cm=offset,
                size_cm=size,
                tags=valley_piece.tags,
            )
        )


def _place_hip_roof(
    *,
    grid: StoreyGrid,
    level: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    pitch: float,
    catalog: _PieceCatalog,
    floor_plan: FloorPlan,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Place four-slope hip roofs per wing span (§6 / S-012).

    L/U/courtyard plans get one hip per enclosed wing volume plus S-019 valley
    stubs on abutments; interior wing seams suppress eave overhang like flat roofs.
    """
    roof_piece = catalog.get("roof_hip")
    roof_z = STOREY_CM
    wing_spans = _massing_wing_roof_spans(floor_plan, grid)
    roof_spans = wing_spans if wing_spans else [(x0, y0, x1, y1)]
    for rx0, ry0, rx1, ry1 in roof_spans:
        modules_x = rx1 - rx0 + 1
        modules_y = ry1 - ry0 + 1
        west, east, south, north = roof_eave_overhang_per_side(
            rx0, ry0, rx1, ry1, roof_spans
        )
        eave_ox, eave_oy, _ = roof_eave_offset_cm(
            overhang_west=west, overhang_south=south
        )
        pid = _next_piece_id(counters, "roof_hip", (rx0, ry0), level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=roof_piece.asset_id,
                kind="roof",
                cell=(rx0, ry0),
                level=level,
                yaw=0,
                offset_cm=(eave_ox, eave_oy, roof_z),
                size_cm=roof_hip_span_size_cm(
                    modules_x,
                    modules_y,
                    pitch=pitch,
                    overhang_west=west,
                    overhang_east=east,
                    overhang_south=south,
                    overhang_north=north,
                ),
                tags=roof_piece.tags,
            )
        )
    _place_valley_stubs(
        level=level,
        pitch=pitch,
        catalog=catalog,
        roof_spans=roof_spans,
        placements=placements,
        counters=counters,
    )


def _tower_attach_skip_yaw(
    tower: Volume,
    bodies: List[Volume],
) -> Optional[int]:
    """Wall yaw facing the attached hall — no window punched into the joint."""
    body = _tower_attached_body(tower, bodies)
    if body is None:
        return None
    west = tower.x1 < body.x0
    east = tower.x0 > body.x1
    south = tower.y1 < body.y0
    north = tower.y0 > body.y1
    if west:
        return 180  # east face toward hall
    if east:
        return 0
    if south:
        return 90
    if north:
        return 270
    return None


def _tower_has_spiral_stair(fp: FloorPlan, cell: Tuple[int, int]) -> bool:
    if fp.massing is None:
        return False
    kind = str(getattr(fp.massing, "stair_kind", "") or "").lower()
    if kind != "spiral":
        return False
    return cell in set(fp.stair_cells)


def _tower_window_slots(
    *,
    level: int,
    helical: bool,
    skip_yaw: Optional[int],
) -> List[Tuple[int, int]]:
    """(quarter_index, yaw) slots for drum windows on one storey.

    Helical (spiral stair): one aperture per quarter turn, matching stair yaw
    order 0/90/180/270 so each window sits at that tread height.
    Perimeter (no spiral): one window per storey, yaw rotating with level.
    """
    if helical:
        slots = list(enumerate(_TOWER_QUARTER_YAWS))
    else:
        yaw = _TOWER_QUARTER_YAWS[level % 4]
        slots = [(level % 4, yaw)]
    if skip_yaw is None:
        return slots
    return [(qi, yaw) for qi, yaw in slots if yaw != skip_yaw]


def _tower_window_shell_pose(
    drum_xy: Tuple[float, float],
    yaw: int,
    *,
    z_off: float,
    height_cm: float,
    chord_cm: float,
    skip_yaw: Optional[int],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Size + offset for a drum-rim window overlay.

    Pushes the piece to the outer shell (half-extent ``MODULE/2``) along the face
    normal. Thin/long axes are baked into ``size_cm`` because centred AABBs do
    not follow yaw. When the face is perpendicular to the attach axis, the chord
    is biased toward the free hemisphere so it clears the hall kiss wall.
    """
    thick = WALL_T_CM
    half = MODULE_CM * 0.5
    radial = half - thick * 0.5
    dx, dy = drum_xy
    # Tangential bias: flush the chord to the exterior side of the drum.
    shift = max(0.0, half - chord_cm * 0.5)
    bias_x = 0.0
    bias_y = 0.0
    if skip_yaw in (0, 180) and yaw in (90, 270):
        bias_x = shift if skip_yaw == 0 else -shift
    elif skip_yaw in (90, 270) and yaw in (0, 180):
        bias_y = shift if skip_yaw == 270 else -shift

    if yaw == 0:  # west face — thin in X
        size = (thick, chord_cm, height_cm)
        ox, oy = dx - radial + bias_x, dy + bias_y
    elif yaw == 180:  # east face
        size = (thick, chord_cm, height_cm)
        ox, oy = dx + radial + bias_x, dy + bias_y
    elif yaw == 90:  # north face — thin in Y
        size = (chord_cm, thick, height_cm)
        ox, oy = dx + bias_x, dy + radial + bias_y
    else:  # 270 south face
        size = (chord_cm, thick, height_cm)
        ox, oy = dx + bias_x, dy - radial + bias_y
    return size, (ox, oy, z_off)


def _tower_exterior_cell(cell: Tuple[int, int], yaw: int) -> Tuple[int, int]:
    """Neighbour cell on the exterior side of a tower window (by wall yaw)."""
    cx, cy = cell
    if yaw == 0:
        return (cx - 1, cy)
    if yaw == 90:
        return (cx, cy + 1)
    if yaw == 180:
        return (cx + 1, cy)
    return (cx, cy - 1)


def _place_tower_windows(
    *,
    vol: Volume,
    cell: Tuple[int, int],
    drum_xy: Tuple[float, float],
    skip_yaw: Optional[int],
    helical: bool,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    counters: Dict[str, int],
) -> None:
    """Helical / perimeter drum windows (Phase 0.6 / 4.7).

    Windowed arc quarters carry the opening contract; matching wall pieces
    (kind=wall) satisfy ``storey_egress`` VOLUME and stay attached via same-cell
    AABB touch with the drum rim (not a full-bay slab through the drum centre).
    """
    win_arc = catalog.get("tower_arc_quarter_window")
    solid_arc = catalog.get("tower_arc_quarter")
    wall_win = catalog.get(_style_window_asset(style))
    if not (
        "window" in wall_win.asset_id
        or "arrowslit" in wall_win.asset_id
        or "arcade" in wall_win.asset_id
    ):
        wall_win = catalog.get("wall_window")
    quarter_rise = catalog.get("stair_spiral_quarter").size_cm[2]

    for level in range(vol.storeys):
        window_yaws = {
            yaw
            for _, yaw in _tower_window_slots(
                level=level, helical=helical, skip_yaw=skip_yaw
            )
        }
        for yaw in _TOWER_QUARTER_YAWS:
            use_window = yaw in window_yaws
            piece = win_arc if use_window else solid_arc
            pid = _next_piece_id(
                counters,
                f"tower_arc_{'win_' if use_window else ''}{yaw}",
                cell,
                level,
            )
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=piece.asset_id,
                    kind="tower_arc",
                    cell=cell,
                    level=level,
                    yaw=yaw,
                    offset_cm=(drum_xy[0], drum_xy[1], 0.0),
                    size_cm=piece.size_cm,
                    rotates_about_center=True,
                    tags=piece.tags,
                )
            )

        for qi, yaw in _tower_window_slots(
            level=level, helical=helical, skip_yaw=skip_yaw
        ):
            if helical:
                z_off = float(qi * quarter_rise)
                height = min(quarter_rise * 0.9, STOREY_CM * 0.4)
                chord = min(_TOWER_WIN_CHORD_CM, wall_win.size_cm[1] * 0.55)
            else:
                # z=0 keeps wall_window aperture sill (~98 cm) inside [80, 120].
                z_off = 0.0
                height = _TOWER_WIN_HEIGHT_CM
                chord = _TOWER_WIN_CHORD_CM
            size, offset = _tower_window_shell_pose(
                drum_xy,
                yaw,
                z_off=z_off,
                height_cm=height,
                chord_cm=chord,
                skip_yaw=skip_yaw,
            )
            wpid = _next_piece_id(counters, f"tower_win_{yaw}", cell, level)
            tags = wall_win.tags | frozenset({"tower", "drum_window"})
            sp = SolidPlacement(
                piece_id=wpid,
                asset_id=wall_win.asset_id,
                kind="wall",
                cell=cell,
                level=level,
                yaw=yaw,
                offset_cm=offset,
                size_cm=size,
                # Centred AABB on the rim so freestanding joins the drum.
                rotates_about_center=True,
                tags=tags,
            )
            placements.append(sp)
            floor_z = level * STOREY_CM
            world = _aperture_world(sp, "window")
            apertures.append(
                Aperture(
                    piece_id=f"win_{wpid}",
                    kind="window",
                    wall_piece_id=wpid,
                    level=level,
                    sill_z_cm=world[2],
                    floor_z_cm=floor_z,
                    interior_cell=cell,
                    exterior_cell=_tower_exterior_cell(cell, yaw),
                    world_xyz=world,
                )
            )


def _place_tower_arcs(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    counters: Dict[str, int],
) -> None:
    """Place tower drum (arcs + helical windows) and roof junction stack.

    Drum: 4× arc quarters at the *same* cell (§2.2 centred). Selected quarters
    swap to ``tower_arc_quarter_window`` along the spiral (or one per storey).
    Roof: ``tower_junction`` → crown → cap (defined joint, not a floating cone).
    """
    if floor_plan.massing is None:
        return
    junction = catalog.get("tower_junction")
    crown = catalog.get("tower_crown")
    cap = catalog.get("tower_cap")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    for vol in floor_plan.massing.volumes:
        if vol.role != "tower":
            continue
        cell = (vol.x0, vol.y0)
        drum_xy = _tower_drum_xy_offset_cm(vol, bodies)
        skip_yaw = _tower_attach_skip_yaw(vol, bodies)
        helical = _tower_has_spiral_stair(floor_plan, cell)
        _place_tower_windows(
            vol=vol,
            cell=cell,
            drum_xy=drum_xy,
            skip_yaw=skip_yaw,
            helical=helical,
            catalog=catalog,
            style=style,
            placements=placements,
            apertures=apertures,
            counters=counters,
        )
        # @VAL_TOWER_DOOR — hall↔drum doorway on attach face (owned module).
        from pae.tower_entry import place_tower_entry_doors

        door_piece = catalog.get(_style_door_asset(style))
        if "door" not in door_piece.asset_id and "gate" not in door_piece.asset_id:
            door_piece = catalog.get("wall_door")
        place_tower_entry_doors(
            vol=vol,
            cell=cell,
            drum_xy=drum_xy,
            skip_yaw=skip_yaw,
            body=_tower_attached_body(vol, bodies),
            door_asset_id=door_piece.asset_id,
            door_tags=door_piece.tags,
            aperture_world=_aperture_world,
            next_piece_id=_next_piece_id,
            placements=placements,
            apertures=apertures,
            counters=counters,
        )
        top = vol.storeys - 1
        junction_z = STOREY_CM
        crown_z = junction_z + junction.size_cm[2] + _TOWER_STACK_GAP_CM
        cap_z = crown_z + crown.size_cm[2] + _TOWER_STACK_GAP_CM
        for piece, kind, z_off in (
            (junction, "tower_crown", junction_z),
            (crown, "tower_crown", crown_z),
            (cap, "tower_cap", cap_z),
        ):
            pid = _next_piece_id(counters, piece.asset_id, cell, top)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=piece.asset_id,
                    kind=kind,
                    cell=cell,
                    level=top,
                    yaw=0,
                    offset_cm=(drum_xy[0], drum_xy[1], z_off),
                    size_cm=piece.size_cm,
                    rotates_about_center=True,
                    tags=piece.tags,
                )
            )
        # Phase 4.7 (@VAL_TOWER_RAMPART) — walkable deck + rampart tags + crenels.
        from pae.tower_rampart import place_tower_rampart_crown

        floor_piece = catalog.get("floor")
        wall_win = catalog.get(_style_window_asset(style))
        if not (
            "window" in wall_win.asset_id
            or "arrowslit" in wall_win.asset_id
            or "arcade" in wall_win.asset_id
        ):
            wall_win = catalog.get("wall_window")

        def _rampart_pid(prefix: str, c: Tuple[int, int], lvl: int) -> str:
            return _next_piece_id(counters, prefix, c, lvl)

        place_tower_rampart_crown(
            cell=cell,
            level=top,
            drum_xy=drum_xy,
            junction_z=junction_z,
            crown_z=crown_z,
            skip_yaw=skip_yaw,
            floor_piece=floor_piece,
            wall_window_asset_id=wall_win.asset_id,
            wall_window_tags=wall_win.tags,
            next_piece_id=_rampart_pid,
            placements=placements,
            apertures=apertures,
        )


def _ensure_spiral_drum_enclosure(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Fill any missing ``tower_arc`` quarters around spiral climbs (@VAL_SPIRAL_SHELL).

    Idempotent on top of ``_place_tower_arcs``. Designed door bays (tagged
    ``tower_entry`` / ``tower_door`` / ``spiral_door_bay``) are left open for
    @VAL_TOWER_DOOR.
    """
    if floor_plan.massing is None:
        return
    kind = str(getattr(floor_plan.massing, "stair_kind", "") or "").lower()
    if kind != "spiral":
        return
    from pae.spiral_shell import DESIGNED_DOOR_BAY_TAGS, ensure_spiral_drum_quarters

    solid = catalog.get("tower_arc_quarter")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    for cell in floor_plan.stair_cells:
        levels = {
            p.level
            for p in placements
            if p.asset_id == "stair_spiral_quarter" and p.cell == cell
        }
        if not levels:
            continue
        xy_offset = (0.0, 0.0)
        for vol in floor_plan.massing.volumes:
            if vol.role == "tower" and (vol.x0, vol.y0) == cell:
                xy_offset = _tower_drum_xy_offset_cm(vol, bodies)
                break
        door_exempt = {
            int(p.yaw) % 360
            for p in placements
            if p.cell == cell and (DESIGNED_DOOR_BAY_TAGS & set(p.tags))
        }
        ensure_spiral_drum_quarters(
            placements=placements,
            counters=counters,
            cell=cell,
            levels=levels,
            xy_offset=xy_offset,
            solid_arc_size_cm=solid.size_cm,
            solid_arc_tags=solid.tags,
            next_piece_id=_next_piece_id,
            door_exempt_yaws=door_exempt,
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
    tower_cells = _tower_cells(floor_plan)

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
                bbox=(x0, y0, x1, y1),
                placements=placements,
                apertures=apertures,
                piece_ids=run_piece_ids[face],
                counters=counters,
            )
            run_piece_ids[face] = [p.piece_id for p in placements[before:]]

        _place_inhabited_inner_walls(
            grid=grid,
            bbox=(x0, y0, x1, y1),
            level=level,
            catalog=catalog,
            placements=placements,
            counters=counters,
        )

        floor_piece = catalog.get("floor")
        floor_z_off = -FLOOR_T_CM
        if level == 0:
            for (cx, cy), role in grid.cells.items():
                if (level, cx, cy) in stair_occupied:
                    continue
                if (cx, cy) in tower_cells:
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
            # VOID bays also get floor_hole rims; the Blender mesh punches those
            # openings out of the deck so the stair top is not a solid ceiling.
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
                    # Exact module span — no roof eaves (those belong on roof_flat only).
                    size_cm=(
                        modules_x * MODULE_CM,
                        modules_y * MODULE_CM,
                        FLOOR_T_CM,
                    ),
                    tags=floor_piece.tags,
                )
            )
            for (cx, cy), role in grid.cells.items():
                # Punch stairwell openings: plan VOIDs, and any stair-run cell on
                # upper decks (multi-storey wells keep STAIR on intermediate floors).
                needs_hole = role in (CellRole.VOID, CellRole.DOUBLE_VOID) or (
                    level > 0 and (cx, cy) in floor_plan.stair_cells
                )
                if not needs_hole:
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
                wing_spans = _massing_wing_roof_spans(floor_plan, grid)
                roof_spans = wing_spans if wing_spans else [(x0, y0, x1, y1)]
                for rx0, ry0, rx1, ry1 in roof_spans:
                    modules_x = rx1 - rx0 + 1
                    modules_y = ry1 - ry0 + 1
                    west, east, south, north = roof_eave_overhang_per_side(
                        rx0, ry0, rx1, ry1, roof_spans
                    )
                    eave_ox, eave_oy, _ = roof_eave_offset_cm(
                        overhang_west=west, overhang_south=south
                    )
                    pid = _next_piece_id(counters, "roof", (rx0, ry0), level)
                    placements.append(
                        SolidPlacement(
                            piece_id=pid,
                            asset_id=roof_piece.asset_id,
                            kind="roof",
                            cell=(rx0, ry0),
                            level=level,
                            yaw=0,
                            offset_cm=(eave_ox, eave_oy, roof_z),
                            size_cm=roof_flat_span_size_cm(
                                modules_x,
                                modules_y,
                                overhang_west=west,
                                overhang_east=east,
                                overhang_south=south,
                                overhang_north=north,
                            ),
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
                    pitch=floor_plan.roof_pitch,
                    catalog=catalog,
                    tower_cells=_tower_cells(floor_plan),
                    placements=placements,
                    counters=counters,
                    floor_plan=floor_plan,
                )
            elif floor_plan.roof_kind == "hip":
                _place_hip_roof(
                    grid=grid,
                    level=level,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    pitch=floor_plan.roof_pitch,
                    catalog=catalog,
                    floor_plan=floor_plan,
                    placements=placements,
                    counters=counters,
                )

    _place_interior_partitions(
        fp=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        apertures=apertures,
        counters=counters,
    )

    _place_stairs(
        fp=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
        failures=failures,
    )

    _punch_stair_exit_holes(
        fp=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    # Round towers: drum arcs + helical/perimeter windows + junction roof stack.
    _place_tower_arcs(
        floor_plan=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        apertures=apertures,
        counters=counters,
    )

    # Spiral shell: guarantee continuous tower_arc drum around helical climbs.
    # Door bay gaps are exempted by tag (@VAL_TOWER_DOOR); ramparts @VAL_TOWER_RAMPART.
    _ensure_spiral_drum_enclosure(
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
            for gx0, gy0, gx1, gy1 in _ground_spans(floor_plan, grid):
                modules_x = gx1 - gx0 + 1
                modules_y = gy1 - gy0 + 1
                pid = _next_piece_id(counters, "ground", (gx0, gy0), 0)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=plinth.asset_id,
                        kind="ground",
                        cell=(gx0, gy0),
                        level=0,
                        yaw=0,
                        offset_cm=(0.0, 0.0, ground_z),
                        size_cm=ground_plinth_span_size_cm(modules_x, modules_y),
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
            face = _perimeter_wall_face(p.piece_id)
            if face is not None:
                ids_by_face[face].append(p.piece_id)
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
        room_specs=[
            {
                "name": r.name,
                "kind": r.kind,
                "area_bays": r.area_bays,
                "double_height": r.double_height,
            }
            for r in floor_plan.rooms
        ],
        building_class=(
            str(getattr(floor_plan.massing, "building_class", "generic") or "generic")
            if floor_plan.massing is not None
            else "generic"
        ),
        stair_kind=(
            str(getattr(floor_plan.massing, "stair_kind", "straight") or "straight")
            if floor_plan.massing is not None
            else "straight"
        ),
        wide_stair_well_available=_assembly_wide_well_available(floor_plan),
    )
    if floor_plan.massing is not None and floor_plan.massing.entrances:
        entrances = floor_plan.massing.entrances
        if any(e.ensemble for e in entrances):
            assembly, ensemble_failures = expand_entrance_ensembles(
                assembly,
                entrances,
                storeys=storeys,
            )
            failures.extend(ensemble_failures)
            failures.extend(
                check_entrance_ensemble_existence(entrances, assembly)
            )
        failures.extend(check_entrance_existence(entrances, assembly))
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

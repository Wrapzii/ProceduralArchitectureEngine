"""Assembly stage (§6) — WP-5. Placement math only; geometry lives in primitives."""

from __future__ import annotations

import math
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
    TOL_CM,
    WALL_T_CM,
    cell_to_world_cm,
    drum_window_chord_cm,
    drum_window_height_cm,
    gate_span_min_storeys,
    ground_plinth_z_cm,
    height_cm_from_storeys,
    placement_world_aabb,
    rotation_offset_cm,
    storey_datum_z_cm,
)

# Stair kinds that use ``_monumental_flight_pads`` when the well is large enough.
_MONUMENTAL_PAD_KINDS = frozenset({"switchback", "wide", "straight"})

# Tag on walls that span more than one storey (gates / grand arches).
WALL_HEIGHT_SPAN_TAG = "wall_height_span"
from pae.solver import Volume

# Soft separation between stacked tower roof pieces (visual only; junction owns the joint).
_TOWER_STACK_GAP_CM = 0.5
_TOWER_QUARTER_YAWS = (0, 90, 180, 270)
# Drum-rim window overlays (Phase 0.6). ``placement_world_aabb`` with
# ``rotates_about_center=True`` does **not** rotate the XY box — thin/long axes
# must be baked per yaw. The primitive's physical outer radius is ``MODULE``.
# Push to the rim and bias away from the attach kiss so overlays do not slice the
# hall wall (interpenetration / headroom / roof_penetration). Rim thickness = WALL_T_CM.
_TOWER_WIN_CHORD_CM = drum_window_chord_cm()


def _spiral_quarter_yaws(skip_yaw: Optional[int]) -> Tuple[int, ...]:
    """Window/shell yaws with the attached doorway face omitted."""
    if skip_yaw is None:
        return _TOWER_QUARTER_YAWS
    sy = int(skip_yaw) % 360
    return tuple(y for y in _TOWER_QUARTER_YAWS if y != sy)


def _spiral_yaws_from_landing(landing_yaw: Optional[int]) -> Tuple[int, ...]:
    """Four-quarter helix ordered from the doorway/landing direction."""
    if landing_yaw is None:
        return _TOWER_QUARTER_YAWS
    start = int(landing_yaw) % 360
    if start not in _TOWER_QUARTER_YAWS:
        start = min(_TOWER_QUARTER_YAWS, key=lambda y: abs(y - start))
    index = _TOWER_QUARTER_YAWS.index(start)
    return _TOWER_QUARTER_YAWS[index:] + _TOWER_QUARTER_YAWS[:index]


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
    roof_height_field_bands,
    roof_hip_span_size_cm,
    roof_rise_cm,
    structure_ridge_span_modules,
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
from pae.style_pack import (
    resolve_door_piece_id,
    resolve_storey_height_cm,
    resolve_window_piece_id,
)
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
        level: Optional[int] = None,
        level_window_override: Optional[str] = None,
    ) -> _ResolvedPiece:
        if is_door:
            asset_id = _door_asset_for_role(entrance_role, style)
            return self.get(asset_id)
        if is_window:
            return self.get(
                _style_window_asset(
                    style,
                    level=level,
                    level_window_override=level_window_override,
                )
            )
        return self.get("wall_plain")


def _level_window_override(fp: "FloorPlan", level: int) -> Optional[str]:
    tags = getattr(fp, "level_window_tags", None)
    if not tags or level < 0 or level >= len(tags):
        return None
    raw = tags[level]
    return None if raw is None or not str(raw).strip() else str(raw)


def _style_window_asset(
    style: StyleLike,
    *,
    level: Optional[int] = None,
    level_window_override: Optional[str] = None,
) -> str:
    """Map style window tags onto existing aperture wall piece ids."""
    return resolve_window_piece_id(style, level_override=level_window_override)


def _style_door_asset(style: StyleLike) -> str:
    return resolve_door_piece_id(style)


def _door_asset_for_role(role: Optional[str], style: StyleLike) -> str:
    """Map entrance role → wall kit piece (§1.1)."""
    return resolve_door_piece_id(style, entrance_role=role)


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
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ARCADE,
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
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ARCADE,
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
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ARCADE,
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

    Stage A: when a structure declares ``foundation_cells``, emit one span set
    over that foundation mask (once per structure — not per wing volume).

    Otherwise: main/wing massing volumes only — tower attach cells can be DOOR
    roles that widen ``_footprint_bbox`` without a walkable slab. Courtyard /
    multi-wing uses the same per-wing splits as roofs.
    """
    foundation = tuple(getattr(floor_plan, "foundation_cells", ()) or ())
    if not foundation and floor_plan.massing is not None:
        foundation = tuple(getattr(floor_plan.massing, "foundation_cells", ()) or ())
    if foundation:
        from pae.sketch import rect_cover

        return list(rect_cover(set(foundation)))
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
    tower_cells: Optional[Set[Tuple[int, int]]] = None,
    floor_plan: Optional[FloorPlan] = None,
    style: StyleLike = None,
) -> None:
    """Inhabited wall ranges on re-entrant / courtyard boundaries (§11 M4).

    Tower drum cells are skipped — the round ``tower_arc`` shell is the enclosure;
    a rectangular inner wall through the drum is junk (user: crap inside keeps).
    """
    owned = tower_cells or set()
    storey_cm = _style_storey_cm(style)
    datum_dz = (
        _level_datum_delta_cm(floor_plan, level, style)
        if floor_plan is not None
        else 0.0
    )
    level_hu = _level_height_units(floor_plan, level) if floor_plan is not None else 1.0
    for (cx, cy), role in grid.cells.items():
        if role != CellRole.WALL_LINE:
            continue
        if (cx, cy) in owned:
            continue
        for face in _inner_wall_faces(grid, cx, cy, bbox):
            yaw = _YAW_FOR_VOID_FACE[face]
            piece_def = catalog.get("wall_plain")
            sx, sy, _ = piece_def.size_cm
            ox, oy = rotation_offset_cm(
                yaw,
                sx,
                sy,
                rotates_about_center=piece_def.rotates_about_center,
            )
            size_cm = _wall_size_for_height_storeys(
                piece_def, level_hu, storey_cm=storey_cm
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
                    offset_cm=(ox, oy, datum_dz),
                    size_cm=size_cm,
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


def _envelope_bbox(
    floor_plan: FloorPlan, grid: StoreyGrid
) -> Tuple[int, int, int, int]:
    """Primary building envelope, excluding outboard tower plan anchors."""
    if floor_plan.massing is not None:
        bodies = [
            v
            for v in floor_plan.massing.volumes
            if v.role in WING_ROLES
        ]
        if bodies:
            return (
                min(v.x0 for v in bodies),
                min(v.y0 for v in bodies),
                max(v.x1 for v in bodies),
                max(v.y1 for v in bodies),
            )
    return _footprint_bbox(grid)


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
    # Facades use one seeded ground rhythm and repeat it vertically.  Re-picking
    # the first N upper cells independently produced fully glazed lower strips
    # with blank walls above.  Explicit room/void roles may still remove a bay.
    aligned = {
        cell
        for cell in fp.window_cells
        if grid.get(cell[0], cell[1])
        in (CellRole.WALL_LINE, CellRole.DOOR, CellRole.DOUBLE_VOID)
    }
    if aligned:
        return aligned
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


def _gate_passage_footprint_columns(fp: FloorPlan) -> Set[int]:
    """Footprint X columns of south (or any) gate leaves — through-passage corridor."""
    return {
        cell[0]
        for cell, role in fp.entrance_by_cell.items()
        if role == "gate"
    }


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
        level=level,
        level_window_override=_level_window_override(fp, level),
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
    world_z = storey_datum_z_cm(piece.level) + wz + mid_local[2]
    return (world_x, world_y, world_z)


def _declared_wall_height_storeys(fp: FloorPlan) -> float:
    """Building envelope height in storeys — gates/arches span this."""
    wh = getattr(fp, "wall_height_storeys", None)
    if wh is not None:
        return float(max(1.0, float(wh)))
    if fp.massing is not None:
        mwh = getattr(fp.massing, "wall_height_storeys", None)
        if mwh is not None:
            return float(max(1.0, float(mwh)))
        return float(max(1, int(fp.massing.storeys)))
    return float(max(1, len(fp.storeys)))


def _fp_level_height_units(fp: FloorPlan) -> Optional[Tuple[int, ...]]:
    hu = getattr(fp, "level_height_units", None)
    if hu is not None:
        return tuple(int(x) for x in hu)
    if fp.massing is not None:
        mhu = getattr(fp.massing, "level_height_units", None)
        if mhu is not None:
            return tuple(int(x) for x in mhu)
    return None


def _level_height_units(fp: FloorPlan, level: int) -> float:
    """Height of one LevelSpec in storey units (Stage B). Default 1."""
    hu = _fp_level_height_units(fp)
    if not hu:
        return 1.0
    if 0 <= level < len(hu):
        return float(max(1, int(hu[level])))
    return 1.0


def _style_storey_cm(style: StyleLike) -> float:
    """Pack ``geometry.storey_height_cm`` or contract default (Stage I)."""
    return resolve_storey_height_cm(style)


def _fp_datum_z(fp: FloorPlan, style: StyleLike, level: int) -> float:
    """World Z datum for ``level`` — height_units × pack storey height."""
    hu = _fp_level_height_units(fp)
    return storey_datum_z_cm(
        level, height_units=hu, storey_cm=_style_storey_cm(style)
    )


def _level_datum_delta_cm(fp: FloorPlan, level: int, style: StyleLike) -> float:
    """Cumulative-height datum minus uniform grid (via ``storey_datum_z_cm``).

    Baked into ``offset_cm[2]`` so ``cell_to_world`` / ``storey_datum_z_cm(level)``
    callers keep working without threading height_units / pack storey height everywhere.
    """
    hu = _fp_level_height_units(fp)
    scm = _style_storey_cm(style)
    if not hu and abs(scm - STOREY_CM) < 1e-9:
        return 0.0
    return storey_datum_z_cm(level, height_units=hu, storey_cm=scm) - storey_datum_z_cm(
        level
    )


def _wall_piece_height_storeys(
    fp: FloorPlan,
    level: int,
    asset_id: str,
    entrance_role: Optional[str],
) -> float:
    """How many storeys a wall leaf should span (1.0 = one MODULE storey stub)."""
    level_hu = _level_height_units(fp, level)
    if level != 0:
        # Upper LevelSpec walls span that level's height_units (tall hall / arcade).
        return level_hu
    role = (entrance_role or "").lower()
    monumental = (
        role in ("gate", "grand")
        or "gate" in asset_id
        or asset_id
        in (
            "wall_gate_arch",
            "wall_gate_arch_grand",
            "wall_arcade_monumental",
        )
    )
    if monumental:
        # Span the declared envelope, but never shorter than the leaf needed for a
        # one-storey clear opening (profile height_frac < 1.0).
        return max(
            _declared_wall_height_storeys(fp),
            gate_span_min_storeys(),
            level_hu,
        )
    return level_hu


def _wall_size_for_height_storeys(
    piece: _ResolvedPiece,
    height_storeys: float,
    *,
    storey_cm: float = STOREY_CM,
) -> Tuple[float, float, float]:
    """Keep XY kit size; set Z from declared storeys × pack storey height."""
    sx, sy, _sz = piece.size_cm
    return (sx, sy, height_cm_from_storeys(height_storeys, storey_cm=storey_cm))


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
    spanning_keys: Optional[Set[Tuple[str, Tuple[int, int]]]] = None,
) -> None:
    building_class = str(
        getattr(getattr(fp, "massing", None), "building_class", "") or ""
    ).lower()
    # Covered connectors are open-ended roofed links. Their west/east runs are
    # the enclosing side walls; north/south wall leaves would reduce the link
    # to one or more door-sized tunnels and can be offset into the adjoining
    # facade by a full bay.
    if building_class == "connector" and face in ("south", "north"):
        return
    yaw_by_face = {"west": 0, "east": 180, "south": 270, "north": 90}
    yaw = yaw_by_face[face]
    # Outboard drum cells only — inboard stair towers still need the box perimeter
    # as the outer skin (see ``Docs/DESIGN_TOWER_DRUM.md`` §3).
    from pae.drum import (
        inboard_drum_party_faces_from_plan,
        outboard_drum_cells_from_plan,
        should_suppress_perimeter_wall_on_outboard_drum,
    )

    tower_owned = outboard_drum_cells_from_plan(fp)
    # The attached tower owns this party face on every storey. Suppressing it
    # only at ground level left upper hall wall modules running directly through
    # tower rooms and spiral treads.
    party_faces = inboard_drum_party_faces_from_plan(fp)
    span_keys = spanning_keys if spanning_keys is not None else set()
    gate_passage_xs = _gate_passage_footprint_columns(fp)
    for cell in cells:
        if (
            level > 0
            and cell[0] in gate_passage_xs
            and level < int(math.ceil(_declared_wall_height_storeys(fp)))
        ):
            # The ground monumental leaf already owns this vertical facade
            # column. Any ordinary upper wall here splits/reseals the arch.
            continue
        if should_suppress_perimeter_wall_on_outboard_drum(cell, face, tower_owned):
            continue
        if (cell, face) in party_faces:
            continue
        # Tall gate/arch already spans upper storeys — do not stack a second stub.
        if level > 0 and (face, cell) in span_keys:
            continue
        probe = _opening_probe_cell(cell, face)
        north_gate_through = (
            face == "north"
            and level == 0
            and probe[0] in gate_passage_xs
        )

        piece_def = _wall_asset_for_cell(
            fp, cell, face, catalog, style, bbox, level
        )
        entrance_role = fp.entrance_by_cell.get(probe)
        if north_gate_through:
            piece_def = catalog.pick_wall(
                is_door=True,
                is_window=False,
                style=style,
                entrance_role="gate",
            )
            entrance_role = "gate"
        offset = _boundary_wall_offset_cm(face, yaw, piece_def)
        storey_cm = _style_storey_cm(style)
        datum_dz = _level_datum_delta_cm(fp, level, style)
        if abs(datum_dz) > 1e-9:
            offset = (offset[0], offset[1], offset[2] + datum_dz)
        pid = _next_piece_id(counters, f"wall_{face}", cell, level)
        tags = set(piece_def.tags)
        if entrance_role is None:
            entrance_role = fp.entrance_by_cell.get(probe)
        aid = piece_def.asset_id
        if entrance_role and ("door" in aid or "gate" in aid):
            from pae.existence import entrance_role_tag

            tags.add(entrance_role_tag(entrance_role))
        height_storeys = _wall_piece_height_storeys(
            fp, level, aid, entrance_role
        )
        size_cm = _wall_size_for_height_storeys(
            piece_def, height_storeys, storey_cm=storey_cm
        )
        if height_storeys > 1.0 + 1e-9:
            tags.add(WALL_HEIGHT_SPAN_TAG)
            tags.add(f"height_storeys:{height_storeys:g}")
            span_keys.add((face, cell))
        sp = SolidPlacement(
            piece_id=pid,
            asset_id=piece_def.asset_id,
            kind="wall",
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=size_cm,
            rotates_about_center=piece_def.rotates_about_center,
            tags=frozenset(tags),
        )
        placements.append(sp)
        piece_ids.append(pid)

        aid = piece_def.asset_id
        if "door" in aid or "gate" in aid:
            layer = _layer_from_grid(next(g for g in fp.storeys if g.level == level))
            interior, exterior = _resolved_aperture_cells(face, cell, layer)
            floor_z = _fp_datum_z(fp, style, level)
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
            floor_z = _fp_datum_z(fp, style, level)
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
            floor_z = _fp_datum_z(fp, style, level)
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


def _deck_opening_cells(fp: FloorPlan, level: int) -> Set[Tuple[int, int]]:
    """Plan cells on *level* that must stay open (flight below rises through this deck)."""
    if level <= 0:
        return set()
    out: Set[Tuple[int, int]] = set()
    for lv, cx, cy in _stair_occupied_cells(fp):
        if lv == level - 1:
            out.add((cx, cy))
    return out


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
    split = (
        _monumental_pad_split(run_cells, kind)
        if kind in _MONUMENTAL_PAD_KINDS
        else None
    )
    pads = None if split is None else (split[0], split[1])
    base_yaw = (
        _stair_run_anchor_and_yaw(run_cells)[1]
        if kind == "straight"
        else 0
    )
    for level in range(len(fp.storeys) - 1):
        grid = fp.storeys[level]
        if pads is not None:
            pad = pads[level % 2]
            other = pads[(level + 1) % 2]
            if all(grid.get(*c) == CellRole.STAIR for c in pad):
                anchor = _flight_anchor_in_pad(pad, other, kind, base_yaw, split[2])
                for cx, cy in _flight_footprint_from_anchor(
                    anchor, kind, base_yaw, pad
                ):
                    occupied.add((level, cx, cy))
            continue
        if all(grid.get(*c) == CellRole.STAIR for c in run_cells):
            for cx, cy in run_cells:
                occupied.add((level, cx, cy))
    return occupied


def _flight_anchor_in_pad(
    pad: Sequence[Tuple[int, int]],
    other_pad: Sequence[Tuple[int, int]],
    kind: str,
    yaw: int,
    offset_axis: int,
) -> Tuple[int, int]:
    """Where the flight sits inside its 2×2 pad.

    A ``stair_straight`` is a 2×1 run, so it fills one lane and leaves the other
    as landing. When the pads sit side by side, put each flight in the lane
    NEAREST its neighbour — otherwise consecutive flights end up a full pad width
    (two bays) apart and the climber has to cross the landing to find the next
    foot, which is the "stair marches across the building" defect.
    """
    ax = min(c[0] for c in pad)
    ay = min(c[1] for c in pad)
    if kind != "straight" or len(set(pad)) <= 2:
        # A lane pad is already exactly the flight footprint — nothing to place.
        return (ax, ay)
    run_axis = 1 if int(yaw) % 180 == 90 else 0
    if offset_axis == run_axis:
        return (ax, ay)
    if offset_axis == 0:
        return (ax + 1, ay) if min(c[0] for c in other_pad) > ax else (ax, ay)
    return (ax, ay + 1) if min(c[1] for c in other_pad) > ay else (ax, ay)


def _flight_footprint_from_anchor(
    anchor: Tuple[int, int], kind: str, yaw: int, pad: Sequence[Tuple[int, int]]
) -> List[Tuple[int, int]]:
    """Cells a flight anchored at *anchor* covers."""
    if kind != "straight":
        return list(pad)
    ax, ay = anchor
    if int(yaw) % 180 == 90:
        return [(ax, ay), (ax, ay + 1)]
    return [(ax, ay), (ax + 1, ay)]


def _straight_lane_split(
    cells: Sequence[Tuple[int, int]],
    xs: Sequence[int],
    ys: Sequence[int],
    run_yaw: int,
) -> Optional[Tuple[List[Tuple[int, int]], List[Tuple[int, int]], int]]:
    """Two side-by-side 2×1 lanes for a straight flight — a real switchback.

    A ``stair_straight`` is only ONE cell wide, so splitting its well into 2×2 pads
    stacked along the climb makes each storey start where the last one finished. The
    stair then marches down the building and walks its top landing out through the
    far wall. Two lanes across the width keep the core in one place and let the
    flights alternate direction instead.

    The lanes run along *run_yaw* and sit beside each other across it, so the split
    must follow the flight's real orientation rather than the well's proportions.
    """
    if len(xs) < 2 or len(ys) < 2:
        return None
    known = set(cells)
    x0, y0 = xs[0], ys[0]
    if int(run_yaw) % 180 == 90:
        # Climbs along Y — lanes sit beside each other in X.
        pad0 = [(x0, y0), (x0, y0 + 1)]
        pad1 = [(x0 + 1, y0), (x0 + 1, y0 + 1)]
        axis = 0
    else:
        pad0 = [(x0, y0), (x0 + 1, y0)]
        pad1 = [(x0, y0 + 1), (x0 + 1, y0 + 1)]
        axis = 1
    if any(c not in known for c in pad0 + pad1):
        return None
    return pad0, pad1, axis


def _monumental_flight_pads(
    well_cells: Sequence[Tuple[int, int]],
    kind: str = "switchback",
) -> Optional[Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]]:
    """Split a multi-flight monumental well into two 2×2 pads shifted by stair width.

    Returns ``(even_level_pad, odd_level_pad)`` or ``None`` when the well is a single
    2×2 (only one flight) or cannot be split cleanly.
    """
    split = _monumental_pad_split(well_cells, kind)
    if split is None:
        return None
    pad0, pad1, _axis = split
    return pad0, pad1


def _monumental_pad_split(
    well_cells: Sequence[Tuple[int, int]],
    kind: str = "switchback",
) -> Optional[Tuple[List[Tuple[int, int]], List[Tuple[int, int]], int]]:
    """``(pad0, pad1, offset_axis)`` where axis 0 means the pads shift in X, 1 in Y."""
    cells = sorted(set(well_cells))
    if len(cells) < 8:
        return None
    xs = sorted({c[0] for c in cells})
    ys = sorted({c[1] for c in cells})
    x0, y0 = xs[0], ys[0]
    if kind == "straight":
        _anchor, run_yaw = _stair_run_anchor_and_yaw(cells)
        lanes = _straight_lane_split(cells, xs, ys, run_yaw)
        if lanes is not None:
            return lanes
    if len(xs) >= 4 and len(ys) >= 2:
        pad0 = [(x0 + i, y0 + j) for i in range(2) for j in range(2)]
        pad1 = [(x0 + 2 + i, y0 + j) for i in range(2) for j in range(2)]
        axis = 0
    elif len(ys) >= 4 and len(xs) >= 2:
        pad0 = [(x0 + i, y0 + j) for i in range(2) for j in range(2)]
        pad1 = [(x0 + i, y0 + 2 + j) for i in range(2) for j in range(2)]
        axis = 1
    else:
        return None
    if any(c not in set(cells) for c in pad0 + pad1):
        return None
    return pad0, pad1, axis


def _continuous_shaft_cells(fp: FloorPlan, level: int) -> Set[Tuple[int, int]]:
    """Cells where a run climbs straight through deck *level* with no landing.

    A spiral occupies one cell on every storey, so the plan marks it ``STAIR`` on
    this level and the one below. There is nowhere to stand, so the deck stays
    open. A pad-alternating flight is ``STAIR`` here but ``VOID`` below, so it
    gets a solid deck to start from.
    """
    if level <= 0 or level >= len(fp.storeys):
        return set()
    below = fp.storeys[level - 1]
    return {
        (cx, cy)
        for (cx, cy), role in fp.storeys[level].cells.items()
        if role == CellRole.STAIR and below.get(cx, cy) == CellRole.STAIR
    }


def _pads_flip_yaw(offset_axis: int, yaw: int) -> bool:
    """Should the upper flight reverse direction?

    Two flights only form a switchback when the second pad sits BESIDE the first
    (perpendicular to the climb) — then reversing puts its foot next to where the
    lower flight arrives. When the pads are offset ALONG the climb the second
    flight continues in the same direction; reversing it there parks its foot at
    the far end of the well, so the climber arrives facing the top of a flight
    they cannot enter. That is the "stacked 180°, can't walk up" defect.
    """
    run_axis = 1 if int(yaw) % 180 == 90 else 0
    return offset_axis != run_axis


def _place_stairs(
    *,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
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
        skip_yaw: Optional[int] = None
        if fp.massing is not None:
            bodies = [v for v in fp.massing.volumes if v.role in WING_ROLES]
            for vol in fp.massing.volumes:
                if vol.role == "tower" and (vol.x0, vol.y0) == cell:
                    xy_offset = _tower_drum_xy_offset_cm(vol, bodies)
                    skip_yaw = _tower_attach_skip_yaw(vol, bodies)
                    break
        # A real storey climb is four 90-degree quarters. The doorway belongs
        # at the landing elevation; deleting its quadrant leaves a visible and
        # unwalkable 90-degree gap.
        landing_yaw = (
            (int(skip_yaw) + 180) % 360 if skip_yaw is not None else None
        )
        spiral_yaws = _spiral_yaws_from_landing(landing_yaw)
        storey_cm = _style_storey_cm(style)
        # FIT THE TREADS INSIDE THE DRUM. The arc and the stair quarter are both
        # nominally one module square, but the arc is a RING carrying WALL_T of masonry
        # at its outer radius — so a full-module tread runs straight THROUGH the tower
        # wall. On the fortress that was 213 of 524 interpenetration warnings, the
        # single largest cause, and it reads as the stair escaping the tower.
        _outer_radius = MODULE_CM * 0.5 - TOL_CM
        _bore = 2.0 * _outer_radius
        for level in range(len(fp.storeys) - 1):
            grid = fp.storeys[level]
            if grid.get(*cell) != CellRole.STAIR:
                continue
            step_rise = height_cm_from_storeys(
                _level_height_units(fp, level), storey_cm=storey_cm
            ) / len(spiral_yaws)
            for qi, yaw in enumerate(spiral_yaws):
                pid = _next_piece_id(counters, f"stair_spiral_{yaw}", cell, level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=spiral_def.asset_id,
                        kind="stair",
                        cell=cell,
                        level=level,
                        yaw=yaw,
                        offset_cm=(xy_offset[0], xy_offset[1], qi * step_rise),
                        size_cm=(_bore, _bore, step_rise),
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
                stair_outer_radius_cm=_outer_radius,
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

    pad_split = (
        _monumental_pad_split(run_cells, kind)
        if kind in _MONUMENTAL_PAD_KINDS
        else None
    )
    pads = None if pad_split is None else (pad_split[0], pad_split[1])
    climbed = len(fp.storeys) - 1
    if (
        kind in _MONUMENTAL_PAD_KINDS
        and climbed >= 2
        and pads is None
    ):
        failures.append(
            Failure(
                check="stair_flight_stack",
                message=(
                    f"{asset_id} climbs {climbed} storeys but stair_cells only cover "
                    f"a single 2×2 pad {sorted(set(run_cells))} — successive flights "
                    "would stack in the same XY. Expand the well to 4×2 / 2×4 so "
                    "flights shift by one stair width."
                ),
                world_xyz=(
                    min(c[0] for c in run_cells) * MODULE_CM + MODULE_CM,
                    min(c[1] for c in run_cells) * MODULE_CM + MODULE_CM,
                    0.0,
                ),
                critical=True,
            )
        )
        # Fail-closed — do not emit stacked flights after reporting (D3-3).
        return

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
        if pads is not None:
            pad = pads[level % 2]
            check_cells = pad
            lvl_anchor = _flight_anchor_in_pad(
                pad, pads[(level + 1) % 2], kind, yaw, pad_split[2]
            )
            # Only reverse when the pads sit side by side (a real switchback);
            # pads offset along the climb must keep going the same way.
            flip = _pads_flip_yaw(pad_split[2], yaw) and level % 2 == 1
            lvl_yaw = (yaw + 180) % 360 if flip else yaw
        else:
            check_cells = place_cells
            lvl_anchor = anchor
            lvl_yaw = yaw
            # Single-well 2-storey (one flight only): keep historic 180° flip only
            # when it still covers the same cells — never use this for multi-flight
            # stacking (that path requires ``pads`` above).
            if level % 2 and climbed < 2:
                flipped = (yaw + 180) % 360
                fox, foy = rotation_offset_cm(
                    flipped,
                    sx,
                    sy,
                    rotates_about_center=stair_def.rotates_about_center,
                )
                same_cells = _placement_cells(
                    anchor,
                    level,
                    flipped,
                    stair_def.size_cm,
                    (fox, foy, 0.0),
                    stair_def.rotates_about_center,
                ) == _placement_cells(
                    anchor,
                    level,
                    yaw,
                    stair_def.size_cm,
                    (ox, oy, 0.0),
                    stair_def.rotates_about_center,
                )
                if same_cells:
                    lvl_yaw = flipped

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
                            lvl_anchor[0] * MODULE_CM + MODULE_CM * 0.5,
                            lvl_anchor[1] * MODULE_CM + MODULE_CM * 0.5,
                            float(storey_datum_z_cm(level)),
                        ),
                        critical=True,
                    )
                )
            continue
        ox_l, oy_l = rotation_offset_cm(
            lvl_yaw,
            sx,
            sy,
            rotates_about_center=stair_def.rotates_about_center,
        )
        datum_dz = _level_datum_delta_cm(fp, level, style)
        # Stair rise matches the LevelSpec it climbs out of (height_units × storey).
        climb_hu = _level_height_units(fp, level)
        storey_cm = _style_storey_cm(style)
        size = stair_def.size_cm
        if climb_hu > 1.0 + 1e-9:
            size = (
                size[0],
                size[1],
                height_cm_from_storeys(climb_hu, storey_cm=storey_cm),
            )
        pid = _next_piece_id(counters, "stair", lvl_anchor, level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=stair_def.asset_id,
                kind="stair",
                cell=lvl_anchor,
                level=level,
                yaw=lvl_yaw,
                offset_cm=(ox_l, oy_l, datum_dz),
                size_cm=size,
                rotates_about_center=stair_def.rotates_about_center,
                tags=stair_def.tags,
            )
        )


def _placement_cells(
    cell: Tuple[int, int],
    level: int,
    yaw: int,
    size_cm: Tuple[float, float, float],
    offset_cm: Tuple[float, float, float],
    rotates_about_center: bool,
) -> Set[Tuple[int, int]]:
    """Grid cells a hypothetical placement would cover — used to test a pose before use."""
    mn, mx = placement_world_aabb(
        cell[0], cell[1], level, yaw, size_cm, offset_cm,
        rotates_about_center=rotates_about_center,
    )
    eps = MODULE_CM * 0.25
    out: Set[Tuple[int, int]] = set()
    x = mn[0] + eps
    while x < mx[0] - eps * 0.5:
        y = mn[1] + eps
        while y < mx[1] - eps * 0.5:
            out.add((int(x // MODULE_CM), int(y // MODULE_CM)))
            y += MODULE_CM
        x += MODULE_CM
    return out


def _rect_cover(cells: Set[Tuple[int, int]]) -> List[Tuple[int, int, int, int]]:
    """Cover a cell set with maximal axis-aligned rectangles: ``(x0, y0, w, h)``.

    Greedy and deterministic: take the lowest remaining cell, grow east while the set
    allows, then grow north while every cell of the next row is present. Good enough for
    stairwells and light wells, which are small and rectangular, and it never emits
    overlapping rectangles because consumed cells are removed as it goes.
    """
    remaining = set(cells)
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
    # Prefer existing floor/tower_deck levels so taller keep drums can open the
    # crown slab even when the hall FloorPlan has fewer storeys.
    max_floor_level = max(
        (p.level for p in placements if p.kind == "floor"),
        default=len(fp.storeys) - 1,
    )
    for stair in placements:
        if stair.kind != "stair":
            continue
        top_level = stair.level + 1
        if top_level > max_floor_level:
            continue
        # ONE opening matching the run's own footprint. Punching a 1x1 hole per covered
        # cell gave a 2x1 stairwell two separate square holes instead of the single 2x1
        # well the stair needs. A stair is one spanning placement; so is its opening.
        cells = covered_cells(stair)
        if all((top_level, c) in existing for c in cells):
            continue
        existing |= {(top_level, c) for c in cells}
        pid = _next_piece_id(counters, "floor_hole", stair.cell, top_level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=hole_piece.asset_id,
                kind="floor",
                cell=stair.cell,
                level=top_level,
                yaw=stair.yaw,
                # Plan extent copied from the run; thickness stays the deck's.
                offset_cm=(stair.offset_cm[0], stair.offset_cm[1], -FLOOR_T_CM),
                size_cm=(
                    stair.size_cm[0],
                    stair.size_cm[1],
                    hole_piece.size_cm[2],
                ),
                rotates_about_center=stair.rotates_about_center,
                tags=hole_piece.tags,
            )
        )


def _reconcile_stair_well_holes(
    *,
    fp: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Trim stair-well holes to the actual flights; floor the unused well cells.

    The plan reserves a whole stair well (``stair_cells``, often wider/longer than
    one flight) and marks it ``STAIR``/``VOID``. Upper decks then punched a hole over
    the ENTIRE reserved well, so a 1×2 flight inside a 2×4 well left a permanent
    orphan opening beside the stairs — the "hole next to the stairs" defect on every
    3+ storey building. Reserved cells that no flight uses are landings: they must be
    walkable floor, not void.

    A hole cell is justified when, at that level, either
      * a stair flight one level below covers the cell (the run rises through this
        deck and the climber emerges here), or
      * the plan deliberately marked the cell ``VOID`` / ``DOUBLE_VOID``.

    A flight standing ON this deck does **not** justify a hole — it needs the deck
    solid underneath it.
    """
    from pae.trim import covered_cells

    stairs = [p for p in placements if p.kind == "stair"]
    if not stairs:
        return

    cells_by_level: Dict[int, Set[Tuple[int, int]]] = {}
    for st in stairs:
        cells_by_level.setdefault(st.level, set()).update(covered_cells(st))

    def _plan_role(level: int, cell: Tuple[int, int]):
        if level < 0 or level >= len(fp.storeys):
            return None
        return fp.storeys[level].get(cell[0], cell[1])

    # Cells the plan RESERVED for the well. ``VOID`` here is a by-product of the
    # reservation (plan marks VOID above every stair top), not design intent — so it
    # must not justify an opening on its own. Genuine VOID outside the well (double
    # height halls, light wells) still does.
    reserved_well = set(fp.stair_cells)

    def _justified(level: int, cell: Tuple[int, int]) -> bool:
        # A flight standing on this deck needs it solid, so only the flight BELOW
        # (which rises through this deck) opens it.
        if cell in cells_by_level.get(level, set()):
            return False
        if cell in cells_by_level.get(level - 1, set()):
            return True
        if cell in reserved_well:
            return False
        if cell in _deck_opening_cells(fp, level):
            return True
        return _plan_role(level, cell) in (CellRole.VOID, CellRole.DOUBLE_VOID)

    floor_piece = catalog.get("floor")
    hole_piece = catalog.get("floor_hole")
    kept: List[SolidPlacement] = []
    added: List[SolidPlacement] = []

    for p in placements:
        if p.asset_id != hole_piece.asset_id or p.kind != "floor":
            kept.append(p)
            continue
        cells = set(covered_cells(p))
        if not cells:
            kept.append(p)
            continue
        good = {c for c in cells if _justified(p.level, c)}
        orphan = cells - good
        if not orphan:
            kept.append(p)
            continue
        # Re-emit the justified opening as rectangles.
        for hx, hy, hw, hh in _rect_cover(good):
            pid = _next_piece_id(counters, "floor_hole", (hx, hy), p.level)
            added.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=hole_piece.asset_id,
                    kind="floor",
                    cell=(hx, hy),
                    level=p.level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, p.offset_cm[2]),
                    size_cm=(hw * MODULE_CM, hh * MODULE_CM, hole_piece.size_cm[2]),
                    tags=hole_piece.tags,
                )
            )
        # Unused reserved well cells become walkable landing deck.
        for fx, fy, fw, fh in _rect_cover(orphan):
            pid = _next_piece_id(counters, "floor_deck", (fx, fy), p.level)
            added.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=floor_piece.asset_id,
                    kind="floor",
                    cell=(fx, fy),
                    level=p.level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, p.offset_cm[2]),
                    size_cm=(fw * MODULE_CM, fh * MODULE_CM, FLOOR_T_CM),
                    tags=floor_piece.tags,
                )
            )

    if added:
        placements[:] = kept + added


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

    The catalog quarter has an outer radius of one module (8 m diameter after
    four quarters). Larger habitable drums scale that radius explicitly.
    Resolve the real radius against the hall boundary so the shell kisses the
    envelope instead of overlapping it or leaving an air gap.
    """
    cell_corner_x = tower.x0 * MODULE_CM
    cell_corner_y = tower.y0 * MODULE_CM
    body = _tower_attached_body(tower, bodies)
    if body is None:
        return (0.0, 0.0)

    r = _tower_radius_cm(tower)
    west = tower.x1 < body.x0
    east = tower.x0 > body.x1
    south = tower.y1 < body.y0
    north = tower.y0 > body.y1

    # Resolve the drum centre from the hall boundary using the primitive's real
    # radius, not the one-cell logical anchor used by the plan.
    cx = cell_corner_x + r
    cy = cell_corner_y + r
    # A tangent circle touches the host at one mathematical point and leaves
    # two open wedges beside the doorway. Embed the attached mass far enough to
    # create a real chord/vestibule junction, capped at half a module so even
    # large lighthouse drums do not consume an entire host bay.
    # A deep radius-proportional embed made large guard towers consume half a
    # hall bay and put their shell through stairs/floors. One-and-a-half wall
    # thicknesses creates a real doorway chord without moving the tower room
    # into the host building.
    embed = min(MODULE_CM * 0.25, WALL_T_CM * 1.5)
    if west:
        cx = body.x0 * MODULE_CM - r + embed
    elif east:
        cx = (body.x1 + 1) * MODULE_CM + r - embed
    if south:
        cy = body.y0 * MODULE_CM - r + embed
    elif north:
        cy = (body.y1 + 1) * MODULE_CM + r - embed

    # Wall attach (single-axis abut): centre on the shared edge midline.
    if (west or east) and not (south or north):
        cy = _shared_edge_mid_cm(tower, body, axis="y")
    elif (south or north) and not (west or east):
        cx = _shared_edge_mid_cm(tower, body, axis="x")

    return (cx - cell_corner_x, cy - cell_corner_y)


def _tower_radius_cm(tower: Volume) -> float:
    """Physical outer radius of a tower drum (plan anchor remains one cell)."""
    return MODULE_CM * max(
        0.5, float(getattr(tower, "tower_radius_bays", 1.0))
    )


def _tower_cells(fp: FloorPlan) -> Set[Tuple[int, int]]:
    """Cells owned by tower volumes (cap/arcs, not pitched roof)."""
    cells: Set[Tuple[int, int]] = set()
    if fp.massing is None:
        return cells
    for vol in fp.massing.volumes:
        if vol.role == "tower":
            cells |= vol.cells()
    return cells


def _roof_level_cells_for_structure(fp: FloorPlan) -> List[Set[Tuple[int, int]]]:
    """Built cells per level for the Stage C roof height field.

    Prefers ``massing.level_cells`` (StructureSpec). Falls back to enclosed
    volume coverage so legacy BuildingSpec paths still get a column field.
    Courtyard / exterior cells never enter the field.
    """
    from pae.plan import _enclosed_cells_at_level

    n = len(fp.storeys)
    out: List[Set[Tuple[int, int]]] = []
    for level in range(n):
        if fp.massing is not None:
            cells = set(_enclosed_cells_at_level(fp.massing, level))
        else:
            grid = fp.storeys[level]
            cells = {
                (x, y)
                for (x, y), role in grid.cells.items()
                if role
                not in (
                    CellRole.EXTERIOR,
                    CellRole.COURTYARD,
                    CellRole.VOID,
                    CellRole.DOUBLE_VOID,
                )
            }
        out.append(cells)
    return out


def _roof_z_offset_cm(fp: FloorPlan, level: int, style: StyleLike) -> float:
    """Local Z so the roof deck sits on the wall head of ``level``."""
    storey_cm = _style_storey_cm(style)
    return height_cm_from_storeys(
        _level_height_units(fp, level), storey_cm=storey_cm
    ) + _level_datum_delta_cm(fp, level, style)


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

    Stage C: spans come from the column height field (not massing wing roles).
    Ridge height uses ``structure_ridge_span_modules`` so a sketched U gets one
    ridge family instead of three (D3-9).
    """
    if floor_plan is not None:
        _place_structure_roofs(
            floor_plan=floor_plan,
            catalog=catalog,
            tower_cells=tower_cells,
            placements=placements,
            counters=counters,
            style=None,
            kinds_only=("pitched",),
        )
        return
    # Legacy single-bbox path (no FloorPlan / height field).
    _place_pitched_roof_spans(
        level=level,
        pitch=pitch,
        catalog=catalog,
        tower_cells=tower_cells,
        roof_spans=[(x0, y0, x1, y1)],
        ridge_span_modules=min(x1 - x0 + 1, y1 - y0 + 1),
        roof_z=STOREY_CM,
        placements=placements,
        counters=counters,
    )


def _place_pitched_roof_spans(
    *,
    level: int,
    pitch: float,
    catalog: _PieceCatalog,
    tower_cells: Set[Tuple[int, int]],
    roof_spans: Sequence[Tuple[int, int, int, int]],
    ridge_span_modules: int,
    roof_z: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Emit pitched slopes + gables for one height band."""
    gable_piece = catalog.get("roof_gable_infill")
    slope_piece = catalog.get("roof_pitched_slope")
    ridge_modules = max(1, int(ridge_span_modules))
    full_rise = roof_rise_cm(pitch, ridge_modules * MODULE_CM)
    gable_height = full_rise + FLOOR_T_CM
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
        roof_z=roof_z,
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
    roof_z: float = STOREY_CM,
) -> None:
    """Place V-trough valley strips on L/U wing abutments (S-019 stub).

    Does not resolve a single watertight multi-wing surface (S-021) — only
    marks the shared eave seams so adjacent hips/slopes no longer collide bare.
    """
    if len(roof_spans) < 2:
        return
    valley_piece = catalog.get("roof_valley")
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
    """Place four-slope hip roofs from the structure height field (§6 / S-012).

    Stage C: one ridge family per eaves band (D3-9). L/U abutments still get
    S-019 valley stubs from height-field spans.
    """
    _place_structure_roofs(
        floor_plan=floor_plan,
        catalog=catalog,
        tower_cells=_tower_cells(floor_plan),
        placements=placements,
        counters=counters,
        style=None,
        kinds_only=("hip",),
    )


def _place_hip_roof_spans(
    *,
    level: int,
    pitch: float,
    catalog: _PieceCatalog,
    roof_spans: Sequence[Tuple[int, int, int, int]],
    ridge_span_modules: int,
    roof_z: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Emit hip plates for one height band."""
    roof_piece = catalog.get("roof_hip")
    ridge_modules = max(1, int(ridge_span_modules))
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
                    ridge_span_modules=ridge_modules,
                ),
                tags=roof_piece.tags,
            )
        )
    _place_valley_stubs(
        level=level,
        pitch=pitch,
        catalog=catalog,
        roof_spans=roof_spans,
        roof_z=roof_z,
        placements=placements,
        counters=counters,
    )


def _place_flat_roof_spans(
    *,
    level: int,
    catalog: _PieceCatalog,
    tower_cells: Set[Tuple[int, int]],
    roof_spans: Sequence[Tuple[int, int, int, int]],
    roof_z: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Emit flat roof decks for one height band."""
    roof_piece = catalog.get("roof_flat")
    for rx0, ry0, rx1, ry1 in roof_spans:
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
        west, east, south, north = roof_eave_overhang_per_side(
            sx0, sy0, sx1, sy1, roof_spans
        )
        eave_ox, eave_oy, _ = roof_eave_offset_cm(
            overhang_west=west, overhang_south=south
        )
        pid = _next_piece_id(counters, "roof", (sx0, sy0), level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=roof_piece.asset_id,
                kind="roof",
                cell=(sx0, sy0),
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


def _place_structure_roofs(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    tower_cells: Set[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    style: StyleLike,
    kinds_only: Optional[Sequence[str]] = None,
) -> None:
    """One roof system per structure from the column height field (Stage C).

    Stepping: columns that top out on different levels get separate eaves bands.
    Within a band, ridge height is unified (D3-9).
    """
    kind = floor_plan.roof_kind
    if kinds_only is not None and kind not in kinds_only:
        return
    if kind not in ("flat", "pitched", "hip"):
        return

    level_cells = _roof_level_cells_for_structure(floor_plan)
    bands = roof_height_field_bands(
        level_cells,
        height_units=_fp_level_height_units(floor_plan),
        exclude=set(tower_cells),
    )
    if not bands:
        return

    pitch = float(floor_plan.roof_pitch)
    for band in bands:
        roof_z = _roof_z_offset_cm(floor_plan, band.top_level, style)
        ridge = structure_ridge_span_modules(band.spans)
        if kind == "flat":
            _place_flat_roof_spans(
                level=band.top_level,
                catalog=catalog,
                tower_cells=tower_cells,
                roof_spans=band.spans,
                roof_z=roof_z,
                placements=placements,
                counters=counters,
            )
        elif kind == "pitched":
            _place_pitched_roof_spans(
                level=band.top_level,
                pitch=pitch,
                catalog=catalog,
                tower_cells=tower_cells,
                roof_spans=band.spans,
                ridge_span_modules=ridge,
                roof_z=roof_z,
                placements=placements,
                counters=counters,
            )
        elif kind == "hip":
            _place_hip_roof_spans(
                level=band.top_level,
                pitch=pitch,
                catalog=catalog,
                roof_spans=band.spans,
                ridge_span_modules=ridge,
                roof_z=roof_z,
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


def _spiral_tower_drum_cells(fp: FloorPlan) -> Set[Tuple[int, int]]:
    """Tower cells that own a helical drum stair (TowerSpec or building spiral)."""
    cells: Set[Tuple[int, int]] = set()
    if fp.massing is None:
        return cells
    kind = str(getattr(fp.massing, "stair_kind", "") or "").lower()
    if kind == "spiral":
        cells |= set(fp.stair_cells)
    for vol in fp.massing.volumes:
        if vol.role != "tower":
            continue
        if str(getattr(vol, "stair_kind", "") or "").lower() == "spiral":
            cells |= vol.cells()
    return cells


def _tower_has_spiral_stair(
    fp: FloorPlan,
    cell: Tuple[int, int],
    placements: Optional[Sequence[SolidPlacement]] = None,
) -> bool:
    if placements is not None:
        if any(
            p.asset_id == "stair_spiral_quarter" and p.cell == cell for p in placements
        ):
            return True
    return cell in _spiral_tower_drum_cells(fp)


def _place_habitable_tower_spirals(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Helical climb inside every TowerSpec with ``stair_kind=spiral``.

    Hall may keep switchback/straight; each multi-storey keep drum still needs
    its own vertical circulation (Phase 4.7 / @TOWER_KEEP_HABITABLE). Skips cells
    that already have ``stair_spiral_quarter`` (building-level spiral path).
    """
    if floor_plan.massing is None:
        return
    spiral_def = catalog.get("stair_spiral_quarter")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    owned_cells = {
        (v.x0, v.y0)
        for v in floor_plan.massing.volumes
        if v.role == "tower"
        and str(getattr(v, "stair_kind", "") or "").lower() == "spiral"
    }
    # TowerSpec owns the full physical shaft. The generic building stair pass
    # may have emitted a one-storey, module-sized spiral in the same logical
    # cell; replace it so tiny bores are clamped and tall turrets climb every
    # requested storey.
    placements[:] = [
        p
        for p in placements
        if not (
            p.cell in owned_cells
            and p.asset_id == "stair_spiral_quarter"
        )
    ]
    for vol in floor_plan.massing.volumes:
        if vol.role != "tower":
            continue
        if str(getattr(vol, "stair_kind", "") or "").lower() != "spiral":
            continue
        if vol.storeys < 2:
            continue
        cell = (vol.x0, vol.y0)
        xy_offset = _tower_drum_xy_offset_cm(vol, bodies)
        radius = _tower_radius_cm(vol)
        # Keep the actual tread outer radius inside the masonry inner face.
        clear_bore = max(0.0, radius - WALL_T_CM)
        stair_outer_radius = max(
            WALL_T_CM,
            min(
                MODULE_CM - 2.0 * WALL_T_CM,
                clear_bore - TOL_CM,
            ),
        )
        stair_span = 2.0 * stair_outer_radius
        body = _tower_attached_body(vol, bodies)
        door_yaw = _tower_attach_skip_yaw(vol, bodies)
        # Door yaw is the shell face orientation; its physical doorway lies on
        # the opposite radial side of the stair centre. Start the helix at that
        # doorway radius, not at the face yaw itself.
        landing_yaw = (
            (int(door_yaw) + 180) % 360 if door_yaw is not None else None
        )
        spiral_yaws = _spiral_yaws_from_landing(landing_yaw)
        storey_cm = _style_storey_cm(style)
        step_rise = storey_cm / len(spiral_yaws)
        # Climb every shaft storey to the crown landing under ``tower_deck``.
        climb = max(0, vol.storeys - 1)
        for level in range(climb):
            for qi, yaw in enumerate(spiral_yaws):
                pid = _next_piece_id(
                    counters, f"stair_spiral_{yaw}", cell, level
                )
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=spiral_def.asset_id,
                        kind="stair",
                        cell=cell,
                        level=level,
                        yaw=yaw,
                        offset_cm=(
                            xy_offset[0],
                            xy_offset[1],
                            _level_datum_delta_cm(floor_plan, level, style)
                            + qi * step_rise,
                        ),
                        # Clear bore, not the full module — see the note in
                        # ``_place_stairs``: the drum arc is a RING with WALL_T of
                        # masonry, so a full-module tread runs through the tower wall.
                        size_cm=(
                            stair_span,
                            stair_span,
                            step_rise,
                        ),
                        rotates_about_center=True,
                        tags=spiral_def.tags | frozenset({"tower", "habitable_drum"}),
                    )
                )
            from pae.spiral_shell import place_spiral_newels

            place_spiral_newels(
                placements=placements,
                counters=counters,
                cell=cell,
                levels=(level,),
                xy_offset=xy_offset,
                next_piece_id=_next_piece_id,
                stair_outer_radius_cm=stair_outer_radius,
                height_cm=storey_cm,
                z_offset_cm=_level_datum_delta_cm(
                    floor_plan, level, style
                ),
            )


def _place_habitable_tower_rooms(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Add usable floor plates and an enclosed stair core to large drums.

    A tower remains one logical plan cell, but its physical radius may be two or
    three modules.  The room deck is the largest square inside the circular bore.
    Spiral towers receive four slab strips around a central opening plus a
    four-sided stair enclosure with one real door module per storey.
    """
    if floor_plan.massing is None:
        return
    floor_piece = catalog.get("floor")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    storey_cm = _style_storey_cm(style)

    for vol in floor_plan.massing.volumes:
        if vol.role != "tower":
            continue
        cell = (vol.x0, vol.y0)
        radius = _tower_radius_cm(vol)
        inner_radius = radius - WALL_T_CM
        if inner_radius <= MODULE_CM * 0.5:
            continue
        if str(getattr(vol, "tower_shape", "round") or "round").lower() == "square":
            # Square shell: slab bears halfway into each perimeter wall instead
            # of merely touching its inner face (zero-area contact).
            side = 2.0 * (radius - WALL_T_CM * 0.25)
        else:
            # Round shell: largest axis-aligned square inside the clear bore.
            side = (2.0 * inner_radius) / math.sqrt(2.0)
        drum_xy = _tower_drum_xy_offset_cm(vol, bodies)
        has_spiral = _tower_has_spiral_stair(
            floor_plan, cell, placements
        )
        # The standard radius-one spiral drum is a stair tower, not a room.
        # From radius 1.25 upward the measured inscribed deck has a positive
        # landing band around the compact core; use that real clearance rather
        # than an arbitrary radius-two cutoff.
        room_bearing = has_spiral and radius >= MODULE_CM * 1.25
        if not room_bearing:
            continue

        stair_spans = [
            max(float(p.size_cm[0]), float(p.size_cm[1]))
            for p in placements
            if p.cell == cell
            and p.asset_id == "stair_spiral_quarter"
        ]
        core_outer = (
            max(stair_spans, default=MODULE_CM)
            + max(TOL_CM * 2.0, WALL_T_CM * 0.25)
            if has_spiral
            else 0.0
        )
        if has_spiral and core_outer >= side - TOL_CM:
            continue
        band = (side - core_outer) * 0.5 if has_spiral else 0.0
        room_floor_tags = frozenset(floor_piece.tags) | frozenset(
            {"tower", "tower_room", "tower_room_floor", "walkable"}
        )

        for level in range(vol.storeys):
            floor_z = (
                _level_datum_delta_cm(floor_plan, level, style)
                - FLOOR_T_CM
            )
            if not has_spiral:
                floor_specs = [(0.0, 0.0, side, side)]
            else:
                centre_step = core_outer * 0.5 + band * 0.5
                floor_specs = [
                    (-centre_step, 0.0, band, side),
                    (centre_step, 0.0, band, side),
                    (0.0, -centre_step, core_outer, band),
                    (0.0, centre_step, core_outer, band),
                ]
            for index, (dx, dy, sx, sy) in enumerate(floor_specs):
                pid = _next_piece_id(
                    counters, f"tower_room_floor_{index}", cell, level
                )
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=floor_piece.asset_id,
                        kind="floor",
                        cell=cell,
                        level=level,
                        yaw=0,
                        offset_cm=(
                            drum_xy[0] + dx,
                            drum_xy[1] + dy,
                            floor_z,
                        ),
                        size_cm=(sx, sy, FLOOR_T_CM),
                        rotates_about_center=True,
                        tags=room_floor_tags,
                    )
                )

            # The exterior drum is the stair enclosure.  A second rectangular
            # core around the helix consumes the tread path in large towers.
            # Upper room floors retain their central well; guard rails belong
            # to that well edge, not full-height walls through the staircase.


def _place_tower_spiral_exit_holes(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Declare every landing opening in shafts taller than the attached body.

    The ordinary floor pass only knows the hall's storey count. A five-storey
    turret attached to a two/three-storey house therefore needs explicit upper
    well markers even when it is too small to contain annular rooms.
    """
    if floor_plan.massing is None:
        return
    from pae.trim import covered_cells

    hole = catalog.get("floor_hole")
    existing = {
        (p.level, c)
        for p in placements
        if p.asset_id == "floor_hole"
        for c in covered_cells(p)
    }
    tower_by_cell = {
        (v.x0, v.y0): v
        for v in floor_plan.massing.volumes
        if v.role == "tower"
    }
    stairs = [
        p
        for p in placements
        if p.kind == "stair"
        and "habitable_drum" in p.tags
        and p.cell in tower_by_cell
    ]
    for level in sorted({p.level + 1 for p in stairs}):
        level_stairs = [p for p in stairs if p.level + 1 == level]
        if not level_stairs:
            continue
        # All quarter treads in a storey share the same centred plan footprint.
        stair = level_stairs[0]
        cells = covered_cells(stair)
        if all((level, c) in existing for c in cells):
            continue
        existing |= {(level, c) for c in cells}
        pid = _next_piece_id(counters, "tower_floor_hole", stair.cell, level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=hole.asset_id,
                kind="floor",
                cell=stair.cell,
                level=level,
                yaw=stair.yaw,
                offset_cm=(
                    stair.offset_cm[0],
                    stair.offset_cm[1],
                    -FLOOR_T_CM,
                ),
                size_cm=(
                    stair.size_cm[0],
                    stair.size_cm[1],
                    hole.size_cm[2],
                ),
                rotates_about_center=stair.rotates_about_center,
                tags=frozenset(hole.tags) | frozenset({"tower", "tower_stairwell"}),
            )
        )


def _place_tower_entry_landings(
    *,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Bridge every tower doorway to the first/last tread at each floor.

    The stair is deliberately inset from the masonry shell. Without this small
    threshold slab the doorway can be visually clear yet the whole helix is a
    freestanding island separated from the building by an air gap.
    """
    floor_piece = catalog.get("floor")
    entries = [p for p in placements if "tower_entry" in p.tags]
    stairs = [
        p for p in placements if p.asset_id == "stair_spiral_quarter"
    ]
    # A one-tolerance kiss is numerically connected but reads as an air gap
    # against the tapered first tread. Carry the threshold a full footstep into
    # both the doorway and helix footprint.
    overlap_cm = max(TOL_CM * 4.0, 40.0)
    for door in entries:
        candidates = [
            p
            for p in stairs
            if p.cell == door.cell
            and p.level == door.level
            and int(p.yaw) % 360 == (int(door.yaw) + 180) % 360
        ]
        if not candidates:
            continue
        stair = min(candidates, key=lambda p: float(p.offset_cm[2]))
        dx = float(door.offset_cm[0]) - float(stair.offset_cm[0])
        dy = float(door.offset_cm[1]) - float(stair.offset_cm[1])
        distance = math.hypot(dx, dy)
        if distance <= TOL_CM:
            continue
        ux, uy = dx / distance, dy / distance
        yaw = int(door.yaw) % 360
        radial_thickness = (
            float(door.size_cm[0]) if yaw in (0, 180) else float(door.size_cm[1])
        )
        chord = (
            float(door.size_cm[1]) if yaw in (0, 180) else float(door.size_cm[0])
        )
        inner_face = distance - radial_thickness * 0.5
        stair_outer = max(float(stair.size_cm[0]), float(stair.size_cm[1])) * 0.5
        near = max(0.0, stair_outer - overlap_cm)
        far = inner_face + overlap_cm
        depth = max(overlap_cm * 2.0, far - near)
        centre_radius = 0.5 * (near + far)
        centre_x = float(stair.offset_cm[0]) + ux * centre_radius
        centre_y = float(stair.offset_cm[1]) + uy * centre_radius
        width = max(90.0, min(chord * 0.72, 140.0))
        if abs(dx) >= abs(dy):
            size_xy = (depth, width)
        else:
            size_xy = (width, depth)
        pid = _next_piece_id(
            counters, "tower_entry_landing", door.cell, door.level
        )
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=floor_piece.asset_id,
                kind="floor",
                cell=door.cell,
                level=door.level,
                yaw=0,
                offset_cm=(
                    centre_x,
                    centre_y,
                    float(door.offset_cm[2]) - FLOOR_T_CM,
                ),
                size_cm=(size_xy[0], size_xy[1], FLOOR_T_CM),
                rotates_about_center=True,
                tags=frozenset(floor_piece.tags)
                | frozenset(
                    {
                        "tower",
                        "tower_entry_landing",
                        "walkable",
                        "structural",
                    }
                ),
            )
        )


def _place_gate_passage_side_walls(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Enclose each paired through-gate lane for its full arch height/depth."""
    south = [
        p
        for p in placements
        if p.level == 0
        and p.piece_id.startswith("wall_south_")
        and "gate" in p.tags
    ]
    north_by_x = {
        p.cell[0]: p
        for p in placements
        if p.level == 0
        and p.piece_id.startswith("wall_north_")
        and "gate" in p.tags
    }
    if not south or not north_by_x:
        return
    wall = catalog.get("wall_plain")
    door = catalog.get("wall_door_gothic")
    arch_height = max(
        float(p.size_cm[2]) for p in south + list(north_by_x.values())
    )
    # The occupied arch volume has no intermediate storey. Its ground-level
    # envelope therefore spans the same two-storey height as the gate leaves;
    # emitting ordinary L1 wall modules would imply a floor that does not exist.
    for p in placements:
        if (
            p.level == 0
            and p.kind == "wall"
            and p.piece_id.startswith(("wall_west_", "wall_east_", "wall_south_", "wall_north_"))
            and "tower" not in p.tags
        ):
            p.size_cm = (p.size_cm[0], p.size_cm[1], max(p.size_cm[2], arch_height))
            p.tags = frozenset(p.tags) | frozenset(
                {
                    "wall_height_span",
                    f"height_storeys:{arch_height / STOREY_CM:g}",
                }
            )
    for front in south:
        rear = north_by_x.get(front.cell[0])
        if rear is None:
            continue
        lane_x = front.cell[0]
        y0 = min(front.cell[1], rear.cell[1])
        y1 = max(front.cell[1], rear.cell[1])
        height = max(float(front.size_cm[2]), float(rear.size_cm[2]))
        door_y = y0 + max(0, (y1 - y0 - 1) // 2)
        for y in range(y0, y1):
            for side, x_off in (
                ("west", 0.0),
                ("east", MODULE_CM - WALL_T_CM),
            ):
                adjacent_cell = (
                    lane_x - 1 if side == "west" else lane_x + 1,
                    y,
                )
                # A passage-side doorway owns this opening when a stair lands
                # directly beside the gate lane. Do not place a full-height
                # wall (or masonry stacked over its door) through that landing.
                if any(
                    grid.get(*adjacent_cell) == CellRole.STAIR
                    for grid in floor_plan.storeys
                ):
                    continue
                if y == door_y:
                    # Ground-storey guard door with solid masonry above. The
                    # carriage lane is double-height, so there is no level-1
                    # floor or doorway to serve.
                    door_levels = max(1, int(math.ceil(height / STOREY_CM)))
                    for door_level in range(door_levels):
                        piece = door if door_level == 0 else wall
                        pid = _next_piece_id(
                            counters,
                            (
                                f"gate_guard_door_{side}"
                                if door_level == 0
                                else f"gate_passage_upper_{side}"
                            ),
                            (lane_x, y),
                            door_level,
                        )
                        placements.append(
                            SolidPlacement(
                                piece_id=pid,
                                asset_id=piece.asset_id,
                                kind="wall",
                                cell=(lane_x, y),
                                level=door_level,
                                yaw=0,
                                offset_cm=(x_off, 0.0, 0.0),
                                size_cm=(
                                    WALL_T_CM,
                                    MODULE_CM,
                                    min(STOREY_CM, height - door_level * STOREY_CM),
                                ),
                                tags=frozenset(piece.tags)
                                | frozenset(
                                    {
                                        "gate_guard_door",
                                        "gate_passage_wall",
                                        f"gate_passage_side_{side}",
                                        "structural",
                                    }
                                ),
                            )
                        )
                    continue
                pid = _next_piece_id(
                    counters, f"gate_passage_{side}", (lane_x, y), 0
                )
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=wall.asset_id,
                        kind="wall",
                        cell=(lane_x, y),
                        level=0,
                        yaw=0,
                        offset_cm=(x_off, 0.0, 0.0),
                        size_cm=(WALL_T_CM, MODULE_CM, height),
                        tags=frozenset(wall.tags)
                        | frozenset(
                            {
                                "gate_passage_wall",
                                f"gate_passage_side_{side}",
                                f"height_storeys:{height / STOREY_CM:g}",
                                "structural",
                            }
                        ),
                    )
                )


def _place_attached_tower_roof_notches(
    *,
    floor_plan: FloorPlan,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Declare vertical roof cutters where an attached tower enters its host.

    The cutter uses the tower's clear inner footprint, leaving masonry thickness
    under the roof edge. The renderer consumes these placements as deterministic
    roof exclusions; validation consumes the same contract when checking
    headroom and roof penetration. Runtime Blender booleans are deliberately
    forbidden here because exact coplanar roof/tower cuts can crash Blender.
    """
    if floor_plan.massing is None:
        return
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    roofs = [p for p in placements if p.kind == "roof"]
    for vol in floor_plan.massing.volumes:
        if vol.role != "tower" or _tower_attached_body(vol, bodies) is None:
            continue
        cell = (vol.x0, vol.y0)
        centre = _tower_drum_xy_offset_cm(vol, bodies)
        # Match the authored room-floor inner edge (half a floor thickness in
        # from the shell). Using a full wall-thickness inset left a 45 cm strip
        # of host roof inside the usable tower room.
        clear_radius = max(
            TOL_CM, _tower_radius_cm(vol) - FLOOR_T_CM * 0.5
        )
        probe_min = (
            cell[0] * MODULE_CM + centre[0] - clear_radius,
            cell[1] * MODULE_CM + centre[1] - clear_radius,
        )
        probe_max = (
            cell[0] * MODULE_CM + centre[0] + clear_radius,
            cell[1] * MODULE_CM + centre[1] + clear_radius,
        )
        overlapping = []
        for roof in roofs:
            rmin, rmax = placement_world_aabb(
                roof.cell[0],
                roof.cell[1],
                roof.level,
                roof.yaw,
                roof.size_cm,
                roof.offset_cm,
                rotates_about_center=roof.rotates_about_center,
            )
            if (
                min(probe_max[0], rmax[0]) - max(probe_min[0], rmin[0]) > TOL_CM
                and min(probe_max[1], rmax[1]) - max(probe_min[1], rmin[1]) > TOL_CM
            ):
                overlapping.append((roof, rmin, rmax))
        if not overlapping:
            continue
        level = min(item[0].level for item in overlapping)
        z_min = min(item[1][2] for item in overlapping) - TOL_CM
        z_max = max(item[2][2] for item in overlapping) + TOL_CM
        pid = _next_piece_id(counters, "roof_hole_tower", cell, level)
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id="roof_hole",
                kind="void",
                cell=cell,
                level=level,
                yaw=0,
                offset_cm=(
                    centre[0],
                    centre[1],
                    z_min - storey_datum_z_cm(level),
                ),
                size_cm=(
                    clear_radius * 2.0,
                    clear_radius * 2.0,
                    z_max - z_min,
                ),
                rotates_about_center=True,
                tags=frozenset(
                    {"void", "roof_hole", "tower", "tower_host_junction"}
                ),
            )
        )


def _place_double_height_hall_arch_ribs(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Alternate transverse ribs across a declared double-height pitched hall."""
    if (
        floor_plan.roof_kind != "pitched"
        or len(floor_plan.storeys) < 3
        or floor_plan.massing is None
    ):
        return
    open_level = floor_plan.storeys[1]
    double_voids = {
        cell
        for cell, role in open_level.cells.items()
        if role == CellRole.DOUBLE_VOID
    }
    bodies = [
        v for v in floor_plan.massing.volumes if v.role in WING_ROLES
    ]
    if not double_voids or not bodies:
        return
    body = max(bodies, key=lambda v: len(v.cells()))
    if not body.cells().issubset(double_voids):
        return
    spacing = int(
        getattr(
            floor_plan.massing, "interior_arch_rib_every_bays", 0
        )
        or 0
    )
    if spacing < 1:
        return
    rib = catalog.get("arch_rib_freestanding")
    span_y = (body.y1 - body.y0 + 1) * MODULE_CM
    rib_level = 1
    rib_height = (
        _fp_datum_z(floor_plan, {}, rib_level + 1)
        - _fp_datum_z(floor_plan, {}, rib_level)
    )
    datum_delta = _fp_datum_z(floor_plan, {}, rib_level) - storey_datum_z_cm(
        rib_level
    )
    # Style is not threaded into this feature pass; the massing stores the
    # resolved style name, so use it for its host-storey datum.
    try:
        from pae.style_pack import resolve_style_pack

        rib_style = resolve_style_pack(floor_plan.style)
        rib_height = (
            _fp_datum_z(floor_plan, rib_style, rib_level + 1)
            - _fp_datum_z(floor_plan, rib_style, rib_level)
        )
        datum_delta = _level_datum_delta_cm(
            floor_plan, rib_level, rib_style
        )
    except Exception:
        pass
    for x in range(body.x0 + 1, body.x1, spacing):
        pid = _next_piece_id(
            counters, "great_hall_arch_rib", (x, body.y0), 1
        )
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=rib.asset_id,
                kind="wall",
                cell=(x, body.y0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, datum_delta),
                size_cm=(WALL_T_CM, span_y, rib_height),
                tags=frozenset(rib.tags)
                | frozenset(
                    {"interior_arch_rib", "double_height_hall"}
                ),
            )
        )


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
        # Preserve the full-turn quarter index so window height matches the
        # tread beside it; only the doorway-facing window is omitted.
        slots = [
            (qi, yaw)
            for qi, yaw in enumerate(_spiral_yaws_from_landing(skip_yaw))
            if yaw != skip_yaw
        ]
        return slots
    else:
        start = level % 4
        ordered = (
            _TOWER_QUARTER_YAWS[start:]
            + _TOWER_QUARTER_YAWS[:start]
        )
        yaw = next((candidate for candidate in ordered if candidate != skip_yaw), ordered[0])
        slots = [(start, yaw)]
    if skip_yaw is None:
        return slots
    return [(qi, yaw) for qi, yaw in slots if yaw != skip_yaw]


def _clamp_tower_window_tangential_offset(
    ox: float,
    oy: float,
    *,
    yaw: int,
    size_xy: Tuple[float, float],
) -> Tuple[float, float]:
    """Keep the chord's tangential centre inside the host tower cell.

    Attach-face bias may flush a N/S (or E/W) rim shell fully into a side-neighbour
    cell. After compound merge that neighbour often carries another building's roof,
    so ``covered_cells`` falsely reports ``roof_penetration`` on tall gatehouse
    arrowslits. Radial (outward) offset is left alone so hall-kiss clearance stays.
    """
    sx, sy = size_xy
    hx, hy = sx * 0.5, sy * 0.5
    if yaw in (90, 270):
        # Chord runs in X — clamp X only.
        lo, hi = hx, MODULE_CM - hx
        if lo <= hi:
            ox = min(max(ox, lo), hi)
        else:
            ox = MODULE_CM * 0.5
    elif yaw in (0, 180):
        lo, hi = hy, MODULE_CM - hy
        if lo <= hi:
            oy = min(max(oy, lo), hi)
        else:
            oy = MODULE_CM * 0.5
    return ox, oy


def _tower_window_shell_pose(
    drum_xy: Tuple[float, float],
    yaw: int,
    *,
    z_off: float,
    height_cm: float,
    chord_cm: float,
    skip_yaw: Optional[int],
    radius_cm: float = MODULE_CM,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Size + offset for a drum-rim window overlay.

    Pushes the piece to the outer shell at the tower's physical radius along the face
    normal. Thin/long axes are baked into ``size_cm`` because centred AABBs do
    not follow yaw. When the face is perpendicular to the attach axis, the chord
    is biased toward the free hemisphere so it clears the hall kiss wall.
    """
    thick = WALL_T_CM
    half = float(radius_cm)
    # Sink the flat framed insert a quarter-wall into the curved shell. A pure
    # tangent box only touches the cylinder along its centreline and visibly
    # floats at both chord ends in Blender.
    radial = half - thick * 0.75
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
    floor_plan: FloorPlan,
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
    max_glazed_storeys: Optional[int] = None,
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
    # Crown / above-hall storeys stay solid arcs — glazing there pokes through
    # abutting hall/curtain roofs after compound merge (roof_penetration).
    glazed_storeys = (
        max(1, vol.storeys - 1)
        if max_glazed_storeys is None
        else max(1, int(max_glazed_storeys))
    )
    radius_cm = _tower_radius_cm(vol)
    radius_scale = radius_cm / MODULE_CM
    storey_cm = _style_storey_cm(style)
    for level in range(vol.storeys):
        datum_delta = _level_datum_delta_cm(floor_plan, level, style)
        window_yaws = {
            yaw
            for _, yaw in _tower_window_slots(
                level=level, helical=helical, skip_yaw=skip_yaw
            )
        }
        if level >= glazed_storeys:
            window_yaws = set()
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
                    offset_cm=(drum_xy[0], drum_xy[1], datum_delta),
                    size_cm=(
                        piece.size_cm[0] * radius_scale,
                        piece.size_cm[1] * radius_scale,
                        storey_cm,
                    ),
                    rotates_about_center=True,
                    tags=piece.tags,
                )
            )

        if level >= glazed_storeys:
            continue
        for qi, yaw in _tower_window_slots(
            level=level, helical=helical, skip_yaw=skip_yaw
        ):
            if helical:
                step_rise = storey_cm / 4.0
                z_off = datum_delta + float(qi * step_rise)
                height = min(
                    drum_window_height_cm(helical=True)
                    * storey_cm
                    / STOREY_CM,
                    step_rise * 0.95,
                )
                chord = _TOWER_WIN_CHORD_CM
            else:
                # z=0 keeps wall_window aperture sill (~98 cm) inside [80, 120].
                z_off = datum_delta
                height = (
                    drum_window_height_cm(helical=False)
                    * storey_cm
                    / STOREY_CM
                )
                chord = _TOWER_WIN_CHORD_CM
            size, offset = _tower_window_shell_pose(
                drum_xy,
                yaw,
                z_off=z_off,
                height_cm=height,
                chord_cm=chord,
                skip_yaw=skip_yaw,
                radius_cm=radius_cm,
            )
            wpid = _next_piece_id(counters, f"tower_win_{yaw}", cell, level)
            # Logical egress proxy.  The curved ``tower_arc_quarter_window``
            # owns the visible masonry opening; rendering this second flat wall
            # leaf produces the floating rectangular blocks seen outside every
            # drum.  Validation still consumes the proxy's aperture contract.
            tags = wall_win.tags | frozenset(
                {"tower", "drum_window", "non_rendering_aperture_proxy"}
            )
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
            floor_z = _fp_datum_z(floor_plan, style, level)
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


def _place_square_tower_shell(
    *,
    floor_plan: FloorPlan,
    vol: Volume,
    cell: Tuple[int, int],
    drum_xy: Tuple[float, float],
    skip_yaw: Optional[int],
    catalog: _PieceCatalog,
    style: StyleLike,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    counters: Dict[str, int],
    max_glazed_storeys: Optional[int] = None,
) -> None:
    """Emit a scalable four-sided tower from real wall/door/window modules.

    The logical plan anchor remains one cell, while the physical half-width is
    ``tower_radius_bays * MODULE``. Each facade is divided into an odd number of
    pieces so it always has a centred door/window bay at any continuous size.
    """
    radius = _tower_radius_cm(vol)
    span = 2.0 * radius
    segment_count = max(1, int(math.ceil(span / MODULE_CM)))
    if segment_count % 2 == 0:
        segment_count += 1
    segment = span / segment_count
    centre_index = segment_count // 2
    plain = catalog.get("wall_plain")
    window = catalog.get(_style_window_asset(style))
    if not (
        "window" in window.asset_id
        or "arrowslit" in window.asset_id
        or "arcade" in window.asset_id
    ):
        window = catalog.get("wall_window")
    glazed_storeys = (
        max(1, vol.storeys - 1)
        if max_glazed_storeys is None
        else max(1, int(max_glazed_storeys))
    )
    radial = radius - WALL_T_CM * 0.5
    storey_cm = _style_storey_cm(style)

    for level in range(vol.storeys):
        datum_delta = _level_datum_delta_cm(floor_plan, level, style)
        for yaw in _TOWER_QUARTER_YAWS:
            if yaw == skip_yaw:
                doorway_chord = min(span - 2.0 * WALL_T_CM, MODULE_CM * 0.88)
                side_width = max(WALL_T_CM, (span - doorway_chord) * 0.5)
                face_segments = (
                    (0, -radius + side_width * 0.5, side_width),
                    (1, radius - side_width * 0.5, side_width),
                )
            else:
                face_segments = tuple(
                    (
                        index,
                        -radius + segment * (index + 0.5),
                        segment,
                    )
                    for index in range(segment_count)
                )
            for index, tangent, current_segment in face_segments:
                # The actual doorway module is emitted by tower_entry.py.
                use_window = (
                    index == centre_index
                    and yaw != skip_yaw
                    and level < glazed_storeys
                )
                piece = window if use_window else plain
                if yaw == 0:
                    dx, dy = -radial, tangent
                    size = (WALL_T_CM, current_segment, storey_cm)
                elif yaw == 180:
                    dx, dy = radial, tangent
                    size = (WALL_T_CM, current_segment, storey_cm)
                elif yaw == 90:
                    dx, dy = tangent, radial
                    size = (current_segment, WALL_T_CM, storey_cm)
                else:
                    dx, dy = tangent, -radial
                    size = (current_segment, WALL_T_CM, storey_cm)
                pid = _next_piece_id(
                    counters,
                    f"square_tower_{'win' if use_window else 'wall'}_{yaw}_{index}",
                    cell,
                    level,
                )
                tags = frozenset(piece.tags) | frozenset(
                    {"tower", "square_tower", "tower_shell", f"face_{yaw}"}
                )
                if use_window:
                    tags |= frozenset({"drum_window"})
                placed = SolidPlacement(
                    piece_id=pid,
                    asset_id=piece.asset_id,
                    kind="wall",
                    cell=cell,
                    level=level,
                    yaw=yaw,
                    offset_cm=(
                        drum_xy[0] + dx,
                        drum_xy[1] + dy,
                        datum_delta,
                    ),
                    size_cm=size,
                    rotates_about_center=True,
                    tags=tags,
                )
                placements.append(placed)
                if use_window:
                    world = _aperture_world(placed, "window")
                    apertures.append(
                        Aperture(
                            piece_id=f"win_{pid}",
                            kind="window",
                            wall_piece_id=pid,
                            level=level,
                            sill_z_cm=world[2],
                            floor_z_cm=_fp_datum_z(
                                floor_plan, style, level
                            ),
                            interior_cell=cell,
                            exterior_cell=_tower_exterior_cell(cell, yaw),
                            world_xyz=world,
                        )
                    )


def _tower_cell_xy_world(cell: Tuple[int, int]) -> Tuple[float, float, float, float]:
    """Inclusive world XY bounds of a tower drum cell (min_x, min_y, max_x, max_y)."""
    wx, wy, _ = cell_to_world_cm(cell[0], cell[1], 0)
    return (wx, wy, wx + MODULE_CM, wy + MODULE_CM)


def _hall_roof_top_over_tower_cm(
    cell: Tuple[int, int],
    placements: Sequence[SolidPlacement],
) -> Optional[float]:
    """Max world-Z top of hall roof AABBs that overlap the tower drum cell in XY.

    Pitched/hip decks are tall wedge AABBs; eaves overhang and gable ends often
    bleed into the attach tower cell even when that cell is excluded from the
    roof footprint. Returns ``None`` when no overlapping roof is present.
    """
    tx0, ty0, tx1, ty1 = _tower_cell_xy_world(cell)
    # Eave/gable overhang may sit just outside the cell — still graze the crown.
    pad = WALL_T_CM + TOL_CM
    top: Optional[float] = None
    for p in placements:
        if p.kind != "roof":
            continue
        mn, mx = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        if mx[0] <= tx0 - pad or mn[0] >= tx1 + pad:
            continue
        if mx[1] <= ty0 - pad or mn[1] >= ty1 + pad:
            continue
        top = mx[2] if top is None else max(top, mx[2])
    return top


def _tower_rampart_junction_z_cm(
    *,
    floor_plan: FloorPlan,
    style: StyleLike,
    cell: Tuple[int, int],
    top_level: int,
    placements: Sequence[SolidPlacement],
) -> float:
    """Level-local Z for ``tower_junction`` / rampart deck top.

    Default is one storey above the crown level plate. When an adjacent hall roof
    prism overlaps the drum in XY, raise the junction so the walkable deck bottom
    clears that roof AABB (no interpenetration demotion for deck/crenels).
    """
    base = _style_storey_cm(style)
    roof_top = _hall_roof_top_over_tower_cm(cell, placements)
    if roof_top is None:
        return base
    level_base = _fp_datum_z(floor_plan, style, top_level)
    # Deck bottom = level_base + junction_z - FLOOR_T; clear roof top by TOL.
    needed = roof_top - level_base + FLOOR_T_CM + TOL_CM
    return max(base, needed)


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
    square_cap = catalog.get("tower_cap_square")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    for vol in floor_plan.massing.volumes:
        if vol.role != "tower":
            continue
        cell = (vol.x0, vol.y0)
        drum_xy = _tower_drum_xy_offset_cm(vol, bodies)
        skip_yaw = _tower_attach_skip_yaw(vol, bodies)
        helical = _tower_has_spiral_stair(floor_plan, cell, placements)
        body = _tower_attached_body(vol, bodies)
        # Every occupied tower storey needs daylight/egress.  The attachment
        # face remains blank and the host roof is notched at the junction, so
        # suppressing all windows above the host body merely creates blind
        # upper rooms in tall spires and lighthouses.
        max_glaze = vol.storeys
        tower_shape = str(getattr(vol, "tower_shape", "round") or "round").lower()
        if tower_shape == "square":
            _place_square_tower_shell(
                floor_plan=floor_plan,
                vol=vol,
                cell=cell,
                drum_xy=drum_xy,
                skip_yaw=skip_yaw,
                catalog=catalog,
                style=style,
                placements=placements,
                apertures=apertures,
                counters=counters,
                max_glazed_storeys=max_glaze,
            )
        else:
            _place_tower_windows(
                floor_plan=floor_plan,
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
                max_glazed_storeys=max_glaze,
            )
        # @VAL_TOWER_DOOR — hall↔drum doorway on attach face (owned module).
        from pae.tower_entry import place_tower_entry_doors

        # Tower-to-building passages use the wider monumental arch. A compact
        # door profile leaves too little shoulder clearance beside a helix.
        door_piece = catalog.get("wall_gate_arch")
        aperture = getattr(door_piece, "aperture", None)
        door_chord = MODULE_CM * 0.88
        if aperture is not None:
            door_chord = max(
                1.0, float(aperture.max_cm[1] - aperture.min_cm[1])
            )
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
            floor_plan=floor_plan,
            radius_cm=_tower_radius_cm(vol),
            chord_cm=door_chord,
            storey_height_cm=_style_storey_cm(style),
            datum_z_cm=lambda level, _fp=floor_plan, _style=style: _fp_datum_z(
                _fp, _style, level
            ),
        )
        # A doorway-bearing flat chord replaces the curved drum quarter on that
        # face. Keeping both produces a visually valid door frame backed by an
        # impassable cylindrical wall—the exact blocked doorway seen in the
        # Blender cutaway.
        entry_doors = [
            p
            for p in placements
            if p.cell == cell
            and p.kind == "wall"
            and "tower_entry" in p.tags
        ]
        if entry_doors and tower_shape == "round":
            entry_levels = {p.level for p in entry_doors}
            placements[:] = [
                p
                for p in placements
                if not (
                    p.cell == cell
                    and p.level in entry_levels
                    and (
                        p.kind == "tower_arc"
                        or "drum_window" in p.tags
                    )
                )
            ]
            ring = catalog.get("tower_drum_door_ring")
            radius = _tower_radius_cm(vol)
            for entry in entry_doors:
                pid = _next_piece_id(
                    counters, "tower_drum_door_cut", cell, entry.level
                )
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=ring.asset_id,
                        kind="tower_arc",
                        cell=cell,
                        level=entry.level,
                        # Prototype opening faces west. Reverse Y-axis face
                        # rotation so the cut follows tower-entry yaw semantics.
                        yaw=(-int(entry.yaw)) % 360,
                        offset_cm=(
                            drum_xy[0],
                            drum_xy[1],
                            _level_datum_delta_cm(
                                floor_plan, entry.level, style
                            ),
                        ),
                        size_cm=(
                            2.0 * radius,
                            2.0 * radius,
                            _style_storey_cm(style),
                        ),
                        rotates_about_center=True,
                        tags=frozenset(ring.tags)
                        | frozenset(
                            {
                                "tower_door_cut_ring",
                                f"door_face_yaw:{int(entry.yaw) % 360}",
                            }
                        ),
                    )
                )
        top = vol.storeys - 1
        top_datum_delta = _level_datum_delta_cm(
            floor_plan, top, style
        )
        # Raise crown/deck/crenels above overlapping hall roof AABB (m3 pitched).
        junction_z = _tower_rampart_junction_z_cm(
            floor_plan=floor_plan,
            style=style,
            cell=cell,
            top_level=top,
            placements=placements,
        )
        crown_z = junction_z + junction.size_cm[2] + _TOWER_STACK_GAP_CM
        cap_z = crown_z + crown.size_cm[2] + _TOWER_STACK_GAP_CM
        # Drum walls must continue through the hall roof to the rampart wall-head
        # so raised crenels keep vertical_support (not floating battlements).
        storey_cm = _style_storey_cm(style)
        if crown_z > storey_cm + TOL_CM:
            for p in placements:
                if p.cell == cell and p.level == top and p.kind == "tower_arc":
                    sx, sy, sz = p.size_cm
                    if sz + TOL_CM < crown_z:
                        p.size_cm = (sx, sy, crown_z)
        radius_scale = _tower_radius_cm(vol) / MODULE_CM
        cap_style = str(
            getattr(vol, "tower_cap_style", "auto") or "auto"
        ).lower()
        if cap_style == "auto":
            cap_style = "square_spire" if tower_shape == "square" else "cone"
        cap_piece = square_cap if cap_style == "square_spire" else cap
        requested_spire = getattr(vol, "tower_spire_height_storeys", None)
        # Any conical/pyramidal cap closes the top. Treating an automatic round
        # cone as an open rampart produced a contradictory crown: battlements,
        # no deck, and a roof occupying the same platform.
        closed_spire = cap_style in ("cone", "square_spire")
        stack = []
        if tower_shape == "round":
            stack.extend(
                (
                    (junction, "tower_crown", junction_z),
                    (crown, "tower_crown", crown_z),
                )
            )
        if cap_style != "flat":
            stack.append(
                (
                    cap_piece,
                    "tower_cap",
                    cap_z if tower_shape == "round" else storey_cm,
                )
            )
        for piece, kind, z_off in stack:
            piece_height = piece.size_cm[2]
            if kind == "tower_cap" and requested_spire is not None:
                piece_height = float(requested_spire) * storey_cm
            pid = _next_piece_id(counters, piece.asset_id, cell, top)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id=piece.asset_id,
                    kind=kind,
                    cell=cell,
                    level=top,
                    yaw=0,
                    offset_cm=(
                        drum_xy[0],
                        drum_xy[1],
                        top_datum_delta + z_off,
                    ),
                    size_cm=(
                        piece.size_cm[0] * radius_scale,
                        piece.size_cm[1] * radius_scale,
                        piece_height,
                    ),
                    rotates_about_center=True,
                    tags=(
                        frozenset(piece.tags) | frozenset({"closed_spire"})
                        if kind == "tower_cap" and closed_spire
                        else piece.tags
                    ),
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

        if tower_shape == "round" and not closed_spire:
            place_tower_rampart_crown(
                cell=cell,
                level=top,
                drum_xy=drum_xy,
                # tower_rampart still consumes offsets relative to the legacy
                # grid datum, so include the host-style datum correction.
                junction_z=top_datum_delta + junction_z,
                crown_z=top_datum_delta + crown_z,
                skip_yaw=skip_yaw,
                floor_piece=floor_piece,
                wall_window_asset_id=wall_win.asset_id,
                wall_window_tags=wall_win.tags,
                next_piece_id=_rampart_pid,
                placements=placements,
                apertures=apertures,
                radius_cm=_tower_radius_cm(vol),
            )


def _ensure_spiral_drum_enclosure(
    *,
    floor_plan: FloorPlan,
    catalog: _PieceCatalog,
    style: StyleLike,
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
    from pae.spiral_shell import DESIGNED_DOOR_BAY_TAGS, ensure_spiral_drum_quarters

    solid = catalog.get("tower_arc_quarter")
    bodies = [v for v in floor_plan.massing.volumes if v.role in WING_ROLES]
    spiral_cells = {
        p.cell
        for p in placements
        if p.asset_id == "stair_spiral_quarter"
    } | _spiral_tower_drum_cells(floor_plan)
    for cell in sorted(spiral_cells):
        levels = {
            p.level
            for p in placements
            if p.asset_id == "stair_spiral_quarter" and p.cell == cell
        }
        if not levels:
            continue
        xy_offset = (0.0, 0.0)
        radius_scale = 1.0
        for vol in floor_plan.massing.volumes:
            if vol.role == "tower" and (vol.x0, vol.y0) == cell:
                xy_offset = _tower_drum_xy_offset_cm(vol, bodies)
                radius_scale = _tower_radius_cm(vol) / MODULE_CM
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
            solid_arc_size_cm=(
                solid.size_cm[0] * radius_scale,
                solid.size_cm[1] * radius_scale,
                _style_storey_cm(style),
            ),
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
    # Gate/grand leaves that span N storeys — upper levels skip these (face, cell).
    spanning_wall_keys: Set[Tuple[str, Tuple[int, int]]] = set()

    for grid in floor_plan.storeys:
        level = grid.level
        floor_layers[level] = _layer_from_grid(grid)
        x0, y0, x1, y1 = _envelope_bbox(floor_plan, grid)

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
                spanning_keys=spanning_wall_keys,
            )
            run_piece_ids[face] = [p.piece_id for p in placements[before:]]

        _place_inhabited_inner_walls(
            grid=grid,
            bbox=(x0, y0, x1, y1),
            level=level,
            catalog=catalog,
            placements=placements,
            counters=counters,
            tower_cells=tower_cells,
            floor_plan=floor_plan,
            style=style,
        )

        floor_piece = catalog.get("floor")
        floor_z_off = -FLOOR_T_CM + _level_datum_delta_cm(floor_plan, level, style)
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
            # Use real floor-role cells only — bbox fill around outboard turrets
            # invented empty bays that spanned under neighbour compound roofs
            # (gatehouse L2 × cloister hip headroom).
            # ``STAIR`` on an upper storey means a flight STANDS on this deck, so
            # the deck must be solid there. Only the deck ABOVE a flight is opened,
            # and the plan already marks that cell ``VOID``. Treating every STAIR
            # cell as a hole left each flight above the ground floor hanging over
            # its own stairwell.
            #
            # The exception is a continuous shaft — a spiral climbs the SAME cell on
            # every storey, so there is no landing to stand on and the deck must
            # stay open. The plan shows that as STAIR on two consecutive levels.
            shaft_cells = _continuous_shaft_cells(floor_plan, level)
            spiral_drum_cells = {
                (v.x0, v.y0)
                for v in (
                    floor_plan.massing.volumes
                    if floor_plan.massing is not None
                    else ()
                )
                if v.role == "tower"
                and str(getattr(v, "stair_kind", "") or "").lower() == "spiral"
                and abs(float(getattr(v, "tower_radius_bays", 1.0)) - 1.0)
                <= 1e-6
            }
            void_cells = {
                (cx, cy)
                for (cx, cy), role in grid.cells.items()
                if role in (CellRole.VOID, CellRole.DOUBLE_VOID)
            }
            opening_cells = (
                _deck_opening_cells(floor_plan, level)
                | spiral_drum_cells
                | shaft_cells
            )
            # Reserved-well VOID pads that no flight uses are landings — walkable
            # floor, not a hole beside the stairs (3+ storey monumental wells).
            landing_void = (void_cells - opening_cells) & set(floor_plan.stair_cells)
            deck_cells = [
                (cx, cy)
                for (cx, cy), role in grid.cells.items()
                if role in _FLOOR_ROLES
                and (cx, cy) not in tower_cells
                and (cx, cy) not in shaft_cells
            ] + list(landing_void)
            # Never turn a non-rectangular plan into one bounding-box slab.
            # That covered courtyards, double-height gate lanes, and stair voids
            # with walkable geometry even though their logical cells were VOID.
            # Rectangle-cover the actual floor-role cells instead; each emitted
            # deck is therefore wholly supported by the plan it represents.
            for dx0, dy0, modules_x, modules_y in _rect_cover(set(deck_cells)):
                pid = _next_piece_id(counters, "floor_deck", (dx0, dy0), level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=floor_piece.asset_id,
                        kind="floor",
                        cell=(dx0, dy0),
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
            # Punch stairwell openings: flight below rises through this deck only.
            # Habitable keep drums (TowerSpec.stair_kind=spiral): exclude the drum
            # from the hall spanning slab so the helix is not a ceiling plug.
            # Scaled towers move their physical centre away from the one-cell
            # plan anchor and receive measured holes after spiral placement.
            hole_cells = (void_cells & opening_cells) | spiral_drum_cells | shaft_cells
            # Merge into RECTANGLES. One hole per cell gave a 2x1 stairwell two separate
            # square openings instead of the single 2x1 well the run needs — the deck
            # read as two punched squares with a rib of floor left between them.
            hole = catalog.get("floor_hole")
            for (hx, hy, hw, hh) in _rect_cover(hole_cells):
                pid = _next_piece_id(counters, "floor_hole", (hx, hy), level)
                placements.append(
                    SolidPlacement(
                        piece_id=pid,
                        asset_id=hole.asset_id,
                        kind="floor",
                        cell=(hx, hy),
                        level=level,
                        yaw=0,
                        offset_cm=(0.0, 0.0, floor_z_off),
                        size_cm=(
                            hw * MODULE_CM,
                            hh * MODULE_CM,
                            hole.size_cm[2],
                        ),
                        tags=hole.tags,
                    )
                )

        if level == storeys - 1:
            # Stage C: one structure roof from the column height field (all eaves
            # bands). Called once on the top storey iteration — bands may still
            # emit plates on lower top_level indices when the building steps.
            _place_structure_roofs(
                floor_plan=floor_plan,
                catalog=catalog,
                tower_cells=tower_cells,
                placements=placements,
                counters=counters,
                style=style,
            )

    _place_attached_tower_roof_notches(
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
    _place_double_height_hall_arch_ribs(
        floor_plan=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )
    _place_gate_passage_side_walls(
        floor_plan=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    _place_stairs(
        fp=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        counters=counters,
        failures=failures,
    )

    # Per-tower drum helixes (keep/gatehouse) — before arcs so windows go helical
    # and before hole punch so wells cover the full spiral footprint (Rule 5.1).
    _place_habitable_tower_spirals(
        floor_plan=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        counters=counters,
    )

    _place_habitable_tower_rooms(
        floor_plan=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        counters=counters,
    )
    _place_tower_spiral_exit_holes(
        floor_plan=floor_plan,
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
    _place_tower_entry_landings(
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    # Spiral shell: guarantee continuous tower_arc drum around helical climbs.
    # Door bay gaps are exempted by tag (@VAL_TOWER_DOOR); ramparts @VAL_TOWER_RAMPART.
    _ensure_spiral_drum_enclosure(
        floor_plan=floor_plan,
        catalog=catalog,
        style=style,
        placements=placements,
        counters=counters,
    )

    # Punch after tower decks/spirals so crown arrival wells are covered too.
    _punch_stair_exit_holes(
        fp=floor_plan,
        catalog=catalog,
        placements=placements,
        counters=counters,
    )

    # Reserved stair wells are wider than one flight: keep openings on the flights,
    # floor the leftover landing cells (no orphan hole beside the stairs).
    _reconcile_stair_well_holes(
        fp=floor_plan,
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
        x0, y0, x1, y1 = _envelope_bbox(floor_plan, grid)
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
        entrance_specs=[
            {
                "role": e.role,
                "facade": e.facade,
                "bay": e.bay,
                "storey": e.storey,
            }
            for e in (
                floor_plan.massing.entrances
                if floor_plan.massing is not None
                else ()
            )
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
        interior_arch_rib_every_bays=(
            getattr(
                floor_plan.massing,
                "interior_arch_rib_every_bays",
                None,
            )
            if floor_plan.massing is not None
            else None
        ),
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
    # Autofix stair landing solid-wall blockers (CRITICAL stair_landing_clear).
    from pae.stair_occupancy import repair_stair_landing_walls

    assembly = repair_stair_landing_walls(assembly)

    # Stage A: stamp structure:<id> on every piece. freestanding already partitions
    # on structure: when declared (Handbook §11d) — same change as tagging.
    sid = getattr(floor_plan, "structure_id", None)
    if not sid and floor_plan.massing is not None:
        sid = getattr(floor_plan.massing, "structure_id", None)
    if sid:
        from pae.structure_identity import apply_structure_tags

        assembly = apply_structure_tags(assembly, str(sid))

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

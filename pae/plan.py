"""Floor plan (§5.2–5.3) — WP-4.

Massing → FloorPlan (CellRole grid per storey) + circulation graph proof.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.contract import cell_to_world_cm
from pae.report import Failure, Report
from pae.solver import Massing, Volume
from pae.spec import EntranceSpec


class CellRole(Enum):
    EXTERIOR = 0
    INTERIOR = 1
    WALL_LINE = 2
    DOOR = 3
    STAIR = 4
    VOID = 5  # stairwell / light well — no floor
    COURTYARD = 6  # open to sky, has ground, no roof
    CORRIDOR = 7  # school / program circulation spine
    CLASSROOM = 8  # programmed room cell (door to corridor)
    DOUBLE_VOID = 9  # double-height volume — no intermediate floor slab
    ROOM = 10  # generic named program room from StructureSpec
    HALL = 11  # Stage G — open hall / great hall (no inner partitions)
    SERVICE = 12  # Stage G — service / kitchen / store
    ARCADE = 13  # Stage G — walkable courtyard arcade gallery (a room)


@dataclass
class StoreyGrid:
    level: int
    # Sparse map; missing cells are EXTERIOR.
    cells: Dict[Tuple[int, int], CellRole] = field(default_factory=dict)
    origin: Tuple[int, int] = (0, 0)  # min cell
    size: Tuple[int, int] = (0, 0)  # width, height in cells

    def get(self, x: int, y: int) -> CellRole:
        return self.cells.get((x, y), CellRole.EXTERIOR)

    def set(self, x: int, y: int, role: CellRole) -> None:
        self.cells[(x, y)] = role


@dataclass
class CirculationGraph:
    """Nodes = (storey, region_id); edges = stair runs."""

    nodes: Set[Tuple[int, int]] = field(default_factory=set)
    edges: List[Tuple[Tuple[int, int], Tuple[int, int]]] = field(default_factory=list)

    def add_node(self, storey: int, region: int) -> None:
        self.nodes.add((storey, region))

    def add_edge(
        self, a: Tuple[int, int], b: Tuple[int, int]
    ) -> None:
        self.edges.append((a, b))
        self.edges.append((b, a))

    def connected_from(self, start: Tuple[int, int]) -> Set[Tuple[int, int]]:
        adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)
        for u, v in self.edges:
            adj[u].append(v)
        seen: Set[Tuple[int, int]] = set()
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in adj[cur]:
                if nxt not in seen:
                    q.append(nxt)
        return seen


@dataclass
class FloorPlan:
    storeys: List[StoreyGrid]
    circulation: CirculationGraph
    entrance_cell: Tuple[int, int]
    door_cells: List[Tuple[int, int]] = field(default_factory=list)
    window_cells: List[Tuple[int, int]] = field(default_factory=list)
    entrance_by_cell: Dict[Tuple[int, int], str] = field(default_factory=dict)
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)
    ground_slab: bool = True
    name: str = "building"
    style: str = "townhouse"
    seed: int = 0
    roof_kind: str = "flat"
    roof_pitch: float = 1.0
    massing: Optional[Massing] = None
    classroom_cells: List[Tuple[int, int, int]] = field(default_factory=list)
    corridor_cells: List[Tuple[int, int, int]] = field(default_factory=list)
    # (cell_x, cell_y, level, face toward corridor, is_door)
    interior_partitions: List[Tuple[int, int, int, str, bool]] = field(
        default_factory=list
    )
    rooms: List = field(default_factory=list)  # RoomSpec from spec (optional)
    # (cell_x, cell_y, level, program name)
    program_cells: List[Tuple[int, int, int, str]] = field(default_factory=list)
    #: Envelope / monumental wall span (storeys). None → len(storeys).
    wall_height_storeys: Optional[float] = None
    # --- Master Plan Stage A/B ---
    structure_id: Optional[str] = None
    foundation_cells: Tuple[Tuple[int, int], ...] = ()
    level_height_units: Optional[Tuple[int, ...]] = None
    level_wall_styles: Optional[Tuple[Optional[str], ...]] = None
    level_window_tags: Optional[Tuple[Optional[str], ...]] = None
    level_programs: Optional[
        Tuple[Dict[str, Tuple[Tuple[int, int, int, int], ...]], ...]
    ] = None


def _bbox(volumes: List[Volume]) -> Tuple[int, int, int, int]:
    xs0 = [v.x0 for v in volumes]
    ys0 = [v.y0 for v in volumes]
    xs1 = [v.x1 for v in volumes]
    ys1 = [v.y1 for v in volumes]
    return min(xs0), min(ys0), max(xs1), max(ys1)


def _enclosed_cells_at_level(massing: Massing, level: int) -> Set[Tuple[int, int]]:
    """Built cells for one level.

    When ``massing.level_cells`` is set (StructureSpec / Stage B), honour the
    per-level mask so an upper level may omit a wing. Otherwise fall back to
    volume.storeys coverage (legacy BuildingSpec path).
    """
    level_cells = getattr(massing, "level_cells", None)
    if level_cells is not None and 0 <= level < len(level_cells):
        return set(level_cells[level])
    cells: Set[Tuple[int, int]] = set()
    for v in massing.enclosed_volumes():
        if level < v.storeys:
            cells |= v.cells()
    return cells


def _void_cells_at_level(massing: Massing, level: int) -> Set[Tuple[int, int]]:
    """Open-to-below / void marks for a level (``.`` in Stage B sketches)."""
    voids = getattr(massing, "level_void_cells", None)
    if voids is None or level < 0 or level >= len(voids):
        return set()
    return set(voids[level])


def _courtyard_cells(massing: Massing) -> Set[Tuple[int, int]]:
    cells: Set[Tuple[int, int]] = set()
    for v in massing.volumes:
        if v.role == "courtyard":
            cells |= v.cells()
    return cells


def _is_wall_line(x: int, y: int, interior: Set[Tuple[int, int]]) -> bool:
    if (x, y) not in interior:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if (x + dx, y + dy) not in interior:
            return True
    return False


def _regions(
    interior: Set[Tuple[int, int]], blocked: Set[Tuple[int, int]]
) -> Dict[Tuple[int, int], int]:
    """4-connected region ids over walkable interior cells (not VOID)."""
    walkable = interior - blocked
    region_of: Dict[Tuple[int, int], int] = {}
    rid = 0
    for start in sorted(walkable):
        if start in region_of:
            continue
        q = deque([start])
        region_of[start] = rid
        while q:
            cx, cy = q.popleft()
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                n = (cx + dx, cy + dy)
                if n in walkable and n not in region_of:
                    region_of[n] = rid
                    q.append(n)
        rid += 1
    return region_of


def _pick_region_for_cells(
    rmap: Dict[Tuple[int, int], int],
    cells: Sequence[Tuple[int, int]],
    *,
    neighbor_expand: bool = False,
) -> Optional[int]:
    """First walkable region id covering any of *cells* (optional 4-neighbour expand)."""
    for x, y in cells:
        r = rmap.get((x, y))
        if r is not None:
            return r
    if not neighbor_expand:
        return None
    for x, y in cells:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r = rmap.get((x + dx, y + dy))
            if r is not None:
                return r
    return None


def _link_stair_void_regions(
    storeys: List[StoreyGrid],
    region_maps: Dict[int, Dict[Tuple[int, int], int]],
    graph: CirculationGraph,
) -> None:
    """Intra-storey edges where a stair VOID well touches multiple regions (Stage D).

    Offset monumental flights leave VOID on upper storeys; regions on either side of
    the well (e.g. L/U wings on the top floor) must bridge through the opening.
    """
    for grid in storeys:
        level = grid.level
        rmap = region_maps.get(level, {})
        voids = {c for c, role in grid.cells.items() if role == CellRole.VOID}
        if not voids:
            continue
        seen: Set[Tuple[int, int]] = set()
        for start in sorted(voids):
            if start in seen:
                continue
            cluster: Set[Tuple[int, int]] = set()
            q = deque([start])
            while q:
                cx, cy = q.popleft()
                if (cx, cy) in seen or grid.get(cx, cy) != CellRole.VOID:
                    continue
                seen.add((cx, cy))
                cluster.add((cx, cy))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    n = (cx + dx, cy + dy)
                    if n in voids and n not in seen:
                        q.append(n)
            touch_regs: Set[int] = set()
            for x, y in cluster:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    r = rmap.get((x + dx, y + dy))
                    if r is not None:
                        touch_regs.add(r)
            for ra in touch_regs:
                for rb in touch_regs:
                    if ra != rb:
                        graph.add_node(level, ra)
                        graph.add_node(level, rb)
                        graph.add_edge((level, ra), (level, rb))


def _wall_cells_on_facade(
    wall_cells: List[Tuple[int, int]],
    interior: Set[Tuple[int, int]],
    facade: str,
) -> List[Tuple[int, int]]:
    """Sorted wall-line cells on one exterior face."""
    facade = facade.lower()
    if facade == "south":
        out = [(x, y) for x, y in wall_cells if (x, y - 1) not in interior]
    elif facade == "north":
        out = [(x, y) for x, y in wall_cells if (x, y + 1) not in interior]
    elif facade == "west":
        out = [(x, y) for x, y in wall_cells if (x - 1, y) not in interior]
    elif facade == "east":
        out = [(x, y) for x, y in wall_cells if (x + 1, y) not in interior]
    else:
        raise ValueError(f"unknown facade {facade!r}")
    return sorted(out)


def _resolve_entrance_bay(
    cells: List[Tuple[int, int]],
    *,
    bay: Optional[int],
    role: str,
) -> Optional[Tuple[int, int]]:
    if not cells:
        return None
    if bay is not None:
        idx = max(0, min(bay, len(cells) - 1))
        return cells[idx]
    if role in ("grand", "gate"):
        return cells[len(cells) // 2]
    return cells[0]


def _place_entrance_doors(
    grid: StoreyGrid,
    interior: Set[Tuple[int, int]],
    entrances: List[EntranceSpec],
) -> Tuple[List[Tuple[int, int]], Dict[Tuple[int, int], str]]:
    """Place ground doors from declarative entrance specs (§1.1–1.2)."""
    doors: List[Tuple[int, int]] = []
    entrance_by_cell: Dict[Tuple[int, int], str] = {}
    wall_cells = [
        (x, y)
        for (x, y), role in grid.cells.items()
        if role == CellRole.WALL_LINE
    ]
    used: Set[Tuple[int, int]] = set()
    for spec in entrances:
        facade = spec.facade or "south"
        candidates = _wall_cells_on_facade(wall_cells, interior, facade)
        candidates = [c for c in candidates if c not in used]
        cell = _resolve_entrance_bay(candidates, bay=spec.bay, role=spec.role)
        if cell is None:
            continue
        grid.set(cell[0], cell[1], CellRole.DOOR)
        doors.append(cell)
        entrance_by_cell[cell] = spec.role
        used.add(cell)
    return doors, entrance_by_cell


def _place_doors_windows(
    grid: StoreyGrid,
    interior: Set[Tuple[int, int]],
    massing: Massing,
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]], Dict[Tuple[int, int], str]]:
    """Place ground-floor doors/windows on WALL_LINE cells (south face preferred)."""
    if massing.entrances:
        doors, entrance_by_cell = _place_entrance_doors(
            grid, interior, massing.entrances
        )
    else:
        doors = []
        entrance_by_cell = {}
        wall_cells = [
            (x, y)
            for (x, y), role in grid.cells.items()
            if role == CellRole.WALL_LINE
        ]
        # Prefer south-face wall cells (no interior neighbour to -Y).
        south = [
            (x, y)
            for x, y in wall_cells
            if (x, y - 1) not in interior
        ]
        south.sort()
        n_doors = max(0, massing.openings_doors_ground)
        for i in range(min(n_doors, len(south))):
            cell = south[i]
            grid.set(cell[0], cell[1], CellRole.DOOR)
            doors.append(cell)

    remaining_wall = [
        (x, y)
        for (x, y), role in grid.cells.items()
        if role == CellRole.WALL_LINE
    ]
    remaining_wall.sort()
    south = [
        (x, y)
        for x, y in remaining_wall
        if (x, y - 1) not in interior
    ]
    south.sort()
    n_doors = len(doors)
    windows: List[Tuple[int, int]] = []
    if massing.openings_skip_ground_windows:
        n_win = 0
    elif massing.openings_windows_ground is not None:
        n_win = massing.openings_windows_ground
    else:
        # Approximate: per_bay along longest exterior edge.
        n_win = max(0, massing.openings_windows_per_bay * max(1, len(south) - n_doors))
    placed = 0
    for cell in remaining_wall:
        if placed >= n_win:
            break
        # Skip door cells; mark as window by recording only (role stays WALL_LINE
        # — assembly selects window assets on wall runs). Track separately.
        windows.append(cell)
        placed += 1
    return doors, windows, entrance_by_cell


def _face_toward(
    from_cell: Tuple[int, int], to_cell: Tuple[int, int]
) -> Optional[str]:
    fx, fy = from_cell
    tx, ty = to_cell
    if tx == fx + 1 and ty == fy:
        return "east"
    if tx == fx - 1 and ty == fy:
        return "west"
    if ty == fy + 1 and tx == fx:
        return "north"
    if ty == fy - 1 and tx == fx:
        return "south"
    return None


_CARVE_STOREY_USES = frozenset({"classroom", "classrooms", "dormitory"})

# Room kind → solver volume role(s) for cell assignment (first match wins).
_KIND_TO_VOLUME_ROLES: Dict[str, Tuple[str, ...]] = {
    "hall": ("hall", "main"),
    "classroom": ("classroom_wing",),
    "chapel": ("admin",),
    "library": ("admin",),
    "dormitory": ("classroom_wing",),
    "kitchen": ("admin",),
    "store": ("admin",),
}

# Legacy default when RoomSpec only has ``double_height=True`` (no height_storeys).
_DOUBLE_HEIGHT_DEFAULT_STOREYS = 2


def _volume_cells_for_room(massing: Massing, kind: str) -> Set[Tuple[int, int]]:
    roles = _KIND_TO_VOLUME_ROLES.get(kind)
    if not roles:
        return set()
    for role in roles:
        cells: Set[Tuple[int, int]] = set()
        for vol in massing.volumes:
            if vol.role == role:
                cells |= vol.cells()
        if cells:
            return cells
    return set()


_DOUBLE_HEIGHT_CARVEABLE = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ROOM,
        CellRole.ARCADE,
    }
)


def _role_for_program_label(label: str) -> CellRole:
    """Map a StructureSpec / sketch program name to a CellRole (Stage G).

    ``hall`` is an open programmed room — *not* a corridor. Older code treated any
    label containing ``hall`` as circulation, which made great-hall regions into
    CORRIDOR spines and broke room partitions.

    Only the Stage G vocabulary (hall / classroom / service / corridor / arcade)
    gets dedicated roles; other authored names (living_room, kitchen, …) stay
    generic ``ROOM``.
    """
    lowered = str(label).lower().replace("-", "_").strip()
    parts = set(lowered.split("_"))
    if lowered in ("hallway", "corridor", "circulation", "gallery", "landing") or (
        "corridor" in parts
    ):
        return CellRole.CORRIDOR
    if "arcade" in parts or lowered == "arcade":
        return CellRole.ARCADE
    if "classroom" in parts or lowered in ("class", "classrooms"):
        return CellRole.CLASSROOM
    if lowered == "service" or parts == {"service"}:
        return CellRole.SERVICE
    if "hall" in parts or lowered in ("hall", "great_hall", "main_hall"):
        # ``hallway`` already returned CORRIDOR above.
        return CellRole.HALL
    return CellRole.ROOM


def _wall_line_adjacency(grid: StoreyGrid, x: int, y: int) -> int:
    """Count orthogonal WALL_LINE neighbours (gallery-ring heuristic)."""
    return sum(
        1
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if grid.get(x + dx, y + dy) == CellRole.WALL_LINE
    )


def _carve_double_void_cells(
    grid: StoreyGrid,
    cells: Set[Tuple[int, int]],
    *,
    keep_gallery_ring: bool,
) -> int:
    """Mark carveable cells DOUBLE_VOID. Returns how many cells changed."""
    carved = 0
    for x, y in cells:
        role = grid.get(x, y)
        if role not in _DOUBLE_HEIGHT_CARVEABLE:
            continue
        if keep_gallery_ring and _wall_line_adjacency(grid, x, y) > 0:
            continue
        grid.set(x, y, CellRole.DOUBLE_VOID)
        carved += 1
    return carved


def _carve_double_void_fallback(
    grid: StoreyGrid,
    cells: Set[Tuple[int, int]],
) -> int:
    """When the gallery ring ate every cell, force an open void (fail-closed).

    Prefers cells farthest from WALL_LINE so a walkable ring can remain when
    the volume is large enough; always carves at least one carveable cell.
    """
    candidates: List[Tuple[int, int, int]] = []
    for x, y in cells:
        role = grid.get(x, y)
        if role not in _DOUBLE_HEIGHT_CARVEABLE:
            continue
        candidates.append((_wall_line_adjacency(grid, x, y), x, y))
    if not candidates:
        return 0
    candidates.sort()  # least wall-adjacent first
    # Carve the least-adjacent half (at least one) so tiny halls still open.
    n = max(1, len(candidates) // 2)
    carved = 0
    for _, x, y in candidates[:n]:
        grid.set(x, y, CellRole.DOUBLE_VOID)
        carved += 1
    return carved


def _apply_double_height_rooms(
    storeys: List[StoreyGrid],
    massing: Massing,
) -> List[Failure]:
    """Suppress intermediate floors over double-height room cells (§2.4).

    Perimeter WALL_LINE cells are preserved so walls still enclose the volume.
    Interior cells on intermediate storeys become DOUBLE_VOID (no floor slab).
    A one-cell gallery ring along the room perimeter stays walkable so wings
    can still reach stairs across a double-height hall.

    Fail-closed: a declared ``double_height`` room that cannot open any
    DOUBLE_VOID cell (missing volume, or every interior cell blocked) yields a
    plan failure rather than a silent solid intermediate floor.
    """
    from pae.spec import room_height_storeys, room_is_multi_height

    failures: List[Failure] = []
    if not massing.rooms or massing.storeys < 2:
        return failures
    for room in massing.rooms:
        if not room_is_multi_height(room) and not room.double_height:
            continue
        cells = _volume_cells_for_room(massing, room.kind)
        if not cells:
            failures.append(
                Failure(
                    check="double_height_carve",
                    message=(
                        f"room {room.name!r} is double_height but no volume "
                        f"cells for kind {room.kind!r}"
                    ),
                    world_xyz=None,
                )
            )
            continue
        carved = 0
        try:
            span = int(math.ceil(room_height_storeys(room)))
        except ValueError:
            span = _DOUBLE_HEIGHT_DEFAULT_STOREYS
        # Open intermediate floors up to the declared height (not hard-capped at 2).
        levels = list(range(1, min(span, massing.storeys)))
        for level in levels:
            if level >= len(storeys):
                break
            carved += _carve_double_void_cells(
                storeys[level], cells, keep_gallery_ring=True
            )
        if carved == 0:
            for level in levels:
                if level >= len(storeys):
                    break
                carved += _carve_double_void_fallback(storeys[level], cells)
        if carved == 0:
            failures.append(
                Failure(
                    check="double_height_carve",
                    message=(
                        f"room {room.name!r} is double_height but plan carved "
                        "0 DOUBLE_VOID cells"
                    ),
                    world_xyz=None,
                )
            )
    return failures


def _carve_double_loaded_wings(
    storeys: List[StoreyGrid],
    massing: Massing,
) -> Tuple[
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int, str, bool]],
]:
    """Carve full-depth classrooms off a centerline corridor.

    The former implementation only marked the first cell beside the corridor,
    leaving the rest of each nominal classroom as an unpartitioned open hall.
    Here every interior cell on either side belongs to a classroom strip.  The
    strip is divided into rooms of at most three bays along the corridor, with a
    continuous corridor wall, one doorway per room, and cross-walls between
    adjoining rooms.
    """
    classroom_cells: List[Tuple[int, int, int]] = []
    corridor_cells: List[Tuple[int, int, int]] = []
    partitions: List[Tuple[int, int, int, str, bool]] = []
    wings = [v for v in massing.volumes if v.role == "classroom_wing"]
    if not wings:
        return classroom_cells, corridor_cells, partitions

    classroom_seen: Set[Tuple[int, int, int]] = set()
    corridor_seen: Set[Tuple[int, int, int]] = set()

    for level, grid in enumerate(storeys):
        use = (
            massing.storey_use[level]
            if level < len(massing.storey_use)
            else "hall"
        )
        if use not in _CARVE_STOREY_USES:
            continue
        for vol in wings:
            cells = [
                (x, y)
                for (x, y) in vol.cells()
                if grid.get(x, y) == CellRole.INTERIOR
            ]
            if len(cells) < 3:
                continue
            horizontal = (vol.x1 - vol.x0) >= (vol.y1 - vol.y0)
            if horizontal:
                cy = (vol.y0 + vol.y1) // 2
                corridor = {(x, y) for (x, y) in cells if y == cy}
                if len(corridor) < 2:
                    for dy in (1, -1, 2, -2):
                        corridor = {(x, y) for (x, y) in cells if y == cy + dy}
                        if len(corridor) >= 2:
                            break
            else:
                cx = (vol.x0 + vol.x1) // 2
                corridor = {(x, y) for (x, y) in cells if x == cx}
                if len(corridor) < 2:
                    for dx in (1, -1, 2, -2):
                        corridor = {(x, y) for (x, y) in cells if x == cx + dx}
                        if len(corridor) >= 2:
                            break
            if len(corridor) < 2:
                continue
            for c in sorted(corridor):
                grid.set(c[0], c[1], CellRole.CORRIDOR)
                key = (level, c[0], c[1])
                if key not in corridor_seen:
                    corridor_seen.add(key)
                    corridor_cells.append(key)
            rooms = sorted(c for c in cells if c not in corridor)
            for c in rooms:
                grid.set(c[0], c[1], CellRole.CLASSROOM)
                key = (level, c[0], c[1])
                if key not in classroom_seen:
                    classroom_seen.add(key)
                    classroom_cells.append(key)

            if horizontal:
                corridor_coord = next(iter(corridor))[1]
                side_sets = [
                    {c for c in rooms if c[1] < corridor_coord},
                    {c for c in rooms if c[1] > corridor_coord},
                ]
                along = lambda c: c[0]
                step = (1, 0)
            else:
                corridor_coord = next(iter(corridor))[0]
                side_sets = [
                    {c for c in rooms if c[0] < corridor_coord},
                    {c for c in rooms if c[0] > corridor_coord},
                ]
                along = lambda c: c[1]
                step = (0, 1)

            for side in side_sets:
                if not side:
                    continue
                boundary = sorted(
                    (
                        c
                        for c in side
                        if any(
                            n in corridor
                            for n in (
                                (c[0] + 1, c[1]),
                                (c[0] - 1, c[1]),
                                (c[0], c[1] + 1),
                                (c[0], c[1] - 1),
                            )
                        )
                    ),
                    key=lambda c: (along(c), c),
                )
                along_values = sorted({along(c) for c in boundary})
                chunks = [
                    along_values[i : i + 3]
                    for i in range(0, len(along_values), 3)
                ]
                for chunk_index, chunk in enumerate(chunks):
                    door_along = chunk[len(chunk) // 2]
                    door_placed = False
                    for c in (c for c in boundary if along(c) in chunk):
                        neighbor = next(
                            (
                                n
                                for n in (
                                    (c[0] + 1, c[1]),
                                    (c[0] - 1, c[1]),
                                    (c[0], c[1] + 1),
                                    (c[0], c[1] - 1),
                                )
                                if n in corridor
                            ),
                            None,
                        )
                        face = _face_toward(c, neighbor) if neighbor else None
                        if face is None:
                            continue
                        is_door = along(c) == door_along and not door_placed
                        door_placed = door_placed or is_door
                        partitions.append((c[0], c[1], level, face, is_door))

                    # A wall across the full room depth separates this chunk
                    # from the next one. The corridor wall above closes its
                    # inboard end; the exterior shell closes its outboard end.
                    if chunk_index + 1 >= len(chunks):
                        continue
                    cut_along = chunk[-1]
                    for c in sorted(side):
                        if along(c) != cut_along:
                            continue
                        neighbor = (c[0] + step[0], c[1] + step[1])
                        if neighbor not in side:
                            continue
                        face = _face_toward(c, neighbor)
                        if face is not None:
                            partitions.append(
                                (c[0], c[1], level, face, False)
                            )
    return classroom_cells, corridor_cells, partitions


_PROGRAM_PAINTABLE = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ARCADE,
    }
)

# Halls stay open: no partition against unlabelled INTERIOR (great hall spill).
# Partitions still fire between unlike *named* programs (hall↔classroom, etc.).
_HALL_OPEN_NEIGHBOURS = frozenset({CellRole.INTERIOR, CellRole.HALL})


def _carve_program_regions(
    storeys: List[StoreyGrid],
    massing: Massing,
) -> Tuple[
    List[Tuple[int, int, int, str]],
    List[Tuple[int, int, int, str, bool]],
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int]],
]:
    """Turn StructureSpec program rectangles into rooms and complete partitions.

    Every named rectangle labels walkable cells. Boundaries between unlike
    programs (or between a program and an unlabelled hall) receive a partition,
    with one deterministic doorway per adjoining program pair.

    Stage G roles: ``hall`` / ``classroom`` / ``service`` / ``corridor`` (and
    ``arcade``) map to dedicated CellRoles — not a generic ROOM dump.
    """
    programs = getattr(massing, "level_programs", None)
    if not programs:
        return [], [], [], []

    program_cells: List[Tuple[int, int, int, str]] = []
    partitions: List[Tuple[int, int, int, str, bool]] = []
    classroom_cells: List[Tuple[int, int, int]] = []
    corridor_cells: List[Tuple[int, int, int]] = []
    classroom_seen: Set[Tuple[int, int, int]] = set()
    corridor_seen: Set[Tuple[int, int, int]] = set()

    for level, raw_program in enumerate(programs):
        if level >= len(storeys) or not raw_program:
            continue
        grid = storeys[level]
        labels: Dict[Tuple[int, int], str] = {}
        for name, regions in raw_program.items():
            label = str(name)
            for x0, y0, x1, y1 in regions:
                for x in range(int(x0), int(x1) + 1):
                    for y in range(int(y0), int(y1) + 1):
                        role = grid.get(x, y)
                        if role not in _PROGRAM_PAINTABLE:
                            continue
                        previous = labels.get((x, y))
                        if previous is not None and previous != label:
                            # Overlapping program rectangles are authoring errors;
                            # retain the first deterministically rather than making
                            # one cell belong to two rooms.
                            continue
                        labels[(x, y)] = label

        for (x, y), label in sorted(labels.items()):
            role = _role_for_program_label(label)
            grid.set(x, y, role)
            program_cells.append((x, y, level, label))
            key = (level, x, y)
            if role == CellRole.CLASSROOM and key not in classroom_seen:
                classroom_seen.add(key)
                classroom_cells.append(key)
            elif role == CellRole.CORRIDOR and key not in corridor_seen:
                corridor_seen.add(key)
                corridor_cells.append(key)

        edges: List[
            Tuple[Tuple[str, str], Tuple[int, int], str]
        ] = []
        seen_edges: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
        for cell, label in sorted(labels.items()):
            x, y = cell
            role = grid.get(x, y)
            for neighbor in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                other = labels.get(neighbor)
                neighbor_role = grid.get(*neighbor)
                if other == label:
                    continue
                # A named corridor/classroom rectangle may extend an existing
                # school program of the same role. Do not insert a wall merely
                # because the adjoining cells lack the same authoring label.
                if other is None and neighbor_role == role:
                    continue
                # Great hall: do not wall off into unlabelled INTERIOR.
                if role == CellRole.HALL and other is None and neighbor_role in (
                    CellRole.INTERIOR,
                ):
                    continue
                if other is None and neighbor_role not in _PROGRAM_PAINTABLE:
                    continue
                # Same open-hall spill both ways.
                if (
                    other is None
                    and role in _HALL_OPEN_NEIGHBOURS
                    and neighbor_role in _HALL_OPEN_NEIGHBOURS
                ):
                    continue
                edge_key = tuple(sorted((cell, neighbor)))
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                face = _face_toward(cell, neighbor)
                if face is None:
                    continue
                pair = tuple(sorted((label, other or "__hall__")))
                edges.append((pair, cell, face))

        level_partitions: List[Tuple[int, int, int, str, bool]] = []
        first_door_for_pair: Set[Tuple[str, str]] = set()
        for pair, (x, y), face in sorted(edges):
            is_door = pair not in first_door_for_pair
            first_door_for_pair.add(pair)
            level_partitions.append((x, y, level, face, is_door))

        # Program rectangles normally stop one cell inside the envelope because
        # perimeter cells are WALL_LINE, not ROOM. Extend each partition run
        # through that final wall-line cell so it physically terminates at the
        # exterior shell instead of leaving a one-module bypass around each end.
        canonical: Dict[Tuple[str, int, int], Tuple[int, int, int, str, bool]] = {}
        for x, y, part_level, face, is_door in level_partitions:
            if face == "east":
                key = ("vertical", x + 1, y)
                value = (x, y, part_level, "east", is_door)
            elif face == "west":
                key = ("vertical", x, y)
                value = (x - 1, y, part_level, "east", is_door)
            elif face == "north":
                key = ("horizontal", y + 1, x)
                value = (x, y, part_level, "north", is_door)
            else:
                key = ("horizontal", y, x)
                value = (x, y - 1, part_level, "north", is_door)
            previous = canonical.get(key)
            canonical[key] = value if previous is None else (
                previous[0],
                previous[1],
                previous[2],
                previous[3],
                previous[4] or is_door,
            )

        groups: Dict[Tuple[str, int], Set[int]] = defaultdict(set)
        for axis, plane, along in canonical:
            groups[(axis, plane)].add(along)
        for (axis, plane), along_values in sorted(groups.items()):
            lo, hi = min(along_values), max(along_values)
            if axis == "vertical":
                before = ((plane - 1, lo - 1), (plane, lo - 1))
                after = ((plane - 1, hi + 1), (plane, hi + 1))
                if all(grid.get(*c) == CellRole.WALL_LINE for c in before):
                    canonical[("vertical", plane, lo - 1)] = (
                        plane - 1, lo - 1, level, "east", False
                    )
                if all(grid.get(*c) == CellRole.WALL_LINE for c in after):
                    canonical[("vertical", plane, hi + 1)] = (
                        plane - 1, hi + 1, level, "east", False
                    )
            else:
                before = ((lo - 1, plane - 1), (lo - 1, plane))
                after = ((hi + 1, plane - 1), (hi + 1, plane))
                if all(grid.get(*c) == CellRole.WALL_LINE for c in before):
                    canonical[("horizontal", plane, lo - 1)] = (
                        lo - 1, plane - 1, level, "north", False
                    )
                if all(grid.get(*c) == CellRole.WALL_LINE for c in after):
                    canonical[("horizontal", plane, hi + 1)] = (
                        hi + 1, plane - 1, level, "north", False
                    )
        partitions.extend(canonical[key] for key in sorted(canonical))

    return program_cells, partitions, classroom_cells, corridor_cells


def _filter_stair_void_blocked(
    storeys: List[StoreyGrid],
    classroom_cells: List[Tuple[int, int, int]],
    corridor_cells: List[Tuple[int, int, int]],
    partitions: List[Tuple[int, int, int, str, bool]],
) -> Tuple[
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int, str, bool]],
]:
    """Drop classroom/corridor/partition entries on cells marked STAIR or VOID."""
    blocked = frozenset({CellRole.STAIR, CellRole.VOID, CellRole.DOUBLE_VOID})

    def is_blocked(level: int, x: int, y: int) -> bool:
        if level < 0 or level >= len(storeys):
            return True
        return storeys[level].get(x, y) in blocked

    classrooms = [
        c for c in classroom_cells if not is_blocked(c[0], c[1], c[2])
    ]
    corridors = [c for c in corridor_cells if not is_blocked(c[0], c[1], c[2])]
    parts = [
        p for p in partitions if not is_blocked(p[2], p[0], p[1])
    ]
    return classrooms, corridors, parts


# Roles the corridor spine may walk through / reclaim while linking to stairs.
_SPINE_WALK = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.CORRIDOR,
        CellRole.DOOR,
        CellRole.HALL,
        CellRole.ARCADE,
    }
)
_SPINE_RECLAIM = frozenset({CellRole.CLASSROOM, CellRole.SERVICE, CellRole.ROOM})
_SPINE_GOAL = frozenset({CellRole.STAIR, CellRole.VOID})


def _stair_goal_cells(
    grid: StoreyGrid, stair_xy: List[Tuple[int, int]]
) -> Set[Tuple[int, int]]:
    """STAIR on climbed levels; VOID well cells on the top landing storey."""
    goals: Set[Tuple[int, int]] = set()
    for x, y in stair_xy:
        role = grid.get(x, y)
        if role in _SPINE_GOAL:
            goals.add((x, y))
    return goals


def _corridor_component_reaches_stair(
    corridor: Set[Tuple[int, int]],
    goals: Set[Tuple[int, int]],
    grid: StoreyGrid,
) -> bool:
    """True if any corridor cell is 4-adjacent to a stair/void goal (spine already linked)."""
    if not corridor or not goals:
        return False
    for cx, cy in corridor:
        if (cx, cy) in goals:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (cx + dx, cy + dy) in goals:
                return True
    return False


def _shortest_spine_path(
    starts: Set[Tuple[int, int]],
    goals: Set[Tuple[int, int]],
    grid: StoreyGrid,
) -> Optional[List[Tuple[int, int]]]:
    """BFS through INTERIOR/CORRIDOR/DOOR and reclaimable CLASSROOM toward stair goals.

    Returns the list of cells to mark CORRIDOR (excluding the goal stair/void cell).
    Prefer paths that reclaim fewer CLASSROOM cells (cost 1 vs 0 for open spine).
    """
    if not starts or not goals:
        return None
    # state: cell → (prev, cost)
    prev: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}
    cost: Dict[Tuple[int, int], int] = {}
    q: deque[Tuple[int, int]] = deque()
    for s in sorted(starts):
        prev[s] = None
        cost[s] = 0
        q.append(s)
    found: Optional[Tuple[int, int]] = None
    found_cost = 10**9
    while q:
        cur = q.popleft()
        cx, cy = cur
        # Success: standing on a cell adjacent to a goal (or on a corridor that already
        # touches one — handled before BFS). Do not enter the goal cell itself.
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (cx + dx, cy + dy)
            if n in goals and cost[cur] < found_cost:
                found = cur
                found_cost = cost[cur]
        if found is not None and cost[cur] > found_cost:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (cx + dx, cy + dy)
            role = grid.get(*n)
            step = 0
            if role in _SPINE_WALK or n in starts:
                step = 0
            elif role in _SPINE_RECLAIM:
                step = 1
            else:
                continue
            new_cost = cost[cur] + step
            if n in cost and cost[n] <= new_cost:
                continue
            if n in goals:
                continue
            cost[n] = new_cost
            prev[n] = cur
            q.append(n)
    if found is None:
        return None
    path: List[Tuple[int, int]] = []
    cur_o: Optional[Tuple[int, int]] = found
    while cur_o is not None:
        path.append(cur_o)
        cur_o = prev.get(cur_o)
    path.reverse()
    return path


def _corridor_components(
    cells: Set[Tuple[int, int]],
) -> List[Set[Tuple[int, int]]]:
    """4-connected components over a corridor cell set."""
    remaining = set(cells)
    comps: List[Set[Tuple[int, int]]] = []
    while remaining:
        start = min(remaining)
        comp: Set[Tuple[int, int]] = set()
        q: deque[Tuple[int, int]] = deque([start])
        remaining.discard(start)
        while q:
            cur = q.popleft()
            comp.add(cur)
            cx, cy = cur
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cx + dx, cy + dy)
                if n in remaining:
                    remaining.discard(n)
                    q.append(n)
        comps.append(comp)
    return comps


def _extend_corridor_spine_to_stairs(
    storeys: List[StoreyGrid],
    massing: Massing,
    classroom_cells: List[Tuple[int, int, int]],
    corridor_cells: List[Tuple[int, int, int]],
    partitions: List[Tuple[int, int, int, str, bool]],
) -> Tuple[
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int]],
    List[Tuple[int, int, int, str, bool]],
    List[Failure],
]:
    """Phase 2.3: grow CORRIDOR through INTERIOR (reclaim CLASSROOM if needed) to stairs.

    Rooms hang off the corridor; the corridor must reach every stair well. When a
    double-loaded wing seals the corridor behind classrooms, reclaim the shortest
    classroom bridge so the spine touches STAIR (or top-storey VOID well).
    """
    failures: List[Failure] = []
    if not corridor_cells:
        return classroom_cells, corridor_cells, partitions, failures

    stair_xy = list(massing.stair_cells)
    if massing.storeys <= 1 or not stair_xy:
        # Single-storey / no stairs: spine need not reach a well.
        return classroom_cells, corridor_cells, partitions, failures

    classroom_set = set(classroom_cells)
    corridor_set = set(corridor_cells)
    corridor_seen = set(corridor_cells)

    for level, grid in enumerate(storeys):
        goals = _stair_goal_cells(grid, stair_xy)
        level_corr = {(x, y) for (lv, x, y) in corridor_set if lv == level}
        if not level_corr:
            continue
        if not goals:
            failures.append(
                Failure(
                    check="corridor_spine",
                    message=(
                        f"storey {level} has corridor cells but no stair/void "
                        "goal to link the circulation spine"
                    ),
                    world_xyz=cell_to_world_cm(0, 0, level),
                )
            )
            continue

        for comp in _corridor_components(level_corr):
            if _corridor_component_reaches_stair(comp, goals, grid):
                continue
            path = _shortest_spine_path(comp, goals, grid)
            if path is None:
                sample = next(iter(comp))
                failures.append(
                    Failure(
                        check="corridor_spine",
                        message=(
                            f"corridor component at {sample} level {level} "
                            "cannot reach a stair"
                        ),
                        world_xyz=cell_to_world_cm(sample[0], sample[1], level),
                    )
                )
                continue
            for x, y in path:
                if (x, y) in set(stair_xy):
                    continue
                role = grid.get(x, y)
                if role == CellRole.CORRIDOR:
                    continue
                if role in _SPINE_RECLAIM:
                    classroom_set.discard((level, x, y))
                    partitions = [
                        p
                        for p in partitions
                        if not (p[2] == level and p[0] == x and p[1] == y)
                    ]
                if role in _SPINE_WALK or role in _SPINE_RECLAIM:
                    grid.set(x, y, CellRole.CORRIDOR)
                    key = (level, x, y)
                    if key not in corridor_seen:
                        corridor_seen.add(key)
                        corridor_set.add(key)
                        level_corr.add((x, y))
            linked = set(comp) | set(path)
            if not _corridor_component_reaches_stair(linked, goals, grid):
                sample = path[-1]
                failures.append(
                    Failure(
                        check="corridor_spine",
                        message=(
                            f"spine path at level {level} ended at {sample} "
                            "without adjoining a stair"
                        ),
                        world_xyz=cell_to_world_cm(sample[0], sample[1], level),
                    )
                )

    classrooms = sorted(classroom_set)
    corridors = sorted(corridor_set)
    return classrooms, corridors, partitions, failures


def _apply_stairs(
    storeys: List[StoreyGrid],
    massing: Massing,
    interior_by_level: Dict[int, Set[Tuple[int, int]]],
) -> List[Failure]:
    """Mark STAIR on ground..top-1 and VOID above each stair top (§5.3)."""
    failures: List[Failure] = []
    stair_cells = list(massing.stair_cells)
    if massing.storeys <= 1:
        return failures
    if not stair_cells:
        failures.append(
            Failure(
                check="stair_serves_upper",
                message="no stair cells for multi-storey plan",
                world_xyz=cell_to_world_cm(0, 0, 1),
            )
        )
        return failures

    # Straight run: first cell is bottom; occupies listed cells on each climbed level.
    # Spiral: single tower/interior cell — may be DOOR or WALL_LINE, not INTERIOR.
    # Monumental wells (4×2 / 2×4): only the active 2×2 pad per level (D3-3).
    from pae.assemble import _MONUMENTAL_PAD_KINDS, _monumental_flight_pads

    is_spiral = (massing.stair_kind or "").lower() == "spiral"
    kind = (massing.stair_kind or "straight").lower()
    pads = (
        _monumental_flight_pads(stair_cells)
        if kind in _MONUMENTAL_PAD_KINDS
        else None
    )
    for level in range(massing.storeys - 1):
        interior = interior_by_level.get(level, set())
        if pads is not None:
            level_cells = pads[level % 2]
        else:
            level_cells = stair_cells
        for sx, sy in level_cells:
            if not is_spiral and (sx, sy) not in interior:
                failures.append(
                    Failure(
                        check="stair_in_interior",
                        message=f"stair cell {(sx, sy)} not interior at level {level}",
                        world_xyz=cell_to_world_cm(sx, sy, level),
                    )
                )
                continue
            storeys[level].set(sx, sy, CellRole.STAIR)
            # VOID on the storey above the stair top (character must not hit ceiling).
            above = level + 1
            if above < len(storeys):
                if (sx, sy) in interior_by_level.get(above, set()):
                    storeys[above].set(sx, sy, CellRole.VOID)
                else:
                    # Still mark void intent if the cell exists in grid bbox.
                    storeys[above].set(sx, sy, CellRole.VOID)
    return failures


def _reserve_monumental_stairwell(
    storeys: List[StoreyGrid],
    massing: Massing,
    interior_by_level: Dict[int, Set[Tuple[int, int]]],
) -> None:
    """After corridor spine: keep full offset-well footprint on L0 STAIR and top VOID.

    D3-3 offset pads mark only the active 2×2 per climbed level for flights, but
    the school (and corridor spine) still require the entire 4×2 / 2×4 well reserved
    on ground and fully open on the top landing — corridor must not reclaim the
    inactive half on the upper storey.
    """
    stair_cells = list(massing.stair_cells)
    if massing.storeys <= 1 or len(stair_cells) < 8:
        return
    from pae.assemble import _MONUMENTAL_PAD_KINDS, _monumental_flight_pads

    kind = (massing.stair_kind or "straight").lower()
    if kind not in _MONUMENTAL_PAD_KINDS:
        return
    if _monumental_flight_pads(stair_cells) is None:
        return

    # Only double-loaded school wings run corridor spine through the inactive
    # offset half — L/U monumental wells rely on _link_stair_void_regions instead.
    is_school = massing.name == "school_academy" or any(
        v.role == "classroom_wing" for v in massing.volumes
    )
    if not is_school:
        return

    well = set(stair_cells)
    top = massing.storeys - 1
    interior0 = interior_by_level.get(0, set())
    for x, y in well:
        if (x, y) in interior0:
            storeys[0].set(x, y, CellRole.STAIR)
    for x, y in well:
        storeys[top].set(x, y, CellRole.VOID)


def _build_circulation(
    massing: Massing,
    interior_by_level: Dict[int, Set[Tuple[int, int]]],
    storeys: List[StoreyGrid],
) -> Tuple[CirculationGraph, List[Failure]]:
    """Prove ground-to-top connectivity via stair edges between regions."""
    failures: List[Failure] = []
    graph = CirculationGraph()

    region_maps: Dict[int, Dict[Tuple[int, int], int]] = {}
    for level in range(massing.storeys):
        interior = interior_by_level.get(level, set())
        voidish = {
            c
            for c, role in storeys[level].cells.items()
            if role in (CellRole.VOID, CellRole.DOUBLE_VOID)
        }
        # Stairs are walkable landings for region membership at their level.
        rmap = _regions(interior, voidish)
        region_maps[level] = rmap
        for r in set(rmap.values()):
            graph.add_node(level, r)

    # Stair edges between storeys. Monumental 4×2 / 2×4 wells offset pads by level
    # (D3-3) — link pad L to pad L+1, not same XY cell.
    from pae.assemble import _MONUMENTAL_PAD_KINDS, _monumental_flight_pads

    kind = (massing.stair_kind or "straight").lower()
    pads = (
        _monumental_flight_pads(list(massing.stair_cells))
        if kind in _MONUMENTAL_PAD_KINDS
        else None
    )
    if pads is not None:
        for level in range(massing.storeys - 1):
            low_pad = pads[level % 2]
            high_pad = pads[(level + 1) % 2]
            r0 = _pick_region_for_cells(region_maps[level], low_pad)
            r1 = _pick_region_for_cells(
                region_maps[level + 1], high_pad, neighbor_expand=True
            )
            if r0 is None or r1 is None:
                anchor = low_pad[0]
                failures.append(
                    Failure(
                        check="stair_graph",
                        message=(
                            f"stair pad {sorted(low_pad)} level {level} does not "
                            f"link to upper pad {sorted(high_pad)} — "
                            "offset flights must share circulation regions"
                        ),
                        world_xyz=cell_to_world_cm(anchor[0], anchor[1], level),
                    )
                )
                continue
            graph.add_node(level, r0)
            graph.add_node(level + 1, r1)
            graph.add_edge((level, r0), (level + 1, r1))
    else:
        # Straight / spiral: a STAIR cell at level L connects region(L, cell) to
        # region(L+1, cell) if the cell above is VOID (stairwell opening).
        for level in range(massing.storeys - 1):
            for (x, y), role in storeys[level].cells.items():
                if role != CellRole.STAIR:
                    continue
                r0 = region_maps[level].get((x, y))
                above_map = region_maps[level + 1]
                r1 = above_map.get((x, y))
                if r1 is None:
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        r1 = above_map.get((x + dx, y + dy))
                        if r1 is not None:
                            break
                if r0 is None or r1 is None:
                    failures.append(
                        Failure(
                            check="stair_graph",
                            message=(
                                f"stair at {(x, y)} level {level} does not link regions"
                            ),
                            world_xyz=cell_to_world_cm(x, y, level),
                        )
                    )
                    continue
                graph.add_node(level, r0)
                graph.add_node(level + 1, r1)
                graph.add_edge((level, r0), (level + 1, r1))

    _link_stair_void_regions(storeys, region_maps, graph)

    if massing.storeys <= 1:
        return graph, failures

    # Prove every upper-storey region is reachable from some ground region.
    ground_nodes = [n for n in graph.nodes if n[0] == 0]
    if not ground_nodes:
        failures.append(
            Failure(
                check="stair_reachability",
                message="no ground-storey circulation nodes",
                world_xyz=cell_to_world_cm(0, 0, 0),
            )
        )
        return graph, failures

    reachable: Set[Tuple[int, int]] = set()
    for g in ground_nodes:
        reachable |= graph.connected_from(g)

    for level in range(1, massing.storeys):
        upper = [n for n in graph.nodes if n[0] == level]
        if not upper:
            failures.append(
                Failure(
                    check="stair_reachability",
                    message=f"storey {level} has no circulation region",
                    world_xyz=cell_to_world_cm(0, 0, level),
                )
            )
            continue
        for node in upper:
            if node not in reachable:
                failures.append(
                    Failure(
                        check="stair_reachability",
                        message=(
                            f"storey {level} region {node[1]} unreachable from ground"
                        ),
                        world_xyz=cell_to_world_cm(0, 0, level),
                    )
                )
    return graph, failures


def plan(massing: Massing) -> Tuple[Optional[FloorPlan], Report]:
    """Build CellRole grids per storey and prove circulation connectivity."""
    failures: List[Failure] = []
    if not massing.volumes:
        return None, Report.from_failures(
            [
                Failure(
                    check="plan_empty",
                    message="massing has no volumes",
                    world_xyz=None,
                )
            ]
        )

    all_vols = massing.volumes
    x0, y0, x1, y1 = _bbox(all_vols)
    width = x1 - x0 + 1
    height = y1 - y0 + 1
    courtyard = _courtyard_cells(massing)

    storeys: List[StoreyGrid] = []
    interior_by_level: Dict[int, Set[Tuple[int, int]]] = {}

    for level in range(massing.storeys):
        grid = StoreyGrid(level=level, origin=(x0, y0), size=(width, height))
        interior = _enclosed_cells_at_level(massing, level)
        # Courtyard cells are never INTERIOR — outside envelope by role.
        interior -= courtyard
        voids = _void_cells_at_level(massing, level)
        # Open marks that sit on built cells below (or L0 courtyard hole) are
        # not exterior: L0 → COURTYARD, upper → DOUBLE_VOID (open to below).
        interior_by_level[level] = set(interior)

        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if (x, y) in courtyard:
                    grid.set(x, y, CellRole.COURTYARD)
                elif (x, y) in voids and (x, y) not in interior:
                    if level == 0:
                        grid.set(x, y, CellRole.COURTYARD)
                    else:
                        grid.set(x, y, CellRole.DOUBLE_VOID)
                elif (x, y) in interior:
                    if _is_wall_line(x, y, interior):
                        grid.set(x, y, CellRole.WALL_LINE)
                    else:
                        grid.set(x, y, CellRole.INTERIOR)
                elif (x, y) in voids:
                    # Void marked on a cell that would otherwise be exterior —
                    # still treat as open-to-below when above the foundation.
                    if level == 0:
                        grid.set(x, y, CellRole.COURTYARD)
                    else:
                        grid.set(x, y, CellRole.DOUBLE_VOID)
                else:
                    grid.set(x, y, CellRole.EXTERIOR)
        storeys.append(grid)

    door_cells: List[Tuple[int, int]] = []
    window_cells: List[Tuple[int, int]] = []
    entrance_by_cell: Dict[Tuple[int, int], str] = {}
    if storeys:
        door_cells, window_cells, entrance_by_cell = _place_doors_windows(
            storeys[0], interior_by_level[0], massing
        )

    classroom_cells, corridor_cells, interior_partitions = _carve_double_loaded_wings(
        storeys, massing
    )
    (
        program_cells,
        program_partitions,
        program_classrooms,
        program_corridors,
    ) = _carve_program_regions(storeys, massing)
    interior_partitions.extend(program_partitions)
    # Merge StructureSpec / sketch program paint into school lists (dedupe).
    seen_cls = set(classroom_cells)
    for key in program_classrooms:
        if key not in seen_cls:
            seen_cls.add(key)
            classroom_cells.append(key)
    seen_corr = set(corridor_cells)
    for key in program_corridors:
        if key not in seen_corr:
            seen_corr.add(key)
            corridor_cells.append(key)

    failures.extend(_apply_double_height_rooms(storeys, massing))

    failures.extend(_apply_stairs(storeys, massing, interior_by_level))

    classroom_cells, corridor_cells, interior_partitions = _filter_stair_void_blocked(
        storeys, classroom_cells, corridor_cells, interior_partitions
    )

    # Phase 2.3: corridor spine reaches stairs (may reclaim classroom bridges).
    classroom_cells, corridor_cells, interior_partitions, spine_failures = (
        _extend_corridor_spine_to_stairs(
            storeys,
            massing,
            classroom_cells,
            corridor_cells,
            interior_partitions,
        )
    )
    failures.extend(spine_failures)

    _reserve_monumental_stairwell(storeys, massing, interior_by_level)

    graph, circ_failures = _build_circulation(massing, interior_by_level, storeys)
    failures.extend(circ_failures)

    # Courtyard role check: no COURTYARD cell may also be INTERIOR.
    for grid in storeys:
        for (x, y), role in grid.cells.items():
            if role == CellRole.COURTYARD and (x, y) in interior_by_level.get(
                grid.level, set()
            ):
                failures.append(
                    Failure(
                        check="courtyard_outside_envelope",
                        message=f"courtyard cell {(x, y)} leaked into interior",
                        world_xyz=cell_to_world_cm(x, y, grid.level),
                    )
                )

    is_school = massing.name == "school_academy" or any(
        v.role == "classroom_wing" for v in massing.volumes
    )
    if is_school and not classroom_cells:
        failures.append(
            Failure(
                check="school_program",
                message="school plan produced no classroom cells after carve",
                world_xyz=None,
            )
        )

    if failures:
        return None, Report.from_failures(failures)

    entrance = door_cells[0] if door_cells else next(
        iter(interior_by_level.get(0, {(0, 0)}))
    )

    fp = FloorPlan(
        storeys=storeys,
        circulation=graph,
        entrance_cell=entrance,
        door_cells=door_cells,
        window_cells=window_cells,
        entrance_by_cell=entrance_by_cell,
        stair_cells=list(massing.stair_cells),
        ground_slab=massing.ground_slab,
        name=massing.name,
        style=massing.style,
        seed=massing.seed,
        roof_kind=massing.roof_kind,
        roof_pitch=massing.roof_pitch,
        massing=massing,
        classroom_cells=classroom_cells,
        corridor_cells=corridor_cells,
        interior_partitions=interior_partitions,
        rooms=list(massing.rooms),
        program_cells=program_cells,
        wall_height_storeys=massing.wall_height_storeys,
        structure_id=getattr(massing, "structure_id", None),
        foundation_cells=tuple(getattr(massing, "foundation_cells", ()) or ()),
        level_height_units=getattr(massing, "level_height_units", None),
        level_wall_styles=getattr(massing, "level_wall_styles", None),
        level_window_tags=getattr(massing, "level_window_tags", None),
        level_programs=getattr(massing, "level_programs", None),
    )
    return fp, Report.from_failures([])

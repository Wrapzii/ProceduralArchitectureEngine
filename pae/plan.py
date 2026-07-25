"""Floor plan (§5.2–5.3) — WP-4.

Massing → FloorPlan (CellRole grid per storey) + circulation graph proof.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from pae.contract import cell_to_world_cm
from pae.report import Failure, Report
from pae.solver import Massing, Volume


class CellRole(Enum):
    EXTERIOR = 0
    INTERIOR = 1
    WALL_LINE = 2
    DOOR = 3
    STAIR = 4
    VOID = 5  # stairwell / light well — no floor
    COURTYARD = 6  # open to sky, has ground, no roof
    CORRIDOR = 7  # school circulation spine
    CLASSROOM = 8  # programmed room cell (door to corridor)


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
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)
    ground_slab: bool = True
    name: str = "building"
    style: str = "townhouse"
    seed: int = 0
    roof_kind: str = "flat"
    roof_pitch: float = 1.0
    massing: Optional[Massing] = None
    classroom_cells: List[Tuple[int, int]] = field(default_factory=list)
    corridor_cells: List[Tuple[int, int]] = field(default_factory=list)
    # (cell_x, cell_y, level, face toward corridor, is_door)
    interior_partitions: List[Tuple[int, int, int, str, bool]] = field(
        default_factory=list
    )


def _bbox(volumes: List[Volume]) -> Tuple[int, int, int, int]:
    xs0 = [v.x0 for v in volumes]
    ys0 = [v.y0 for v in volumes]
    xs1 = [v.x1 for v in volumes]
    ys1 = [v.y1 for v in volumes]
    return min(xs0), min(ys0), max(xs1), max(ys1)


def _enclosed_cells_at_level(massing: Massing, level: int) -> Set[Tuple[int, int]]:
    cells: Set[Tuple[int, int]] = set()
    for v in massing.enclosed_volumes():
        if level < v.storeys:
            cells |= v.cells()
    return cells


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


def _place_doors_windows(
    grid: StoreyGrid,
    interior: Set[Tuple[int, int]],
    massing: Massing,
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Place ground-floor doors/windows on WALL_LINE cells (south face preferred)."""
    doors: List[Tuple[int, int]] = []
    windows: List[Tuple[int, int]] = []
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
    return doors, windows


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


def _carve_double_loaded_wings(
    storeys: List[StoreyGrid],
    massing: Massing,
) -> Tuple[
    List[Tuple[int, int]],
    List[Tuple[int, int]],
    List[Tuple[int, int, int, str, bool]],
]:
    """Mark CORRIDOR / CLASSROOM in classroom wings; record interior door partitions.

    Double-loaded hall: centerline corridor through each ``classroom_wing`` volume,
    remaining INTERIOR cells become CLASSROOM. Every classroom-corridor adjacency
    gets a partition; alternating adjacencies are doors.
    """
    classroom_cells: List[Tuple[int, int]] = []
    corridor_cells: List[Tuple[int, int]] = []
    partitions: List[Tuple[int, int, int, str, bool]] = []
    wings = [v for v in massing.volumes if v.role == "classroom_wing"]
    if not wings:
        return classroom_cells, corridor_cells, partitions

    classroom_seen: Set[Tuple[int, int]] = set()
    corridor_seen: Set[Tuple[int, int]] = set()

    for level, grid in enumerate(storeys):
        use = (
            massing.storey_use[level]
            if level < len(massing.storey_use)
            else "hall"
        )
        # Bias: carve whenever storey is classroom-oriented, or always for school wings.
        if use not in ("classroom", "classrooms", "dormitory", "hall"):
            # Still carve school wings — storey_use may say hall on ground.
            pass
        for vol in wings:
            cells = [
                (x, y)
                for (x, y) in vol.cells()
                if grid.get(x, y) == CellRole.INTERIOR
            ]
            if len(cells) < 3:
                continue
            if (vol.x1 - vol.x0) >= (vol.y1 - vol.y0):
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
                if c not in corridor_seen:
                    corridor_seen.add(c)
                    corridor_cells.append(c)
            rooms = [c for c in cells if c not in corridor]
            for c in sorted(rooms):
                touches_corridor = any(
                    n in corridor
                    for n in (
                        (c[0] + 1, c[1]),
                        (c[0] - 1, c[1]),
                        (c[0], c[1] + 1),
                        (c[0], c[1] - 1),
                    )
                )
                if not touches_corridor:
                    # Keep as INTERIOR (open hall bay) — not a room without a door.
                    continue
                grid.set(c[0], c[1], CellRole.CLASSROOM)
                if c not in classroom_seen:
                    classroom_seen.add(c)
                    classroom_cells.append(c)
                door_placed = False
                for nx, ny in (
                    (c[0] + 1, c[1]),
                    (c[0] - 1, c[1]),
                    (c[0], c[1] + 1),
                    (c[0], c[1] - 1),
                ):
                    if (nx, ny) not in corridor:
                        continue
                    face = _face_toward(c, (nx, ny))
                    if face is None:
                        continue
                    is_door = not door_placed
                    door_placed = True
                    partitions.append((c[0], c[1], level, face, is_door))
    return classroom_cells, corridor_cells, partitions


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
    for level in range(massing.storeys - 1):
        interior = interior_by_level.get(level, set())
        for sx, sy in stair_cells:
            if (sx, sy) not in interior:
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
            if role in (CellRole.VOID,)
        }
        # Stairs are walkable landings for region membership at their level.
        rmap = _regions(interior, voidish)
        region_maps[level] = rmap
        for r in set(rmap.values()):
            graph.add_node(level, r)

    # Stair edges: a STAIR cell at level L connects region(L, cell) to region(L+1, cell)
    # if the cell above is VOID (stairwell opening).
    for level in range(massing.storeys - 1):
        for (x, y), role in storeys[level].cells.items():
            if role != CellRole.STAIR:
                continue
            r0 = region_maps[level].get((x, y))
            # VOID cells are removed from walkable regions; attach to neighbouring region above.
            above_map = region_maps[level + 1]
            r1 = above_map.get((x, y))
            if r1 is None:
                # Look at 4-neighbours on the upper floor for a landing region.
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    r1 = above_map.get((x + dx, y + dy))
                    if r1 is not None:
                        break
            if r0 is None or r1 is None:
                failures.append(
                    Failure(
                        check="stair_graph",
                        message=f"stair at {(x, y)} level {level} does not link regions",
                        world_xyz=cell_to_world_cm(x, y, level),
                    )
                )
                continue
            graph.add_node(level, r0)
            graph.add_node(level + 1, r1)
            graph.add_edge((level, r0), (level + 1, r1))

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
        interior_by_level[level] = set(interior)

        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if (x, y) in courtyard:
                    grid.set(x, y, CellRole.COURTYARD)
                elif (x, y) in interior:
                    if _is_wall_line(x, y, interior):
                        grid.set(x, y, CellRole.WALL_LINE)
                    else:
                        grid.set(x, y, CellRole.INTERIOR)
                else:
                    grid.set(x, y, CellRole.EXTERIOR)
        storeys.append(grid)

    door_cells: List[Tuple[int, int]] = []
    window_cells: List[Tuple[int, int]] = []
    if storeys:
        door_cells, window_cells = _place_doors_windows(
            storeys[0], interior_by_level[0], massing
        )

    classroom_cells, corridor_cells, interior_partitions = _carve_double_loaded_wings(
        storeys, massing
    )

    failures.extend(_apply_stairs(storeys, massing, interior_by_level))

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
    )
    return fp, Report.from_failures([])

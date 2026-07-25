"""Constraint solver (§5.1) — WP-4.

Greedy placement + local repair. No SAT solver.
Input: BuildingSpec → Output: Massing (rectangular cell volumes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from pae.contract import cell_to_world_cm
from pae.report import Failure, Report
from pae.spec import (
    BuildingSpec,
    EntranceSpec,
    FootprintSpec,
    RoomSpec,
    TowerSpec,
    SUPPORTED_STAIR_KINDS,
)


# Enclosed building bodies (not courtyard). Includes school program roles.
BODY_ROLES = frozenset(
    {"main", "wing", "hall", "admin", "classroom_wing", "chapel", "tower"}
)
# Ranges that get per-wing roofs / ground spans (not towers).
WING_ROLES = frozenset(
    {"main", "wing", "hall", "admin", "classroom_wing", "chapel"}
)


@dataclass
class Volume:
    """Axis-aligned rectangular volume in cell coordinates (inclusive)."""

    id: str
    x0: int
    y0: int
    x1: int
    y1: int
    storeys: int
    role: str = "main"  # main | wing | hall | admin | classroom_wing | tower | courtyard
    entrance: bool = False
    # Per-tower drum circulation (from TowerSpec.stair_kind). "" = none.
    stair_kind: str = ""

    def cells(self) -> Set[Tuple[int, int]]:
        return {
            (x, y)
            for x in range(self.x0, self.x1 + 1)
            for y in range(self.y0, self.y1 + 1)
        }

    def overlaps(self, other: "Volume") -> bool:
        if self.role == "courtyard" or other.role == "courtyard":
            # Courtyard is outside envelope — may sit inside footprint hole.
            return False
        return not (
            self.x1 < other.x0
            or other.x1 < self.x0
            or self.y1 < other.y0
            or other.y1 < self.y0
        )

    def abuts(self, other: "Volume") -> bool:
        """True if volumes share an edge (or corner for tower attach)."""
        if self.overlaps(other):
            return True
        # Edge abutment (inclusive cells touching by 1).
        x_gap = max(other.x0 - self.x1, self.x0 - other.x1)
        y_gap = max(other.y0 - self.y1, self.y0 - other.y1)
        if x_gap == 1 and y_gap <= 0:
            return True
        if y_gap == 1 and x_gap <= 0:
            return True
        # Corner touch (diagonal) — allowed for corner towers.
        if x_gap == 1 and y_gap == 1:
            return True
        return False

    def centre_world_cm(self) -> Tuple[float, float, float]:
        cx = (self.x0 + self.x1) // 2
        cy = (self.y0 + self.y1) // 2
        return cell_to_world_cm(cx, cy, 0)


@dataclass
class Massing:
    volumes: List[Volume]
    entrance_volume_id: str
    storeys: int
    seed: int
    ground_slab: bool = True
    style: str = "townhouse"
    name: str = "building"
    # Spec fields assembly/plan need
    openings_doors_ground: int = 1
    openings_windows_ground: Optional[int] = None
    openings_windows_per_bay: int = 1
    openings_skip_ground_windows: bool = False
    stair_kind: str = "straight"
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)
    roof_kind: str = "flat"
    roof_pitch: float = 1.0
    storey_use: List[str] = field(default_factory=list)
    rooms: List[RoomSpec] = field(default_factory=list)
    entrances: List[EntranceSpec] = field(default_factory=list)
    building_class: str = "generic"
    #: Envelope / monumental wall span (storeys). None → ``storeys``.
    wall_height_storeys: Optional[float] = None

    def volume_by_id(self, vid: str) -> Optional[Volume]:
        for v in self.volumes:
            if v.id == vid:
                return v
        return None

    def enclosed_volumes(self) -> List[Volume]:
        return [v for v in self.volumes if v.role != "courtyard"]

    def wing_volumes(self) -> List[Volume]:
        return [v for v in self.volumes if v.role in WING_ROLES]


def _rect_volume(
    vid: str,
    x0: int,
    y0: int,
    bays_x: int,
    bays_y: int,
    storeys: int,
    role: str = "main",
    entrance: bool = False,
) -> Volume:
    return Volume(
        id=vid,
        x0=x0,
        y0=y0,
        x1=x0 + bays_x - 1,
        y1=y0 + bays_y - 1,
        storeys=storeys,
        role=role,
        entrance=entrance,
    )


def _place_footprint(fp: FootprintSpec, storeys: int) -> List[Volume]:
    """Greedy footprint volumes from FootprintSpec."""
    vols: List[Volume] = []
    if fp.kind == "cells":
        # ARBITRARY OUTLINE. The mask is decomposed into maximal rectangles because the
        # rest of the solver reasons in rectangular Volumes. This is the path that lets
        # a sketch describe any shape instead of picking one of five named kinds — the
        # limitation that turned every non-standard building into a hardcoded preset.
        from pae.sketch import rect_cover

        mask = {(int(x), int(y)) for x, y in (fp.cells or ())}
        if not mask:
            return vols
        rects = rect_cover(mask)
        # Largest first, so the biggest mass becomes 'main' and carries the entrance.
        # Ties break on position, keeping the decomposition deterministic.
        rects.sort(key=lambda r: (-((r[2] - r[0] + 1) * (r[3] - r[1] + 1)), r[0], r[1]))
        for i, (x0, y0, x1, y1) in enumerate(rects):
            vols.append(
                Volume(
                    id="main" if i == 0 else f"wing_{i}",
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    storeys=storeys,
                    role="main" if i == 0 else "wing",
                    entrance=(i == 0),
                )
            )
        return vols

    if fp.kind == "rect":
        vols.append(
            _rect_volume("main", 0, 0, fp.bays_x, fp.bays_y, storeys, "main", True)
        )
        return vols

    if fp.kind == "L":
        # Long bar along X, short wing along Y at west end.
        depth = max(1, min(fp.wing_depth, fp.bays_y))
        vols.append(
            _rect_volume("main", 0, 0, fp.bays_x, depth, storeys, "main", True)
        )
        wing_h = fp.bays_y - depth
        if wing_h > 0:
            vols.append(
                _rect_volume(
                    "wing_n",
                    0,
                    depth,
                    depth,
                    wing_h,
                    storeys,
                    "wing",
                    False,
                )
            )
        return vols

    if fp.kind == "U":
        depth = max(1, min(fp.wing_depth, fp.bays_y // 2 or 1))
        # South bar
        vols.append(
            _rect_volume("main", 0, 0, fp.bays_x, depth, storeys, "main", True)
        )
        # West + east legs northward
        leg_h = fp.bays_y - depth
        if leg_h > 0:
            vols.append(
                _rect_volume("wing_w", 0, depth, depth, leg_h, storeys, "wing")
            )
            vols.append(
                _rect_volume(
                    "wing_e",
                    fp.bays_x - depth,
                    depth,
                    depth,
                    leg_h,
                    storeys,
                    "wing",
                )
            )
        return vols

    if fp.kind == "school":
        return _place_school_academy(fp, storeys)

    if fp.kind == "courtyard" or fp.courtyard:
        # Ring of enclosed ranges; courtyard volume is outside the envelope by role.
        depth = max(1, min(fp.wing_depth, min(fp.bays_x, fp.bays_y) // 2 or 1))
        # South range (entrance)
        vols.append(
            _rect_volume("main", 0, 0, fp.bays_x, depth, storeys, "main", True)
        )
        # North range
        vols.append(
            _rect_volume(
                "wing_n",
                0,
                fp.bays_y - depth,
                fp.bays_x,
                depth,
                storeys,
                "wing",
            )
        )
        mid_h = fp.bays_y - 2 * depth
        if mid_h > 0:
            vols.append(
                _rect_volume("wing_w", 0, depth, depth, mid_h, storeys, "wing")
            )
            vols.append(
                _rect_volume(
                    "wing_e",
                    fp.bays_x - depth,
                    depth,
                    depth,
                    mid_h,
                    storeys,
                    "wing",
                )
            )
        cx0, cy0 = depth, depth
        cx1, cy1 = fp.bays_x - depth - 1, fp.bays_y - depth - 1
        if cx1 >= cx0 and cy1 >= cy0:
            vols.append(
                Volume(
                    id="courtyard",
                    x0=cx0,
                    y0=cy0,
                    x1=cx1,
                    y1=cy1,
                    storeys=storeys,
                    role="courtyard",
                    entrance=False,
                )
            )
        return vols

    # compound → treat as rect for now; local repair can expand later
    vols.append(
        _rect_volume("main", 0, 0, fp.bays_x, fp.bays_y, storeys, "main", True)
    )
    return vols


def _place_school_academy(fp: FootprintSpec, storeys: int) -> List[Volume]:
    """Named school volumes: hall + classroom wings + admin + courtyard.

    Uses a courtyard ring like ``kind=courtyard`` but assigns program roles so
    plan/assemble can carve double-loaded classrooms and style the facade.
    Wing depth must be ≥4 so a center corridor has classroom cells beside it.
    """
    depth = max(4, min(fp.wing_depth if fp.wing_depth else 5, min(fp.bays_x, fp.bays_y) // 2 or 4))
    vols: List[Volume] = []
    # South hall (entrance)
    vols.append(
        _rect_volume("hall", 0, 0, fp.bays_x, depth, storeys, "hall", True)
    )
    # North admin / chapel range
    vols.append(
        _rect_volume(
            "admin",
            0,
            fp.bays_y - depth,
            fp.bays_x,
            depth,
            storeys,
            "admin",
        )
    )
    mid_h = fp.bays_y - 2 * depth
    if mid_h > 0:
        vols.append(
            _rect_volume(
                "classroom_w",
                0,
                depth,
                depth,
                mid_h,
                storeys,
                "classroom_wing",
            )
        )
        vols.append(
            _rect_volume(
                "classroom_e",
                fp.bays_x - depth,
                depth,
                depth,
                mid_h,
                storeys,
                "classroom_wing",
            )
        )
    cx0, cy0 = depth, depth
    cx1, cy1 = fp.bays_x - depth - 1, fp.bays_y - depth - 1
    if fp.courtyard and cx1 >= cx0 and cy1 >= cy0:
        vols.append(
            Volume(
                id="courtyard",
                x0=cx0,
                y0=cy0,
                x1=cx1,
                y1=cy1,
                storeys=storeys,
                role="courtyard",
                entrance=False,
            )
        )
    return vols


def _tower_volume(spec: TowerSpec, index: int, building_storeys: int) -> Volume:
    # Towers occupy a 1×1 cell footprint by default.
    storeys = max(spec.storeys, building_storeys)
    return Volume(
        id=f"tower_{index}",
        x0=spec.cell[0],
        y0=spec.cell[1],
        x1=spec.cell[0],
        y1=spec.cell[1],
        storeys=storeys,
        role="tower",
        entrance=False,
        stair_kind=str(getattr(spec, "stair_kind", "") or "").lower(),
    )


def _volumes_overlap_failures(volumes: List[Volume]) -> List[Failure]:
    failures: List[Failure] = []
    enclosed = [v for v in volumes if v.role != "courtyard"]
    for i, a in enumerate(enclosed):
        for b in enclosed[i + 1 :]:
            if a.overlaps(b):
                # Report intersection centre.
                ix0 = max(a.x0, b.x0)
                iy0 = max(a.y0, b.y0)
                failures.append(
                    Failure(
                        check="volumes_no_overlap",
                        message=f"volumes '{a.id}' and '{b.id}' overlap",
                        world_xyz=cell_to_world_cm(ix0, iy0, 0),
                    )
                )
    return failures


def _tower_attach_failures(volumes: List[Volume]) -> List[Failure]:
    failures: List[Failure] = []
    mains = [v for v in volumes if v.role in WING_ROLES]
    for t in volumes:
        if t.role != "tower":
            continue
        attached = any(_tower_touches(t, m) for m in mains)
        if not attached:
            failures.append(
                Failure(
                    check="tower_attached",
                    message=f"tower '{t.id}' does not attach to a wall or corner",
                    world_xyz=t.centre_world_cm(),
                )
            )
    return failures


def _tower_touches(tower: Volume, body: Volume) -> bool:
    """Tower must sit on wall run or corner of body (edge or corner adjacency)."""
    # Shared cell with body perimeter, or abutting outside perimeter.
    body_cells = body.cells()
    t_cells = tower.cells()
    if t_cells & body_cells:
        # Interior overlap of tower into body is attach-by-embedding — reject
        # unless only on perimeter. Treat interior as failure via overlap check.
        return True
    # Outside abutting: any tower cell adjacent (8-neighbour) to body.
    for tx, ty in t_cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if (tx + dx, ty + dy) in body_cells:
                    return True
    return False


def _courtyard_role_failures(volumes: List[Volume]) -> List[Failure]:
    """Courtyards must be role=courtyard (outside envelope), never a hole role."""
    failures: List[Failure] = []
    for v in volumes:
        if v.id.startswith("courtyard") and v.role != "courtyard":
            failures.append(
                Failure(
                    check="courtyard_outside_envelope",
                    message=f"'{v.id}' must use role=courtyard (outside envelope)",
                    world_xyz=v.centre_world_cm(),
                )
            )
    return failures


def _reachability_failures(volumes: List[Volume], entrance_id: str) -> List[Failure]:
    """Every enclosed volume reachable from entrance via abutting graph."""
    enclosed = [v for v in volumes if v.role != "courtyard"]
    by_id: Dict[str, Volume] = {v.id: v for v in enclosed}
    if entrance_id not in by_id:
        return [
            Failure(
                check="entrance_reachable",
                message=f"entrance volume '{entrance_id}' missing",
                world_xyz=None,
            )
        ]
    # BFS on abutment graph
    seen: Set[str] = set()
    stack = [entrance_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        a = by_id[cur]
        for b in enclosed:
            if b.id in seen:
                continue
            if a.abuts(b) or a.overlaps(b) or _tower_touches(a, b) or _tower_touches(b, a):
                stack.append(b.id)
    failures: List[Failure] = []
    for v in enclosed:
        if v.id not in seen:
            failures.append(
                Failure(
                    check="entrance_reachable",
                    message=f"volume '{v.id}' unreachable from entrance '{entrance_id}'",
                    world_xyz=v.centre_world_cm(),
                )
            )
    return failures


def _stair_storey_failures(spec: BuildingSpec, volumes: List[Volume]) -> List[Failure]:
    """Every storey above ground must be served by at least one stair."""
    if spec.storeys <= 1:
        return []
    max_level = max(v.storeys for v in volumes if v.role != "courtyard")
    if max_level <= 1:
        return [
            Failure(
                check="stair_serves_upper",
                message="multi-storey massing has no upper storey volume",
                world_xyz=cell_to_world_cm(0, 0, 1),
            )
        ]
    # Straight stairs: need at least one stair cell declared or auto-place later.
    # Solver records intent; if storeys>1 and no stair_cells, attempt auto cell.
    if spec.circulation.stair_cells:
        return []
    # Auto-intent: solver will inject a default stair cell into massing; not a failure yet.
    return []


def _tower_needs_repair(tower: Volume, bodies: List[Volume]) -> bool:
    """True if tower overlaps a body or fails to attach to any body."""
    if any(tower.overlaps(b) for b in bodies):
        return True
    return not any(_tower_touches(tower, b) for b in bodies)


def _tower_candidate_volume(cx: int, cy: int) -> Volume:
    return Volume(
        id="_cand",
        x0=cx,
        y0=cy,
        x1=cx,
        y1=cy,
        storeys=1,
        role="tower",
    )


def _valid_tower_attach_cell(
    cx: int,
    cy: int,
    bodies: List[Volume],
) -> bool:
    """True when *(cx, cy)* is outside all bodies and 8-adjacent to a wing."""
    cand = _tower_candidate_volume(cx, cy)
    if any(cand.overlaps(b) for b in bodies):
        return False
    return any(_tower_touches(cand, b) for b in bodies)


def _body_perimeter_outside_cells(
    body: Volume,
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Outside cells along *body* perimeter — wall (4-neighbour) then corners (8-only)."""
    body_cells = body.cells()
    perimeter: Set[Tuple[int, int]] = set()
    for x, y in body_cells:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            if (x + dx, y + dy) not in body_cells:
                perimeter.add((x, y))
                break

    wall: List[Tuple[int, int]] = []
    corners: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for x, y in sorted(perimeter):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ox, oy = x + dx, y + dy
            if (ox, oy) in body_cells or (ox, oy) in seen:
                continue
            seen.add((ox, oy))
            wall.append((ox, oy))
        for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            ox, oy = x + dx, y + dy
            if (ox, oy) in body_cells or (ox, oy) in seen:
                continue
            seen.add((ox, oy))
            corners.append((ox, oy))
    return wall, corners


def exterior_tower_attach_cells(
    bodies: List[Volume],
    *,
    prefer_wall: bool = True,
) -> List[Tuple[int, int]]:
    """Exterior 1×1 cells that abut any ``WING_ROLES`` body (for factories / repair).

    Walks the full perimeter of every body — not just mid-wall samples — so L/U/
    courtyard/school massing always exposes valid attach points on hall, wing, admin,
    and classroom_wing volumes.
    """
    wing_bodies = [b for b in bodies if b.role in WING_ROLES]
    if not wing_bodies:
        return []

    wall: List[Tuple[int, int]] = []
    corners: List[Tuple[int, int]] = []
    for body in wing_bodies:
        w, c = _body_perimeter_outside_cells(body)
        wall.extend(w)
        corners.extend(c)

    ordered = wall + corners if prefer_wall else corners + wall
    good: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for cx, cy in ordered:
        if (cx, cy) in seen:
            continue
        seen.add((cx, cy))
        if _valid_tower_attach_cell(cx, cy, wing_bodies):
            good.append((cx, cy))
    return good


def _exterior_tower_candidates(bodies: List[Volume]) -> List[Tuple[int, int]]:
    """Wall-edge then corner cells outside every enclosed body (M3 prefers wall)."""
    return exterior_tower_attach_cells(bodies, prefer_wall=True)


def _nearest_tower_attach_cell(
    tx: int,
    ty: int,
    bodies: List[Volume],
) -> Optional[Tuple[int, int]]:
    """Closest valid exterior attach cell, or ``None`` when no attach exists."""
    candidates = _exterior_tower_candidates(bodies)
    if candidates:
        return min(candidates, key=lambda c: abs(c[0] - tx) + abs(c[1] - ty))

    # Last resort: scan a padded bbox around the union of all wing bodies.
    x0 = min(b.x0 for b in bodies) - 2
    y0 = min(b.y0 for b in bodies) - 2
    x1 = max(b.x1 for b in bodies) + 2
    y1 = max(b.y1 for b in bodies) + 2
    fallback: List[Tuple[int, int]] = []
    for cx in range(x0, x1 + 1):
        for cy in range(y0, y1 + 1):
            if _valid_tower_attach_cell(cx, cy, bodies):
                fallback.append((cx, cy))
    if not fallback:
        return None
    return min(fallback, key=lambda c: abs(c[0] - tx) + abs(c[1] - ty))


def _local_repair_towers(volumes: List[Volume]) -> List[Volume]:
    """Snap free-floating *or overlapping* towers onto a wing body perimeter.

    Historical bugs (Ledger C-5):
    - Interior tower cells ``_tower_touches`` via overlap, so repair skipped them.
    - Mid-wall-only candidates missed valid attach on L/U/courtyard wings.
    - Fallback corners were not filtered for touch / no-overlap.
    """
    mains = [v for v in volumes if v.role in WING_ROLES]
    if not mains:
        return volumes
    repaired: List[Volume] = []
    for v in volumes:
        if v.role != "tower" or not _tower_needs_repair(v, mains):
            repaired.append(v)
            continue
        best = _nearest_tower_attach_cell(v.x0, v.y0, mains)
        if best is None:
            repaired.append(v)
            continue
        repaired.append(
            Volume(
                id=v.id,
                x0=best[0],
                y0=best[1],
                x1=best[0],
                y1=best[1],
                storeys=v.storeys,
                role=v.role,
                entrance=False,
                stair_kind=str(getattr(v, "stair_kind", "") or ""),
            )
        )
    return repaired


def _primary_body(volumes: List[Volume]) -> Optional[Volume]:
    """Prefer hall/main for stairs and entrance-adjacent circulation."""
    for role in ("hall", "main", "classroom_wing", "wing", "admin"):
        for v in volumes:
            if v.role == role:
                return v
    enclosed = [v for v in volumes if v.role != "courtyard"]
    return enclosed[0] if enclosed else None


def _default_stair_cell(volumes: List[Volume]) -> Optional[Tuple[int, int]]:
    """Pick an interior cell near the south edge of the primary body for a straight stair."""
    m = _primary_body(volumes)
    if m is None:
        return None
    # Need 2 modules span in +Y for a straight run (§5.3).
    if (m.y1 - m.y0) < 1 or (m.x1 - m.x0) < 0:
        return None
    sx = m.x0 + (m.x1 - m.x0) // 2
    sy = m.y0 + 1  # one bay in from south exterior wall when depth allows
    if sy + 1 > m.y1:
        sy = m.y0
    if sy + 1 > m.y1:
        return None
    return (sx, sy)


def _default_spiral_stair_cell(volumes: List[Volume]) -> Optional[Tuple[int, int]]:
    """Single interior cell for a freestanding spiral (no tower)."""
    m = _primary_body(volumes)
    if m is None:
        return None
    return (m.x0 + (m.x1 - m.x0) // 2, m.y0 + (m.y1 - m.y0) // 2)


def _tower_stair_cell(volumes: List[Volume]) -> Optional[Tuple[int, int]]:
    """First tower footprint cell — preferred anchor for spiral stairs."""
    for v in volumes:
        if v.role == "tower":
            return (v.x0, v.y0)
    return None


def _tower_blocked_cells(volumes: List[Volume]) -> Set[Tuple[int, int]]:
    """Hall grid cells owned by attached tower drums (not outboard snap coords)."""
    blocked: Set[Tuple[int, int]] = set()
    mains = [v for v in volumes if v.role in WING_ROLES]
    for tower in volumes:
        if tower.role != "tower":
            continue
        blocked.add((tower.x0, tower.y0))
        for hall in mains:
            if tower.y0 < hall.y0 or tower.y0 >= hall.y1:
                continue
            if tower.x0 < hall.x0:
                blocked.add((hall.x0, tower.y0))
            if tower.x0 >= hall.x1:
                blocked.add((hall.x1, tower.y0))
    return blocked


def _default_stair_cells(
    volumes: List[Volume],
    stair_kind: str,
    storeys: int = 1,
) -> List[Tuple[int, int]]:
    """Auto stair footprint: 2×1 straight, 2×2 switchback/wide, 1×1 spiral.

    Multi-storey monumental wells (storeys ≥ 3) expand to 4×2 / 2×4 so successive
    flights can shift by one stair width instead of stacking in the same XY
    (see assemble ``_monumental_flight_pads``).
    """
    kind = (stair_kind or "straight").lower()
    if kind == "spiral":
        tower_cell = _tower_stair_cell(volumes)
        if tower_cell is not None:
            return [tower_cell]
        auto = _default_spiral_stair_cell(volumes)
        return [auto] if auto is not None else []
    m = _primary_body(volumes)
    if m is None:
        return []
    if kind in ("switchback", "wide"):
        # 2×2 stairwell inset from the SW corner of the primary body.
        if (m.x1 - m.x0) < 2 or (m.y1 - m.y0) < 2:
            return []
        x0 = m.x0 + 1
        y0 = m.y0 + 1
        if x0 + 1 >= m.x1:
            x0 = m.x0
        if y0 + 1 >= m.y1:
            y0 = m.y0
        pad = [
            (x0, y0),
            (x0 + 1, y0),
            (x0, y0 + 1),
            (x0 + 1, y0 + 1),
        ]
        # Need two adjacent 2×2 pads when more than one flight is stacked.
        if storeys >= 3:
            bx = m.x1 - m.x0
            by = m.y1 - m.y0
            # Prefer the long axis so a shallow hall (e.g. 15×4) still fits.
            if bx >= 4 and x0 + 3 < m.x1:
                return pad + [
                    (x0 + 2, y0),
                    (x0 + 3, y0),
                    (x0 + 2, y0 + 1),
                    (x0 + 3, y0 + 1),
                ]
            if by >= 4 and y0 + 3 < m.y1:
                return pad + [
                    (x0, y0 + 2),
                    (x0 + 1, y0 + 2),
                    (x0, y0 + 3),
                    (x0 + 1, y0 + 3),
                ]
            if bx >= 4 and x0 + 3 >= m.x1:
                x0 = max(m.x0, m.x1 - 4)
                y0 = min(y0, m.y1 - 2)
                return [
                    (x0 + i, y0 + j) for i in range(4) for j in range(2)
                ]
            if by >= 4 and y0 + 3 >= m.y1:
                y0 = max(m.y0, m.y1 - 4)
                x0 = min(x0, m.x1 - 2)
                return [
                    (x0 + i, y0 + j) for i in range(2) for j in range(4)
                ]
        return pad
    auto = _default_stair_cell(volumes)
    if auto is None:
        return []
    if storeys < 3:
        return [auto, (auto[0], auto[1] + 1)]
    m = _primary_body(volumes)
    if m is None:
        return [auto, (auto[0], auto[1] + 1)]
    blocked = _tower_blocked_cells(volumes)
    # Multi-flight straight runs need two 2×2 pads (Roadmap 10.4 / D3-3).
    pads: List[List[Tuple[int, int]]] = []
    for x0 in range(m.x0, m.x1 - 1):
        for y0 in range(m.y0, m.y1):
            if y0 + 3 >= m.y1:
                continue
            cand = [(x0 + i, y0 + j) for i in range(2) for j in range(4)]
            if not all(
                m.x0 <= c[0] <= m.x1 and m.y0 <= c[1] <= m.y1 for c in cand
            ):
                continue
            if any(c in blocked for c in cand):
                continue
            pads.append(cand)
    if not pads:
        for x0 in range(m.x0, max(m.x0, m.x1 - 2)):
            for y0 in range(m.y0, m.y1 + 1):
                if y0 + 1 > m.y1:
                    continue
                cand = [(x0 + i, y0 + j) for i in range(4) for j in range(2)]
                if not all(
                m.x0 <= c[0] <= m.x1 and m.y0 <= c[1] <= m.y1 for c in cand
            ):
                    continue
                if any(c in blocked for c in cand):
                    continue
                pads.append(cand)
    if pads:
        def _pad_rank(cand: List[Tuple[int, int]]) -> Tuple[int, int, int, int]:
            """Prefer auto anchor, avoid south perimeter and outer X columns, favour depth."""
            south_row = sum(1 for c in cand if c[1] == m.y0)
            edge_cols = sum(1 for c in cand if c[0] == m.x0 or c[0] == m.x1)
            depth = min(c[1] for c in cand)
            auto_miss = 0 if auto in cand else 1
            return (auto_miss, south_row, edge_cols, -depth)

        return min(pads, key=_pad_rank)
    return [auto, (auto[0], auto[1] + 1)]


def solve(spec: BuildingSpec) -> Tuple[Optional[Massing], Report]:
    """Greedy massing from BuildingSpec. Hard constraints fail the report."""
    volumes = _place_footprint(spec.footprint, spec.storeys)
    for i, t in enumerate(spec.towers):
        volumes.append(_tower_volume(t, i, spec.storeys))

    # Local repair: snap detached towers.
    volumes = _local_repair_towers(volumes)

    entrance = next((v for v in volumes if v.entrance), volumes[0] if volumes else None)
    if entrance is None:
        return None, Report.from_failures(
            [
                Failure(
                    check="massing_empty",
                    message="solver produced no volumes",
                    world_xyz=None,
                )
            ]
        )

    failures: List[Failure] = []

    if spec.footprint.kind == "school":
        wing_vols = [v for v in volumes if v.role == "classroom_wing"]
        if not wing_vols:
            failures.append(
                Failure(
                    check="school_program",
                    message=(
                        "school footprint cannot produce classroom_wing volumes "
                        f"(bays={spec.footprint.bays_x}x{spec.footprint.bays_y}, "
                        f"wing_depth={spec.footprint.wing_depth})"
                    ),
                    world_xyz=None,
                )
            )

    stair_kind = (spec.circulation.stair_kind or "straight").lower()
    has_tower = any(v.role == "tower" for v in volumes)
    if spec.storeys > 1 and stair_kind == "spiral" and not has_tower:
        failures.append(
            Failure(
                check="stair_kind",
                message=(
                    "spiral stair_kind requires a tower volume "
                    "(single-cell tower well)"
                ),
                world_xyz=cell_to_world_cm(0, 0, 1),
            )
        )
    elif spec.storeys > 1 and stair_kind not in SUPPORTED_STAIR_KINDS:
        supported = ", ".join(sorted(SUPPORTED_STAIR_KINDS))
        failures.append(
            Failure(
                check="stair_kind",
                message=(
                    f"unsupported stair_kind '{stair_kind}' for auto placement "
                    f"— supported: {supported}"
                ),
                world_xyz=cell_to_world_cm(0, 0, 1),
            )
        )

    stair_cells = list(spec.circulation.stair_cells)
    if spec.storeys > 1 and not stair_cells and not failures:
        stair_cells = _default_stair_cells(
            volumes, spec.circulation.stair_kind, storeys=spec.storeys
        )

    failures.extend(_volumes_overlap_failures(volumes))
    failures.extend(_tower_attach_failures(volumes))
    failures.extend(_courtyard_role_failures(volumes))
    failures.extend(_reachability_failures(volumes, entrance.id))
    failures.extend(_stair_storey_failures(spec, volumes))

    if spec.storeys > 1 and not stair_cells:
        failures.append(
            Failure(
                check="stair_serves_upper",
                message="storeys > 1 but no stair cells could be placed",
                world_xyz=cell_to_world_cm(0, 0, 1),
            )
        )

    if failures:
        return None, Report.from_failures(failures)

    # S-011…S-021 — style/spec roof hooks (kind + pitch clamps) resolve here once.
    from pae.spec import derive_building_class
    from pae.style_pack import resolve_roof_kind, resolve_roof_pitch, resolve_style_pack

    style_pack = None
    try:
        style_pack = resolve_style_pack(spec.style)
    except Exception:
        style_pack = None
    style_arg = style_pack if style_pack is not None else {}
    roof_kind = resolve_roof_kind(style_arg, spec_kind=spec.roof.kind)
    roof_pitch = resolve_roof_pitch(style_arg, spec_pitch=spec.roof.pitch)

    massing = Massing(
        volumes=volumes,
        entrance_volume_id=entrance.id,
        storeys=spec.storeys,
        seed=spec.seed,
        ground_slab=spec.ground_slab,
        style=spec.style,
        name=spec.name,
        openings_doors_ground=spec.openings.doors_ground,
        openings_windows_ground=spec.openings.windows_ground,
        openings_windows_per_bay=spec.openings.windows_per_bay,
        openings_skip_ground_windows=spec.openings.skip_ground_windows,
        stair_kind=spec.circulation.stair_kind,
        stair_cells=stair_cells,
        roof_kind=roof_kind,
        roof_pitch=roof_pitch,
        storey_use=list(spec.storey_use),
        entrances=list(spec.entrances),
        rooms=list(spec.rooms),
        building_class=derive_building_class(spec),
        wall_height_storeys=spec.wall_height_storeys,
    )
    return massing, Report.from_failures([])

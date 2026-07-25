"""Constraint solver (§5.1) — WP-4.

Greedy placement + local repair. No SAT solver.
Input: BuildingSpec → Output: Massing (rectangular cell volumes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from pae.contract import cell_to_world_cm
from pae.report import Failure, Report
from pae.spec import BuildingSpec, FootprintSpec, TowerSpec


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


def _exterior_tower_candidates(bodies: List[Volume]) -> List[Tuple[int, int]]:
    """Wall-edge then corner cells outside every enclosed body (M3 prefers wall)."""
    wall: List[Tuple[int, int]] = []
    corners: List[Tuple[int, int]] = []
    for body in bodies:
        mx = body.x0 + (body.x1 - body.x0) // 2
        my = body.y0 + (body.y1 - body.y0) // 2
        wall.extend(
            [
                (body.x0 - 1, my),
                (body.x1 + 1, my),
                (mx, body.y0 - 1),
                (mx, body.y1 + 1),
            ]
        )
        corners.extend(
            [
                (body.x0 - 1, body.y0 - 1),
                (body.x1 + 1, body.y0 - 1),
                (body.x0 - 1, body.y1 + 1),
                (body.x1 + 1, body.y1 + 1),
            ]
        )
    # Prefer wall abut (edge) over diagonal corners — keeps 4-connect circulation.
    ordered = wall + corners
    good: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for cx, cy in ordered:
        if (cx, cy) in seen:
            continue
        seen.add((cx, cy))
        cand = Volume(
            id="_cand",
            x0=cx,
            y0=cy,
            x1=cx,
            y1=cy,
            storeys=1,
            role="tower",
        )
        if any(cand.overlaps(b) for b in bodies):
            continue
        if not any(_tower_touches(cand, b) for b in bodies):
            continue
        good.append((cx, cy))
    return good


def _local_repair_towers(volumes: List[Volume]) -> List[Volume]:
    """Nudge free-floating *or overlapping* towers to nearest exterior wall/corner.

    Historical bug: interior tower cells ``_tower_touches`` the body via overlap,
    so repair skipped them and ``volumes_no_overlap`` failed the solve.
    """
    mains = [v for v in volumes if v.role in ("main", "wing")]
    if not mains:
        return volumes
    candidates = _exterior_tower_candidates(mains)
    repaired: List[Volume] = []
    for v in volumes:
        if v.role != "tower" or not _tower_needs_repair(v, mains):
            repaired.append(v)
            continue
        tx, ty = v.x0, v.y0
        if not candidates:
            # Fallback: primary-body corners (legacy behaviour).
            body = mains[0]
            candidates = [
                (body.x0 - 1, body.y0 - 1),
                (body.x1 + 1, body.y0 - 1),
                (body.x0 - 1, body.y1 + 1),
                (body.x1 + 1, body.y1 + 1),
            ]
        best = min(candidates, key=lambda c: abs(c[0] - tx) + abs(c[1] - ty))
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


def _default_stair_cells(
    volumes: List[Volume],
    stair_kind: str,
) -> List[Tuple[int, int]]:
    """Auto stair footprint: 2×1 straight or 2×2 switchback/wide."""
    kind = (stair_kind or "straight").lower()
    m = _primary_body(volumes)
    if m is None:
        return []
    if kind in ("switchback", "wide"):
        # 2×2 stairwell inset from the SW corner of the primary body.
        if (m.x1 - m.x0) < 2 or (m.y1 - m.y0) < 2:
            return []
        x0 = m.x0 + 1
        y0 = m.y0 + 1
        if x0 + 1 > m.x1:
            x0 = m.x0
        if y0 + 1 > m.y1:
            y0 = m.y0
        return [
            (x0, y0),
            (x0 + 1, y0),
            (x0, y0 + 1),
            (x0 + 1, y0 + 1),
        ]
    auto = _default_stair_cell(volumes)
    if auto is None:
        return []
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

    stair_cells = list(spec.circulation.stair_cells)
    if spec.storeys > 1 and not stair_cells:
        stair_cells = _default_stair_cells(volumes, spec.circulation.stair_kind)

    failures: List[Failure] = []
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
        roof_kind=spec.roof.kind,
        roof_pitch=spec.roof.pitch,
        storey_use=list(spec.storey_use),
    )
    return massing, Report.from_failures([])

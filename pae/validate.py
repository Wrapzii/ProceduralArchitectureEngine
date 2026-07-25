"""Validation stage (§7) — WP-1 owns this module.

Acceptance: report.ok is True and report.critical is empty.
Export must refuse to run when critical defects exist.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple

from pae.assembly_types import (
    Assembly,
    FloorPlanLayer,
    SolidPlacement,
    WallRun,
)
from pae.contract import (
    CHEST_HEIGHT_CM,
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    VERTICAL_SUPPORT_TOL_CM,
    WALL_T_CM,
    aabb_intersects,
    aabb_overlap,
    placement_world_aabb,
)
from pae.plan import CellRole
from pae.report import Failure, Report


def validate(assembly: Assembly) -> Tuple[Assembly, Report]:
    """Validate an assembly. Returns (assembly, report)."""
    failures: List[Failure] = []
    failures.extend(_check_end_connectivity(assembly))
    failures.extend(_check_vertical_support(assembly))
    failures.extend(_check_collinear_gaps(assembly))
    failures.extend(_check_interpenetration(assembly))
    failures.extend(_check_enclosure(assembly))
    failures.extend(_check_floor_coverage(assembly))
    failures.extend(_check_stair_reachability(assembly))
    failures.extend(_check_run_fit(assembly))
    failures.extend(_check_aperture_sanity(assembly))
    failures = _sort_failures(failures)
    return assembly, Report.from_failures(failures)


# --- helpers ----------------------------------------------------------------


def _sort_failures(failures: List[Failure]) -> List[Failure]:
    return sorted(
        failures,
        key=lambda f: (
            f.check,
            f.piece_id or "",
            f.world_xyz or (0.0, 0.0, 0.0),
            f.message,
        ),
    )


def _placement_aabb(p: SolidPlacement) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _piece_map(assembly: Assembly) -> Dict[str, SolidPlacement]:
    return {p.piece_id: p for p in assembly.placements}


def _is_wall(p: SolidPlacement) -> bool:
    return p.kind == "wall" or "wall" in p.tags


def _is_floor_like(p: SolidPlacement) -> bool:
    return p.kind in ("floor", "ground") or p.kind == "stair"


def _centre(a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _wall_long_axis(p: SolidPlacement) -> str:
    """Return 'x' or 'y' for the wall run direction in world space."""
    sx, sy, _ = p.size_cm
    if p.yaw in (0, 180):
        return "y" if sy >= sx else "x"
    return "x" if sy >= sx else "y"


def _wall_end_faces(
    p: SolidPlacement,
) -> Tuple[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]], ...]:
    """Each end: (label, probe_min, probe_max)."""
    bb_min, bb_max = _placement_aabb(p)
    axis = _wall_long_axis(p)
    probe = TOL_CM
    if axis == "y":
        y0, y1 = bb_min[1], bb_max[1]
        x0, x1 = bb_min[0], bb_max[0]
        z0, z1 = bb_min[2], bb_max[2]
        low_probe = (
            (x0, y0 - probe, z0),
            (x1, y0, z1),
        )
        high_probe = (
            (x0, y1, z0),
            (x1, y1 + probe, z1),
        )
        low_xyz = (x0 + (x1 - x0) * 0.5, y0, z0 + (z1 - z0) * 0.5)
        high_xyz = (x0 + (x1 - x0) * 0.5, y1, z0 + (z1 - z0) * 0.5)
        return (("end_a", low_xyz, low_probe), ("end_b", high_xyz, high_probe))
    x0, x1 = bb_min[0], bb_max[0]
    y0, y1 = bb_min[1], bb_max[1]
    z0, z1 = bb_min[2], bb_max[2]
    low_probe = (
        (x0 - probe, y0, z0),
        (x0, y1, z1),
    )
    high_probe = (
        (x1, y0, z0),
        (x1 + probe, y1, z1),
    )
    low_xyz = (x0, y0 + (y1 - y0) * 0.5, z0 + (z1 - z0) * 0.5)
    high_xyz = (x1, y0 + (y1 - y0) * 0.5, z0 + (z1 - z0) * 0.5)
    return (("end_a", low_xyz, low_probe), ("end_b", high_xyz, high_probe))


# --- §7.1 end connectivity ---------------------------------------------------


def _check_end_connectivity(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    solids = assembly.placements
    for wall in solids:
        if not _is_wall(wall):
            continue
        for end_name, world_xyz, probe in _wall_end_faces(wall):
            pmin, pmax = probe
            hit = False
            for other in solids:
                if other.piece_id == wall.piece_id:
                    continue
                omin, omax = _placement_aabb(other)
                if aabb_intersects(pmin, pmax, omin, omax):
                    hit = True
                    break
            if not hit:
                failures.append(
                    Failure(
                        check="end_connectivity",
                        message=(
                            f"dangling wall end {end_name} on {wall.piece_id} "
                            f"({wall.asset_id}) — no geometry within {TOL_CM} cm"
                        ),
                        world_xyz=world_xyz,
                        piece_id=wall.piece_id,
                        critical=True,
                    )
                )
    return failures


# --- §7.2 vertical support ---------------------------------------------------


def _check_vertical_support(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    tol = VERTICAL_SUPPORT_TOL_CM
    for p in assembly.placements:
        if p.kind == "ground":
            continue
        bb_min, bb_max = _placement_aabb(p)
        bottom_z = bb_min[2]
        if bottom_z <= tol:
            continue
        supported = False
        for other in assembly.placements:
            if other.piece_id == p.piece_id:
                continue
            omin, omax = _placement_aabb(other)
            if abs(omin[2] - bottom_z) > tol and abs(omax[2] - bottom_z) > tol:
                if not (omin[2] < bottom_z <= omax[2] + tol):
                    continue
            else:
                top = omax[2]
                if abs(top - bottom_z) > tol:
                    continue
            if _xy_footprint_overlap(bb_min, bb_max, omin, omax, tol):
                supported = True
                break
        if not supported:
            failures.append(
                Failure(
                    check="vertical_support",
                    message=(
                        f"floating piece {p.piece_id} ({p.asset_id}) — "
                        f"no support within {tol} cm below z={bottom_z:.1f}"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


def _xy_footprint_overlap(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
    tol: float,
) -> bool:
    return (
        min(a_max[0], b_max[0]) - max(a_min[0], b_min[0]) > tol
        and min(a_max[1], b_max[1]) - max(a_min[1], b_min[1]) > tol
    )


# --- §7.3 collinear gaps -----------------------------------------------------


def _check_collinear_gaps(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    pieces = _piece_map(assembly)

    # Derive gaps from wall placements (authoritative geometry).
    buckets: Dict[Tuple[int, str, float, str], List[Tuple[str, float, float]]] = {}
    for wall in assembly.placements:
        if not _is_wall(wall):
            continue
        bb_min, bb_max = _placement_aabb(wall)
        axis = _wall_long_axis(wall)
        if axis == "y":
            key = (wall.level, "y", round(bb_min[0], 3), "x")
            span = (bb_min[1], bb_max[1])
            plane = bb_min[0]
        else:
            key = (wall.level, "x", round(bb_min[1], 3), "y")
            span = (bb_min[0], bb_max[0])
            plane = bb_min[1]
        buckets.setdefault(key, []).append((wall.piece_id, span[0], span[1]))

    for (level, axis, plane, _), spans in buckets.items():
        spans.sort(key=lambda s: s[1])
        for i in range(len(spans) - 1):
            id_a, _, end_a = spans[i]
            id_b, start_b, _ = spans[i + 1]
            gap = start_b - end_a
            if gap > TOL_CM:
                mid = (end_a + start_b) * 0.5
                if axis == "y":
                    xyz = (plane, mid, level * STOREY_CM + STOREY_CM * 0.5)
                else:
                    xyz = (mid, plane, level * STOREY_CM + STOREY_CM * 0.5)
                failures.append(
                    Failure(
                        check="collinear_gap",
                        message=(
                            f"collinear gap {gap:.1f} cm between {id_a} and {id_b} "
                            f"on level {level}"
                        ),
                        world_xyz=xyz,
                        piece_id=id_a,
                        critical=False,
                    )
                )

    # Also honour explicit runs when they list multiple pieces (assembly metadata).
    if assembly.wall_runs:
        for run in assembly.wall_runs:
            if len(run.piece_ids) > 1:
                failures.extend(_gaps_along_run(run, pieces))
    return failures


def _gaps_along_run(run: WallRun, pieces: Dict[str, SolidPlacement]) -> List[Failure]:
    failures: List[Failure] = []
    spans: List[Tuple[str, float, float]] = []
    for pid in run.piece_ids:
        p = pieces.get(pid)
        if p is None:
            continue
        bb_min, bb_max = _placement_aabb(p)
        if run.axis == "y":
            spans.append((pid, bb_min[1], bb_max[1]))
        else:
            spans.append((pid, bb_min[0], bb_max[0]))
    spans.sort(key=lambda s: s[1])
    for i in range(len(spans) - 1):
        id_a, _, end_a = spans[i]
        id_b, start_b, _ = spans[i + 1]
        gap = start_b - end_a
        if gap > TOL_CM:
            mid = (end_a + start_b) * 0.5
            if run.axis == "y":
                xyz = (run.plane_cm, mid, run.level * STOREY_CM + STOREY_CM * 0.5)
            else:
                xyz = (mid, run.plane_cm, run.level * STOREY_CM + STOREY_CM * 0.5)
            failures.append(
                Failure(
                    check="collinear_gap",
                    message=(
                        f"collinear gap {gap:.1f} cm between {id_a} and {id_b} "
                        f"in run {run.run_id}"
                    ),
                    world_xyz=xyz,
                    piece_id=id_a,
                    critical=False,
                )
            )
    return failures


# --- §7.4 interpenetration ---------------------------------------------------

# Tower kit kinds placed at the same cell (§2.2 centred annulus).
_TOWER_SOLID_KINDS = frozenset({"tower_arc", "tower_crown", "tower_cap"})
# Roof decks that tuck over perimeter walls at the eave (§6 / assemble).
_ROOF_DECK_ASSET_IDS = frozenset(
    {"roof_flat", "roof_pitched_slope", "roof_gable_infill"}
)


def _is_roof_deck(p: SolidPlacement) -> bool:
    return p.kind == "roof" and p.asset_id in _ROOF_DECK_ASSET_IDS


def _is_tower_solid(p: SolidPlacement) -> bool:
    return p.kind in _TOWER_SOLID_KINDS


def _xy_overlap_extent(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> Tuple[float, float]:
    return (
        min(a_max[0], b_max[0]) - max(a_min[0], b_min[0]),
        min(a_max[1], b_max[1]) - max(a_min[1], b_min[1]),
    )


def _z_overlap_extent(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> float:
    return min(a_max[2], b_max[2]) - max(a_min[2], b_min[2])


def _has_xy_overlap(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
    *,
    tol: float = TOL_CM,
) -> bool:
    ox, oy = _xy_overlap_extent(a_min, a_max, b_min, b_max)
    return ox > tol and oy > tol


def _designed_tower_cell_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Same-cell tower annulus quarters, crown/cap, and gable-at-tower overlaps."""
    if a.cell != b.cell:
        return False
    tower_a, tower_b = _is_tower_solid(a), _is_tower_solid(b)
    if tower_a and tower_b:
        if a.kind == "tower_arc" and b.kind == "tower_arc":
            return a.level == b.level
        return True
    if tower_a or tower_b:
        tower = a if tower_a else b
        other = b if tower_a else a
        if other.kind == "wall":
            return tower.level == other.level
        if _is_roof_deck(other):
            return True
    return False


def _designed_wall_corner_pair(
    a: SolidPlacement,
    b: SolidPlacement,
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    """Perimeter corners overlap by ``WALL_T`` — not a defect (§2.3)."""
    if not (_is_wall(a) and _is_wall(b)):
        return False
    ox, oy = _xy_overlap_extent(a_min, a_max, b_min, b_max)
    corner_lim = WALL_T_CM + TOL_CM
    return ox > TOL_CM and oy > TOL_CM and ox <= corner_lim and oy <= corner_lim


def _designed_wall_roof_pair(
    a: SolidPlacement,
    b: SolidPlacement,
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    """Wall thickness tucks under a roof deck at the eave within ``FLOOR_T``."""
    if _is_wall(a) and _is_roof_deck(b):
        wall, roof = a, b
    elif _is_wall(b) and _is_roof_deck(a):
        wall, roof = b, a
    else:
        return False
    del wall, roof
    if not _has_xy_overlap(a_min, a_max, b_min, b_max):
        return False
    z_overlap = _z_overlap_extent(a_min, a_max, b_min, b_max)
    eave_band = FLOOR_T_CM + TOL_CM
    return 0.0 < z_overlap <= eave_band


def _designed_floor_upper_pair(
    a: SolidPlacement,
    b: SolidPlacement,
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    """Storey slab above wall / stair / tower drum in the level below (§2.4)."""
    kinds = {a.kind, b.kind}
    if "floor" not in kinds:
        return False
    floor = a if a.kind == "floor" else b
    other = b if floor is a else a
    if other.kind not in ("wall", "stair", "tower_arc"):
        return False
    if floor.level != other.level + 1:
        return False
    return _has_xy_overlap(a_min, a_max, b_min, b_max)


def _designed_floor_hole_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Spanning deck overlaps a stair-hole bay — opening, not double slab."""
    if a.kind != "floor" or b.kind != "floor":
        return False
    ids = {a.asset_id, b.asset_id}
    return ids == {"floor", "floor_hole"}


def _designed_stair_opening_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Stair shaft shares a wall cell or upper floor opening."""
    kinds = {a.kind, b.kind}
    if kinds == {"stair", "wall"}:
        return a.cell == b.cell
    if kinds == {"floor", "stair"}:
        floor = a if a.kind == "floor" else b
        stair = b if floor is a else a
        return floor.level == stair.level + 1
    return False


def _designed_roof_gable_slope_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Gable-end infill and slope deck share ridge-end volume by design (§6)."""
    ids = {a.asset_id, b.asset_id}
    if ids != {"roof_gable_infill", "roof_pitched_slope"}:
        return False
    return a.kind == "roof" and b.kind == "roof" and a.level == b.level


def _interpenetration_pair_allowed(
    a: SolidPlacement,
    b: SolidPlacement,
    *,
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    """Pairs that may touch by design — not reported as overlap defects."""
    kinds = {a.kind, b.kind}
    if kinds == {"floor", "ground"}:
        return True
    if _designed_tower_cell_pair(a, b):
        return True
    if _designed_wall_corner_pair(a, b, a_min, a_max, b_min, b_max):
        return True
    if _designed_wall_roof_pair(a, b, a_min, a_max, b_min, b_max):
        return True
    if _designed_floor_upper_pair(a, b, a_min, a_max, b_min, b_max):
        return True
    if _designed_floor_hole_pair(a, b):
        return True
    if _designed_stair_opening_pair(a, b):
        return True
    if _designed_roof_gable_slope_pair(a, b):
        return True
    return False


def _check_interpenetration(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    placements = assembly.placements
    for i in range(len(placements)):
        a = placements[i]
        amin, amax = _placement_aabb(a)
        for j in range(i + 1, len(placements)):
            b = placements[j]
            bmin, bmax = _placement_aabb(b)
            if _interpenetration_pair_allowed(
                a, b, a_min=amin, a_max=amax, b_min=bmin, b_max=bmax
            ):
                continue
            if a.level != b.level and not _vertical_stack_overlap(amin, amax, bmin, bmax):
                if max(amin[2], bmin[2]) >= min(amax[2], bmax[2]) - TOL_CM:
                    continue
            if aabb_overlap(amin, amax, bmin, bmax):
                failures.append(
                    Failure(
                        check="interpenetration",
                        message=(
                            f"solids {a.piece_id} and {b.piece_id} overlap "
                            f"by more than {TOL_CM} cm on all axes"
                        ),
                        world_xyz=_centre(
                            (
                                max(amin[0], bmin[0]),
                                max(amin[1], bmin[1]),
                                max(amin[2], bmin[2]),
                            ),
                            (
                                min(amax[0], bmax[0]),
                                min(amax[1], bmax[1]),
                                min(amax[2], bmax[2]),
                            ),
                        ),
                        piece_id=a.piece_id,
                        critical=False,
                    )
                )
    return failures


def _vertical_stack_overlap(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    return aabb_intersects(a_min, a_max, b_min, b_max)


# --- §7.5 enclosure ----------------------------------------------------------


def _check_enclosure(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    for level, layer in sorted(assembly.floor_plan.items()):
        leaks = _flood_interior_leaks(layer, assembly, level)
        for cell, xyz in leaks:
            failures.append(
                Failure(
                    check="enclosure",
                    message=(
                        f"enclosure leak at cell ({cell[0]}, {cell[1]}) "
                        f"level {level} — exterior flood reached INTERIOR"
                    ),
                    world_xyz=xyz,
                    piece_id=None,
                    critical=True,
                )
            )
    return failures


def _flood_interior_leaks(
    layer: FloorPlanLayer,
    assembly: Assembly,
    level: int,
) -> List[Tuple[Tuple[int, int], Tuple[float, float, float]]]:
    """Return interior cells reached from outside at chest height."""
    z_probe = level * STOREY_CM + CHEST_HEIGHT_CM
    blocked: set[Tuple[int, int]] = set()
    for p in assembly.placements:
        if not _is_wall(p) and p.kind not in ("tower_arc",):
            continue
        if p.level != level and p.level != level - 1:
            # walls may span storeys — include if AABB crosses probe height
            bb_min, bb_max = _placement_aabb(p)
            if not (bb_min[2] <= z_probe <= bb_max[2]):
                continue
        bb_min, bb_max = _placement_aabb(p)
        if z_probe < bb_min[2] - TOL_CM or z_probe > bb_max[2] + TOL_CM:
            continue
        _mark_cells_blocked_by_aabb(layer, bb_min, bb_max, blocked)

    leaks: List[Tuple[Tuple[int, int], Tuple[float, float, float]]] = []
    visited: set[Tuple[int, int]] = set()
    queue: List[Tuple[int, int]] = []

    def cell_world(cx: int, cy: int) -> Tuple[float, float, float]:
        return (
            cx * MODULE_CM + MODULE_CM * 0.5,
            cy * MODULE_CM + MODULE_CM * 0.5,
            z_probe,
        )

    def neighbours(cx: int, cy: int) -> Iterable[Tuple[int, int]]:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yield (cx + dx, cy + dy)

    # Seed flood from EXTERIOR cells on the grid border.
    ox, oy = layer.origin_cell
    for lx in range(layer.width):
        for ly in range(layer.height):
            cx, cy = ox + lx, oy + ly
            role = layer.cells[ly][lx]
            if role == CellRole.COURTYARD:
                continue
            on_border = lx == 0 or ly == 0 or lx == layer.width - 1 or ly == layer.height - 1
            if on_border and role == CellRole.EXTERIOR:
                queue.append((cx, cy))

    while queue:
        cx, cy = queue.pop()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        role = layer.role_at(cx, cy)
        if role is None:
            continue
        if (cx, cy) in blocked:
            continue
        if role == CellRole.INTERIOR:
            leaks.append(((cx, cy), cell_world(cx, cy)))
            continue
        if role in (CellRole.COURTYARD, CellRole.VOID):
            continue
        for n in neighbours(cx, cy):
            if n not in visited:
                queue.append(n)

    return leaks


def _mark_cells_blocked_by_aabb(
    layer: FloorPlanLayer,
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    blocked: set[Tuple[int, int]],
) -> None:
    ox, oy = layer.origin_cell
    cx0 = int(math.floor(bb_min[0] / MODULE_CM))
    cy0 = int(math.floor(bb_min[1] / MODULE_CM))
    cx1 = int(math.ceil(bb_max[0] / MODULE_CM))
    cy1 = int(math.ceil(bb_max[1] / MODULE_CM))
    for cx in range(cx0, cx1 + 1):
        for cy in range(cy0, cy1 + 1):
            wx0 = cx * MODULE_CM
            wy0 = cy * MODULE_CM
            wx1 = wx0 + MODULE_CM
            wy1 = wy0 + MODULE_CM
            if min(bb_max[0], wx1) - max(bb_min[0], wx0) > TOL_CM and min(bb_max[1], wy1) - max(
                bb_min[1], wy0
            ) > TOL_CM:
                if layer.role_at(cx, cy) is not None:
                    blocked.add((cx, cy))


# --- §7.6 floor coverage -----------------------------------------------------


def _check_floor_coverage(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    floors_by_level: Dict[int, List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]] = {}
    for p in assembly.placements:
        if not _is_floor_like(p):
            continue
        floors_by_level.setdefault(p.level, []).append(_placement_aabb(p))

    for level, layer in sorted(assembly.floor_plan.items()):
        ox, oy = layer.origin_cell
        floor_z = level * STOREY_CM
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if role != CellRole.INTERIOR:
                    continue
                cx, cy = ox + lx, oy + ly
                cell_min = (cx * MODULE_CM, cy * MODULE_CM, floor_z - FLOOR_T_CM - TOL_CM)
                cell_max = (
                    (cx + 1) * MODULE_CM,
                    (cy + 1) * MODULE_CM,
                    floor_z + TOL_CM,
                )
                covered = False
                for fmin, fmax in floors_by_level.get(level, []):
                    if aabb_intersects(cell_min, cell_max, fmin, fmax):
                        covered = True
                        break
                if not covered:
                    xyz = (
                        cx * MODULE_CM + MODULE_CM * 0.5,
                        cy * MODULE_CM + MODULE_CM * 0.5,
                        floor_z,
                    )
                    failures.append(
                        Failure(
                            check="floor_coverage",
                            message=(
                                f"missing floor slab under INTERIOR cell "
                                f"({cx}, {cy}) level {level}"
                            ),
                            world_xyz=xyz,
                            piece_id=None,
                            critical=False,
                        )
                    )
    return failures


# --- §7.7 stair reachability -------------------------------------------------


def _check_stair_reachability(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    if assembly.storeys <= 1:
        return failures

    reached = {0}
    edges = assembly.circulation
    changed = True
    while changed:
        changed = False
        for e in edges:
            if e.from_level in reached and e.to_level not in reached:
                reached.add(e.to_level)
                changed = True
            if e.to_level in reached and e.from_level not in reached:
                reached.add(e.from_level)
                changed = True

    for level in range(assembly.storeys):
        if level not in reached:
            failures.append(
                Failure(
                    check="stair_reachability",
                    message=f"storey {level} unreachable from ground via circulation graph",
                    world_xyz=(0.0, 0.0, level * STOREY_CM),
                    piece_id=None,
                    critical=True,
                )
            )
    return failures


# --- §7.8 run fit ------------------------------------------------------------


def _check_run_fit(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    for run in assembly.wall_runs:
        length = run.end_cm - run.start_cm
        if length <= 0:
            continue
        leftover = length % MODULE_CM
        if leftover <= TOL_CM or leftover >= MODULE_CM - TOL_CM:
            continue
        scale = (length + (MODULE_CM - leftover)) / length
        mid = (run.start_cm + run.end_cm) * 0.5
        if run.axis == "y":
            xyz = (run.plane_cm, mid, run.level * STOREY_CM)
        else:
            xyz = (mid, run.plane_cm, run.level * STOREY_CM)
        failures.append(
            Failure(
                check="run_fit",
                message=(
                    f"wall run {run.run_id} leftover {leftover:.1f} cm "
                    f"(scale factor {scale:.4f} to close)"
                ),
                world_xyz=xyz,
                piece_id=run.piece_ids[0] if run.piece_ids else None,
                critical=False,
            )
        )
    return failures


# --- §7.9 aperture sanity ----------------------------------------------------


def _check_aperture_sanity(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    policy = assembly.aperture_policy
    layer_map = assembly.floor_plan

    for ap in assembly.apertures:
        sill_above_floor = ap.sill_z_cm - ap.floor_z_cm
        if ap.kind == "door":
            if sill_above_floor > TOL_CM:
                failures.append(
                    Failure(
                        check="aperture_sanity",
                        message=(
                            f"door {ap.piece_id} sill {sill_above_floor:.1f} cm "
                            f"above floor — doors must reach the floor"
                        ),
                        world_xyz=ap.world_xyz,
                        piece_id=ap.piece_id,
                        critical=False,
                    )
                )
        elif ap.kind == "window":
            if sill_above_floor <= TOL_CM:
                failures.append(
                    Failure(
                        check="aperture_sanity",
                        message=f"window {ap.piece_id} sill at floor level",
                        world_xyz=ap.world_xyz,
                        piece_id=ap.piece_id,
                        critical=False,
                    )
                )
            elif not (
                policy.window_sill_min_cm - TOL_CM
                <= sill_above_floor
                <= policy.window_sill_max_cm + TOL_CM
            ):
                failures.append(
                    Failure(
                        check="aperture_sanity",
                        message=(
                            f"window {ap.piece_id} sill height {sill_above_floor:.1f} cm "
                            f"outside band "
                            f"[{policy.window_sill_min_cm}, {policy.window_sill_max_cm}]"
                        ),
                        world_xyz=ap.world_xyz,
                        piece_id=ap.piece_id,
                        critical=False,
                    )
                )

        if ap.kind == "door":
            failures.extend(_check_door_walkable(ap, layer_map))

    return failures


def _check_door_walkable(
    ap,
    layer_map: Dict[int, FloorPlanLayer],
) -> List[Failure]:
    failures: List[Failure] = []
    layer = layer_map.get(ap.level)
    if layer is None:
        return failures

    def interior_walkable(cell: Tuple[int, int]) -> bool:
        role = layer.role_at(cell[0], cell[1])
        return role in (CellRole.INTERIOR, CellRole.STAIR, CellRole.DOOR)

    def exterior_walkable(cell: Tuple[int, int]) -> bool:
        role = layer.role_at(cell[0], cell[1])
        if role is None:
            return True
        return role in (
            CellRole.EXTERIOR,
            CellRole.COURTYARD,
            CellRole.DOOR,
        )

    if not interior_walkable(ap.interior_cell):
        failures.append(
            Failure(
                check="aperture_sanity",
                message=(
                    f"door {ap.piece_id} interior side cell "
                    f"{ap.interior_cell} is not walkable"
                ),
                world_xyz=ap.world_xyz,
                piece_id=ap.piece_id,
                critical=False,
            )
        )
    if not exterior_walkable(ap.exterior_cell):
        failures.append(
            Failure(
                check="aperture_sanity",
                message=(
                    f"door {ap.piece_id} exterior side cell "
                    f"{ap.exterior_cell} is not walkable"
                ),
                world_xyz=ap.world_xyz,
                piece_id=ap.piece_id,
                critical=False,
            )
        )
    return failures


__all__ = ["validate"]

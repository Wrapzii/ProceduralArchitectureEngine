"""Validation stage (§7) — WP-1 owns this module.

Acceptance: report.ok is True and report.critical is empty.
Export must refuse to run when critical defects exist.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Set, Tuple

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

# S-130 / roadmap 2.1 m standing clearance above walkable surfaces (not CHEST_HEIGHT_CM).
HEADROOM_CLEARANCE_CM = 210.0

# Roadmap §1.4 — vertically stacked openings must share a plan centre line.
APERTURE_ALIGNMENT_TOL_CM = TOL_CM


def validate(assembly: Assembly) -> Tuple[Assembly, Report]:
    """Validate an assembly. Returns (assembly, report)."""
    failures: List[Failure] = []
    failures.extend(_check_end_connectivity(assembly))
    failures.extend(_check_vertical_support(assembly))
    failures.extend(_check_collinear_gaps(assembly))
    failures.extend(_check_tower_hall_kiss(assembly))
    failures.extend(_check_interpenetration(assembly))
    failures.extend(_check_enclosure(assembly))
    failures.extend(_check_floor_coverage(assembly))
    failures.extend(_check_fitout_containment(assembly))
    failures.extend(_check_double_height_no_floor(assembly))
    failures.extend(_check_room_specs(assembly))
    failures.extend(_check_stair_reachability(assembly))
    failures.extend(_check_stair_exit_clearance(assembly))
    failures.extend(_check_classroom_corridor_connectivity(assembly))
    failures.extend(_check_corridor_stair_connectivity(assembly))
    failures.extend(_check_run_fit(assembly))
    failures.extend(_check_aperture_sanity(assembly))
    failures.extend(_check_no_bare_aperture_holes(assembly))
    failures.extend(_check_aperture_alignment(assembly))
    failures.extend(_check_structural_islands(assembly))
    failures.extend(_check_canopy_attachment(assembly))
    failures.extend(_check_roof_bears_on_wall(assembly))
    failures.extend(_check_roof_penetration(assembly))
    failures.extend(_check_roof_valley_join(assembly))
    failures.extend(_check_band_attachment(assembly))
    failures.extend(_check_aperture_reachability(assembly))
    failures.extend(_check_tower_entry_door(assembly))
    failures.extend(_check_upper_entrance_landing(assembly))
    failures.extend(_check_storey_egress(assembly))
    failures.extend(_check_stair_landing_clearance(assembly))
    failures.extend(_check_stair_typology_match(assembly))
    failures.extend(_check_headroom(assembly))
    failures.extend(_check_roof_covers_enclosed(assembly))
    failures.extend(_check_spiral_shell(assembly))
    failures.extend(_check_tower_ramparts(assembly))
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
    # Rule 5.1: ``p.cell`` is the placement anchor for world transforms — intentional here.
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

# A wall end must meet *structure*, not a stray prop or marker. Counting any AABB
# as a joint was a false negative: a dangling run "connected" to a brazier still
# left a hole in the façade. Floors/ground remain valid abutments (partition ends
# often meet the deck at a free tip); props/bands/markers do not.
_END_CONNECT_KINDS = frozenset(
    {
        "wall",
        "tower_arc",
        "tower_crown",
        "tower_cap",
        "battlement",
        "column",
        "stair",
        "floor",
        "roof",
        "ground",
    }
)


def _counts_for_end_connectivity(other: SolidPlacement) -> bool:
    if other.kind in _END_CONNECT_KINDS:
        return True
    if other.kind == "barrier" and (
        "parapet" in other.tags or "battlement" in other.tags
    ):
        return True
    return False


def _check_end_connectivity(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    solids = assembly.placements
    for wall in solids:
        if not _is_wall(wall):
            continue
        # Drum window overlays are short rim shells on the annulus — their free
        # ends are not façade joints (Phase 0.6). Connectivity is via AABB touch
        # to the drum (freestanding), not wall-end probes.
        if "drum_window" in wall.tags or wall.piece_id.startswith("tower_win_"):
            continue
        for end_name, world_xyz, probe in _wall_end_faces(wall):
            pmin, pmax = probe
            hit = False
            for other in solids:
                if other.piece_id == wall.piece_id:
                    continue
                if not _counts_for_end_connectivity(other):
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
                            f"({wall.asset_id}) — no structure within {TOL_CM} cm"
                        ),
                        world_xyz=world_xyz,
                        piece_id=wall.piece_id,
                        critical=True,
                    )
                )
    return failures


# --- §7.2 vertical support ---------------------------------------------------

# Parapet / battlement must bear on a wall head (or designed bearer), not merely
# rest on posts/props. Primary roof decks use the dedicated ``roof_bears_on_wall``
# check (@VAL_ROOF_CONNECT) — do not double-fail roofs here.
_WALL_HEAD_BORNE = frozenset({"battlement"})


def _needs_wall_head_bearing(p: SolidPlacement) -> bool:
    if p.kind in _WALL_HEAD_BORNE:
        return True
    return p.kind == "barrier" and "parapet" in p.tags


def _is_wall_head_bearer(other: SolidPlacement) -> bool:
    """Pieces whose top may legitimately carry a parapet or battlement."""
    if other.kind in ("wall", "tower_arc", "battlement", "roof"):
        return True
    if other.kind == "barrier" and "parapet" in other.tags:
        return True
    if other.kind in ("floor", "ground"):
        return True
    return False


def _piece_supports_at(
    supported: SolidPlacement,
    supporter: SolidPlacement,
    *,
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    bottom_z: float,
    tol: float,
) -> bool:
    if supporter.piece_id == supported.piece_id:
        return False
    omin, omax = _placement_aabb(supporter)
    if abs(omin[2] - bottom_z) > tol and abs(omax[2] - bottom_z) > tol:
        if not (omin[2] < bottom_z <= omax[2] + tol):
            return False
    else:
        top = omax[2]
        if abs(top - bottom_z) > tol:
            return False
    return _xy_footprint_overlap(
        bb_min, bb_max, omin, omax, _support_overlap_tol(bb_min, bb_max, tol)
    )


def _check_vertical_support(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    tol = VERTICAL_SUPPORT_TOL_CM
    for p in assembly.placements:
        if p.kind == "ground":
            continue
        if p.kind == "band":
            # DOCUMENTED EXEMPTION (Handbook §3). A stringcourse at mid-storey has nothing
            # beneath it and never will — it is carried by the face it is fixed to. The
            # band_attachment check replaces this one for this kind, with four conditions
            # rather than one, so "attached" means attached, not merely "touching".
            continue
        bb_min, bb_max = _placement_aabb(p)
        bottom_z = bb_min[2]
        if bottom_z <= tol:
            continue
        supporters = [
            other
            for other in assembly.placements
            if _piece_supports_at(
                p, other, bb_min=bb_min, bb_max=bb_max, bottom_z=bottom_z, tol=tol
            )
        ]
        if not supporters:
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
            continue
        if _needs_wall_head_bearing(p) and not any(
            _is_wall_head_bearer(s) for s in supporters
        ):
            failures.append(
                Failure(
                    check="vertical_support",
                    message=(
                        f"wall-head bearing missing for {p.piece_id} ({p.asset_id}) — "
                        f"parapet/battlement must rest on a wall (or designed bearer), "
                        f"not posts alone"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


def _support_overlap_tol(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    tol: float,
) -> float:
    """XY overlap a piece needs before it counts as supported.

    The vertical tolerance (35 cm) was being reused as the horizontal one, so any piece
    THINNER than 35 cm could never be supported by anything: an 11 cm railing standing
    squarely on a floor slab reported as floating. The threshold has to scale with the
    piece being tested, not with a constant that only suits walls and slabs.

    Half the piece's smaller footprint dimension, capped at the vertical tolerance: a
    railing needs 5.5 cm of slab under it, a wall still needs the full 35 cm.
    """
    smallest = min(bb_max[0] - bb_min[0], bb_max[1] - bb_min[1])
    return min(tol, max(0.0, smallest * 0.5))


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


def _cluster_spans_by_plane(
    items: List[Tuple[float, str, float, float]],
    *,
    tol: float = TOL_CM,
) -> List[Tuple[float, List[Tuple[str, float, float]]]]:
    """Cluster collinear spans whose planes lie within a diameter of *tol*.

    Exact ``round(plane, 3)`` bucketing missed gaps when two segments of the same
    face differed by a few centimetres (still within ``TOL_CM``) — a false negative
    for wall-run continuity. Diameter ≤ tol keeps opposite faces (WALL_T apart)
    in separate clusters.
    """
    if not items:
        return []
    ordered = sorted(items, key=lambda t: (t[0], t[2], t[1]))
    clusters: List[List[Tuple[float, str, float, float]]] = [[ordered[0]]]
    for item in ordered[1:]:
        cluster = clusters[-1]
        plane_min = cluster[0][0]
        if item[0] - plane_min <= tol:
            cluster.append(item)
        else:
            clusters.append([item])
    out: List[Tuple[float, List[Tuple[str, float, float]]]] = []
    for cluster in clusters:
        plane = sum(c[0] for c in cluster) / len(cluster)
        spans = [(pid, a, b) for _, pid, a, b in cluster]
        out.append((plane, spans))
    return out


def _emit_collinear_span_gaps(
    *,
    level: int,
    axis: str,
    plane: float,
    spans: List[Tuple[str, float, float]],
    run_id: str = "",
) -> List[Failure]:
    failures: List[Failure] = []
    spans = sorted(spans, key=lambda s: s[1])
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
            where = f"in run {run_id}" if run_id else f"on level {level}"
            failures.append(
                Failure(
                    check="collinear_gap",
                    message=(
                        f"collinear gap {gap:.1f} cm between {id_a} and {id_b} {where}"
                    ),
                    world_xyz=xyz,
                    piece_id=id_a,
                    critical=False,
                )
            )
    return failures


def _check_collinear_gaps(assembly: Assembly) -> List[Failure]:
    failures: List[Failure] = []
    pieces = _piece_map(assembly)

    groups: Dict[Tuple[int, str], List[Tuple[float, str, float, float]]] = {}
    for wall in assembly.placements:
        if not _is_wall(wall):
            continue
        if "drum_window" in wall.tags or wall.piece_id.startswith("tower_win_"):
            continue
        bb_min, bb_max = _placement_aabb(wall)
        axis = _wall_long_axis(wall)
        if axis == "y":
            plane = bb_min[0]
            span = (bb_min[1], bb_max[1])
        else:
            plane = bb_min[1]
            span = (bb_min[0], bb_max[0])
        groups.setdefault((wall.level, axis), []).append(
            (plane, wall.piece_id, span[0], span[1])
        )

    for (level, axis), items in groups.items():
        for plane, spans in _cluster_spans_by_plane(items):
            failures.extend(
                _emit_collinear_span_gaps(
                    level=level, axis=axis, plane=plane, spans=spans
                )
            )

    if assembly.wall_runs:
        for run in assembly.wall_runs:
            if len(run.piece_ids) > 1:
                failures.extend(_gaps_along_run(run, pieces))
    return failures


def _gaps_along_run(run: WallRun, pieces: Dict[str, SolidPlacement]) -> List[Failure]:
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
    return _emit_collinear_span_gaps(
        level=run.level,
        axis=run.axis,
        plane=run.plane_cm,
        spans=spans,
        run_id=run.run_id,
    )


# --- §7.3b tower ↔ hall kiss -------------------------------------------------


def _is_hall_envelope_wall(p: SolidPlacement) -> bool:
    """Hall / range wall — not a tower drum overlay or tower-tagged shell piece."""
    if p.kind != "wall":
        return False
    if "drum_window" in p.tags or p.piece_id.startswith("tower_win_"):
        return False
    if "tower" in p.tags:
        return False
    return True


def _check_tower_hall_kiss(assembly: Assembly) -> List[Failure]:
    """Every tower drum arc must AABB-kiss a hall wall within ``TOL_CM``.

    WHY: Ledger C-5 shipped a fully detached tower. ``freestanding`` catches islands,
    but a drum that sits near the hall with an air gap can still join the touch graph
    via stairs/floors. Engineering continuity requires the attach *kiss* itself.
    Freestanding drums fail; wall-attached drums (M3) pass.
    """
    arcs = [p for p in assembly.placements if p.kind == "tower_arc"]
    if not arcs:
        return []
    hall_walls = [p for p in assembly.placements if _is_hall_envelope_wall(p)]
    if not hall_walls:
        return []

    hall_boxes = [_placement_aabb(w) for w in hall_walls]
    failures: List[Failure] = []
    for arc in arcs:
        amin, amax = _placement_aabb(arc)
        if any(aabb_intersects(amin, amax, h[0], h[1]) for h in hall_boxes):
            continue
        failures.append(
            Failure(
                check="tower_hall_kiss",
                message=(
                    f"tower drum {arc.piece_id} ({arc.asset_id}) does not kiss a "
                    f"hall wall within {TOL_CM} cm — freestanding or air-gapped attach"
                ),
                world_xyz=_centre(amin, amax),
                piece_id=arc.piece_id,
                critical=True,
            )
        )
    return failures


# --- §7.4 interpenetration ---------------------------------------------------

# Tower kit kinds placed at the same cell (§2.2 centred annulus).
_TOWER_SOLID_KINDS = frozenset({"tower_arc", "tower_crown", "tower_cap"})
# Roof decks that tuck over perimeter walls at the eave (§6 / assemble).
_ROOF_DECK_ASSET_IDS = frozenset(
    {
        "roof_flat",
        "roof_pitched_slope",
        "roof_gable_infill",
        "roof_hip",
        "roof_valley",
    }
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
        # Phase 4.7 crown deck + crenel shells co-occupy the drum cell with the
        # junction/crown/cap stack (designed contact — not a penetration demotion).
        if "tower_deck" in other.tags or "tower_crenel" in other.tags:
            return tower.level == other.level
        if other.kind == "battlement" and "tower" in other.tags:
            return tower.level == other.level
        if other.kind == "floor" and "tower_deck" in other.tags:
            return tower.level == other.level
    tags_a, tags_b = set(a.tags), set(b.tags)
    if {"tower_deck", "tower_crenel", "tower_rampart"} & tags_a and {
        "tower_deck",
        "tower_crenel",
        "tower_rampart",
    } & tags_b:
        return a.level == b.level
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


def _designed_roof_valley_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Valley stub overlaps abutting hip/slope decks on the wing seam (S-019)."""
    ids = {a.asset_id, b.asset_id}
    if "roof_valley" not in ids:
        return False
    partners = ids - {"roof_valley"}
    if not partners.issubset({"roof_hip", "roof_pitched_slope", "roof_gable_infill"}):
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
    if _designed_roof_valley_pair(a, b):
        return True
    # Spiral newel shares the drum cell with helix quarters / tower_arc AABBs.
    from pae.spiral_shell import designed_spiral_newel_pair

    if designed_spiral_newel_pair(a, b):
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
        if role == CellRole.INTERIOR or role in (
            CellRole.CORRIDOR,
            CellRole.CLASSROOM,
        ):
            leaks.append(((cx, cy), cell_world(cx, cy)))
            continue
        if role in (CellRole.COURTYARD, CellRole.VOID, CellRole.DOUBLE_VOID):
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


def _check_fitout_containment(assembly: Assembly) -> List[Failure]:
    """Phase 2.5 — greybox fit-out props must stay inside rooms on the floor slab.

    Applies only to props tagged ``fitout_greybox`` (M5 AssetDB props are unaffected).
    """
    from pae.fitout import _has_declared_hall, is_fitout_cell

    failures: List[Failure] = []
    if not assembly.floor_plan:
        return failures

    hall_declared = _has_declared_hall(assembly)

    for p in assembly.placements:
        if "fitout_greybox" not in p.tags:
            continue
        level = p.level
        cell = p.cell
        if not is_fitout_cell(
            assembly.floor_plan, level, cell, hall_declared=hall_declared
        ):
            failures.append(
                Failure(
                    check="fitout_containment",
                    message=(
                        f"fit-out prop {p.piece_id} at cell {cell} level {level} "
                        "is not in a CLASSROOM or great_hall cell"
                    ),
                    world_xyz=(
                        cell[0] * MODULE_CM + MODULE_CM * 0.5,
                        cell[1] * MODULE_CM + MODULE_CM * 0.5,
                        level * STOREY_CM,
                    ),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
            continue

        floor_z = level * STOREY_CM
        pmin, pmax = _placement_aabb(p)
        if abs(pmin[2] - floor_z) > TOL_CM:
            failures.append(
                Failure(
                    check="fitout_containment",
                    message=(
                        f"fit-out prop {p.piece_id} bottom z={pmin[2]:.1f} cm "
                        f"is not on floor top z={floor_z:.1f} cm"
                    ),
                    world_xyz=_centre(pmin, pmax),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )

        cell_x0 = cell[0] * MODULE_CM - TOL_CM
        cell_y0 = cell[1] * MODULE_CM - TOL_CM
        cell_x1 = (cell[0] + 1) * MODULE_CM + TOL_CM
        cell_y1 = (cell[1] + 1) * MODULE_CM + TOL_CM
        if pmin[0] < cell_x0 or pmin[1] < cell_y0 or pmax[0] > cell_x1 or pmax[1] > cell_y1:
            failures.append(
                Failure(
                    check="fitout_containment",
                    message=(
                        f"fit-out prop {p.piece_id} footprint extends outside "
                        f"cell {cell} bounds"
                    ),
                    world_xyz=_centre(pmin, pmax),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


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
                if role not in (
                    CellRole.INTERIOR,
                    CellRole.CORRIDOR,
                    CellRole.CLASSROOM,
                ):
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
                                f"missing floor slab under {role.name} cell "
                                f"({cx}, {cy}) level {level}"
                            ),
                            world_xyz=xyz,
                            piece_id=None,
                            critical=False,
                        )
                    )
    return failures


def _cell_has_solid_floor(
    assembly: Assembly,
    level: int,
    cx: int,
    cy: int,
    floor_z: float,
) -> bool:
    """True when a solid (non-hole) floor pad plugs *cell* — Rule 5.1 via ``covered_cells``."""
    from pae.trim import covered_cells

    cell = (cx, cy)
    if any(
        p.asset_id == "floor_hole" and p.level == level and cell in covered_cells(p)
        for p in assembly.placements
    ):
        return False
    for p in assembly.placements:
        if p.kind != "floor" or p.level != level or p.asset_id == "floor_hole":
            continue
        if cell not in covered_cells(p):
            continue
        if _is_spanning_floor(p):
            continue
        return True
    return False


def _check_double_height_no_floor(assembly: Assembly) -> List[Failure]:
    """Double-height volumes must not carry a solid floor on intermediate storeys."""
    failures: List[Failure] = []
    hole_cells_by_level: Dict[int, set[Tuple[int, int]]] = {}
    for p in assembly.placements:
        if p.asset_id == "floor_hole" and p.kind == "floor":
            hole_cells_by_level.setdefault(p.level, set()).add(p.cell)

    for level, layer in sorted(assembly.floor_plan.items()):
        if level == 0:
            continue
        floor_z = level * STOREY_CM
        holes = hole_cells_by_level.get(level, set())
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                if layer.cells[ly][lx] != CellRole.DOUBLE_VOID:
                    continue
                cx, cy = ox + lx, oy + ly
                if (cx, cy) in holes:
                    continue
                if _cell_has_solid_floor(assembly, level, cx, cy, floor_z):
                    failures.append(
                        Failure(
                            check="double_height_no_floor",
                            message=(
                                f"solid floor under DOUBLE_VOID cell ({cx}, {cy}) "
                                f"level {level}"
                            ),
                            world_xyz=(
                                cx * MODULE_CM + MODULE_CM * 0.5,
                                cy * MODULE_CM + MODULE_CM * 0.5,
                                floor_z,
                            ),
                            critical=True,
                        )
                    )
    return failures


def _cell_role_is(role: object, expected: CellRole) -> bool:
    """Compare CellRole by value so reload_pae() stale imports do not false-fail.

    ``reload_pae`` drops ``pae.*`` from ``sys.modules``; suites that keep a
    pre-reload ``from pae.plan import CellRole`` then assemble with a fresh
    enum identity. ``role == expected`` is False across those enums even when
    both are DOUBLE_VOID (value 9). Value compare keeps room_spec fail-closed
    on real missing voids without flake criticals.
    """
    if role == expected:
        return True
    value = getattr(role, "value", None)
    return value is not None and value == expected.value


def _check_room_specs(assembly: Assembly) -> List[Failure]:
    """Optional program checks when room_specs were declared on the spec."""
    failures: List[Failure] = []
    if not assembly.room_specs:
        return failures

    classroom_cells = 0
    hall_cells = 0
    double_void_cells = 0
    for level, layer in sorted(assembly.floor_plan.items()):
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if _cell_role_is(role, CellRole.CLASSROOM):
                    classroom_cells += 1
                elif _cell_role_is(role, CellRole.INTERIOR) and level == 0:
                    hall_cells += 1
                if _cell_role_is(role, CellRole.DOUBLE_VOID):
                    double_void_cells += 1

    for room in assembly.room_specs:
        kind = str(room.get("kind", "")).lower()
        name = str(room.get("name", kind))
        if kind == "classroom":
            min_bays = room.get("area_bays")
            if min_bays is not None and classroom_cells < int(min_bays):
                failures.append(
                    Failure(
                        check="room_spec",
                        message=(
                            f"room {name!r} expects >= {min_bays} classroom cells, "
                            f"got {classroom_cells}"
                        ),
                        world_xyz=None,
                        critical=False,
                    )
                )
        elif kind == "hall" and hall_cells == 0:
            failures.append(
                Failure(
                    check="room_spec",
                    message=f"declared hall room {name!r} but plan has no hall interior",
                    world_xyz=None,
                    critical=False,
                )
            )
        if room.get("double_height"):
            if double_void_cells == 0:
                failures.append(
                    Failure(
                        check="room_spec",
                        message=(
                            f"room {name!r} is double_height but plan has no "
                            "DOUBLE_VOID cells"
                        ),
                        world_xyz=None,
                        critical=True,
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


# --- school classroom ↔ corridor ---------------------------------------------

_FACE_TOWARD_DELTA: Dict[str, Tuple[int, int]] = {
    "east": (1, 0),
    "west": (-1, 0),
    "north": (0, 1),
    "south": (0, -1),
}


def _face_toward(
    from_cell: Tuple[int, int], to_cell: Tuple[int, int]
) -> str | None:
    fx, fy = from_cell
    tx, ty = to_cell
    for face, (dx, dy) in _FACE_TOWARD_DELTA.items():
        if tx == fx + dx and ty == fy + dy:
            return face
    return None


def _partition_face_from_tags(tags: Iterable[str]) -> str | None:
    for tag in tags:
        if tag.startswith("face_"):
            return tag[5:]
    return None


def _is_partition_door(p: SolidPlacement) -> bool:
    tags = set(getattr(p, "tags", ()) or ())
    if "partition" not in tags:
        return False
    return "door" in tags or "door" in p.asset_id


def _check_classroom_corridor_connectivity(assembly: Assembly) -> List[Failure]:
    """Every CLASSROOM cell must reach a CORRIDOR via a door partition on the shared edge.

    Buildings without classrooms skip this check. Critical when classrooms exist.
    Uses ``_cell_role_is`` so reload_pae stale CellRole enums do not false-fail.
    """
    from pae.trim import covered_cells

    failures: List[Failure] = []
    door_faces: set[Tuple[int, int, int, str]] = set()
    for p in assembly.placements:
        if not _is_partition_door(p):
            continue
        face = _partition_face_from_tags(p.tags)
        if face is None:
            continue
        # Rule 5.1: partition doors may span bays — register every covered cell.
        for c in covered_cells(p):
            door_faces.add((p.level, c[0], c[1], face))

    for level, layer in sorted(assembly.floor_plan.items()):
        ox, oy = layer.origin_cell
        classrooms: List[Tuple[int, int]] = []
        corridors: set[Tuple[int, int]] = set()
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                cx, cy = ox + lx, oy + ly
                if _cell_role_is(role, CellRole.CLASSROOM):
                    classrooms.append((cx, cy))
                elif _cell_role_is(role, CellRole.CORRIDOR):
                    corridors.add((cx, cy))
        if not classrooms:
            continue
        if not corridors:
            failures.append(
                Failure(
                    check="classroom_corridor",
                    message=f"storey {level} has classrooms but no corridor cells",
                    world_xyz=(0.0, 0.0, float(level * STOREY_CM)),
                    critical=True,
                )
            )
            continue
        for cx, cy in classrooms:
            corridor_neighbors = [
                (cx + dx, cy + dy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (cx + dx, cy + dy) in corridors
            ]
            if not corridor_neighbors:
                failures.append(
                    Failure(
                        check="classroom_corridor",
                        message=(
                            f"classroom cell ({cx}, {cy}) level {level} "
                            "does not adjoin a corridor"
                        ),
                        world_xyz=(
                            cx * MODULE_CM + MODULE_CM * 0.5,
                            cy * MODULE_CM + MODULE_CM * 0.5,
                            float(level * STOREY_CM),
                        ),
                        critical=True,
                    )
                )
                continue
            has_door = any(
                (level, cx, cy, face) in door_faces
                for n in corridor_neighbors
                if (face := _face_toward((cx, cy), n)) is not None
            )
            if not has_door:
                failures.append(
                    Failure(
                        check="classroom_corridor",
                        message=(
                            f"classroom cell ({cx}, {cy}) level {level} "
                            "has no door partition facing its corridor neighbor"
                        ),
                        world_xyz=(
                            cx * MODULE_CM + MODULE_CM * 0.5,
                            cy * MODULE_CM + MODULE_CM * 0.5,
                            float(level * STOREY_CM),
                        ),
                        critical=True,
                    )
                )
    return failures


def _stair_well_xy(assembly: Assembly) -> Set[Tuple[int, int]]:
    """Plan XY of the stair well — any cell that is STAIR on some storey."""
    wells: Set[Tuple[int, int]] = set()
    for layer in assembly.floor_plan.values():
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                if _cell_role_is(layer.cells[ly][lx], CellRole.STAIR):
                    wells.add((ox + lx, oy + ly))
    return wells


def _corridor_reaches_goals(
    corridors: Set[Tuple[int, int]],
    goals: Set[Tuple[int, int]],
) -> bool:
    """Every 4-connected CORRIDOR component must touch a stair/void goal."""
    if not corridors or not goals:
        return False
    from collections import deque

    remaining = set(corridors)
    while remaining:
        start = min(remaining)
        comp: Set[Tuple[int, int]] = set()
        q: deque[Tuple[int, int]] = deque([start])
        remaining.discard(start)
        touches = False
        while q:
            cx, cy = q.popleft()
            comp.add((cx, cy))
            if (cx, cy) in goals:
                touches = True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cx + dx, cy + dy)
                if n in goals:
                    touches = True
                if n in remaining:
                    remaining.discard(n)
                    q.append(n)
        if not touches:
            return False
    return True


def _check_corridor_stair_connectivity(assembly: Assembly) -> List[Failure]:
    """Phase 2.3: every CORRIDOR component must reach the stair well via CORRIDOR cells.

    Skip when the building has no corridor program or no stair well. Critical when
    both exist — rooms hang off the corridor; the corridor must reach every stair.
    """
    failures: List[Failure] = []
    wells = _stair_well_xy(assembly)
    if not wells:
        return failures

    for level, layer in sorted(assembly.floor_plan.items()):
        ox, oy = layer.origin_cell
        corridors: Set[Tuple[int, int]] = set()
        goals: Set[Tuple[int, int]] = set()
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                cx, cy = ox + lx, oy + ly
                if _cell_role_is(role, CellRole.CORRIDOR):
                    corridors.add((cx, cy))
                if (cx, cy) in wells and (
                    _cell_role_is(role, CellRole.STAIR)
                    or _cell_role_is(role, CellRole.VOID)
                ):
                    goals.add((cx, cy))
        if not corridors:
            continue
        if not goals:
            failures.append(
                Failure(
                    check="corridor_stair",
                    message=(
                        f"storey {level} has corridor cells but no stair/void "
                        "well cells to reach"
                    ),
                    world_xyz=(0.0, 0.0, float(level * STOREY_CM)),
                    critical=True,
                )
            )
            continue
        if not _corridor_reaches_goals(corridors, goals):
            sample = next(iter(sorted(corridors)))
            failures.append(
                Failure(
                    check="corridor_stair",
                    message=(
                        f"corridor on storey {level} does not reach a stair "
                        f"(sample cell {sample})"
                    ),
                    world_xyz=(
                        sample[0] * MODULE_CM + MODULE_CM * 0.5,
                        sample[1] * MODULE_CM + MODULE_CM * 0.5,
                        float(level * STOREY_CM),
                    ),
                    critical=True,
                )
            )
    return failures


# --- §7.7b stair exit clearance (no wall / ceiling dead-ends) ----------------


def placement_footprint_cells(p: SolidPlacement) -> List[Tuple[int, int]]:
    """Module cells covered by a placement's XY footprint (anchor = min corner).

    Legacy anchor+extent heuristic for stair tests. Spatial queries in validators must
    use ``pae.trim.covered_cells`` (Rule 5.1) — yawed / spanning pieces differ here.
    """
    sx, sy = float(p.size_cm[0]), float(p.size_cm[1])
    yaw = int(p.yaw) % 360
    if yaw in (90, 270):
        sx, sy = sy, sx
    nx = max(1, int(round(sx / MODULE_CM)))
    ny = max(1, int(round(sy / MODULE_CM)))
    cx, cy = int(p.cell[0]), int(p.cell[1])
    return [(cx + i, cy + j) for i in range(nx) for j in range(ny)]


def _is_module_solid_floor(p: SolidPlacement) -> bool:
    """True for a 1×1 solid floor pad (not a hole rim, not a spanning deck)."""
    if p.kind != "floor" or p.asset_id == "floor_hole":
        return False
    return (
        float(p.size_cm[0]) <= MODULE_CM + TOL_CM
        and float(p.size_cm[1]) <= MODULE_CM + TOL_CM
    )


def _is_spanning_floor(p: SolidPlacement) -> bool:
    if p.kind != "floor" or p.asset_id == "floor_hole":
        return False
    return float(p.size_cm[0]) > MODULE_CM + TOL_CM or float(p.size_cm[1]) > MODULE_CM + TOL_CM


def _hole_inner_world_aabb(
    hole: SolidPlacement,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Inner void AABB of a floor_hole placement (world cm)."""
    from pae.primitives.floors import floor_hole_inner_aabb_cm

    local_min, local_max = floor_hole_inner_aabb_cm(
        float(hole.size_cm[0]), float(hole.size_cm[1])
    )
    # Hole placements use min-corner origin + yaw 0 in assemble.
    ox = hole.cell[0] * MODULE_CM + hole.offset_cm[0]
    oy = hole.cell[1] * MODULE_CM + hole.offset_cm[1]
    oz = hole.level * STOREY_CM + hole.offset_cm[2]
    return (
        (ox + local_min[0], oy + local_min[1], oz + local_min[2]),
        (ox + local_max[0], oy + local_max[1], oz + local_max[2]),
    )


def _stair_head_clearance_aabbs(
    stair: SolidPlacement,
    hole_by_cell: Dict[Tuple[int, int], SolidPlacement],
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Character-pass probes above each top-exit hole (must stay clear).

    Uses a centred corridor inside the hole, not the full void AABB — perimeter
    walls that only kiss the hole rim are not blockers.
    """
    from pae.trim import covered_cells

    # ~80 cm pass-through (half-extent); well inside the 380 cm hole opening.
    half = 40.0
    boxes: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    for cell in covered_cells(stair):
        hole = hole_by_cell.get(cell)
        if hole is None:
            continue
        hmin, hmax = _hole_inner_world_aabb(hole)
        cx = 0.5 * (hmin[0] + hmax[0])
        cy = 0.5 * (hmin[1] + hmax[1])
        z0 = hmax[2]
        z1 = z0 + CHEST_HEIGHT_CM
        boxes.append(
            (
                (cx - half, cy - half, z0),
                (cx + half, cy + half, z1),
            )
        )
    return boxes


def _solid_blocks_headroom(
    solid: SolidPlacement,
    head_min: Tuple[float, float, float],
    head_max: Tuple[float, float, float],
) -> bool:
    """True when a wall/roof/solid floor meaningfully fills the exit head box."""
    if solid.asset_id == "floor_hole":
        return False
    if solid.kind == "prop":
        return False
    # Drum window overlays sit on the exterior shell. Spiral stairs / decks use a
    # full-drum AABB, so a rim wall false-positives as plugging interior headroom.
    if "drum_window" in solid.tags or solid.piece_id.startswith("tower_win_"):
        return False
    # Hall→drum doorway is a passage leaf on the attach rim — walk-through, not a plug.
    if "tower_entry" in solid.tags or solid.piece_id.startswith("tower_entry_"):
        return False
    if solid.kind not in ("wall", "roof", "floor"):
        return False
    # Spanning floors are opened at holes by mesh contract; AABB still covers
    # the bay — do not treat them as blockers when holes exist (checked separately).
    if _is_spanning_floor(solid):
        return False
    smin, smax = _placement_aabb(solid)
    # Require real plug: > TOL on XY and meaningful Z bite into headroom.
    ox = min(head_max[0], smax[0]) - max(head_min[0], smin[0])
    oy = min(head_max[1], smax[1]) - max(head_min[1], smin[1])
    oz = min(head_max[2], smax[2]) - max(head_min[2], smin[2])
    return ox > TOL_CM and oy > TOL_CM and oz > TOL_CM


def _check_stair_exit_clearance(assembly: Assembly) -> List[Failure]:
    """Fail-closed: stair tops must open — never dead-end into floor/roof/wall.

    For each stair:
    1. Every ``covered_cells`` bay on the storey above needs a ``floor_hole``.
    2. No solid 1×1 floor pad may cover those bays (plugs the exit).
    3. Headroom above each hole must not be filled by wall / roof / solid floor.

    Rule 5.1: never match holes or pads by ``p.cell`` alone — spanning decks and
    yawed stairs place holes at origins that differ from the stair anchor.
    """
    from pae.trim import covered_cells

    failures: List[Failure] = []
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    if not stairs:
        return failures

    holes = [
        p
        for p in assembly.placements
        if p.asset_id == "floor_hole" and p.kind == "floor"
    ]

    for stair in stairs:
        top_level = stair.level + 1
        exit_cells = covered_cells(stair)
        hole_by_cell: Dict[Tuple[int, int], SolidPlacement] = {}
        for h in holes:
            if h.level != top_level:
                continue
            for c in covered_cells(h):
                hole_by_cell[c] = h
        smin, smax = _placement_aabb(stair)
        top_xyz = (
            0.5 * (smin[0] + smax[0]),
            0.5 * (smin[1] + smax[1]),
            smax[2],
        )

        for cell in exit_cells:
            if cell not in hole_by_cell:
                failures.append(
                    Failure(
                        check="stair_exit_clearance",
                        message=(
                            f"stair {stair.piece_id} top blocked — missing floor_hole "
                            f"at cell {cell} level {top_level} (ceiling/floor not opened)"
                        ),
                        world_xyz=top_xyz,
                        piece_id=stair.piece_id,
                        critical=True,
                    )
                )

        for p in assembly.placements:
            if p.level != top_level or not _is_module_solid_floor(p):
                continue
            plugged = covered_cells(p) & exit_cells
            if not plugged:
                continue
            failures.append(
                Failure(
                    check="stair_exit_clearance",
                    message=(
                        f"stair {stair.piece_id} top plugged by solid floor "
                        f"{p.piece_id} covering {sorted(plugged)} — use floor_hole, not a pad"
                    ),
                    world_xyz=top_xyz,
                    piece_id=p.piece_id,
                    critical=True,
                )
            )

        for head_min, head_max in _stair_head_clearance_aabbs(stair, hole_by_cell):
            for other in assembly.placements:
                if other.piece_id == stair.piece_id:
                    continue
                if other.asset_id == "floor_hole":
                    continue
                if not _solid_blocks_headroom(other, head_min, head_max):
                    continue
                failures.append(
                    Failure(
                        check="stair_exit_clearance",
                        message=(
                            f"stair {stair.piece_id} exit blocked by {other.kind} "
                            f"{other.piece_id} ({other.asset_id}) in head clearance"
                        ),
                        world_xyz=(
                            0.5 * (head_min[0] + head_max[0]),
                            0.5 * (head_min[1] + head_max[1]),
                            0.5 * (head_min[2] + head_max[2]),
                        ),
                        piece_id=other.piece_id,
                        critical=True,
                    )
                )

    return failures


# --- §7.8 run fit ------------------------------------------------------------


# --- §7.12 freestanding entities --------------------------------------------

# Kinds that are legitimately their own island: ground surfaces tile the site, and a
# boundary fence is SUPPOSED to stand apart from the building. Everything else that is
# part of the structure must be reachable from the structure.
# light_anchor: position-only UE spawn markers — not structural envelope pieces.
ISLAND_EXEMPT_KINDS = frozenset({"surface", "light_anchor"})
ISLAND_EXEMPT_TAGS = frozenset({"site", "boundary", "light_anchor", "marker"})


def _island_exempt(p: SolidPlacement) -> bool:
    return p.kind in ISLAND_EXEMPT_KINDS or bool(ISLAND_EXEMPT_TAGS & set(p.tags))


def _check_structural_islands(assembly: Assembly) -> List[Failure]:
    """Every structural piece must connect, directly or transitively, to the main mass.

    WHY: vertical support only asks "is something under me". A gallery roof carried on its
    own posts satisfies that perfectly while touching nothing else — it is a separate
    building floating beside the real one. That is exactly what shipped: the balcony roofs
    were the right height to stand up and the wrong height to meet the range roof, and the
    render showed a detached canopy that every existing check passed.

    So: build the touch graph over structural placements and require ONE component. Any
    other component is freestanding and reported with its size and location, because a
    two-piece island is a different bug from a two-hundred-piece one.
    """
    candidates = [p for p in assembly.placements if not _island_exempt(p)]
    if len(candidates) < 2:
        return []

    # Partition by BUILDING first. A site holds several buildings that are legitimately
    # separate structures; connectivity is a WITHIN-building property, not a site-wide
    # one. Without this a street of six houses reports five freestanding groups and the
    # check becomes noise the moment you build more than one thing.
    by_building: Dict[str, List[SolidPlacement]] = {}
    for p in candidates:
        mk = next((t for t in p.tags if t.startswith("building:")), "")
        by_building.setdefault(mk, []).append(p)
    if len(by_building) > 1:
        out: List[Failure] = []
        for mk, group in sorted(by_building.items()):
            out.extend(_islands_within(group, mk))
        return out
    return _islands_within(candidates, next(iter(by_building)))


def _islands_within(
    pieces: List[SolidPlacement],
    marker: str = "",
) -> List[Failure]:
    """Island check over ONE building's pieces."""
    if len(pieces) < 2:
        return []

    boxes = [_placement_aabb(p) for p in pieces]
    n = len(pieces)

    from pae.trim import covered_cells

    # Bucket by covered cells so spanning roofs/decks join the touch graph (Rule 5.1).
    buckets: Dict[Tuple[int, int], List[int]] = {}
    piece_cells: List[Set[Tuple[int, int]]] = []
    for i, p in enumerate(pieces):
        cells = covered_cells(p)
        piece_cells.append(cells)
        for c in cells:
            buckets.setdefault(c, []).append(i)

    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, p in enumerate(pieces):
        for cx, cy in piece_cells[i]:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in buckets.get((cx + dx, cy + dy), ()):
                        if j <= i:
                            continue
                        if aabb_intersects(boxes[i][0], boxes[i][1], boxes[j][0], boxes[j][1]):
                            union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    if len(groups) < 2:
        return []

    ordered = sorted(groups.values(), key=len, reverse=True)
    failures: List[Failure] = []
    for island in ordered[1:]:
        rep = pieces[island[0]]
        bb_min, bb_max = boxes[island[0]]
        names = ", ".join(sorted(pieces[i].asset_id for i in island[:4]))
        failures.append(
            Failure(
                check="freestanding",
                message=(
                    f"freestanding group of {len(island)} piece(s) not connected to the "
                    f"structure — {names}"
                ),
                world_xyz=_centre(bb_min, bb_max),
                piece_id=rep.piece_id,
                critical=True,
            )
        )
    return failures


def _check_canopy_attachment(assembly: Assembly) -> List[Failure]:
    """A roof must meet the building envelope, not merely stand on posts.

    WHY THIS IS SEPARATE FROM THE ISLAND CHECK: a gallery roof carried on columns is
    *transitively* connected — roof to post to deck to building — so the touch graph says
    it is fine. But as a roof it is a detached canopy floating beside the real roof with a
    gap between them. Shipped exactly that: gallery roofs at z 670–700 against range roofs
    at 700–730, and 7 of 16 touched no wall and no other roof.

    So the rule is about what a roof must touch, not whether it is reachable: a roof piece
    must abut a wall, a parapet, or another roof that itself abuts one. Columns do not
    count — that is the whole point.
    """
    roofs = [p for p in assembly.placements if p.kind in ("roof", "roofline")]
    if not roofs:
        return []
    envelope = [
        p
        for p in assembly.placements
        if p.kind in ("wall", "battlement", "tower_arc", "tower_crown", "tower_cap")
        or (p.kind == "barrier" and "parapet" in p.tags)
    ]
    if not envelope:
        return []

    roof_boxes = [_placement_aabb(p) for p in roofs]
    env_boxes = [_placement_aabb(p) for p in envelope]

    attached = [
        any(aabb_intersects(rb[0], rb[1], eb[0], eb[1]) for eb in env_boxes)
        for rb in roof_boxes
    ]
    # Spread attachment through roof-to-roof contact until it stops growing.
    changed = True
    while changed:
        changed = False
        for i, ok in enumerate(attached):
            if ok:
                continue
            for j, ok_j in enumerate(attached):
                if not ok_j or i == j:
                    continue
                if aabb_intersects(
                    roof_boxes[i][0], roof_boxes[i][1],
                    roof_boxes[j][0], roof_boxes[j][1],
                ):
                    attached[i] = True
                    changed = True
                    break

    failures: List[Failure] = []
    for p, box, ok in zip(roofs, roof_boxes, attached):
        if ok:
            continue
        failures.append(
            Failure(
                check="canopy_attachment",
                message=(
                    f"freestanding roof {p.piece_id} ({p.asset_id}) — meets no wall, "
                    f"parapet or attached roof; it is a detached canopy"
                ),
                world_xyz=_centre(box[0], box[1]),
                piece_id=p.piece_id,
                critical=True,
            )
        )
    return failures


# Primary roof decks that must bear on the envelope (not valley stubs alone).
_ROOF_BEARING_ASSET_IDS = frozenset(
    {
        "roof_flat",
        "roof_pitched_slope",
        "roof_gable_infill",
        "roof_hip",
    }
)


def _is_roof_bearing_support(p: SolidPlacement) -> bool:
    """Walls / parapets / battlements that can carry a roof eave."""
    if p.kind in ("wall", "battlement"):
        return True
    if p.kind == "barrier" and "parapet" in p.tags:
        return True
    return False


def _check_roof_bears_on_wall(assembly: Assembly) -> List[Failure]:
    """Every primary roof deck must rest on a wall or parapet (Support class).

    WHY THIS IS SEPARATE FROM ``canopy_attachment`` AND ``vertical_support``:
    - canopy_attachment (Connection) only asks "does the roof AABB touch a wall?"
      — a slab kissing a wall face sideways passes while floating past the eaves.
    - vertical_support accepts ANYTHING underneath, including freestanding posts —
      the gallery-on-columns defect that shipped as a detached canopy.

    So: roof bottom must meet a wall/parapet/battlement top within vertical
    support tolerance, with XY footprint overlap. Valley stubs (``roof_valley``)
    are exempt — they sit in the wing trough and are carried by abutting decks
    (S-019); ``canopy_attachment`` still requires they join the roof graph.

    Gallery canopies (``gallery_roof``) are intentionally post-supported on the
    court edge, but they are NOT exempt here: compound places a ``WALL_T_CM``
    bearing overhang onto the court-facing wall head so the eave still bears.
    Posts alone must keep failing (see ``test_engineering_continuity``).
    """
    tol = VERTICAL_SUPPORT_TOL_CM
    roofs = [
        p
        for p in assembly.placements
        if p.kind == "roof" and p.asset_id in _ROOF_BEARING_ASSET_IDS
    ]
    if not roofs:
        return []
    supports = [p for p in assembly.placements if _is_roof_bearing_support(p)]
    if not supports:
        return []

    support_boxes = [_placement_aabb(p) for p in supports]
    failures: List[Failure] = []
    for roof in roofs:
        rmin, rmax = _placement_aabb(roof)
        bottom_z = rmin[2]
        bears = False
        for smin, smax in support_boxes:
            top_z = smax[2]
            if abs(top_z - bottom_z) > tol and not (smin[2] < bottom_z <= top_z + tol):
                continue
            if _xy_footprint_overlap(
                rmin, rmax, smin, smax, _support_overlap_tol(rmin, rmax, tol)
            ):
                bears = True
                break
        if bears:
            continue
        failures.append(
            Failure(
                check="roof_bears_on_wall",
                message=(
                    f"roof {roof.piece_id} ({roof.asset_id}) does not bear on a wall "
                    f"or parapet within {tol} cm of its eave (z={bottom_z:.1f})"
                ),
                world_xyz=_centre(rmin, rmax),
                piece_id=roof.piece_id,
                critical=True,
            )
        )
    return failures


def _check_roof_valley_join(assembly: Assembly) -> List[Failure]:
    """Multi-wing hip roofs must place valley stubs on abutments (S-019 Existence).

    Reconstructs wing spans from ``roof_hip`` covered cells and compares against
    ``roof_valley`` count. Pitched-only multi-wing valleys remain assemble-asserted
    (``test_hip_roof``) until span reconstruction covers slope kits.
    """
    from pae.primitives.roofs import roof_valley_seams
    from pae.trim import covered_cells

    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    if len(hips) < 2:
        return []
    spans: List[Tuple[int, int, int, int]] = []
    for hip in hips:
        cells = covered_cells(hip)
        if not cells:
            continue
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        spans.append((min(xs), min(ys), max(xs), max(ys)))
    seams = roof_valley_seams(spans)
    if not seams:
        return []
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    if len(valleys) >= len(seams):
        return []
    sample = seams[0]
    return [
        Failure(
            check="roof_valley_join",
            message=(
                f"multi-wing hip roof has {len(seams)} abutment seam(s) but only "
                f"{len(valleys)} valley stub(s) — L/U wing joins need valleys (S-019)"
            ),
            world_xyz=(
                sample.run0 * MODULE_CM + MODULE_CM * 0.5,
                sample.cross_hi * MODULE_CM,
                float(hips[0].level * STOREY_CM + STOREY_CM),
            ),
            piece_id=hips[0].piece_id,
            critical=True,
        )
    ]


def _designed_roof_penetration_eave_tuck(
    piece: SolidPlacement,
    *,
    rise_cm: float,
    roof_asset_id: str,
) -> bool:
    """Wall/column head tucked into a flat roof slab (§2.3 / ``_designed_wall_roof_pair``).

    Flat decks are ``STOREY + FLOOR_T``; perimeter walls stop at ``STOREY``.  A rise
    within ``FLOOR_T`` is the designed eave overlap, not a blade through the roof.
    """
    if piece.kind not in ("wall", "column"):
        return False
    if roof_asset_id != "roof_flat":
        return False
    return 0.0 < rise_cm <= FLOOR_T_CM + TOL_CM


def _designed_roof_penetration_gable_ridge(
    piece: SolidPlacement,
    *,
    rise_cm: float,
    roof_asset_id: str,
) -> bool:
    """Perimeter wall meets the gable infill prism at the ridge end (§6 pitched roof).

    Gable-end walls and ``roof_gable_infill`` share the ridge silhouette; the wall
    head may coincide with the infill top within tolerance.
    """
    if piece.kind != "wall" or roof_asset_id != "roof_gable_infill":
        return False
    return 0.0 < rise_cm <= TOL_CM


def _designed_roof_penetration_drum_window(
    piece: SolidPlacement,
    *,
    rise_cm: float,
) -> bool:
    """Tower drum window overlay grazing an adjacent hall roof cell (AABB bleed).

    Full-storey blades (legacy centred full-bay overlays) are NOT exempt — only a
    modest rise from a rim shell whose own tower is crowned separately.
    """
    if "drum_window" not in piece.tags and not piece.piece_id.startswith("tower_win_"):
        return False
    return 0.0 < rise_cm <= STOREY_CM * 0.5 + TOL_CM


def _roof_penetration_exempt(
    piece: SolidPlacement,
    *,
    rise_cm: float,
    roof_asset_id: str,
) -> bool:
    """Pairs that may rise through the local roof plane by design."""
    if _designed_roof_penetration_eave_tuck(
        piece, rise_cm=rise_cm, roof_asset_id=roof_asset_id
    ):
        return True
    if _designed_roof_penetration_gable_ridge(
        piece, rise_cm=rise_cm, roof_asset_id=roof_asset_id
    ):
        return True
    if _designed_roof_penetration_drum_window(piece, rise_cm=rise_cm):
        return True
    return False


def _check_roof_penetration(assembly: Assembly) -> List[Failure]:
    """Nothing structural may poke up through its own roof.

    A wall that runs past the roof plane reads as a blade sticking out of the building.
    Parapets, battlements and roofline pieces (chimneys, spires, dormers) are SUPPOSED to
    rise above the roof, so they are exempt by kind — the check is about walls and columns
    that were never meant to be seen from above.

    Triage (M7 / school academy): gothic_academy flat roofs sit ``FLOOR_T`` above wall
    heads by design — no penetration is reported.  Eave tuck and gable-ridge coincidences
    are exempt via ``_roof_penetration_exempt``.  Any other rise through the roof plane
    is critical (real blade).
    """
    from pae.trim import covered_cells

    roof_top: Dict[Tuple[int, int], Tuple[float, str]] = {}
    for p in assembly.placements:
        if p.kind != "roof":
            continue
        top = _placement_aabb(p)[1][2]
        for c in covered_cells(p):
            prev = roof_top.get(c)
            if prev is None or top > prev[0]:
                roof_top[c] = (top, p.asset_id)
    if not roof_top:
        return []

    failures: List[Failure] = []
    for p in assembly.placements:
        if p.kind not in ("wall", "column"):
            continue
        if {"parapet", "battlement", "roofline"} & set(p.tags):
            continue
        bb_min, bb_max = _placement_aabb(p)
        for c in covered_cells(p):
            entry = roof_top.get(c)
            if entry is None:
                continue
            limit, roof_asset_id = entry
            rise_cm = bb_max[2] - limit
            if rise_cm <= TOL_CM:
                continue
            if _roof_penetration_exempt(
                p, rise_cm=rise_cm, roof_asset_id=roof_asset_id
            ):
                continue
            failures.append(
                Failure(
                    check="roof_penetration",
                    message=(
                        f"{p.piece_id} ({p.asset_id}) rises {rise_cm:.1f} cm "
                        f"through the roof above it"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
            break
    return failures


# --- §7.15 band attachment ---------------------------------------------------

# A band must be in contact along at least this fraction of its own run.
BAND_MIN_CONTACT_FRAC = 0.80


def _check_band_attachment(assembly: Assembly) -> List[Failure]:
    """Banding must be ATTACHED, which is four conditions — not "not freestanding".

    A piece that merely intersects something somewhere passes a naive touch test while
    sitting on a floor slab, clipping one corner of a wall, hovering 5 cm off the face, or
    buried inside it. Each of those is a different defect with a different fix, so each is
    reported separately:

      HOST      the thing it touches must be a WALL
      COVERAGE  contact runs along >= BAND_MIN_CONTACT_FRAC of the band's own length
      FLUSH     its back face is coplanar with that wall's outer face
      PROUD     it projects outward from that face, rather than sinking into the wall
    """
    bands = [p for p in assembly.placements if p.kind == "band"]
    if not bands:
        return []
    walls = [p for p in assembly.placements if p.kind == "wall"]
    if not walls:
        return [
            Failure(
                check="band_attachment",
                message=f"{len(bands)} band piece(s) but no walls to attach them to",
                world_xyz=None,
                piece_id=bands[0].piece_id,
                critical=True,
            )
        ]

    wall_boxes = [(w, _placement_aabb(w)) for w in walls]
    failures: List[Failure] = []

    for b in bands:
        bmn, bmx = _placement_aabb(b)
        run_axis = 0 if (bmx[0] - bmn[0]) >= (bmx[1] - bmn[1]) else 1
        thin_axis = 1 - run_axis
        run_len = bmx[run_axis] - bmn[run_axis]

        best = None
        best_contact = -1.0
        for w, (wmn, wmx) in wall_boxes:
            if bmx[2] < wmn[2] - TOL_CM or bmn[2] > wmx[2] + TOL_CM:
                continue
            gap = max(bmn[thin_axis], wmn[thin_axis]) - min(bmx[thin_axis], wmx[thin_axis])
            if gap > TOL_CM:
                continue  # not in contact on the thin axis
            contact = min(bmx[run_axis], wmx[run_axis]) - max(bmn[run_axis], wmn[run_axis])
            if contact > best_contact:
                best_contact, best = contact, (w, wmn, wmx)

        if best is None:
            failures.append(
                Failure(
                    check="band_attachment",
                    message=(
                        f"band {b.piece_id} ({b.asset_id}) touches no wall — HOST"
                    ),
                    world_xyz=_centre(bmn, bmx),
                    piece_id=b.piece_id,
                    critical=True,
                )
            )
            continue

        if run_len > 0 and best_contact < run_len * BAND_MIN_CONTACT_FRAC:
            failures.append(
                Failure(
                    check="band_attachment",
                    message=(
                        f"band {b.piece_id} ({b.asset_id}) contacts its wall over only "
                        f"{best_contact:.0f} of {run_len:.0f} cm — COVERAGE"
                    ),
                    world_xyz=_centre(bmn, bmx),
                    piece_id=b.piece_id,
                    critical=True,
                )
            )
            continue

        _w, wmn, wmx = best
        overlap = min(bmx[thin_axis], wmx[thin_axis]) - max(bmn[thin_axis], wmn[thin_axis])
        band_depth = bmx[thin_axis] - bmn[thin_axis]
        if overlap > band_depth * 0.5 and "coping" not in b.tags:
            failures.append(
                Failure(
                    check="band_proud",
                    message=(
                        f"band {b.piece_id} ({b.asset_id}) is sunk {overlap:.1f} cm into "
                        f"its wall of {band_depth:.1f} cm depth — PROUD"
                    ),
                    world_xyz=_centre(bmn, bmx),
                    piece_id=b.piece_id,
                    critical=True,
                )
            )

    return failures


# --- §7.16 aperture reachability ---------------------------------------------


def _check_aperture_reachability(assembly: Assembly) -> List[Failure]:
    """A door must open onto something you can stand on.

    WHY: the assembler placed a door on the same bay of EVERY storey, so a four-storey
    tower shipped with three doorways opening into open air one, two and three storeys up.
    Every existing check passed it: the door is a wall variant, the wall is supported, the
    envelope is sealed, nothing floats. Nobody asked what was on the other side.

    Rule: for a door above ground level, there must be a walkable surface — floor, deck,
    balcony or external surface — immediately outside it at that level. Ground-level doors
    are exempt (the site is outside them).

    Phase 9.2: exterior porch landings tagged ``upper_landing`` count the same as
    balcony deck (see ``pae.upper_entrance``).

    ``tower_entry`` doors open onto the interior hall floor at that landing —
    that is the designed walkable side (see ``door_opens_onto_exterior_landing``).
    """
    from pae.upper_entrance import (
        door_opens_onto_exterior_landing,
        _walkable_and_interior,
    )

    doors = [
        p for p in assembly.placements
        if p.kind == "wall" and ("door" in p.asset_id or "gate" in p.asset_id)
        and p.level > 0
        and "partition" not in set(p.tags)
    ]
    if not doors:
        return []

    walkable, balcony_deck, interior = _walkable_and_interior(assembly)

    failures: List[Failure] = []
    for d in doors:
        bb_min, bb_max = _placement_aabb(d)
        if not door_opens_onto_exterior_landing(
            d, walkable, balcony_deck, interior
        ):
            failures.append(
                Failure(
                    check="aperture_reachability",
                    message=(
                        f"door {d.piece_id} ({d.asset_id}) at level {d.level} opens onto "
                        f"nothing — no balcony, gallery or landing outside it"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=d.piece_id,
                    critical=True,
                )
            )
    return failures


def _check_tower_entry_door(assembly: Assembly) -> List[Failure]:
    """Existence: spiral / tower-stair drums need a hall→drum doorway."""
    from pae.existence import check_tower_entry_door

    return check_tower_entry_door(assembly)


def _check_upper_entrance_landing(assembly: Assembly) -> List[Failure]:
    """Phase 9.2 T-007/T-009 — role-tagged upper_exterior doors need a landing."""
    from pae.upper_entrance import check_upper_entrance_landing

    return check_upper_entrance_landing(assembly)


# --- §7.17 storey egress -----------------------------------------------------


def _is_outdoor_tower_deck_floor(p: SolidPlacement) -> bool:
    """Outdoor crown / rampart deck — not an indoor habitable storey slab.

    Phase 4.7 ``tower_deck`` / ``tower_top`` floors sit under the crown in open
    air (same exemption family as headroom). They must not invent a STOREY or
    VOLUME ``storey_egress`` critical merely because a floor-kind piece exists
    above the last indoor landing. Deck existence / walkability is owned by
    ``tower_top_walkable`` / rampart checks — do **not** demote storey_egress
    for ordinary indoor floors, and do **not** broaden this tag set casually.
    """
    if p.kind != "floor" or "hole" in p.asset_id:
        return False
    return "tower_deck" in p.tags or "tower_top" in p.tags


def _check_storey_egress(assembly: Assembly) -> List[Failure]:
    """Every enclosed space must be enterable, and every storey must have a way in and out.

    Three rules, reported separately:

      GROUND    the building has at least one exterior door at level 0. A sealed building
                is a solid, not architecture.
      STOREY    every storey above ground is served by a stair arriving at it. Without
                this an upper floor is a room with no way in — which the engine has
                shipped, because floor_coverage and enclosure both pass happily on it.
      VOLUME    every level with floor area has at least one aperture (door or window).
                A windowless, doorless enclosed volume is a mistake, not a cellar.

    Outdoor tower crown / rampart decks (``tower_deck`` / ``tower_top``) are
    excluded from the floor-level set — they are open-air wall-walks, not
    enclosed habitable storeys (Handbook: outdoor tower deck exemption).

    NOTE: true PER-ROOM door checking needs the room graph (roadmap Phase 2.1/2.2). Until
    interior partitions exist there is one room per storey, and this is that check. When
    partitions land, this must be extended to iterate rooms rather than storeys.
    """
    from pae.trim import covered_cells

    failures: List[Failure] = []

    levels_with_floor: Dict[int, set] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            # Outdoor crown/rampart deck — not an indoor storey (see helper).
            if _is_outdoor_tower_deck_floor(p):
                continue
            levels_with_floor.setdefault(p.level, set()).update(covered_cells(p))
    if not levels_with_floor:
        return failures

    doors_by_level: Dict[int, int] = {}
    apertures_by_level: Dict[int, int] = {}
    for p in assembly.placements:
        if p.kind != "wall":
            continue
        if "door" in p.asset_id or "gate" in p.asset_id:
            doors_by_level[p.level] = doors_by_level.get(p.level, 0) + 1
            apertures_by_level[p.level] = apertures_by_level.get(p.level, 0) + 1
        elif "window" in p.asset_id or "arcade" in p.asset_id or "arrowslit" in p.asset_id:
            apertures_by_level[p.level] = apertures_by_level.get(p.level, 0) + 1

    # GROUND
    if doors_by_level.get(0, 0) == 0:
        failures.append(
            Failure(
                check="storey_egress",
                message="building has no exterior door at ground level — GROUND",
                world_xyz=None,
                piece_id=None,
                critical=True,
            )
        )

    # STOREY — a stair must ARRIVE at each upper level (i.e. start on the level below).
    stair_from: Dict[int, int] = {}
    for p in assembly.placements:
        if p.kind == "stair":
            stair_from[p.level] = stair_from.get(p.level, 0) + 1

    for level in sorted(levels_with_floor):
        if level == 0:
            continue
        if stair_from.get(level - 1, 0) == 0:
            failures.append(
                Failure(
                    check="storey_egress",
                    message=(
                        f"storey {level} has floor area but no stair arrives from "
                        f"storey {level - 1} — STOREY"
                    ),
                    world_xyz=None,
                    piece_id=None,
                    critical=True,
                )
            )

    # VOLUME
    for level in sorted(levels_with_floor):
        if apertures_by_level.get(level, 0) == 0:
            failures.append(
                Failure(
                    check="storey_egress",
                    message=(
                        f"storey {level} is enclosed with no door and no window — VOLUME"
                    ),
                    world_xyz=None,
                    piece_id=None,
                    critical=True,
                )
            )

    return failures


# --- §7.18 headroom (S-130) --------------------------------------------------


def _is_walkable_surface(p: SolidPlacement) -> bool:
    """Indoor walk surfaces only — not site ground/surface tiles under the building."""
    if p.kind == "stair":
        return True
    if p.kind == "floor" and "hole" not in p.asset_id:
        # Outdoor tower crown / wall-walk (Phase 4.7) — open sky by design; hall eaves
        # that graze the drum cell must not false-positive indoor headroom.
        if "tower_deck" in p.tags or "tower_top" in p.tags:
            return False
        return True
    return False


def _walk_surface_z_at_cell(p: SolidPlacement, cell: Tuple[int, int]) -> float | None:
    """Approximate tread / deck top (world Z) for a walkable piece in *cell*."""
    from pae.trim import covered_cells

    smin, smax = _placement_aabb(p)
    wx0, wy0 = cell[0] * MODULE_CM, cell[1] * MODULE_CM
    wx1, wy1 = wx0 + MODULE_CM, wy0 + MODULE_CM
    ox = min(smax[0], wx1) - max(smin[0], wx0)
    oy = min(smax[1], wy1) - max(smin[1], wy0)
    if ox <= TOL_CM or oy <= TOL_CM:
        return None
    if p.kind == "stair":
        axis = 1 if p.yaw in (0, 180) else 0
        ordered = sorted(covered_cells(p), key=lambda c: c[axis])
        if len(ordered) <= 1:
            return smax[2]
        try:
            idx = ordered.index(cell)
        except ValueError:
            return None
        frac = idx / (len(ordered) - 1)
        return smin[2] + frac * (smax[2] - smin[2])
    return smax[2]


def _head_probe_boxes_for_walkable(
    p: SolidPlacement,
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Character-pass probes above each walkable bay (reuses stair exit head pattern)."""
    from pae.trim import covered_cells

    half = 40.0
    boxes: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    for cell in covered_cells(p):
        z0 = _walk_surface_z_at_cell(p, cell)
        if z0 is None:
            continue
        cx = cell[0] * MODULE_CM + MODULE_CM * 0.5
        cy = cell[1] * MODULE_CM + MODULE_CM * 0.5
        z1 = z0 + HEADROOM_CLEARANCE_CM
        boxes.append(
            (
                (cx - half, cy - half, z0),
                (cx + half, cy + half, z1),
            )
        )
    return boxes


def _check_headroom(assembly: Assembly) -> List[Failure]:
    """Walkable floors and stairs need standing clearance without solid plugs above.

    Reuses ``_solid_blocks_headroom`` from stair exit clearance (S-130 / roadmap 2.1 m).
    """
    failures: List[Failure] = []
    walkables = [p for p in assembly.placements if _is_walkable_surface(p)]
    if not walkables:
        return failures

    for walk in walkables:
        for head_min, head_max in _head_probe_boxes_for_walkable(walk):
            for other in assembly.placements:
                if other.piece_id == walk.piece_id:
                    continue
                if other.asset_id == "floor_hole":
                    continue
                if not _solid_blocks_headroom(other, head_min, head_max):
                    continue
                failures.append(
                    Failure(
                        check="headroom",
                        message=(
                            f"walkable {walk.piece_id} ({walk.asset_id}) blocked by "
                            f"{other.kind} {other.piece_id} ({other.asset_id}) — "
                            f"less than {HEADROOM_CLEARANCE_CM:.0f} cm clearance"
                        ),
                        world_xyz=(
                            0.5 * (head_min[0] + head_max[0]),
                            0.5 * (head_min[1] + head_max[1]),
                            0.5 * (head_min[2] + head_max[2]),
                        ),
                        piece_id=other.piece_id,
                        critical=True,
                    )
                )
    return failures


# --- §7.19 roof covers enclosed / watertight progress (S-021) ---------------


def _check_roof_covers_enclosed(assembly: Assembly) -> List[Failure]:
    """Top-storey enclosed interior cells should have roof ``covered_cells``.

    Watertight progress toward S-021 (one resolved multi-wing surface). Still a
    **warning** until full envelope merge ships — critical would block every
    courtyard / double-height void we intentionally leave open. Renamed from
    ``watertight_envelope`` so connection-suite tests can assert the slug.
    """
    from pae.trim import covered_cells

    floor_by_level: Dict[int, Set[Tuple[int, int]]] = {}
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            floor_by_level.setdefault(p.level, set()).update(covered_cells(p))
    if not floor_by_level:
        return []

    interior_cells: Set[Tuple[int, int]] = set()
    for layer in assembly.floor_plan.values():
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if role in (
                    CellRole.INTERIOR,
                    CellRole.CLASSROOM,
                    CellRole.CORRIDOR,
                ):
                    interior_cells.add((ox + lx, oy + ly))

    roof_cells: Set[Tuple[int, int]] = set()
    for p in assembly.placements:
        if p.kind == "roof":
            roof_cells |= covered_cells(p)

    top_level = max(floor_by_level)
    uncovered = (floor_by_level[top_level] & interior_cells) - roof_cells
    if not uncovered:
        return []

    sample = next(iter(uncovered))
    return [
        Failure(
            check="roof_covers_enclosed",
            message=(
                f"storey {top_level} has {len(uncovered)} enclosed floor cell(s) "
                f"without roof coverage (e.g. {sample})"
            ),
            world_xyz=(
                sample[0] * MODULE_CM + MODULE_CM * 0.5,
                sample[1] * MODULE_CM + MODULE_CM * 0.5,
                float(top_level * STOREY_CM),
            ),
            piece_id=None,
            critical=False,
        )
    ]


def _check_watertight_envelope(assembly: Assembly) -> List[Failure]:
    """Alias for ``roof_covers_enclosed`` (S-021 stub name kept for callers)."""
    return _check_roof_covers_enclosed(assembly)


# --- 7.18 stair landing clearance -------------------------------------------

# How far in front of a stair end must be clear, as a fraction of a module.
STAIR_LANDING_CLEAR_FRAC = 0.5


def _check_stair_landing_clearance(assembly: Assembly) -> List[Failure]:
    """A stair must not dead-end into solid at either end.

    Implementation lives in ``pae.stair_occupancy`` so spiral helix co-occupancy and
    landing false-positive triage share one model (Handbook 5.1 covered_cells).
    """
    from pae.stair_occupancy import check_stair_landing_clearance

    return check_stair_landing_clearance(assembly)


def _check_stair_typology_match(assembly: Assembly) -> List[Failure]:
    """Stair assets must match building_class policy (VAL_STAIR_TYPOLOGY).

    Rules (see Docs/VALIDATION_HANDBOOK + DEFECT_LEDGER D-22):
    - Never place buttress pieces as stairs (critical).
    - House / cottage must not get monumental ``stair_wide`` / ``stair_switchback``
      (critical).
    - Industrial / academy / castle multi-storey with a 2×2 well available must not
      be served only by a compact single-cell ``stair_straight`` (warning).
    """
    from pae.spec import (
        COMPACT_STAIR_ASSETS,
        MONUMENTAL_STAIR_ASSETS,
        SPIRAL_STAIR_ASSETS,
        STAIR_TYPOLOGY_FORBIDDEN_ASSETS,
        STAIR_TYPOLOGY_POLICY,
        continuity_safe_stair_kinds,
        stair_kind_from_asset,
    )

    building_class = str(
        getattr(assembly, "building_class", None) or "generic"
    ).lower()
    if building_class not in STAIR_TYPOLOGY_POLICY:
        building_class = "generic"

    stairs = [p for p in assembly.placements if p.kind == "stair"]
    mislabeled = [
        p
        for p in assembly.placements
        if p.kind == "stair"
        and (
            p.asset_id in STAIR_TYPOLOGY_FORBIDDEN_ASSETS
            or str(p.asset_id).startswith("buttress")
        )
    ]

    failures: List[Failure] = []
    for p in mislabeled:
        bb_min, bb_max = _placement_aabb(p)
        failures.append(
            Failure(
                check="stair_typology_match",
                message=(
                    f"buttress asset {p.asset_id!r} placed as kind=stair — "
                    "buttresses are structural trim, never circulation"
                ),
                world_xyz=_centre(bb_min, bb_max),
                piece_id=p.piece_id,
                critical=True,
            )
        )

    if assembly.storeys <= 1 and not stairs:
        return failures

    declared_kind = str(getattr(assembly, "stair_kind", "") or "").lower()
    wide_well = bool(getattr(assembly, "wide_stair_well_available", False))
    has_tower = declared_kind == "spiral" or any(
        p.asset_id in SPIRAL_STAIR_ASSETS for p in stairs
    )
    safe = continuity_safe_stair_kinds(
        building_class,
        has_tower=has_tower,
        wide_well=wide_well,
        storeys=assembly.storeys,
    )
    policy_allowed = set(
        STAIR_TYPOLOGY_POLICY.get(building_class, STAIR_TYPOLOGY_POLICY["generic"])[
            "allowed"
        ]
    )

    if assembly.storeys > 1 and declared_kind:
        if declared_kind not in policy_allowed:
            critical = building_class in ("house", "cottage") or declared_kind in (
                "wide",
                "switchback",
                "spiral",
            )
            if not (
                building_class in ("industrial", "academy", "castle")
                and declared_kind == "straight"
            ):
                failures.append(
                    Failure(
                        check="stair_typology_match",
                        message=(
                            f"building_class={building_class!r} forbids "
                            f"stair_kind={declared_kind!r}; "
                            f"allowed={sorted(policy_allowed)}"
                        ),
                        world_xyz=None,
                        critical=critical,
                    )
                )

    placed_kinds: Set[str] = set()
    compact_only = True
    for p in stairs:
        if p.asset_id in STAIR_TYPOLOGY_FORBIDDEN_ASSETS or str(p.asset_id).startswith(
            "buttress"
        ):
            continue
        kind = stair_kind_from_asset(p.asset_id)
        if kind is None:
            continue
        placed_kinds.add(kind)
        if p.asset_id not in COMPACT_STAIR_ASSETS:
            compact_only = False

        if building_class in ("house", "cottage") and p.asset_id in MONUMENTAL_STAIR_ASSETS:
            bb_min, bb_max = _placement_aabb(p)
            failures.append(
                Failure(
                    check="stair_typology_match",
                    message=(
                        f"{building_class} must use compact stairs "
                        f"(stair_straight / stair_half); got {p.asset_id}"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
        elif kind not in policy_allowed and kind not in safe:
            bb_min, bb_max = _placement_aabb(p)
            failures.append(
                Failure(
                    check="stair_typology_match",
                    message=(
                        f"stair asset {p.asset_id} (kind={kind}) not allowed for "
                        f"building_class={building_class!r}; "
                        f"allowed={sorted(policy_allowed)}"
                    ),
                    world_xyz=_centre(bb_min, bb_max),
                    piece_id=p.piece_id,
                    critical=building_class in ("house", "cottage"),
                )
            )

    if (
        building_class in ("industrial", "academy", "castle")
        and assembly.storeys >= 2
        and wide_well
        and stairs
        and compact_only
        and not (placed_kinds & {"wide", "switchback", "spiral"})
    ):
        sample = stairs[0]
        bb_min, bb_max = _placement_aabb(sample)
        failures.append(
            Failure(
                check="stair_typology_match",
                message=(
                    f"{building_class} multi-storey with 2×2 well available must not "
                    f"use undersized compact stairs only "
                    f"(got {[p.asset_id for p in stairs[:4]]}); "
                    "expected stair_wide or stair_switchback"
                ),
                world_xyz=_centre(bb_min, bb_max),
                piece_id=sample.piece_id,
                critical=False,
            )
        )

    return failures


def _check_spiral_shell(assembly: Assembly) -> List[Failure]:
    """Spiral tower newel existence + continuous drum enclosure (@VAL_SPIRAL_SHELL)."""
    from pae.spiral_shell import check_spiral_shell

    return check_spiral_shell(assembly)


def _check_tower_ramparts(assembly: Assembly) -> List[Failure]:
    """Phase 4.7 — walkable crown deck, rampart ring coverage, view crenels."""
    from pae.tower_rampart import check_tower_ramparts

    return check_tower_ramparts(assembly)


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


def _check_no_bare_aperture_holes(assembly: Assembly) -> List[Failure]:
    """Roadmap §1.5 — passage openings must carry a door/gate leaf (extends aperture family).

    Appended separately so ``_check_aperture_sanity`` / ``_check_aperture_reachability``
    bodies stay owned by their lanes; this only adds the bare-hole leaf rule.
    """
    from pae.existence import check_no_bare_aperture_holes

    return check_no_bare_aperture_holes(assembly)


def _check_aperture_sanity(assembly: Assembly) -> List[Failure]:
    """Sill bands + door side walkability.

    `tower_entry` hall↔drum doors are a through-passage: both sides use
    stairwell/hall roles (see `_check_door_walkable(..., tower_entry=True)`).
    Ordinary exterior doors still require EXTERIOR/COURTYARD outside — this is
    not a global demotion of aperture_sanity.
    """
    failures: List[Failure] = []
    policy = assembly.aperture_policy
    layer_map = assembly.floor_plan
    from pae.tower_entry import is_tower_entry_piece

    tower_entry_walls = {
        p.piece_id for p in assembly.placements if is_tower_entry_piece(p)
    }

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
            failures.extend(
                _check_door_walkable(
                    ap,
                    layer_map,
                    tower_entry=ap.wall_piece_id in tower_entry_walls,
                )
            )

    return failures


def _check_door_walkable(
    ap,
    layer_map: Dict[int, FloorPlanLayer],
    *,
    tower_entry: bool = False,
) -> List[Failure]:
    failures: List[Failure] = []
    layer = layer_map.get(ap.level)
    if layer is None:
        return failures

    def interior_walkable(cell: Tuple[int, int]) -> bool:
        role = layer.role_at(cell[0], cell[1])
        return role in (
            CellRole.INTERIOR,
            CellRole.STAIR,
            CellRole.DOOR,
            CellRole.CORRIDOR,
            CellRole.CLASSROOM,
        )

    def exterior_walkable(cell: Tuple[int, int]) -> bool:
        role = layer.role_at(cell[0], cell[1])
        if role is None:
            return True
        return role in (
            CellRole.EXTERIOR,
            CellRole.COURTYARD,
            CellRole.DOOR,
        )

    # tower_entry: hall↔drum passage — both sides must be passable inhabited /
    # stairwell cells. Do NOT accept EXTERIOR here, and do NOT weaken the
    # exterior_walkable rule for ordinary perimeter doors.
    if tower_entry:
        from pae.tower_entry import _DRUM_PASSABLE, _HALL_WALKABLE

        drum_role = layer.role_at(*ap.interior_cell)
        hall_role = layer.role_at(*ap.exterior_cell)
        if drum_role not in _DRUM_PASSABLE:
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
        if hall_role not in _HALL_WALKABLE:
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


# --- §7.9b aperture alignment (roadmap §1.4) ---------------------------------


_WALL_FACE_BY_YAW: Dict[int, str] = {0: "west", 180: "east", 270: "south", 90: "north"}


def _aperture_facade_column(
    interior_cell: Tuple[int, int],
    exterior_cell: Tuple[int, int],
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    return (interior_cell, exterior_cell)


def _wall_facade_column(p: SolidPlacement) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    face = _WALL_FACE_BY_YAW.get(p.yaw, "south")
    x, y = p.cell
    if face == "west":
        return (x + 1, y), (x, y)
    if face == "east":
        return (x - 1, y), (x, y)
    if face == "south":
        return (x, y + 1), (x, y)
    return (x, y - 1), (x, y)


def _is_opening_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = p.asset_id
    return "door" in aid or "gate" in aid or "window" in aid


def _opening_samples(assembly: Assembly) -> List[Tuple[str, int, float, float, Tuple[Tuple[int, int], Tuple[int, int]]]]:
    """(piece_id, level, plan_x, plan_y, facade_column) for each tracked opening."""
    hosted: Set[str] = {ap.wall_piece_id for ap in assembly.apertures}
    samples: List[Tuple[str, int, float, float, Tuple[Tuple[int, int], Tuple[int, int]]]] = []
    for ap in assembly.apertures:
        column = _aperture_facade_column(ap.interior_cell, ap.exterior_cell)
        samples.append((ap.piece_id, ap.level, ap.world_xyz[0], ap.world_xyz[1], column))
    for p in assembly.placements:
        if not _is_opening_wall(p) or p.piece_id in hosted:
            continue
        bb_min, bb_max = _placement_aabb(p)
        centre = _centre(bb_min, bb_max)
        column = _wall_facade_column(p)
        samples.append((p.piece_id, p.level, centre[0], centre[1], column))
    return samples


def _check_aperture_alignment(assembly: Assembly) -> List[Failure]:
    """Stacked openings on the same façade column share a plan centre line (roadmap §1.4).

    A ground entrance with a balcony door directly above must read as one vertical
  stack — not two openings offset along the wall run.
    """
    samples = _opening_samples(assembly)
    if len(samples) < 2:
        return []

    tol = APERTURE_ALIGNMENT_TOL_CM
    by_column: Dict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[str, int, float, float]]] = {}
    for piece_id, level, px, py, column in samples:
        by_column.setdefault(column, []).append((piece_id, level, px, py))

    failures: List[Failure] = []
    for column, group in by_column.items():
        levels = {level for _pid, level, _px, _py in group}
        if len(levels) < 2:
            continue
        ref_piece, ref_level, ref_x, ref_y = min(group, key=lambda g: (g[1], g[0]))
        for piece_id, level, px, py in group:
            if level == ref_level and piece_id == ref_piece:
                continue
            dx = abs(px - ref_x)
            dy = abs(py - ref_y)
            if dx <= tol and dy <= tol:
                continue
            failures.append(
                Failure(
                    check="aperture_alignment",
                    message=(
                        f"opening {piece_id} at level {level} is offset "
                        f"({dx:.1f}, {dy:.1f}) cm from stacked column "
                        f"{column} reference {ref_piece} at level {ref_level} "
                        f"(tolerance {tol} cm)"
                    ),
                    world_xyz=(px, py, ref_level * STOREY_CM),
                    piece_id=piece_id,
                    critical=False,
                )
            )
    return failures


__all__ = [
    "validate",
    "HEADROOM_CLEARANCE_CM",
    "APERTURE_ALIGNMENT_TOL_CM",
    "placement_footprint_cells",
    "_check_stair_exit_clearance",
    "_check_stair_typology_match",
    "_check_headroom",
    "_check_no_bare_aperture_holes",
    "_check_aperture_alignment",
    "_check_upper_entrance_landing",
]

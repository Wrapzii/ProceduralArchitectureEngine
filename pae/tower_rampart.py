"""Phase 4.7 — tower crown ramparts: walkable deck, battlement ring, view crenels.

Habitable tower tops need:
  1. A walkable floor/deck at the drum plate (under the crown).
  2. A battlement / parapet ring covering the drum perimeter.
  3. Outward-facing view apertures (crenels) so you can see out.

Validation enforces existence + a railing/battlement continuity stub
(angular coverage around the drum with no large gaps).

Rampart pieces are tagged ``battlement`` / ``parapet`` / ``tower_rampart`` so
``roof_penetration`` does not treat them as rogue walls through hall roofs.
Crenel shells sit on the drum rim (same pose family as drum windows) and stay
on the tower cell — they must not falsely pierce adjacent pitched roofs.
"""

from __future__ import annotations

import math
from typing import Any, Callable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Aperture, Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    cell_to_world_cm,
    placement_world_aabb,
)
from pae.report import Failure

Cell = Tuple[int, int]

# Crenel sill above the crown deck — stays inside the usual window sill band.
_CRENEL_SILL_ABOVE_DECK_CM = 90.0

TOWER_DECK_TAG = "tower_deck"
TOWER_RAMPART_TAG = "tower_rampart"
TOWER_CRENEL_TAG = "tower_crenel"
TOWER_TOP_TAG = "tower_top"

# Angular ring sampling — continuity stub for circular railing / battlement.
_RING_SAMPLES = 16
# Max allowed gap between consecutive covered samples (90° = one open quarter).
_MAX_RING_GAP_DEG = 90.0
# Deck top must meet crown base within this (plate joint).
_DECK_CROWN_Z_TOL_CM = max(TOL_CM * 4.0, FLOOR_T_CM + TOL_CM)

_QUARTER_YAWS = (0, 90, 180, 270)

# Crenel shell — short chord at crown height; battlement-tagged so roof_penetration skips.
_CRENEL_CHORD_CM = MODULE_CM * 0.28
_CRENEL_HEIGHT_CM = STOREY_CM * 0.14


def _placement_aabb(
    p: SolidPlacement,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _is_rampart_piece(p: SolidPlacement) -> bool:
    """Battlement / parapet / crown ring that guards the tower top."""
    if TOWER_RAMPART_TAG in p.tags:
        return True
    if p.kind == "battlement":
        return True
    if p.kind == "barrier" and "parapet" in p.tags:
        return True
    if p.asset_id == "tower_crown" or (
        p.kind == "tower_crown" and "crown" in p.tags and "junction" not in p.tags
    ):
        return True
    if {"battlement", "parapet"} & set(p.tags) and p.kind in (
        "battlement",
        "barrier",
        "tower_crown",
        "wall",
    ):
        return True
    return False


def _is_tower_deck(p: SolidPlacement) -> bool:
    if TOWER_DECK_TAG in p.tags or TOWER_TOP_TAG in p.tags:
        return p.kind == "floor" and "hole" not in p.asset_id
    return False


def _is_crenel_piece(p: SolidPlacement) -> bool:
    return TOWER_CRENEL_TAG in p.tags or (
        "crenel" in p.tags and p.kind in ("wall", "battlement")
    )


def _tower_cells_from_assembly(assembly: Assembly) -> Set[Cell]:
    """Infer tower drum cells from arc / crown / cap placements."""
    cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("tower_arc", "tower_crown", "tower_cap") or "tower" in p.tags:
            if p.asset_id.startswith("tower_") or p.kind.startswith("tower_"):
                cells.add(p.cell)
    return cells


def _tower_top_level(assembly: Assembly, cell: Cell) -> Optional[int]:
    tops = [
        p.level
        for p in assembly.placements
        if p.cell == cell
        and (
            p.asset_id in ("tower_crown", "tower_junction", "tower_cap")
            or p.kind in ("tower_crown", "tower_cap")
        )
    ]
    if not tops:
        tops = [
            p.level
            for p in assembly.placements
            if p.cell == cell and p.kind == "tower_arc"
        ]
    return max(tops) if tops else None


def _drum_center_xy(assembly: Assembly, cell: Cell, level: int) -> Tuple[float, float]:
    """World XY of the drum rotation centre (placement origin for centred pieces)."""
    for p in assembly.placements:
        if p.cell != cell or p.level != level:
            continue
        if p.asset_id in ("tower_crown", "tower_junction") or p.kind == "tower_arc":
            wx, wy, _ = cell_to_world_cm(
                cell[0], cell[1], level, p.offset_cm[0], p.offset_cm[1], 0.0
            )
            # ``rotates_about_center``: offset origin *is* the circle centre.
            if p.rotates_about_center:
                return (wx, wy)
            return (wx + MODULE_CM * 0.5, wy + MODULE_CM * 0.5)
    wx, wy, _ = cell_to_world_cm(cell[0], cell[1], level)
    return (wx + MODULE_CM * 0.5, wy + MODULE_CM * 0.5)


def _crown_base_z(assembly: Assembly, cell: Cell, level: int) -> Optional[float]:
    crowns = [
        p
        for p in assembly.placements
        if p.cell == cell
        and p.level == level
        and p.asset_id == "tower_crown"
        and "junction" not in p.tags
    ]
    if not crowns:
        crowns = [
            p
            for p in assembly.placements
            if p.cell == cell and p.level == level and _is_rampart_piece(p)
        ]
    if not crowns:
        return None
    return min(_placement_aabb(p)[0][2] for p in crowns)


def _rim_shell_pose(
    drum_xy: Tuple[float, float],
    yaw: int,
    *,
    z_off: float,
    height_cm: float,
    chord_cm: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Same rim family as assemble drum windows — keeps shells off hall roofs."""
    thick = WALL_T_CM
    half = MODULE_CM * 0.5
    radial = half - thick * 0.5
    dx, dy = drum_xy
    if yaw == 0:
        size = (thick, chord_cm, height_cm)
        ox, oy = dx - radial, dy
    elif yaw == 180:
        size = (thick, chord_cm, height_cm)
        ox, oy = dx + radial, dy
    elif yaw == 90:
        size = (chord_cm, thick, height_cm)
        ox, oy = dx, dy + radial
    else:
        size = (chord_cm, thick, height_cm)
        ox, oy = dx, dy - radial
    return size, (ox, oy, z_off)


def _exterior_cell(cell: Cell, yaw: int) -> Cell:
    cx, cy = cell
    if yaw == 0:
        return (cx - 1, cy)
    if yaw == 90:
        return (cx, cy + 1)
    if yaw == 180:
        return (cx + 1, cy)
    return (cx, cy - 1)


def place_tower_rampart_crown(
    *,
    cell: Cell,
    level: int,
    drum_xy: Tuple[float, float],
    junction_z: float,
    crown_z: float,
    skip_yaw: Optional[int],
    floor_piece: Any,
    wall_window_asset_id: str,
    wall_window_tags: frozenset,
    next_piece_id: Callable[[str, Cell, int], str],
    placements: List[SolidPlacement],
    apertures: List[Aperture],
) -> None:
    """Append walkable deck + tag crown as rampart + place crenel view shells.

    ``floor_piece`` must expose ``asset_id`` / ``tags`` (catalog resolved piece).
    Crown / junction / cap must already be on ``placements`` — this tags matching
    crown pieces and adds deck + crenels around them.
    """
    rampart_tags = frozenset(
        {TOWER_RAMPART_TAG, "battlement", "parapet", TOWER_TOP_TAG}
    )
    # Tag existing crown as rampart ring (do not retag junction/cap).
    for p in placements:
        if (
            p.cell == cell
            and p.level == level
            and p.asset_id == "tower_crown"
            and "junction" not in p.tags
        ):
            p.tags = frozenset(p.tags) | rampart_tags

    # Walkable deck at drum plate — top flush with junction_z (crown sits above).
    deck_h = FLOOR_T_CM
    deck_z = junction_z - deck_h
    deck_span = MODULE_CM * 0.85  # interior of drum; stays inside battlement ring
    deck_tags = frozenset(getattr(floor_piece, "tags", frozenset())) | frozenset(
        {TOWER_DECK_TAG, TOWER_TOP_TAG, "tower", "walkable"}
    )
    deck_id = next_piece_id("tower_deck", cell, level)
    placements.append(
        SolidPlacement(
            piece_id=deck_id,
            asset_id=getattr(floor_piece, "asset_id", "floor"),
            kind="floor",
            cell=cell,
            level=level,
            yaw=0,
            offset_cm=(drum_xy[0], drum_xy[1], deck_z),
            size_cm=(deck_span, deck_span, deck_h),
            rotates_about_center=True,
            tags=deck_tags,
        )
    )

    # Outward crenels / view apertures at crown height (skip attach face).
    # kind=battlement — roof_penetration only inspects wall/column (no demotion).
    deck_top_world = level * STOREY_CM + junction_z
    for yaw in _QUARTER_YAWS:
        if skip_yaw is not None and yaw == skip_yaw:
            continue
        size, offset = _rim_shell_pose(
            drum_xy,
            yaw,
            z_off=crown_z,
            height_cm=_CRENEL_HEIGHT_CM,
            chord_cm=_CRENEL_CHORD_CM,
        )
        cid = next_piece_id(f"tower_crenel_{yaw}", cell, level)
        tags = frozenset(wall_window_tags) | frozenset(
            {
                TOWER_CRENEL_TAG,
                TOWER_RAMPART_TAG,
                "battlement",
                "crenel",
                "tower",
                "view",
                TOWER_TOP_TAG,
            }
        )
        placements.append(
            SolidPlacement(
                piece_id=cid,
                asset_id=wall_window_asset_id,
                kind="battlement",
                cell=cell,
                level=level,
                yaw=yaw,
                offset_cm=offset,
                size_cm=size,
                rotates_about_center=True,
                tags=tags,
            )
        )
        sill_z = deck_top_world + _CRENEL_SILL_ABOVE_DECK_CM
        wx, wy, _ = cell_to_world_cm(
            cell[0], cell[1], level, offset[0], offset[1], offset[2]
        )
        apertures.append(
            Aperture(
                piece_id=f"crenel_{cid}",
                kind="window",
                wall_piece_id=cid,
                level=level,
                sill_z_cm=sill_z,
                floor_z_cm=deck_top_world,
                interior_cell=cell,
                exterior_cell=_exterior_cell(cell, yaw),
                world_xyz=(wx, wy, sill_z),
            )
        )


def _ring_sample_hits_rampart(
    cx: float,
    cy: float,
    radius: float,
    angle_rad: float,
    ramparts: Sequence[SolidPlacement],
    *,
    z_lo: float,
    z_hi: float,
) -> bool:
    """True when a perimeter sample point falls inside a rampart AABB (with tol)."""
    px = cx + radius * math.cos(angle_rad)
    py = cy + radius * math.sin(angle_rad)
    pz = 0.5 * (z_lo + z_hi)
    for p in ramparts:
        mn, mx = _placement_aabb(p)
        if (
            mn[0] - TOL_CM <= px <= mx[0] + TOL_CM
            and mn[1] - TOL_CM <= py <= mx[1] + TOL_CM
            and mn[2] - TOL_CM <= pz <= mx[2] + TOL_CM
        ):
            return True
        # Also accept near-miss on the ring band (thin annulus crowns).
        # Expand XY by WALL_T so a centred crown ring registers at outer radius.
        if (
            mn[0] - WALL_T_CM <= px <= mx[0] + WALL_T_CM
            and mn[1] - WALL_T_CM <= py <= mx[1] + WALL_T_CM
            and mn[2] - TOL_CM <= pz <= mx[2] + TOL_CM
        ):
            # Prefer samples near the outer shell of this AABB.
            mid_x = 0.5 * (mn[0] + mx[0])
            mid_y = 0.5 * (mn[1] + mx[1])
            # Crown fills its AABB; any sample in the expanded box on the ring counts.
            dist = math.hypot(px - mid_x, py - mid_y)
            half_diag = 0.5 * math.hypot(mx[0] - mn[0], mx[1] - mn[1])
            if dist <= half_diag + TOL_CM:
                return True
    return False


def _angular_coverage_gaps(
    hits: Sequence[bool],
) -> List[float]:
    """Return gap sizes in degrees for contiguous False runs (circular)."""
    n = len(hits)
    if n == 0:
        return [360.0]
    step = 360.0 / n
    # Rotate so we don't split a gap at index 0 awkwardly for measurement.
    gaps: List[float] = []
    i = 0
    while i < n:
        if hits[i]:
            i += 1
            continue
        j = i
        while j < n and not hits[j]:
            j += 1
        gaps.append((j - i) * step)
        i = j
    # Merge wrap-around gap if both ends are uncovered.
    if not hits[0] and not hits[-1] and len(gaps) >= 2:
        merged = gaps[0] + gaps[-1]
        gaps = gaps[1:-1] + [merged]
    return gaps


def check_tower_rampart_ring(assembly: Assembly) -> List[Failure]:
    """Battlement/parapet must cover the drum perimeter within angular tolerance.

    Continuity stub: no uncovered arc wider than ``_MAX_RING_GAP_DEG``.
    """
    failures: List[Failure] = []
    for cell in sorted(_tower_cells_from_assembly(assembly)):
        level = _tower_top_level(assembly, cell)
        if level is None:
            continue
        ramparts = [
            p
            for p in assembly.placements
            if p.cell == cell and p.level == level and _is_rampart_piece(p)
        ]
        if not ramparts:
            failures.append(
                Failure(
                    check="tower_rampart_ring",
                    message=(
                        f"tower at {cell} L{level} has no battlement/parapet "
                        f"rampart ring"
                    ),
                    world_xyz=None,
                    piece_id=None,
                    critical=True,
                )
            )
            continue

        cx, cy = _drum_center_xy(assembly, cell, level)
        z_lo = min(_placement_aabb(p)[0][2] for p in ramparts)
        z_hi = max(_placement_aabb(p)[1][2] for p in ramparts)
        # Sample on the outer drum radius (MODULE from centre).
        radius = MODULE_CM * 0.92
        hits = [
            _ring_sample_hits_rampart(
                cx,
                cy,
                radius,
                2.0 * math.pi * i / _RING_SAMPLES,
                ramparts,
                z_lo=z_lo,
                z_hi=z_hi,
            )
            for i in range(_RING_SAMPLES)
        ]
        covered = sum(1 for h in hits if h)
        # Existence: majority of samples must hit (full ring / centred crown).
        if covered < _RING_SAMPLES * 0.75:
            rep = ramparts[0]
            failures.append(
                Failure(
                    check="tower_rampart_ring",
                    message=(
                        f"tower rampart at {cell} L{level} covers only "
                        f"{covered}/{_RING_SAMPLES} perimeter samples "
                        f"(need ≥75%)"
                    ),
                    world_xyz=_centre(*_placement_aabb(rep)),
                    piece_id=rep.piece_id,
                    critical=True,
                )
            )
            continue

        gaps = _angular_coverage_gaps(hits)
        bad = [g for g in gaps if g > _MAX_RING_GAP_DEG + 1e-6]
        if bad:
            rep = ramparts[0]
            failures.append(
                Failure(
                    check="tower_rampart_ring",
                    message=(
                        f"tower rampart continuity gap {max(bad):.0f}° at {cell} "
                        f"L{level} (max {_MAX_RING_GAP_DEG:.0f}°) — railing/"
                        f"battlement ring broken"
                    ),
                    world_xyz=_centre(*_placement_aabb(rep)),
                    piece_id=rep.piece_id,
                    critical=True,
                )
            )
    return failures


def check_tower_top_walkable(assembly: Assembly) -> List[Failure]:
    """Every tower crown needs a walkable floor/deck under the rampart ring."""
    failures: List[Failure] = []
    for cell in sorted(_tower_cells_from_assembly(assembly)):
        level = _tower_top_level(assembly, cell)
        if level is None:
            continue
        decks = [
            p
            for p in assembly.placements
            if p.cell == cell and p.level == level and _is_tower_deck(p)
        ]
        # Also accept a plain floor whose top meets the crown base (poison-proof).
        if not decks:
            crown_z = _crown_base_z(assembly, cell, level)
            if crown_z is not None:
                for p in assembly.placements:
                    if p.cell != cell or p.level != level:
                        continue
                    if p.kind != "floor" or "hole" in p.asset_id:
                        continue
                    top = _placement_aabb(p)[1][2]
                    if abs(top - crown_z) <= _DECK_CROWN_Z_TOL_CM:
                        decks.append(p)
        if not decks:
            failures.append(
                Failure(
                    check="tower_top_walkable",
                    message=(
                        f"tower at {cell} L{level} has no walkable crown deck "
                        f"under the rampart"
                    ),
                    world_xyz=None,
                    piece_id=None,
                    critical=True,
                )
            )
            continue

        crown_z = _crown_base_z(assembly, cell, level)
        if crown_z is None:
            continue
        ok = False
        for d in decks:
            top = _placement_aabb(d)[1][2]
            if abs(top - crown_z) <= _DECK_CROWN_Z_TOL_CM or top <= crown_z + TOL_CM:
                # Deck under or flush with crown base.
                if top >= crown_z - _DECK_CROWN_Z_TOL_CM:
                    ok = True
                    break
        if not ok:
            d = decks[0]
            top = _placement_aabb(d)[1][2]
            failures.append(
                Failure(
                    check="tower_top_walkable",
                    message=(
                        f"tower deck {d.piece_id} top z={top:.1f} does not meet "
                        f"crown base z={crown_z:.1f} at {cell} L{level}"
                    ),
                    world_xyz=_centre(*_placement_aabb(d)),
                    piece_id=d.piece_id,
                    critical=True,
                )
            )
    return failures


def check_view_aperture_exists(assembly: Assembly) -> List[Failure]:
    """Optional but fail-closed when a tower crown exists: outward crenels/windows.

    Severity: WARNING — existence stub for Phase 4.7 view openings. Promote later
    when every style guarantees crenels.
    """
    failures: List[Failure] = []
    for cell in sorted(_tower_cells_from_assembly(assembly)):
        level = _tower_top_level(assembly, cell)
        if level is None:
            continue
        has_crown = any(
            p.cell == cell
            and p.level == level
            and (p.asset_id == "tower_crown" or _is_rampart_piece(p))
            for p in assembly.placements
        )
        if not has_crown:
            continue
        crenels = [
            p
            for p in assembly.placements
            if p.cell == cell and p.level == level and _is_crenel_piece(p)
        ]
        view_aps = [
            a
            for a in assembly.apertures
            if a.kind == "window"
            and a.interior_cell == cell
            and a.level == level
            and (
                (a.wall_piece_id or "").startswith("tower_crenel_")
                or a.piece_id.startswith("crenel_")
            )
        ]
        if crenels or view_aps:
            continue
        failures.append(
            Failure(
                check="view_aperture_exists",
                message=(
                    f"tower crown at {cell} L{level} has no outward view "
                    f"aperture (crenel/window)"
                ),
                world_xyz=None,
                piece_id=None,
                critical=False,
            )
        )
    return failures


def check_tower_ramparts(assembly: Assembly) -> List[Failure]:
    """Run all Phase 4.7 tower-top rampart checks."""
    out: List[Failure] = []
    out.extend(check_tower_rampart_ring(assembly))
    out.extend(check_tower_top_walkable(assembly))
    out.extend(check_view_aperture_exists(assembly))
    return out

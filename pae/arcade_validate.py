"""Arcade / cloister / gallery validation — continuity, pier bearing, court railings.

WHY THIS EXISTS: monumental arches and cloister walks are trim/compound features.
Without targeted checks they ship as one-bay stepped blobs, floating arcade pieces,
or gallery decks with no balustrade on the court drop.

Checks (stable slugs):
  * ``arcade_pier_bearing`` — arcade arch/pier at ground must stand on structure
  * ``arcade_continuity`` — court-facing arcade bays share bearing / touch in run
  * ``gallery_court_railing`` — upper deck overlooking court must be guarded
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, TOL_CM, placement_world_aabb, storey_datum_z_cm
from pae.report import Failure
from pae.trim import covered_cells

Cell = Tuple[int, int]

_NEIGHBOURS = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}

_ARCADE_ASSETS = frozenset(
    {
        "wall_arcade",
        "wall_arcade_monumental",
        "arch_freestanding",
        "pier_square",
    }
)


def _all_tags(assembly: Assembly) -> Set[str]:
    tags: Set[str] = set()
    for p in assembly.placements:
        tags |= set(p.tags)
    return tags


def assembly_has_arcade_language(assembly: Assembly) -> bool:
    """True when arcade/cloister/gallery checks apply."""
    tags = _all_tags(assembly)
    if tags & {"cloister", "arcade", "gallery", "fortress_compound"}:
        return True
    for p in assembly.placements:
        if p.asset_id in _ARCADE_ASSETS and (
            "trim" in p.tags or "cloister" in p.tags or "arcade" in p.tags
        ):
            return True
    return False


def _support_cells_level0(assembly: Assembly) -> Set[Cell]:
    return _bearing_support_cells(assembly)


def _courtyard_cells(assembly: Assembly) -> Set[Cell]:
    from pae.plan import CellRole

    layer = assembly.floor_plan.get(0)
    if layer is None:
        return set()
    court: Set[Cell] = set()
    ox, oy = layer.origin_cell
    role = getattr(CellRole, "COURTYARD", None)
    for ly in range(layer.height):
        for lx in range(layer.width):
            if layer.cells[ly][lx] == role:
                court.add((ox + lx, oy + ly))
    return court


def _bearing_support_cells(assembly: Assembly) -> Set[Cell]:
    """Structural cells at L0 — excludes trim arcade (hosted on walls)."""
    supported: Set[Cell] = set()
    for p in assembly.placements:
        if p.level != 0:
            continue
        if p.asset_id in _ARCADE_ASSETS and "trim" in p.tags:
            continue
        if p.kind in ("floor", "ground", "plinth", "wall", "stair", "surface", "column"):
            supported |= covered_cells(p)
    return supported


def _arcade_placements(assembly: Assembly) -> List[SolidPlacement]:
    """Freestanding arcade / piers that must bear on structure (not wall_arcade cuts)."""
    return [
        p
        for p in assembly.placements
        if p.asset_id in ("arch_freestanding", "pier_square")
        and p.level == 0
        and ("arcade" in p.tags or "cloister" in p.tags or "trim" in p.tags)
    ]


def _arcade_run_placements(assembly: Assembly) -> List[SolidPlacement]:
    """All trim arcade pieces including wall-embedded bays (continuity checks)."""
    return [
        p
        for p in assembly.placements
        if p.asset_id in _ARCADE_ASSETS
        and p.level == 0
        and ("arcade" in p.tags or "cloister" in p.tags or "trim" in p.tags)
    ]


def check_arcade_pier_bearing(assembly: Assembly) -> List[Failure]:
    """Ground arcade pieces must bear on floor / wall / pier structure."""
    pieces = _arcade_placements(assembly)
    if not pieces:
        return []
    supported = _bearing_support_cells(assembly)
    failures: List[Failure] = []
    for p in pieces:
        cells = covered_cells(p)
        if cells & supported:
            continue
        bb = placement_world_aabb(
            p.cell[0],
            p.cell[1],
            p.level,
            p.yaw,
            p.size_cm,
            p.offset_cm,
            rotates_about_center=p.rotates_about_center,
        )
        centre = (
            (bb[0][0] + bb[1][0]) * 0.5,
            (bb[0][1] + bb[1][1]) * 0.5,
            (bb[0][2] + bb[1][2]) * 0.5,
        )
        failures.append(
            Failure(
                check="arcade_pier_bearing",
                message=(
                    f"arcade piece {p.piece_id} ({p.asset_id}) has no structural "
                    f"support under its footprint at ground level"
                ),
                world_xyz=centre,
                piece_id=p.piece_id,
                critical=True,
            )
        )
    return failures


def check_arcade_continuity(assembly: Assembly) -> List[Failure]:
    """Adjacent court-facing arcade bays on the same wall run must touch or share a pier."""
    court = _courtyard_cells(assembly)
    if not court:
        return []

    by_wall_face: Dict[Tuple[Cell, str], List[SolidPlacement]] = {}
    for p in _arcade_run_placements(assembly):
        if p.asset_id not in (
            "wall_arcade",
            "wall_arcade_monumental",
            "arch_freestanding",
        ):
            continue
        for cx, cy in sorted(court):
            for face, (dx, dy) in _NEIGHBOURS.items():
                wall_cell = (cx + dx, cy + dy)
                if wall_cell in covered_cells(p) or p.cell == wall_cell:
                    by_wall_face.setdefault((wall_cell, face), []).append(p)
                    break

    failures: List[Failure] = []
    piers = {
        c
        for p in assembly.placements
        if p.asset_id == "pier_square" and p.level == 0
        for c in covered_cells(p)
    }

    for (wall_cell, face), group in sorted(by_wall_face.items()):
        if len(group) < 2:
            continue
        dx, dy = _NEIGHBOURS[face]
        run_axis = 0 if dx else 1
        sorted_group = sorted(
            group,
            key=lambda p: p.cell[run_axis] if run_axis == 0 else p.cell[1],
        )
        for a, b in zip(sorted_group, sorted_group[1:]):
            a_cells = covered_cells(a)
            b_cells = covered_cells(b)
            gap_cells = {
                (wall_cell[0] + dx, wall_cell[1] + dy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            }
            if a_cells & b_cells:
                continue
            if gap_cells & piers:
                continue
            # Touching AABBs along the run axis counts as continuous.
            a_bb = placement_world_aabb(
                a.cell[0], a.cell[1], a.level, a.yaw, a.size_cm, a.offset_cm,
                rotates_about_center=a.rotates_about_center,
            )
            b_bb = placement_world_aabb(
                b.cell[0], b.cell[1], b.level, b.yaw, b.size_cm, b.offset_cm,
                rotates_about_center=b.rotates_about_center,
            )
            run_gap = abs(
                (a_bb[1][run_axis + 0] + a_bb[0][run_axis + 0]) * 0.5
                - (b_bb[1][run_axis + 0] + b_bb[0][run_axis + 0]) * 0.5
            )
            if run_gap <= MODULE_CM + TOL_CM:
                continue
            failures.append(
                Failure(
                    check="arcade_continuity",
                    message=(
                        f"arcade gap between {a.piece_id} and {b.piece_id} on "
                        f"wall {wall_cell} — missing pier or abutting arch"
                    ),
                    world_xyz=None,
                    piece_id=a.piece_id,
                    critical=True,
                )
            )
    return failures


def check_gallery_court_railing(assembly: Assembly) -> List[Failure]:
    """Upper deck cells overlooking the courtyard must carry a balustrade on that edge."""
    court = _courtyard_cells(assembly)
    if not court:
        return []

    decks: Dict[int, Set[Cell]] = {}
    walls: Dict[int, Set[Cell]] = {}
    barriers: Dict[int, Set[Tuple[Cell, str]]] = {}
    for p in assembly.placements:
        if p.kind == "floor":
            decks.setdefault(p.level, set()).update(covered_cells(p))
        if p.kind == "wall":
            walls.setdefault(p.level, set()).update(covered_cells(p))
        if p.kind == "barrier":
            face = None
            marker = "_gallery_"
            if marker in p.piece_id:
                candidate = p.piece_id.rsplit(marker, 1)[-1]
                if candidate in _NEIGHBOURS:
                    face = candidate
            # Legacy barriers did not retain a face tag. Yaw alone is
            # insufficient because north/south share 90° and east/west share
            # 0° under the boundary-line primitive contract.
            if face:
                barriers.setdefault(p.level, set()).add((p.cell, face))

    failures: List[Failure] = []
    for level, cells in decks.items():
        if level <= 0:
            continue
        wall_cells = walls.get(level, set())
        guarded = barriers.get(level, set())
        for cx, cy in sorted(cells):
            for face, (dx, dy) in _NEIGHBOURS.items():
                n = (cx + dx, cy + dy)
                if n not in court:
                    continue
                if n in cells or n in wall_cells:
                    continue
                if ((cx, cy), face) in guarded:
                    continue
                failures.append(
                    Failure(
                        check="gallery_court_railing",
                        message=(
                            f"gallery deck ({cx},{cy}) level {level} faces open court "
                            f"to the {face} with no balustrade"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, storey_datum_z_cm(level)),
                        piece_id=f"gallery_{level}_{cx}_{cy}",
                        critical=True,
                    )
                )
    return failures


def check_gallery_support_spacing(assembly: Assembly) -> List[Failure]:
    """Upper court rails/roof edges need piers at corners and ≤2-bay spacing."""
    barriers: List[Tuple[SolidPlacement, str]] = []
    supports: Dict[Tuple[int, str], Set[Cell]] = {}
    for p in assembly.placements:
        if "gallery_support_pier" in p.tags:
            face = next(
                (
                    tag[5:]
                    for tag in p.tags
                    if tag.startswith("face_") and tag[5:] in _NEIGHBOURS
                ),
                None,
            )
            if face:
                supports.setdefault((p.level, face), set()).add(p.cell)
        if p.kind == "barrier" and "_gallery_" in p.piece_id:
            face = p.piece_id.rsplit("_gallery_", 1)[-1]
            if face in _NEIGHBOURS:
                barriers.append((p, face))

    failures: List[Failure] = []
    for barrier, face in barriers:
        candidates = supports.get((barrier.level, face), set())
        axis = 0 if face in ("south", "north") else 1
        cross_axis = 1 - axis
        supported = any(
            abs(cell[axis] - barrier.cell[axis]) <= 2
            and cell[cross_axis] == barrier.cell[cross_axis]
            for cell in candidates
        )
        if supported:
            continue
        failures.append(
            Failure(
                check="gallery_support_spacing",
                message=(
                    f"gallery rail {barrier.piece_id} has no roof-support pier "
                    "within two bays on the same courtyard run"
                ),
                world_xyz=(
                    barrier.cell[0] * MODULE_CM,
                    barrier.cell[1] * MODULE_CM,
                    storey_datum_z_cm(barrier.level),
                ),
                piece_id=barrier.piece_id,
                critical=True,
            )
        )
    return failures


def check_gallery_support_bearing(assembly: Assembly) -> List[Failure]:
    """Gallery columns must physically meet a deck below and roof above."""
    supports = [
        p for p in assembly.placements if "gallery_support_pier" in p.tags
    ]
    floors = [p for p in assembly.placements if p.kind == "floor"]
    roofs = [p for p in assembly.placements if p.kind == "roof"]
    failures: List[Failure] = []
    for support in supports:
        smin, smax = placement_world_aabb(
            support.cell[0],
            support.cell[1],
            support.level,
            support.yaw,
            support.size_cm,
            support.offset_cm,
            rotates_about_center=support.rotates_about_center,
        )
        centre_x = (smin[0] + smax[0]) * 0.5
        centre_y = (smin[1] + smax[1]) * 0.5

        def _contains_support_axis(
            placement: SolidPlacement,
        ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
            pmin, pmax = placement_world_aabb(
                placement.cell[0],
                placement.cell[1],
                placement.level,
                placement.yaw,
                placement.size_cm,
                placement.offset_cm,
                rotates_about_center=placement.rotates_about_center,
            )
            if not (
                pmin[0] - TOL_CM <= centre_x <= pmax[0] + TOL_CM
                and pmin[1] - TOL_CM <= centre_y <= pmax[1] + TOL_CM
            ):
                return None
            return pmin, pmax

        has_base = any(
            bounds is not None and abs(bounds[1][2] - smin[2]) <= TOL_CM
            for floor in floors
            for bounds in (_contains_support_axis(floor),)
        )
        has_head = any(
            bounds is not None and abs(bounds[0][2] - smax[2]) <= TOL_CM
            for roof in roofs
            for bounds in (_contains_support_axis(roof),)
        )
        if has_base and has_head:
            continue
        failures.append(
            Failure(
                check="gallery_support_bearing",
                message=(
                    f"{support.piece_id} does not bear at both ends "
                    f"(deck={has_base}, roof={has_head})"
                ),
                world_xyz=(
                    (smin[0] + smax[0]) * 0.5,
                    (smin[1] + smax[1]) * 0.5,
                    (smin[2] + smax[2]) * 0.5,
                ),
                piece_id=support.piece_id,
                critical=True,
            )
        )
    return failures


def check_no_redundant_inner_court_walls(assembly: Assembly) -> List[Failure]:
    """Arcade-owned court edges may not retain freestanding room-divider walls."""
    # Legacy decorative trim can include an isolated arcade asset without
    # transferring ownership of the court edge.  The Stage-G arcade system
    # marks its complete walk/edge contract with ``arcade_gallery``.
    if not any("arcade_gallery" in p.tags for p in assembly.placements):
        return []
    failures: List[Failure] = []
    for placement in assembly.placements:
        if not placement.piece_id.startswith("wall_inner_"):
            continue
        failures.append(
            Failure(
                check="arcade_redundant_inner_wall",
                message=(
                    f"{placement.piece_id} is a freestanding generic inner wall "
                    "inside an arcade-owned courtyard"
                ),
                world_xyz=(
                    placement.cell[0] * MODULE_CM,
                    placement.cell[1] * MODULE_CM,
                    storey_datum_z_cm(placement.level),
                ),
                piece_id=placement.piece_id,
                critical=True,
            )
        )
    return failures


def check_arcade_gallery(assembly: Assembly) -> List[Failure]:
    """Run arcade/gallery checks when the assembly uses cloister language."""
    if not assembly_has_arcade_language(assembly):
        return []
    failures: List[Failure] = []
    failures.extend(check_arcade_pier_bearing(assembly))
    failures.extend(check_arcade_continuity(assembly))
    failures.extend(check_gallery_court_railing(assembly))
    failures.extend(check_gallery_support_spacing(assembly))
    failures.extend(check_gallery_support_bearing(assembly))
    failures.extend(check_no_redundant_inner_court_walls(assembly))
    return failures

"""Court-facing wall skin exclusivity — one structural skin per bay/face (D3-4 sibling).

``trim._colonnade`` and ``compound._add_cloister_arcade`` both place ``wall_arcade`` on
courtyard-facing ground walls while assemble already emitted ``wall_plain``. Without a
shared claim table the arcade reads as a second coplanar skin stacked on the same face.

Hard rules (fail-closed + autofix):
  * No two wall skins coplanar-overlap on the same bay at one level
  * ``wall_arcade`` *replaces* the plain court-facing wall — not stacks on it
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, TOL_CM, WALL_T_CM, aabb_overlap, placement_world_aabb
from pae.existence import is_door_or_gate_asset
from pae.report import Failure

Cell = Tuple[int, int]
FaceKey = Tuple[int, Cell, str]  # (level, anchor_cell, outward_face)

CHECK_WALL_FACE_EXCLUSIVE = "wall_face_exclusive"

_YAW_TO_FACE: Dict[int, str] = {0: "west", 180: "east", 270: "south", 90: "north"}

_WALL_ARCADE_MARKERS = frozenset(
    {
        "wall_arcade",
        "wall_arcade_monumental",
        "wall_arcade_gothic",
        "wall_arcade_round",
    }
)


def is_wall_arcade(p: SolidPlacement) -> bool:
    aid = (p.asset_id or "").lower()
    return p.kind == "wall" and (
        aid in _WALL_ARCADE_MARKERS or aid.startswith("wall_arcade")
    )


def _placement_aabb(p: SolidPlacement) -> Tuple[
    Tuple[float, float, float], Tuple[float, float, float]
]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _xy_overlap_extent(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> Tuple[float, float]:
    ox = min(a_max[0], b_max[0]) - max(a_min[0], b_min[0])
    oy = min(a_max[1], b_max[1]) - max(a_min[1], b_min[1])
    return ox, oy


def _is_wall_skin(p: SolidPlacement) -> bool:
    return p.kind == "wall" and not is_door_or_gate_asset(p.asset_id or "")


def wall_outward_face(p: SolidPlacement) -> Optional[str]:
    """Perimeter face from piece_id or assemble yaw convention."""
    parts = (p.piece_id or "").split("_")
    if len(parts) >= 3 and parts[0] == "wall" and parts[1] in _YAW_TO_FACE.values():
        return parts[1]
    return _YAW_TO_FACE.get(int(p.yaw) % 360)


def wall_face_key(p: SolidPlacement) -> Optional[FaceKey]:
    face = wall_outward_face(p)
    if face is None:
        return None
    return (p.level, p.cell, face)


def claimed_wall_arcade_faces(assembly: Assembly) -> Set[FaceKey]:
    """Faces already occupied by a wall-embedded arcade bay."""
    claimed: Set[FaceKey] = set()
    for p in assembly.placements:
        if not is_wall_arcade(p):
            continue
        key = wall_face_key(p)
        if key is not None:
            claimed.add(key)
    return claimed


def face_is_claimed_for_arcade(
    claimed: Set[FaceKey],
    *,
    level: int,
    cell: Cell,
    face: str,
) -> bool:
    return (level, cell, face) in claimed


def _coplanar_wall_duplicate(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    """True when two wall AABBs share a run-aligned skin (not a designed corner kiss)."""
    ox, oy = _xy_overlap_extent(a_min, a_max, b_min, b_max)
    if ox <= TOL_CM or oy <= TOL_CM:
        return False
    corner_lim = WALL_T_CM + TOL_CM
    if ox <= corner_lim and oy <= corner_lim:
        return False
    run = max(ox, oy)
    thin = min(ox, oy)
    return run >= MODULE_CM * 0.45 and thin <= WALL_T_CM + TOL_CM


def _designed_wall_corner_pair(
    a_min: Tuple[float, float, float],
    a_max: Tuple[float, float, float],
    b_min: Tuple[float, float, float],
    b_max: Tuple[float, float, float],
) -> bool:
    ox, oy = _xy_overlap_extent(a_min, a_max, b_min, b_max)
    corner_lim = WALL_T_CM + TOL_CM
    return ox > TOL_CM and oy > TOL_CM and ox <= corner_lim and oy <= corner_lim


def coplanar_wall_overlap(
    a: SolidPlacement,
    b: SolidPlacement,
) -> bool:
    if not (_is_wall_skin(a) and _is_wall_skin(b)):
        return False
    if a.level != b.level:
        return False
    a_min, a_max = _placement_aabb(a)
    b_min, b_max = _placement_aabb(b)
    if not aabb_overlap(a_min, a_max, b_min, b_max):
        return False
    if _designed_wall_corner_pair(a_min, a_max, b_min, b_max):
        return False
    return _coplanar_wall_duplicate(a_min, a_max, b_min, b_max)


def _wall_face_stack_violation(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Coplanar stack illegal when arcade is involved (plain+arcade or dup arcade)."""
    if not coplanar_wall_overlap(a, b):
        return False
    return is_wall_arcade(a) or is_wall_arcade(b)


def check_wall_face_exclusive(assembly: Assembly) -> List[Failure]:
    """Critical: no coplanar duplicate wall skins on the same bay (cloister stack)."""
    walls = [p for p in assembly.placements if _is_wall_skin(p) or is_wall_arcade(p)]
    failures: List[Failure] = []
    for i in range(len(walls)):
        a = walls[i]
        a_min, a_max = _placement_aabb(a)
        for b in walls[i + 1:]:
            if not _wall_face_stack_violation(a, b):
                continue
            centre = (
                (a_min[0] + a_max[0]) * 0.5,
                (a_min[1] + a_max[1]) * 0.5,
                (a_min[2] + a_max[2]) * 0.5,
            )
            failures.append(
                Failure(
                    check=CHECK_WALL_FACE_EXCLUSIVE,
                    message=(
                        f"coplanar wall skins {a.piece_id} ({a.asset_id}) and "
                        f"{b.piece_id} ({b.asset_id}) stack on the same face at "
                        f"level {a.level} — declare one producer"
                    ),
                    world_xyz=centre,
                    piece_id=a.piece_id,
                    critical=True,
                )
            )
    return failures


def _plain_wall_redundant_with_arcade(
    wall: SolidPlacement,
    arcades: List[SolidPlacement],
) -> bool:
    if not _is_wall_skin(wall) or is_wall_arcade(wall):
        return False
    w_min, w_max = _placement_aabb(wall)
    for arc in arcades:
        if arc.level != wall.level:
            continue
        a_min, a_max = _placement_aabb(arc)
        if _coplanar_wall_duplicate(w_min, w_max, a_min, a_max):
            return True
    return False


def _dedupe_wall_arcades(placements: List[SolidPlacement]) -> List[SolidPlacement]:
    """Keep one ``wall_arcade`` per (level, cell, face)."""
    seen: Set[FaceKey] = set()
    out: List[SolidPlacement] = []
    for p in placements:
        if not is_wall_arcade(p):
            out.append(p)
            continue
        key = wall_face_key(p)
        if key is None:
            out.append(p)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def count_coplanar_wall_stacks(
    assembly: Assembly,
    *,
    placements: Optional[List[SolidPlacement]] = None,
) -> int:
    """Count coplanar arcade-related wall-skin stacks (measurement helper)."""
    walls = placements
    if walls is None:
        walls = [
            p
            for p in assembly.placements
            if _is_wall_skin(p) or is_wall_arcade(p)
        ]
    stacks = 0
    for i in range(len(walls)):
        for b in walls[i + 1:]:
            if _wall_face_stack_violation(walls[i], b):
                stacks += 1
    return stacks


def repair_wall_face_stacks(assembly: Assembly) -> Assembly:
    """Strip redundant plain walls under ``wall_arcade``; dedupe arcade producers."""
    placements = list(assembly.placements)
    arcades = [p for p in placements if is_wall_arcade(p)]
    if not arcades:
        return assembly

    kept: List[SolidPlacement] = []
    for p in placements:
        if _plain_wall_redundant_with_arcade(p, arcades):
            continue
        kept.append(p)
    kept = _dedupe_wall_arcades(kept)

    return Assembly(
        placements=kept,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


__all__ = [
    "CHECK_WALL_FACE_EXCLUSIVE",
    "claimed_wall_arcade_faces",
    "check_wall_face_exclusive",
    "count_coplanar_wall_stacks",
    "coplanar_wall_overlap",
    "face_is_claimed_for_arcade",
    "is_wall_arcade",
    "repair_wall_face_stacks",
    "wall_face_key",
    "wall_outward_face",
]

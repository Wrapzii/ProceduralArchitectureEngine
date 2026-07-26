"""Entrance approach clearance — nothing may block the walkable path to a door.

WHY THIS EXISTS: style-shell forecourt / planter walls were landing in the bay
beside the door outward cell and reading as a blocked front door. Prefer not
placing over demoting validators.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, TOL_CM, placement_world_aabb
from pae.report import Failure, Report

Cell = Tuple[int, int]

# Pieces that must never sit in the approach corridor.
BLOCKING_ASSETS = frozenset(
    {
        "forecourt_wall",
        "planter_wall",
        "porch_post",
        "window_box",
    }
)
BLOCKING_TAGS = frozenset(
    {
        "forecourt",
        "ground_planter",
        "garden_wall",
        "patio_rail",
    }
)
# Walkable / structural approach pieces — allowed in the corridor.
APPROACH_OK_TAGS = frozenset(
    {
        "stoop",
        "steps",
        "porch",
        "patio",
        "deck",
        "platform",
        "door_surround",
        "jamb",
        "lintel",
        "awning",
        "canopy",
        "above_door",
        "window_sill",
        "window_hood",
        "sill",
        "hood",
        "balcony",
        "balcony_deck",
        "balcony_guard",
        "balcony_support",
        "balcony_door",
        "bracket",
        "walkable",
    }
)


def _face_of(door: SolidPlacement, faces: Optional[Dict[str, str]] = None) -> str:
    for t in door.tags:
        if t.startswith("face_"):
            return t.split("_", 1)[1]
        if t.startswith("face:"):
            return t.split(":", 1)[1]
    if faces and door.piece_id in faces:
        return faces[door.piece_id]
    # Heuristic from piece_id / yaw.
    pid = door.piece_id.lower()
    for face in ("south", "north", "east", "west"):
        if face in pid:
            return face
    if door.yaw in (90, 270):
        return "south"
    return "south"


def outward_delta(face: str) -> Cell:
    return {
        "south": (0, -1),
        "north": (0, 1),
        "west": (-1, 0),
        "east": (1, 0),
    }.get(face, (0, -1))


def lateral_deltas(face: str) -> Tuple[Cell, Cell]:
    if face in ("south", "north"):
        return ((-1, 0), (1, 0))
    return ((0, -1), (0, 1))


def approach_clear_cells(
    door: SolidPlacement,
    *,
    face: Optional[str] = None,
    depth: int = 2,
    lateral: int = 1,
) -> Set[Cell]:
    """Cells that must stay free of barriers for a walkable entrance.

    Includes the door bay, ``depth`` cells outward, and ``lateral`` bays each
    side of that approach strip (so forecourt walls leave a real gap).
    """
    face = face or _face_of(door)
    dx, dy = outward_delta(face)
    lx0, ly0 = lateral_deltas(face)[0]
    clear: Set[Cell] = {door.cell}
    for d in range(0, max(1, depth) + 1):
        base = (door.cell[0] + dx * d, door.cell[1] + dy * d)
        clear.add(base)
        for lat in range(1, max(0, lateral) + 1):
            clear.add((base[0] + lx0 * lat, base[1] + ly0 * lat))
            clear.add((base[0] - lx0 * lat, base[1] - ly0 * lat))
    return clear


def all_door_approach_cells(
    placements: Iterable[SolidPlacement],
    *,
    faces: Optional[Dict[str, str]] = None,
    include_balcony: bool = True,
) -> Set[Cell]:
    clear: Set[Cell] = set()
    for p in placements:
        if p.kind != "wall":
            continue
        aid = p.asset_id
        is_door = "door" in aid or "gate" in aid
        if not is_door:
            continue
        if p.level > 0 and not include_balcony:
            continue
        if p.level > 0 and "balcony" not in p.tags and "balcony_door" not in p.tags:
            # Upper non-balcony doors still need a clear outward cell.
            pass
        face = _face_of(p, faces)
        # Ground: deep approach; upper balcony: one cell outward + laterals.
        depth = 2 if p.level == 0 else 1
        clear |= approach_clear_cells(p, face=face, depth=depth, lateral=1)
    return clear


def _is_blocking_piece(p: SolidPlacement) -> bool:
    # Upper balcony kit lives on the door bay but must never be stripped.
    if p.tags & frozenset(
        {"balcony", "balcony_deck", "balcony_guard", "balcony_support", "balcony_door"}
    ):
        return False
    if p.asset_id in BLOCKING_ASSETS:
        return True
    if "window_box" in p.tags or p.asset_id == "window_box":
        return True
    if p.tags & BLOCKING_TAGS:
        return True
    # Ground planter walls tagged planter + forecourt
    if p.asset_id == "planter_wall" and "ground_planter" in p.tags:
        return True
    return False


def _is_approach_ok(p: SolidPlacement) -> bool:
    if p.tags & APPROACH_OK_TAGS:
        return True
    if p.asset_id in ("porch_slab", "steps_external", "steps_grand", "porch_roof"):
        return True
    if p.asset_id.startswith("doorcase"):
        return True
    return False


def filter_blocking_from_approach(
    pieces: Iterable[SolidPlacement],
    approach: Set[Cell],
) -> List[SolidPlacement]:
    """Drop barrier/planter pieces whose cell sits in the approach corridor."""
    kept: List[SolidPlacement] = []
    for p in pieces:
        if _is_approach_ok(p):
            kept.append(p)
            continue
        if _is_blocking_piece(p) and p.cell in approach:
            continue
        kept.append(p)
    return kept


def validate_entrance_approach_clear(
    assembly: Assembly,
    *,
    faces: Optional[Dict[str, str]] = None,
) -> Report:
    """Fail-closed: blocking pieces in door approach cells → critical."""
    approach = all_door_approach_cells(assembly.placements, faces=faces)
    failures: List[Failure] = []
    for p in assembly.placements:
        if _is_approach_ok(p):
            continue
        if not _is_blocking_piece(p):
            continue
        if p.cell not in approach:
            continue
        failures.append(
            Failure(
                check="entrance_approach_clear",
                message=(
                    f"{p.asset_id} {p.piece_id} blocks door approach cell {p.cell}"
                ),
                critical=True,
                piece_id=p.piece_id,
                world_xyz=(
                    p.cell[0] * MODULE_CM + MODULE_CM * 0.5,
                    p.cell[1] * MODULE_CM + MODULE_CM * 0.5,
                    0.0,
                ),
            )
        )
    return Report.from_failures(failures)


def door_approach_aabb_clear(
    door: SolidPlacement,
    piece: SolidPlacement,
    *,
    face: Optional[str] = None,
) -> bool:
    """True when piece does not occupy the door threshold XY slab."""
    if _is_approach_ok(piece):
        return True
    face = face or _face_of(door)
    dmn, dmx = placement_world_aabb(
        door.cell[0],
        door.cell[1],
        door.level,
        door.yaw,
        door.size_cm,
        door.offset_cm,
        rotates_about_center=door.rotates_about_center,
    )
    # Expand outward by ~0.6 MODULE for threshold clearance.
    dx, dy = outward_delta(face)
    pad = MODULE_CM * 0.55
    if face == "south":
        dmn = (dmn[0] - MODULE_CM * 0.15, dmn[1] - pad, dmn[2])
        dmx = (dmx[0] + MODULE_CM * 0.15, dmx[1], dmx[2])
    elif face == "north":
        dmn = (dmn[0] - MODULE_CM * 0.15, dmn[1], dmn[2])
        dmx = (dmx[0] + MODULE_CM * 0.15, dmx[1] + pad, dmx[2])
    elif face == "west":
        dmn = (dmn[0] - pad, dmn[1] - MODULE_CM * 0.15, dmn[2])
        dmx = (dmx[0], dmx[1] + MODULE_CM * 0.15, dmx[2])
    else:
        dmn = (dmn[0], dmn[1] - MODULE_CM * 0.15, dmn[2])
        dmx = (dmx[0] + pad, dmx[1] + MODULE_CM * 0.15, dmx[2])
    pmn, pmx = placement_world_aabb(
        piece.cell[0],
        piece.cell[1],
        piece.level,
        piece.yaw,
        piece.size_cm,
        piece.offset_cm,
        rotates_about_center=piece.rotates_about_center,
    )
    ox = min(dmx[0], pmx[0]) - max(dmn[0], pmn[0])
    oy = min(dmx[1], pmx[1]) - max(dmn[1], pmn[1])
    oz = min(dmx[2] + MODULE_CM, pmx[2]) - max(dmn[2], pmn[2])
    _ = TOL_CM
    return not (ox > TOL_CM and oy > TOL_CM and oz > TOL_CM)


__all__ = [
    "all_door_approach_cells",
    "approach_clear_cells",
    "door_approach_aabb_clear",
    "filter_blocking_from_approach",
    "validate_entrance_approach_clear",
]

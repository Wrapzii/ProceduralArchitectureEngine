"""Spiral tower shell — central newel + continuous outer drum.

WHY THIS EXISTS
---------------
A helical stair without a newel is a floating wedge stack; without a closed
``tower_arc`` drum it is an open stair in a void. Phase 4.7 / user ask: round
spires need an engineering-correct shell (pillar up the axis, outer quarters
enclosing the climb).

Ownership (@VAL_SPIRAL_SHELL):
  * ``spiral_newel`` primitive placement helpers
  * critical checks ``spiral_newel_exists`` / ``spiral_drum_enclosure``
  * deliberately poisoned fixtures (Handbook §6)

NOT owned here (leave hooks only):
  * tower door / hall aperture → @VAL_TOWER_DOOR (``tower_door`` / ``spiral_door_bay``)
  * crown rampart / circular railing → @VAL_TOWER_RAMPART
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, cell_to_world_cm, placement_world_aabb
from pae.report import Failure
from pae.stair_occupancy import SPIRAL_COMPLEMENTARY_YAWS, SPIRAL_QUARTER_ASSET

SPIRAL_NEWEL_ASSET = "spiral_newel"
SPIRAL_NEWEL_TAG = "newel"
SPIRAL_SHELL_TAG = "spiral_shell"

# @VAL_TOWER_DOOR — one drum bay may be open when a designed tower door is present.
# ``tower_entry`` is the assemble tag; legacy aliases kept for fixtures.
DESIGNED_DOOR_BAY_TAGS = frozenset(
    {"tower_entry", "tower_door", "tower_door_bay", "spiral_door_bay"}
)

Cell = Tuple[int, int]
LevelCell = Tuple[int, int, int]  # level, x, y


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


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


def _yaw_norm(yaw: float | int) -> int:
    return int(yaw) % 360


def is_spiral_newel(p: SolidPlacement) -> bool:
    return p.asset_id == SPIRAL_NEWEL_ASSET or SPIRAL_NEWEL_TAG in p.tags


def spiral_anchor_levels(assembly: Assembly) -> Dict[Cell, Set[int]]:
    """Tower anchor cell → storey levels that host ``stair_spiral_quarter``.

    Rule 5.1 note: spiral quarters use ``p.cell`` as the authored tower anchor
    (``rotates_about_center``); ``covered_cells`` may kiss a neighbour bay under
    drum offset. Existence / drum checks key on that anchor, not the expanded set.
    """
    out: Dict[Cell, Set[int]] = {}
    for p in assembly.placements:
        if p.asset_id != SPIRAL_QUARTER_ASSET:
            continue
        out.setdefault(p.cell, set()).add(p.level)
    return out


def _newel_levels_by_cell(assembly: Assembly) -> Dict[Cell, Set[int]]:
    out: Dict[Cell, Set[int]] = {}
    for p in assembly.placements:
        if not is_spiral_newel(p):
            continue
        out.setdefault(p.cell, set()).add(p.level)
    return out


def _tower_arc_yaws_at(
    assembly: Assembly, cell: Cell, level: int
) -> Set[int]:
    """Yaws of ``tower_arc`` quarters sharing the spiral tower anchor cell."""
    yaws: Set[int] = set()
    for p in assembly.placements:
        if p.kind != "tower_arc":
            continue
        if p.cell != cell or p.level != level:
            continue
        yaws.add(_yaw_norm(p.yaw))
    return yaws


def _designed_door_yaws(
    assembly: Assembly, cell: Cell, level: int
) -> Set[int]:
    """Yaws allowed to lack a drum quarter (designed door aperture).

    Hook for @VAL_TOWER_DOOR: tag a door leaf / bay marker with one of
    ``DESIGNED_DOOR_BAY_TAGS``, or register a door aperture whose interior cell
    is the spiral anchor.
    """
    exempt: Set[int] = set()
    for p in assembly.placements:
        if p.cell != cell or p.level != level:
            continue
        if not (DESIGNED_DOOR_BAY_TAGS & set(p.tags)):
            continue
        exempt.add(_yaw_norm(p.yaw))
    for ap in assembly.apertures:
        if ap.kind != "door":
            continue
        if ap.level != level:
            continue
        if ap.interior_cell != cell:
            continue
        # Derive yaw from exterior neighbour when present.
        ix, iy = ap.interior_cell
        ex, ey = ap.exterior_cell
        if ex == ix - 1 and ey == iy:
            exempt.add(0)
        elif ex == ix + 1 and ey == iy:
            exempt.add(180)
        elif ey == iy + 1 and ex == ix:
            exempt.add(90)
        elif ey == iy - 1 and ex == ix:
            exempt.add(270)
    return exempt


def check_spiral_newel_exists(assembly: Assembly) -> List[Failure]:
    """Existence: every spiral climb storey has a central newel on the axis.

    Handbook §2 Q7 / class 1 Existence. Critical — a helix without a pillar is
    not an engineering shell.
    """
    anchors = spiral_anchor_levels(assembly)
    if not anchors:
        return []
    newels = _newel_levels_by_cell(assembly)
    failures: List[Failure] = []
    for cell, levels in sorted(anchors.items()):
        have = newels.get(cell, set())
        for level in sorted(levels):
            if level in have:
                continue
            world = cell_to_world_cm(cell[0], cell[1], level)
            # Centre of bay (newel axis), mid-storey.
            world_xyz = (
                world[0] + MODULE_CM * 0.5,
                world[1] + MODULE_CM * 0.5,
                world[2] + STOREY_CM * 0.5,
            )
            failures.append(
                Failure(
                    check="spiral_newel_exists",
                    message=(
                        f"spiral stair at cell {cell} level {level} has no central "
                        f"newel pillar ({SPIRAL_NEWEL_ASSET})"
                    ),
                    world_xyz=world_xyz,
                    critical=True,
                )
            )
    return failures


def check_spiral_drum_enclosure(assembly: Assembly) -> List[Failure]:
    """Containment: spiral climb levels are enclosed by four ``tower_arc`` yaws.

    Handbook class 8 Containment. A missing quarter is a bay gap unless that yaw
    is a designed door aperture (@VAL_TOWER_DOOR hook).
    """
    anchors = spiral_anchor_levels(assembly)
    if not anchors:
        return []
    required = set(SPIRAL_COMPLEMENTARY_YAWS)
    failures: List[Failure] = []
    for cell, levels in sorted(anchors.items()):
        for level in sorted(levels):
            present = _tower_arc_yaws_at(assembly, cell, level)
            door_yaws = _designed_door_yaws(assembly, cell, level)
            missing = sorted(required - present - door_yaws)
            if not missing:
                continue
            world = cell_to_world_cm(cell[0], cell[1], level)
            world_xyz = (
                world[0] + MODULE_CM * 0.5,
                world[1] + MODULE_CM * 0.5,
                world[2] + STOREY_CM * 0.5,
            )
            failures.append(
                Failure(
                    check="spiral_drum_enclosure",
                    message=(
                        f"spiral drum at cell {cell} level {level} missing tower_arc "
                        f"yaw(s) {missing} (have {sorted(present)}; "
                        f"door_exempt {sorted(door_yaws)})"
                    ),
                    world_xyz=world_xyz,
                    critical=True,
                )
            )
    return failures


def check_spiral_shell(assembly: Assembly) -> List[Failure]:
    """Run all spiral-shell checks (newel + drum)."""
    failures: List[Failure] = []
    failures.extend(check_spiral_newel_exists(assembly))
    failures.extend(check_spiral_drum_enclosure(assembly))
    return failures


def make_spiral_newel_placement(
    *,
    piece_id: str,
    cell: Cell,
    level: int,
    xy_offset: Tuple[float, float] = (0.0, 0.0),
    size_cm: Optional[Tuple[float, float, float]] = None,
    tags: Optional[frozenset] = None,
) -> SolidPlacement:
    """Greybox newel on the tower axis (assemble helper)."""
    from pae.primitives.catalog import get as get_primitive

    desc = get_primitive(SPIRAL_NEWEL_ASSET)
    sx, sy, sz = size_cm or desc.size_cm
    base_tags = set(desc.tags)
    if tags:
        base_tags |= set(tags)
    return SolidPlacement(
        piece_id=piece_id,
        asset_id=desc.id,
        kind=desc.kind,
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(xy_offset[0], xy_offset[1], 0.0),
        size_cm=(sx, sy, sz),
        rotates_about_center=True,
        tags=frozenset(base_tags),
    )


def place_spiral_newels(
    *,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    cell: Cell,
    levels: Iterable[int],
    xy_offset: Tuple[float, float],
    next_piece_id,
) -> None:
    """Emit one ``spiral_newel`` per climb storey on the spiral axis."""
    for level in sorted(set(levels)):
        pid = next_piece_id(counters, "spiral_newel", cell, level)
        placements.append(
            make_spiral_newel_placement(
                piece_id=pid,
                cell=cell,
                level=level,
                xy_offset=xy_offset,
            )
        )


def ensure_spiral_drum_quarters(
    *,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    cell: Cell,
    levels: Iterable[int],
    xy_offset: Tuple[float, float],
    solid_arc_size_cm: Tuple[float, float, float],
    solid_arc_tags: frozenset,
    next_piece_id,
    door_exempt_yaws: Optional[Set[int]] = None,
) -> List[int]:
    """Fill missing ``tower_arc`` yaws for spiral enclosure (idempotent).

    Returns the list of yaw angles that were added. Skips designed door bays.
    Does not steal door/rampart ownership — only solid drum quarters.
    """
    exempt = set(door_exempt_yaws or ())
    # Build a temporary view for present-yaw lookup.
    tmp = Assembly(placements=list(placements))
    added: List[int] = []
    for level in sorted(set(levels)):
        present = _tower_arc_yaws_at(tmp, cell, level)
        for yaw in sorted(SPIRAL_COMPLEMENTARY_YAWS):
            if yaw in present or yaw in exempt:
                continue
            pid = next_piece_id(counters, f"tower_arc_{yaw}", cell, level)
            placements.append(
                SolidPlacement(
                    piece_id=pid,
                    asset_id="tower_arc_quarter",
                    kind="tower_arc",
                    cell=cell,
                    level=level,
                    yaw=yaw,
                    offset_cm=(xy_offset[0], xy_offset[1], 0.0),
                    size_cm=solid_arc_size_cm,
                    rotates_about_center=True,
                    tags=solid_arc_tags | frozenset({SPIRAL_SHELL_TAG}),
                )
            )
            added.append(yaw)
            # Keep tmp in sync for multi-level loops.
            tmp.placements.append(placements[-1])
    return added


# ---------------------------------------------------------------------------
# Handbook §6 poisoned fixtures
# ---------------------------------------------------------------------------


def _stub_spiral_quarter(
    *,
    piece_id: str,
    cell: Cell,
    level: int,
    yaw: int,
    z_off: float = 0.0,
) -> SolidPlacement:
    rise = STOREY_CM * 0.25
    return SolidPlacement(
        piece_id=piece_id,
        asset_id=SPIRAL_QUARTER_ASSET,
        kind="stair",
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=(0.0, 0.0, z_off),
        size_cm=(MODULE_CM, MODULE_CM, rise),
        rotates_about_center=True,
        tags=frozenset({"stair", "spiral"}),
    )


def _stub_tower_arc(
    *,
    piece_id: str,
    cell: Cell,
    level: int,
    yaw: int,
) -> SolidPlacement:
    return SolidPlacement(
        piece_id=piece_id,
        asset_id="tower_arc_quarter",
        kind="tower_arc",
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
        rotates_about_center=True,
        tags=frozenset({"tower", "arc"}),
    )


def make_spiral_missing_newel_defect() -> Assembly:
    """Poison: full helix + closed drum, but no newel pillar."""
    cell: Cell = (3, 3)
    level = 0
    pieces: List[SolidPlacement] = []
    for i, yaw in enumerate((0, 90, 180, 270)):
        pieces.append(
            _stub_spiral_quarter(
                piece_id=f"poison_spiral_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
                z_off=i * STOREY_CM * 0.25,
            )
        )
        pieces.append(
            _stub_tower_arc(
                piece_id=f"poison_arc_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
            )
        )
    return Assembly(placements=pieces, storeys=2)


def make_spiral_drum_bay_gap_defect() -> Assembly:
    """Poison: helix + newel, but one drum quarter missing (no door exemption)."""
    cell: Cell = (4, 4)
    level = 0
    pieces: List[SolidPlacement] = [
        make_spiral_newel_placement(
            piece_id="poison_newel",
            cell=cell,
            level=level,
        )
    ]
    for i, yaw in enumerate((0, 90, 180, 270)):
        pieces.append(
            _stub_spiral_quarter(
                piece_id=f"poison_spiral_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
                z_off=i * STOREY_CM * 0.25,
            )
        )
    # Only three drum quarters — yaw 270 is the bay gap.
    for yaw in (0, 90, 180):
        pieces.append(
            _stub_tower_arc(
                piece_id=f"poison_arc_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
            )
        )
    return Assembly(placements=pieces, storeys=2)


def make_spiral_drum_door_exempt_ok() -> Assembly:
    """Control: bay gap at yaw 0 is OK when tagged as designed tower door."""
    cell: Cell = (5, 5)
    level = 0
    pieces: List[SolidPlacement] = [
        make_spiral_newel_placement(
            piece_id="ok_newel",
            cell=cell,
            level=level,
        ),
        # Door bay marker — @VAL_TOWER_DOOR will place a real leaf; tag is the contract.
        SolidPlacement(
            piece_id="ok_tower_door_bay",
            asset_id="wall_door",
            kind="wall",
            cell=cell,
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(MODULE_CM, MODULE_CM * 0.15, STOREY_CM),
            rotates_about_center=True,
            tags=frozenset({"tower_door", "spiral_door_bay"}),
        ),
    ]
    for i, yaw in enumerate((0, 90, 180, 270)):
        pieces.append(
            _stub_spiral_quarter(
                piece_id=f"ok_spiral_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
                z_off=i * STOREY_CM * 0.25,
            )
        )
    for yaw in (90, 180, 270):
        pieces.append(
            _stub_tower_arc(
                piece_id=f"ok_arc_{yaw}",
                cell=cell,
                level=level,
                yaw=yaw,
            )
        )
    return Assembly(placements=pieces, storeys=2)


def designed_spiral_newel_pair(a: SolidPlacement, b: SolidPlacement) -> bool:
    """Same-cell newel ↔ spiral quarter / tower_arc AABB overlap is by design."""
    if a.cell != b.cell or a.level != b.level:
        return False
    if is_spiral_newel(a) and not is_spiral_newel(b):
        other = b
    elif is_spiral_newel(b) and not is_spiral_newel(a):
        other = a
    else:
        return False
    if other.asset_id == SPIRAL_QUARTER_ASSET:
        return True
    if other.kind == "tower_arc":
        return True
    return False


__all__ = [
    "SPIRAL_NEWEL_ASSET",
    "SPIRAL_NEWEL_TAG",
    "SPIRAL_SHELL_TAG",
    "DESIGNED_DOOR_BAY_TAGS",
    "check_spiral_shell",
    "check_spiral_newel_exists",
    "check_spiral_drum_enclosure",
    "place_spiral_newels",
    "ensure_spiral_drum_quarters",
    "make_spiral_newel_placement",
    "make_spiral_missing_newel_defect",
    "make_spiral_drum_bay_gap_defect",
    "make_spiral_drum_door_exempt_ok",
    "designed_spiral_newel_pair",
    "is_spiral_newel",
    "spiral_anchor_levels",
]

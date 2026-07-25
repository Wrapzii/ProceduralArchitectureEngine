"""Phase 9.2 — upper-storey exterior entrances (validation-first).

Roadmap T-007 / T-009: an ``upper_exterior`` door on storey N opening to outside
air is illegal unless a walkable exterior landing / porch sits immediately
outside it. ``aperture_reachability`` already enforces that geometry rule for
*every* upper door; this module makes the EntranceSpec contract explicit:

  * role ``upper_exterior`` (+ ``EntranceSpec.storey``)
  * critical check ``upper_entrance_landing`` for role-tagged doors
  * 1-bay greybox landing helper for fixtures / future assemble

Do not demote ``aperture_reachability`` — both checks stay critical.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, floor_placement_z_cm
from pae.existence import entrance_role_tag
from pae.report import Failure
from pae.trim import covered_cells

Cell = Tuple[int, int]

UPPER_EXTERIOR_ROLE = "upper_exterior"
UPPER_LANDING_TAG = "upper_landing"
CHECK_UPPER_ENTRANCE_LANDING = "upper_entrance_landing"


def _walkable_and_interior(
    assembly: Assembly,
) -> Tuple[Dict[int, Set[Cell]], Dict[int, Set[Cell]], Dict[int, Set[Cell]]]:
    """Per-level walkable deck, balcony/landing deck, and interior floor cells."""
    walkable: Dict[int, Set[Cell]] = {}
    balcony_deck: Dict[int, Set[Cell]] = {}
    interior: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind in ("floor", "surface") and "hole" not in p.asset_id:
            cells = covered_cells(p)
            walkable.setdefault(p.level, set()).update(cells)
            if p.kind == "floor" and (
                "balcony" in p.tags or UPPER_LANDING_TAG in p.tags
            ):
                balcony_deck.setdefault(p.level, set()).update(cells)
            if p.kind == "floor" and "hole" not in p.asset_id:
                interior.setdefault(p.level, set()).update(cells)
        elif p.kind == "stair":
            walkable.setdefault(p.level, set()).update(covered_cells(p))
    return walkable, balcony_deck, interior


def door_opens_onto_exterior_landing(
    door: SolidPlacement,
    walkable: Dict[int, Set[Cell]],
    balcony_deck: Dict[int, Set[Cell]],
    interior: Dict[int, Set[Cell]],
) -> bool:
    """True when a neighbour cell is walkable and not merely the room interior.

    Matches ``validate._check_aperture_reachability``: balcony / upper_landing
    tagged deck still counts when it shares a bay with interior floor.
    """
    deck = walkable.get(door.level, set())
    inside = interior.get(door.level, set())
    landing = balcony_deck.get(door.level, set())
    for c in covered_cells(door):
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (c[0] + dx, c[1] + dy)
            if n in deck and (n not in inside or n in landing):
                return True
    return False


def make_upper_landing(
    cell: Cell,
    level: int,
    *,
    piece_id: str = "upper_landing",
) -> SolidPlacement:
    """1-bay exterior porch / landing at storey height (T-009 greybox)."""
    if level < 1:
        raise ValueError("upper landing requires level >= 1")
    floor_z = floor_placement_z_cm(level)
    return SolidPlacement(
        piece_id=piece_id,
        asset_id="floor",
        kind="floor",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, floor_z),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor", UPPER_LANDING_TAG}),
    )


def check_upper_entrance_landing(assembly: Assembly) -> List[Failure]:
    """Role-tagged upper_exterior doors must open onto an exterior landing.

    Ground-only doors and untagged upper doors are left to
    ``aperture_reachability`` / entrance existence. This check only fires for
    ``entrance_role_upper_exterior``.
    """
    role_tag = entrance_role_tag(UPPER_EXTERIOR_ROLE)
    doors = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and ("door" in p.asset_id or "gate" in p.asset_id)
        and "partition" not in set(p.tags)
        and role_tag in p.tags
    ]
    if not doors:
        return []

    walkable, balcony_deck, interior = _walkable_and_interior(assembly)
    failures: List[Failure] = []
    for d in doors:
        world_xyz = (
            d.cell[0] * MODULE_CM + MODULE_CM * 0.5,
            d.cell[1] * MODULE_CM + MODULE_CM * 0.5,
            d.level * STOREY_CM,
        )

        if d.level < 1:
            failures.append(
                Failure(
                    check=CHECK_UPPER_ENTRANCE_LANDING,
                    message=(
                        f"upper_exterior door {d.piece_id} is on level {d.level} — "
                        f"role requires storey >= 1 with an exterior landing"
                    ),
                    world_xyz=world_xyz,
                    piece_id=d.piece_id,
                    critical=True,
                )
            )
            continue

        if not door_opens_onto_exterior_landing(
            d, walkable, balcony_deck, interior
        ):
            failures.append(
                Failure(
                    check=CHECK_UPPER_ENTRANCE_LANDING,
                    message=(
                        f"upper_exterior door {d.piece_id} ({d.asset_id}) at "
                        f"level {d.level} has no exterior landing / porch "
                        f"(aperture_reachability pairing required)"
                    ),
                    world_xyz=world_xyz,
                    piece_id=d.piece_id,
                    critical=True,
                )
            )
    return failures


__all__ = [
    "UPPER_EXTERIOR_ROLE",
    "UPPER_LANDING_TAG",
    "CHECK_UPPER_ENTRANCE_LANDING",
    "door_opens_onto_exterior_landing",
    "make_upper_landing",
    "check_upper_entrance_landing",
]

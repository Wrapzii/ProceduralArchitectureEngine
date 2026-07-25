"""Existence checks — declared spec intent must appear in assembled output.

Also hosts Phase 1.5 envelope-breach leaf checks (no bare hole without a door/gate).
"""

from __future__ import annotations

from typing import List, Sequence

from pae.assembly_types import Assembly, SolidPlacement
from pae.report import Failure
from pae.spec import EntranceSpec

_ENTRANCE_ROLE_TAG_PREFIX = "entrance_role_"

# Hall ↔ spiral/tower stairwell passage (Handbook §2 Q7 Existence).
TOWER_ENTRY_TAG = "tower_entry"
CHECK_TOWER_ENTRY_DOOR = "tower_entry_door"


def entrance_role_tag(role: str) -> str:
    return f"{_ENTRANCE_ROLE_TAG_PREFIX}{role}"


def is_door_or_gate_asset(asset_id: str) -> bool:
    """True when *asset_id* is a passage leaf (door or gate), not a bare wall hole.

    Matches assemble's aperture registration heuristic (``"door" in id or "gate" in id``).
    ``wall_arcade`` is intentionally excluded — an arch cut with no leaf is a bare hole
    for passage purposes (roadmap §1.5).
    """
    aid = (asset_id or "").lower()
    return "door" in aid or "gate" in aid


def placed_entrance_roles(assembly: Assembly) -> set[str]:
    """Roles observed on perimeter door placements."""
    roles: set[str] = set()
    for placement in assembly.placements:
        for tag in placement.tags:
            if tag.startswith(_ENTRANCE_ROLE_TAG_PREFIX):
                roles.add(tag[len(_ENTRANCE_ROLE_TAG_PREFIX) :])
    return roles


def check_entrance_existence(
    entrances: Sequence[EntranceSpec],
    assembly: Assembly,
) -> List[Failure]:
    """Every declared entrance role must have ≥1 tagged door placement."""
    if not entrances:
        return []
    declared = {e.role for e in entrances}
    placed = placed_entrance_roles(assembly)
    failures: List[Failure] = []
    for role in sorted(declared):
        if role not in placed:
            failures.append(
                Failure(
                    check="entrance_existence",
                    message=(
                        f"declared entrance role {role!r} has no placed door "
                        f"(expected tag {entrance_role_tag(role)!r})"
                    ),
                    world_xyz=None,
                )
            )
    return failures


def assembly_requires_tower_entry(assembly: Assembly) -> bool:
    """True when a spiral stair or a stair inside a tower drum is present.

    Critical existence for ``tower_entry`` doors — hall must open into the
    stairwell (ground, and preferably each landing storey).
    """
    has_spiral = any(
        p.asset_id == "stair_spiral_quarter" for p in assembly.placements
    )
    if has_spiral:
        return True
    tower_cells = {
        p.cell for p in assembly.placements if p.kind == "tower_arc"
    }
    if not tower_cells:
        return False
    return any(
        p.kind == "stair" and p.cell in tower_cells for p in assembly.placements
    )


def placed_tower_entry_doors(assembly: Assembly) -> List[SolidPlacement]:
    """Door/gate placements tagged ``tower_entry``."""
    return [
        p
        for p in assembly.placements
        if TOWER_ENTRY_TAG in p.tags and is_door_or_gate_asset(p.asset_id)
    ]


def check_tower_entry_door(assembly: Assembly) -> List[Failure]:
    """Spiral / tower-stair assemblies must place a hall→drum doorway.

    Handbook §2 Q7 Existence + Q6 Use. Critical when ``stair_kind=spiral`` or a
    stair shares a tower drum cell. At least one ground-level ``tower_entry``
    door is required; landings are preferred but not existence-gated here.
    """
    if not assembly_requires_tower_entry(assembly):
        return []
    entries = placed_tower_entry_doors(assembly)
    if not entries:
        return [
            Failure(
                check=CHECK_TOWER_ENTRY_DOOR,
                message=(
                    "spiral/tower stair has no hall→drum doorway "
                    f"(expected a door tagged {TOWER_ENTRY_TAG!r})"
                ),
                world_xyz=None,
                critical=True,
            )
        ]
    if not any(p.level == 0 for p in entries):
        return [
            Failure(
                check=CHECK_TOWER_ENTRY_DOOR,
                message=(
                    "tower stairwell has no ground-level tower_entry door — "
                    "hall cannot enter the drum at grade"
                ),
                world_xyz=None,
                critical=True,
            )
        ]
    return []


# Re-export ensemble existence for callers that already import from existence.
def check_entrance_ensemble_existence(
    entrances: Sequence[EntranceSpec],
    assembly: Assembly,
) -> List[Failure]:
    from pae.entrance_ensemble import (
        check_entrance_ensemble_existence as _check,
    )

    return _check(entrances, assembly)


def check_no_bare_aperture_holes(assembly: Assembly) -> List[Failure]:
    """Passage breaches must carry a door/gate asset — never a bare hole (roadmap §1.5).

    Covers:
      * every ``kind=="door"`` aperture's host wall piece
      * every placement tagged ``balcony_door`` (compound balcony access)
      * every placement tagged ``entrance_role_*`` (declarative EntranceSpec)
      * every placement tagged ``tower_entry`` (hall↔tower stairwell)

    Critical: a hole you can walk through with no leaf is a shippable defect.
    """
    by_id = {p.piece_id: p for p in assembly.placements}
    failures: List[Failure] = []

    for ap in assembly.apertures:
        if ap.kind != "door":
            continue
        wall = by_id.get(ap.wall_piece_id)
        if wall is None:
            failures.append(
                Failure(
                    check="no_bare_aperture",
                    message=(
                        f"door aperture {ap.piece_id} references missing wall "
                        f"{ap.wall_piece_id}"
                    ),
                    world_xyz=ap.world_xyz,
                    piece_id=ap.piece_id,
                    critical=True,
                )
            )
            continue
        if not is_door_or_gate_asset(wall.asset_id):
            failures.append(
                Failure(
                    check="no_bare_aperture",
                    message=(
                        f"envelope opening {ap.piece_id} uses {wall.asset_id!r} — "
                        f"passage breaches require a door or gate asset, not a bare hole"
                    ),
                    world_xyz=ap.world_xyz,
                    piece_id=wall.piece_id,
                    critical=True,
                )
            )

    for placement in assembly.placements:
        tagged_passage = (
            "balcony_door" in placement.tags
            or TOWER_ENTRY_TAG in placement.tags
            or any(t.startswith(_ENTRANCE_ROLE_TAG_PREFIX) for t in placement.tags)
        )
        if not tagged_passage:
            continue
        if is_door_or_gate_asset(placement.asset_id):
            continue
        failures.append(
            Failure(
                check="no_bare_aperture",
                message=(
                    f"passage-tagged wall {placement.piece_id} uses "
                    f"{placement.asset_id!r} — door/gate leaf required "
                    f"(balcony_door / entrance_role / tower_entry)"
                ),
                world_xyz=None,
                piece_id=placement.piece_id,
                critical=True,
            )
        )

    return failures

"""Existence checks — declared spec intent must appear in assembled output.

Also hosts Phase 1.5 envelope-breach leaf checks (no bare hole without a door/gate).
"""

from __future__ import annotations

from typing import List, Sequence

from pae.assembly_types import Assembly
from pae.report import Failure
from pae.spec import EntranceSpec

_ENTRANCE_ROLE_TAG_PREFIX = "entrance_role_"


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
        tagged_passage = "balcony_door" in placement.tags or any(
            t.startswith(_ENTRANCE_ROLE_TAG_PREFIX) for t in placement.tags
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
                    f"(balcony_door / entrance_role)"
                ),
                world_xyz=None,
                piece_id=placement.piece_id,
                critical=True,
            )
        )

    return failures

"""Per-volume storey datum consistency — Roadmap 10.6 / T-111 / Handbook §11d.

WHY: ``contract.storey_datum_z_cm`` routes the uniform storey grid today. A wing whose
floors sit half a storey above its neighbour needs a **declared per-volume datum offset** —
not a taller ceiling (``RoomSpec.height_storeys`` already covers that).

This validator fires only when a placement carries both ``volume:<id>`` and an explicit
``datum_offset_cm:<n>`` tag (or inherits the offset from another piece in the same volume).
It checks that ``offset_cm[2]`` matches ``placement_volume_offset_z_cm`` — the delta baked
into the placement while the cell grid remains uniform. No assemble behaviour change.

Coordinate with siblings (do not duplicate):
  * Structure membership / party walls → ``pae/structure_identity.py``
  * ``flight_footprint_distinct`` → ``stair_flight_stack`` in ``validate.py``
  * ``roof_edging_exclusive`` → ``pae/roof_edging.py``
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    DATUM_OFFSET_TAG_PREFIX,
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    VOLUME_TAG_PREFIX,
    datum_offset_cm_from_tags,
    floor_placement_z_cm,
    placement_volume_offset_z_cm,
    placement_world_aabb,
    storey_datum_z_cm,
    volume_id_from_tags,
)
from pae.report import Failure

CHECK_STOREY_DATUM_CONSISTENT = "storey_datum_consistent"

_DATUM_KINDS = frozenset({"floor", "ground", "stair", "wall", "plinth"})


def _datum_offset_tag(offset_cm: float) -> str:
    return f"{DATUM_OFFSET_TAG_PREFIX}{offset_cm}"


def _volume_tag(volume_id: str) -> str:
    return f"{VOLUME_TAG_PREFIX}{volume_id}"


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


def collect_volume_datum_offsets(
    assembly: Assembly,
) -> Tuple[Dict[str, float], List[Failure]]:
    """Map volume id → declared datum offset; report conflicting declarations."""
    offsets: Dict[str, float] = {}
    conflicts: List[Failure] = []
    for p in assembly.placements:
        vid = volume_id_from_tags(p.tags)
        if vid is None:
            continue
        decl = datum_offset_cm_from_tags(p.tags)
        if decl is None:
            continue
        prev = offsets.get(vid)
        if prev is not None and abs(prev - decl) > TOL_CM:
            a_min, a_max = _placement_aabb(p)
            conflicts.append(
                Failure(
                    check=CHECK_STOREY_DATUM_CONSISTENT,
                    message=(
                        f"volume {vid!r} declares conflicting datum offsets "
                        f"{prev:.1f} cm vs {decl:.1f} cm — one offset per volume"
                    ),
                    world_xyz=_centre(a_min, a_max),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
            continue
        offsets[vid] = decl
    return offsets, conflicts


def expected_placement_offset_z_cm(
    p: SolidPlacement,
    volume_offsets: Dict[str, float],
) -> Optional[float]:
    """Expected ``offset_cm[2]`` for a volume-tagged placement, or None if not checked."""
    vid = volume_id_from_tags(p.tags)
    if vid is None:
        return None
    decl = datum_offset_cm_from_tags(p.tags)
    if decl is None:
        decl = volume_offsets.get(vid)
    if decl is None or abs(decl) <= TOL_CM:
        return None
    if p.kind not in _DATUM_KINDS:
        return None
    return placement_volume_offset_z_cm(
        level=p.level,
        kind=p.kind,
        datum_offset_cm=decl,
    )


def check_storey_datum_consistent(assembly: Assembly) -> List[Failure]:
    """Critical: volume-tagged placements must honour declared per-volume datum offsets."""
    volume_offsets, failures = collect_volume_datum_offsets(assembly)
    seen: Set[Tuple[str, int, str]] = set()

    for p in assembly.placements:
        expected_z = expected_placement_offset_z_cm(p, volume_offsets)
        if expected_z is None:
            continue
        actual_z = p.offset_cm[2]
        if abs(actual_z - expected_z) <= TOL_CM:
            continue
        vid = volume_id_from_tags(p.tags) or ""
        key = (vid, p.level, p.kind)
        if key in seen:
            continue
        seen.add(key)
        decl = datum_offset_cm_from_tags(p.tags) or volume_offsets.get(vid, 0.0)
        a_min, a_max = _placement_aabb(p)
        failures.append(
            Failure(
                check=CHECK_STOREY_DATUM_CONSISTENT,
                message=(
                    f"{p.piece_id} ({p.kind}) in volume {vid!r} uses offset_cm[2]="
                    f"{actual_z:.1f} cm but per-volume datum expects "
                    f"{expected_z:.1f} cm at level {p.level} "
                    f"(datum_offset_cm={decl:.1f}) — must use per-volume datum accessor"
                ),
                world_xyz=_centre(a_min, a_max),
                piece_id=p.piece_id,
                critical=True,
            )
        )
    return failures


# ---------------------------------------------------------------------------
# Broken fixtures (Handbook §6 — can-fire first)
# ---------------------------------------------------------------------------


def make_storey_datum_mismatch_defect() -> Assembly:
    """Mezzanine floor ignores declared half-storey volume datum (T-111)."""
    half = STOREY_CM * 0.5
    vid = "mezz_wing"
    return Assembly(
        placements=[
            SolidPlacement(
                piece_id="mezz_floor",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),  # uniform grid — ignores volume offset
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset(
                    {
                        _volume_tag(vid),
                        _datum_offset_tag(half),
                        "floor",
                    }
                ),
            )
        ],
        storeys=2,
    )


def make_storey_datum_stair_mismatch_defect() -> Assembly:
    """Stair base in offset volume still sits on uniform grid datum."""
    half = STOREY_CM * 0.5
    vid = "stepped_wing"
    return Assembly(
        placements=[
            SolidPlacement(
                piece_id="offset_stair",
                asset_id="stair_straight",
                kind="stair",
                cell=(1, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),  # should be half
                size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
                tags=frozenset(
                    {
                        _volume_tag(vid),
                        _datum_offset_tag(half),
                        "stair",
                    }
                ),
            )
        ],
        storeys=2,
    )


def make_storey_datum_conflict_defect() -> Assembly:
    """Two pieces in one volume declare different datum offsets."""
    vid = "conflict_wing"
    return Assembly(
        placements=[
            SolidPlacement(
                piece_id="floor_a",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, floor_placement_z_cm(1, datum_offset_cm=100.0) - storey_datum_z_cm(1)),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({_volume_tag(vid), _datum_offset_tag(100.0), "floor"}),
            ),
            SolidPlacement(
                piece_id="floor_b",
                asset_id="floor",
                kind="floor",
                cell=(1, 0),
                level=1,
                yaw=0,
                offset_cm=(0.0, 0.0, floor_placement_z_cm(1, datum_offset_cm=175.0) - storey_datum_z_cm(1)),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({_volume_tag(vid), _datum_offset_tag(175.0), "floor"}),
            ),
        ],
        storeys=2,
    )


def make_storey_datum_correct_volume() -> Assembly:
    """Offset volume with correctly baked ``offset_cm[2]`` — must pass."""
    half = STOREY_CM * 0.5
    vid = "good_wing"
    return Assembly(
        placements=[
            SolidPlacement(
                piece_id="mezz_ok",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=1,
                yaw=0,
                offset_cm=(
                    0.0,
                    0.0,
                    placement_volume_offset_z_cm(
                        level=1, kind="floor", datum_offset_cm=half
                    ),
                ),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset(
                    {
                        _volume_tag(vid),
                        _datum_offset_tag(half),
                        "floor",
                    }
                ),
            )
        ],
        storeys=2,
    )


__all__ = [
    "CHECK_STOREY_DATUM_CONSISTENT",
    "check_storey_datum_consistent",
    "collect_volume_datum_offsets",
    "expected_placement_offset_z_cm",
    "make_storey_datum_conflict_defect",
    "make_storey_datum_correct_volume",
    "make_storey_datum_mismatch_defect",
    "make_storey_datum_stair_mismatch_defect",
]

"""Handbook §11d ``storey_datum_consistent`` — per-volume datum (T-111), broken fixtures first.

Sibling checks already landed (not covered here):
  * Structure identity / party walls / stair cores → ``pae/structure_identity.py``
  * ``flight_footprint_distinct`` → ``stair_flight_stack`` — ``test_stair_flight_offset.py``
  * ``roof_edging_exclusive`` — ``test_roof_edging_exclusive.py``

Not in scope: ``RoomSpec.height_storeys`` / double-height ceilings — that is vertical
extent, not storey datum Z.
"""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    floor_placement_z_cm,
    placement_volume_offset_z_cm,
    storey_datum_z_cm,
)
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec
from pae.storey_datum_validate import (
    CHECK_STOREY_DATUM_CONSISTENT,
    check_storey_datum_consistent,
    make_storey_datum_conflict_defect,
    make_storey_datum_correct_volume,
    make_storey_datum_mismatch_defect,
    make_storey_datum_stair_mismatch_defect,
)
from pae.validate import validate


def test_mezz_floor_ignoring_volume_datum_fires():
    poisoned = make_storey_datum_mismatch_defect()
    hits = check_storey_datum_consistent(poisoned)
    assert hits, "storey_datum_consistent must fire when volume offset is ignored"
    assert all(f.check == CHECK_STOREY_DATUM_CONSISTENT and f.critical for f in hits)


def test_stair_in_offset_volume_uses_uniform_datum_fires():
    poisoned = make_storey_datum_stair_mismatch_defect()
    hits = check_storey_datum_consistent(poisoned)
    assert hits, "stair base must honour volume datum offset"
    assert all(f.critical for f in hits)


def test_conflicting_volume_datum_offsets_fire():
    poisoned = make_storey_datum_conflict_defect()
    hits = check_storey_datum_consistent(poisoned)
    assert hits, "conflicting datum_offset_cm in one volume must fail closed"
    assert any("conflicting datum offsets" in f.message for f in hits)


def test_correct_volume_datum_offset_passes():
    asm = make_storey_datum_correct_volume()
    assert check_storey_datum_consistent(asm) == []


def test_validate_surfaces_storey_datum_consistent_as_critical():
    _, report = validate(make_storey_datum_mismatch_defect())
    assert any(
        f.check == CHECK_STOREY_DATUM_CONSISTENT and f.critical for f in report.critical
    )


def test_double_height_assembly_without_volume_tags_is_clean():
    """RoomSpec.height_storeys ceilings must not trip datum-offset checks."""
    _, _, asm, _ = run_through_assemble(m2_two_storey_stair_spec())
    datum_hits = [f for f in check_storey_datum_consistent(asm) if f.critical]
    assert datum_hits == [], [f.message for f in datum_hits]


def test_uniform_floor_without_volume_tags_is_clean():
    asm = Assembly(
        placements=[
            SolidPlacement(
                piece_id="plain_floor",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                tags=frozenset({"floor"}),
            )
        ]
    )
    assert check_storey_datum_consistent(asm) == []


def test_placement_volume_offset_z_cm_floor_and_stair():
    half = STOREY_CM * 0.5
    assert placement_volume_offset_z_cm(level=1, kind="floor", datum_offset_cm=half) == (
        half - FLOOR_T_CM
    )
    assert placement_volume_offset_z_cm(level=0, kind="stair", datum_offset_cm=half) == half
    assert floor_placement_z_cm(1, datum_offset_cm=half) == (
        storey_datum_z_cm(1, datum_offset_cm=half) - FLOOR_T_CM
    )

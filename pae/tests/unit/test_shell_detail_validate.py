"""Poison + green tests for style-shell / K2 detail validators.

RAM-safe: fancy manor + synthetic poison fixtures only (no fortress/school/city).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.fancy_manor import build_fancy_manor
from pae.shell_detail_validate import (
    CHECK_BALCONY_ACCESS_GAP,
    CHECK_BALCONY_DECK_SUPPORT,
    CHECK_BALCONY_RAIL_ON_EDGE,
    CHECK_BALCONY_RAIL_ORIENTATION,
    CHECK_DOORWAY_OPENING_CLEAR,
    check_balcony_deck_support,
    check_balcony_rail_contracts,
    check_doorway_opening_clear,
    check_shell_detail_contracts,
)
from pae.validate import validate


def _asm(placements):
    return Assembly(placements=list(placements))


def _door_stub(*, piece_id: str = "wall_south_0_3_0") -> SolidPlacement:
    return SolidPlacement(
        piece_id=piece_id,
        asset_id="wall_door_double",
        kind="wall",
        cell=(3, 0),
        level=0,
        yaw=270,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        rotates_about_center=False,
        tags=frozenset({"door", "face_south", "exterior"}),
    )


def test_poison_post_inside_doorway_is_critical():
    door = _door_stub()
    # Tall post centred in the door bay — occupies the aperture prism.
    post = SolidPlacement(
        piece_id="poison_jamb_mid",
        asset_id="band_pilaster",
        kind="column",
        cell=door.cell,
        level=0,
        yaw=90,
        offset_cm=(MODULE_CM * 0.5, -WALL_T_CM * 0.3, 0.0),
        size_cm=(WALL_T_CM * 0.4, MODULE_CM * 0.35, STOREY_CM * 0.9),
        rotates_about_center=False,
        tags=frozenset({"door_surround", "jamb", "style_shell", "vertical"}),
    )
    asm = _asm([door, post])
    hits = check_doorway_opening_clear(asm)
    assert hits, "expected doorway_opening_clear critical"
    assert all(f.check == CHECK_DOORWAY_OPENING_CLEAR and f.critical for f in hits)
    _, report = validate(asm)
    assert any(f.check == CHECK_DOORWAY_OPENING_CLEAR and f.critical for f in report.critical)


def test_poison_rail_across_balcony_door_is_critical():
    door = SolidPlacement(
        piece_id="wall_south_1_5_0",
        asset_id="wall_door",
        kind="wall",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        rotates_about_center=False,
        tags=frozenset({"door", "balcony_door", "face_south", "balcony"}),
    )
    deck = SolidPlacement(
        piece_id="balcony_deck_wall_south_1_5_0",
        asset_id="balcony_deck",
        kind="floor",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(10.0, -280.0, 0.0),
        size_cm=(280.0, 380.0, 21.0),
        rotates_about_center=False,
        tags=frozenset({"balcony_deck", "balcony", "host:wall_south_1_5_0", "walkable"}),
    )
    # Rail across the near-host access band (blocks walking out the door).
    rail = SolidPlacement(
        piece_id="poison_rail_across",
        asset_id="balustrade_stone",
        kind="barrier",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(40.0, -40.0, 21.0),
        size_cm=(18.0, 300.0, 100.0),
        rotates_about_center=False,
        tags=frozenset(
            {"balcony_guard", "balcony", "exposed_edge", "host:wall_south_1_5_0"}
        ),
    )
    asm = _asm([door, deck, rail])
    hits = check_balcony_rail_contracts(asm)
    assert any(f.check == CHECK_BALCONY_ACCESS_GAP and f.critical for f in hits), hits


def test_poison_rail_wrong_yaw_inside_deck_is_critical():
    door = SolidPlacement(
        piece_id="wall_south_1_5_0",
        asset_id="wall_door",
        kind="wall",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        rotates_about_center=False,
        tags=frozenset({"door", "balcony_door", "face_south", "balcony"}),
    )
    deck = SolidPlacement(
        piece_id="balcony_deck_x",
        asset_id="balcony_deck",
        kind="floor",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(10.0, -280.0, 0.0),
        size_cm=(280.0, 380.0, 21.0),
        rotates_about_center=False,
        tags=frozenset({"balcony_deck", "balcony", "host:wall_south_1_5_0"}),
    )
    # 45° yaw — illegal; also planted in deck interior.
    rail = SolidPlacement(
        piece_id="poison_rail_diag",
        asset_id="balustrade_stone",
        kind="barrier",
        cell=(5, 0),
        level=1,
        yaw=45,
        offset_cm=(100.0, -140.0, 21.0),
        size_cm=(18.0, 200.0, 100.0),
        rotates_about_center=False,
        tags=frozenset(
            {"balcony_guard", "balcony", "exposed_edge", "host:wall_south_1_5_0"}
        ),
    )
    asm = _asm([door, deck, rail])
    hits = check_balcony_rail_contracts(asm)
    assert any(
        f.check in (CHECK_BALCONY_RAIL_ORIENTATION, CHECK_BALCONY_RAIL_ON_EDGE)
        and f.critical
        for f in hits
    ), hits


def test_poison_unsupported_balcony_deck_is_critical():
    deck = SolidPlacement(
        piece_id="balcony_deck_lonely",
        asset_id="balcony_deck",
        kind="floor",
        cell=(5, 0),
        level=1,
        yaw=270,
        offset_cm=(10.0, -280.0, 0.0),
        size_cm=(280.0, 380.0, 21.0),
        rotates_about_center=False,
        tags=frozenset({"balcony_deck", "balcony", "host:missing"}),
    )
    asm = _asm([deck])
    hits = check_balcony_deck_support(asm)
    assert hits
    assert all(f.check == CHECK_BALCONY_DECK_SUPPORT and f.critical for f in hits)


def test_fancy_manor_passes_shell_detail_validators():
    _m, _p, assembly, report = build_fancy_manor(validate_assembly=True)
    assert report.critical == [], [(f.check, f.message[:100]) for f in report.critical]
    hits = check_shell_detail_contracts(assembly)
    critical = [f for f in hits if f.critical]
    assert critical == [], [(f.check, f.message[:100]) for f in critical]
    # Stairs axis-aligned + present.
    stairs = [p for p in assembly.placements if p.kind == "stair"]
    assert len(stairs) >= 2
    assert all(int(p.yaw) % 90 == 0 for p in stairs)
    # Door jambs are one-storey, not multi-storey towers.
    jambs = [p for p in assembly.placements if "jamb" in p.tags]
    assert jambs, "expected door jambs on fancy manor"
    assert all(p.size_cm[2] <= STOREY_CM * 1.05 for p in jambs), [
        (p.piece_id, p.size_cm[2]) for p in jambs
    ]
    # Balcony side rails are depth-oriented (run along Y for south balcony).
    side_rails = [
        p
        for p in assembly.placements
        if "balcony_guard" in p.tags and "side" in p.tags
    ]
    assert len(side_rails) >= 2
    for r in side_rails:
        assert int(r.yaw) % 180 == 0, r  # 0 or 180 — thickness along X


def test_validate_registers_shell_detail_hook():
    """Poison fixture must fail through the normal validate() chain."""
    door = _door_stub()
    post = SolidPlacement(
        piece_id="poison_in_validate",
        asset_id="forecourt_wall",
        kind="barrier",
        cell=door.cell,
        level=0,
        yaw=90,
        offset_cm=(MODULE_CM * 0.45, -10.0, 0.0),
        size_cm=(40.0, MODULE_CM * 0.5, 120.0),
        rotates_about_center=False,
        tags=frozenset({"forecourt", "style_shell"}),
    )
    asm = _asm([door, post])
    _, report = validate(asm)
    assert any(f.check == CHECK_DOORWAY_OPENING_CLEAR for f in report.critical)

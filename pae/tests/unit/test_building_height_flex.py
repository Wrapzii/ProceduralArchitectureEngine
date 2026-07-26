"""Building height flexibility — storeys/cm declaration, spanning gates, validation."""

from __future__ import annotations

import pytest

from pae.assemble import WALL_HEIGHT_SPAN_TAG
from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    GATE_CLEAR_MIN_STOREYS,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    gate_clear_min_cm,
    gate_span_min_storeys,
    height_cm_from_storeys,
    resolve_height_cm,
    resolve_height_storeys,
    storeys_from_height_cm,
)
from pae.pipeline import run_through_assemble
from pae.spec import (
    HeightDecl,
    RoomSpec,
    building_wall_height_storeys,
    castle_curtain_wall_spec,
    castle_gatehouse_spec,
    fortress_bailey_compound_spec,
    fortress_gatehouse_spec,
    load_spec,
    room_height_storeys,
    room_is_multi_height,
)
from pae.trim import covered_cells
from pae.validate import _check_building_height, validate


def test_height_decl_prefers_storeys():
    h = HeightDecl(storeys=2.5, height_cm=9999.0)
    assert h.resolve_cm() == pytest.approx(2.5 * STOREY_CM)
    assert h.resolve_storeys() == pytest.approx(2.5)
    assert resolve_height_cm(storeys=3) == pytest.approx(3 * STOREY_CM)
    assert resolve_height_storeys(height_cm=STOREY_CM * 4) == pytest.approx(4.0)
    assert storeys_from_height_cm(height_cm_from_storeys(1.5)) == pytest.approx(1.5)


def test_room_height_storeys_not_capped_at_two():
    room = RoomSpec(name="nave", kind="hall", height_storeys=4.0)
    assert room_height_storeys(room) == pytest.approx(4.0)
    assert room_is_multi_height(room)
    legacy = RoomSpec(name="hall", kind="hall", double_height=True)
    assert room_height_storeys(legacy) == pytest.approx(2.0)


def test_room_height_storeys_json_round_trip():
    raw = {
        "name": "tall_hall",
        "style": "keep",
        "footprint": {"kind": "rect", "bays_x": 6, "bays_y": 5},
        "storeys": 4,
        "storey_use": ["hall"] * 4,
        "rooms": [
            {"name": "great_hall", "kind": "hall", "height_storeys": 3},
        ],
        "wall_height_storeys": 4,
        "seed": 1,
    }
    spec, report = load_spec(raw)
    assert report.ok, [f.message for f in report.failures]
    assert spec.wall_height_storeys == pytest.approx(4.0)
    hall = spec.rooms[0]
    assert room_height_storeys(hall) == pytest.approx(3.0)
    assert hall.double_height is True


def test_triple_height_room_carves_l1_and_l2():
    """height_storeys=3 opens L1+L2 DOUBLE_VOID — not hard-capped at 2."""
    from pae.plan import CellRole, StoreyGrid, _apply_double_height_rooms
    from pae.solver import Massing, Volume
    from pae.validate import _cell_role_is

    def _filled(level: int) -> StoreyGrid:
        g = StoreyGrid(level=level, origin=(0, 0), size=(4, 4))
        for x in range(4):
            for y in range(4):
                g.set(x, y, CellRole.INTERIOR)
        return g

    storeys = [_filled(0), _filled(1), _filled(2), _filled(3)]
    massing = Massing(
        volumes=[
            Volume(
                id="hall",
                x0=0,
                y0=0,
                x1=3,
                y1=3,
                storeys=4,
                role="hall",
                entrance=True,
            )
        ],
        entrance_volume_id="hall",
        storeys=4,
        seed=1,
        rooms=[RoomSpec(name="great_hall", kind="hall", height_storeys=3.0)],
    )
    failures = _apply_double_height_rooms(storeys, massing)
    assert failures == []
    assert any(
        _cell_role_is(role, CellRole.DOUBLE_VOID)
        for role in storeys[1].cells.values()
    )
    assert any(
        _cell_role_is(role, CellRole.DOUBLE_VOID)
        for role in storeys[2].cells.values()
    ), "height_storeys=3 must open L2, not hard-cap at 2"
    # L3 (index 3) is beyond span=3 — must stay solid INTERIOR.
    assert not any(
        _cell_role_is(role, CellRole.DOUBLE_VOID)
        for role in storeys[3].cells.values()
    )


def test_fortress_gatehouse_gate_spans_declared_height():
    spec = fortress_gatehouse_spec()
    assert building_wall_height_storeys(spec) >= 3.0
    assert spec.storeys >= 3
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, [f.message for f in report.failures]

    gates = [
        p
        for p in assembly.placements
        if p.kind == "wall" and "gate" in p.asset_id
    ]
    assert gates, "expected gate arch leaves"
    need = height_cm_from_storeys(building_wall_height_storeys(spec))
    for g in gates:
        assert WALL_HEIGHT_SPAN_TAG in g.tags
        assert g.size_cm[2] + TOL_CM >= need
        # Rule 5.1 — identity via covered_cells, not origin-only.
        assert covered_cells(g)
        clear = g.size_cm[2] * 0.88  # conservative frac floor
        assert clear + TOL_CM >= gate_clear_min_cm()


def test_curtain_walls_are_multi_storey():
    bailey = fortress_bailey_compound_spec()
    assert bailey.curtain_storeys >= 3
    curtain = castle_curtain_wall_spec("west_curtain", 6, storeys=bailey.curtain_storeys)
    assert curtain.storeys >= 3
    _, _, assembly, report = run_through_assemble(curtain)
    assert report.ok, [f.message for f in report.failures]
    plain = [p for p in assembly.placements if p.asset_id == "wall_plain"]
    levels = {p.level for p in plain}
    assert levels >= {0, 1, 2}, f"curtain should stack ≥3 storeys, got {levels}"


def test_castle_gatehouse_not_one_block_high():
    spec = castle_gatehouse_spec()
    assert building_wall_height_storeys(spec) >= 2.0
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, [f.message for f in report.failures]
    gates = [p for p in assembly.placements if "gate" in p.asset_id]
    assert gates
    for g in gates:
        assert g.size_cm[2] > STOREY_CM + TOL_CM
        assert WALL_HEIGHT_SPAN_TAG in g.tags


def test_gate_clear_height_broken_fixture():
    """Short stub gate must fail gate_clear_height (broken fixture first)."""
    short = SolidPlacement(
        piece_id="poison_gate",
        asset_id="wall_gate_arch",
        kind="wall",
        cell=(0, 0),
        level=0,
        yaw=270,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM * 0.5),
        tags=frozenset({"gate", "wall_height_span", "height_storeys:3"}),
    )
    asm = Assembly(placements=[short], storeys=3)
    hits = _check_building_height(asm)
    names = {f.check for f in hits}
    assert "gate_clear_height" in names or "wall_height_span" in names
    assert any(f.critical for f in hits)


def test_fortress_gatehouse_validate_height_green():
    spec = fortress_gatehouse_spec()
    _, _, assembly, _ = run_through_assemble(spec)
    _, report = validate(assembly)
    height_fails = [
        f
        for f in report.failures
        if f.check in ("wall_height_span", "gate_clear_height")
    ]
    assert height_fails == [], [f.message for f in height_fails]


def test_gate_span_min_storeys_contract():
    assert gate_span_min_storeys() > GATE_CLEAR_MIN_STOREYS
    assert height_cm_from_storeys(gate_span_min_storeys()) * 0.88 + TOL_CM >= (
        gate_clear_min_cm()
    )

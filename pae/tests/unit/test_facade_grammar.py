"""Unit tests — facade grammar slider → BuildingSpec for Georgian townhouses."""

from __future__ import annotations

import json

import pytest

from pae.contract import MODULE_CM
from pae.facade_grammar import (
    FacadeParams,
    build_from_params,
    export_params_json,
    metres_to_bays,
    params_from_json,
    params_to_spec,
    params_to_style_overrides,
    party_wall_faces,
    resolve_storeys,
    resolve_wealth,
)
from pae.shared_ids import interior_material_for_exterior, resolve_shared
from pae.style_pack import load_style_pack


def test_metres_to_bays_ceil():
    assert metres_to_bays(10.0) == 3  # 1000 cm / 400 = 2.5 → 3
    assert metres_to_bays(8.0) == 2
    assert metres_to_bays(0.0) == 0
    assert metres_to_bays(0.4) == 1
    assert metres_to_bays(10.0) == int(__import__("math").ceil(10.0 * 100.0 / MODULE_CM))


def test_params_to_spec_defaults_and_seed():
    params = FacadeParams(seed=4242)
    spec = params_to_spec(params)
    assert spec.seed == 4242
    assert spec.style == "georgian_merchant"
    assert spec.footprint.bays_x == 3
    assert spec.footprint.bays_y == 2
    assert spec.storeys == 4
    assert spec.openings.windows_per_bay >= 1


def test_params_to_spec_auto_storeys_and_zero_metres():
    params = FacadeParams(storeys=0, frontage_m=0, depth_m=0)
    spec = params_to_spec(params)
    assert spec.storeys == resolve_storeys(0)
    assert spec.footprint.bays_x == 3
    assert spec.footprint.bays_y == 2


@pytest.mark.parametrize(
    "row_context,expected",
    [
        ("freestanding", frozenset()),
        ("end_left", frozenset({"west"})),
        ("end_right", frozenset({"east"})),
        ("mid", frozenset({"east", "west"})),
    ],
)
def test_party_wall_faces_row_context(row_context, expected):
    assert party_wall_faces(row_context) == expected


def test_party_wall_faces_rejects_unknown():
    with pytest.raises(ValueError, match="row_context"):
        party_wall_faces("corner")


def test_shared_ids_wealth_picks_richer_pieces():
    assert resolve_wealth(-1) == 2
    low = resolve_shared("door", 1, "main")
    high = resolve_shared("door", 5, "main")
    assert low == "door_plain"
    assert high == "door_georgian"
    assert resolve_shared("stair", 1, "main") == "stair_straight"
    assert resolve_shared("stair", 4, "main") == "stair_switchback"
    assert interior_material_for_exterior("mat_cream_render") == "mat_plaster_interior"
    assert (
        resolve_shared("material", 3, "interior_wall") == "mat_plaster_interior"
    )


def test_params_json_roundtrip():
    params = FacadeParams(seed=99, wealth=4, row_context="mid")
    text = export_params_json(params)
    data = json.loads(text)
    assert data["seed"] == 99
    assert set(data["party_wall_faces"]) == {"east", "west"}
    roundtrip = params_from_json(text)
    assert roundtrip.seed == params.seed
    assert roundtrip.wealth == params.wealth
    assert roundtrip.row_context == params.row_context


def test_georgian_merchant_style_pack_loads():
    pack, report = load_style_pack("georgian_merchant")
    assert report.ok, [f.message for f in report.failures]
    assert pack is not None
    assert pack.id == "georgian_merchant"
    assert pack.materials.wall == "mat_cream_render"
    assert pack.door.tag == "door_georgian"
    assert pack.window.tag == "window_sash_6over6"


def test_params_to_style_overrides_wealth_shell():
    overrides = params_to_style_overrides(FacadeParams(wealth=1))
    assert overrides["shell"]["pilasters"] is False
    assert overrides["door"]["tag"] == "door_plain"
    rich = params_to_style_overrides(FacadeParams(wealth=5))
    assert rich["shell"]["pilasters"] is True
    assert rich["door"]["tag"] == "door_georgian"


def test_build_from_params_returns_assembly():
    params = FacadeParams(
        seed=1812,
        frontage_m=8.0,
        depth_m=8.0,
        storeys=2,
        wealth=2,
        row_context="freestanding",
    )
    massing, floor_plan, assembly, report, out_params = build_from_params(
        params,
        validate_assembly=False,
    )
    assert out_params is params
    assert massing is not None
    assert floor_plan is not None
    assert assembly is not None
    assert len(assembly.placements) > 0
    # Report may carry non-critical warnings; no critical assembly failures expected.
    assert not report.critical, [f.message for f in report.critical]

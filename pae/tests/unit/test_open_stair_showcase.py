"""Headless tests for open-air stair showcase plan."""

from __future__ import annotations

from pae.open_stair_showcase import open_stair_demo_plan


def test_open_stair_demo_plan_has_three_demos():
    plan = open_stair_demo_plan()
    assert len(plan) == 3
    ids = {d["id"] for d in plan}
    assert ids == {"upstairs_connect", "long_stepped", "spiral_one_storey"}


def test_open_stair_long_stepped_is_three_flights():
    long = next(d for d in open_stair_demo_plan() if d["id"] == "long_stepped")
    assert long["flights"] == 3
    assert long["flight_rise_m"] > 0
    assert long["flight_run_m"] > long["landing_m"]


def test_open_stair_upstairs_connect_single_flight():
    a = next(d for d in open_stair_demo_plan() if d["id"] == "upstairs_connect")
    assert a["flights"] == 1
    assert "opened" in a["notes"].lower()


def test_open_stair_tops_open_the_roof():
    plan = open_stair_demo_plan()
    for demo_id in ("upstairs_connect", "long_stepped"):
        demo = next(d for d in plan if d["id"] == demo_id)
        assert "opened" in demo["notes"].lower()

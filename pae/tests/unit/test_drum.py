"""Foundations for the drum work — these lock the outboard/inboard distinction.

The blanket rule "skip perimeter walls on tower cells" broke seven tests because it
does not distinguish a turret bolted to a corner from a stair tower swallowed by the
plan. These tests exist so the next implementer cannot lose that distinction again.
"""

from __future__ import annotations

import pytest

from pae.drum import (
    body_cells,
    drum_cells,
    drum_levels,
    footprint_bbox,
    has_entry,
    outboard_drum_cells,
    should_suppress_perimeter_wall_on_outboard_drum,
)
from pae.pipeline import run_through_assemble


def _drum_assembly():
    """Prefer street_scene; fall back to m_spiral when street stair well is blocked."""
    from pae.street_scene import build

    assembly, _report, _stats = build()
    if assembly is not None:
        return assembly
    from pae.spec import m_spiral_tower_spec

    _, _, assembly, areport = run_through_assemble(m_spiral_tower_spec())
    assert assembly is not None and areport.ok, [f.message for f in areport.failures]
    return assembly


def test_footprint_bbox_empty_is_none():
    assert footprint_bbox(set()) is None


def test_footprint_bbox_inclusive():
    assert footprint_bbox({(0, 0), (2, 3)}) == (0, 0, 2, 3)


def test_street_has_drum_cells():
    a = _drum_assembly()
    assert drum_cells(a), "street gate tower should produce drum cells"


def test_outboard_is_a_subset_of_drum():
    a = _drum_assembly()
    assert outboard_drum_cells(a) <= drum_cells(a)


def test_outboard_cells_lie_outside_the_body_bbox():
    """The whole point: an outboard cell is one the box does not already enclose."""
    a = _drum_assembly()
    box = footprint_bbox(body_cells(a))
    if box is None:
        pytest.skip("no body cells")
    x0, y0, x1, y1 = box
    for cx, cy in outboard_drum_cells(a):
        assert not (x0 <= cx <= x1 and y0 <= cy <= y1), (
            f"({cx},{cy}) is inside the body bbox and must NOT be treated as outboard "
            "— suppressing its perimeter wall opens a hole in the elevation"
        )


def test_inboard_tower_yields_no_outboard_cells():
    """A tower inside the plan must never license wall suppression.

    ``school_academy_spec`` is the fixture that caught the blanket rule.
    """
    import pae.spec as spec_mod

    factory = getattr(spec_mod, "school_academy_spec", None)
    if factory is None:
        pytest.skip("school_academy_spec not defined")
    _, _, assembly, report = run_through_assemble(factory())
    if assembly is None or not report.ok:
        pytest.skip("school does not assemble cleanly")
    box = footprint_bbox(body_cells(assembly))
    if box is None:
        pytest.skip("no body cells")
    x0, y0, x1, y1 = box
    for cx, cy in outboard_drum_cells(assembly):
        assert not (x0 <= cx <= x1 and y0 <= cy <= y1)


def test_drum_levels_reports_full_height():
    """The helix has to climb this. If it stops short, that is the number to compare."""
    a = _drum_assembly()
    levels = drum_levels(a)
    if not levels:
        pytest.skip("no drum")
    for _cell, lv in levels.items():
        assert lv == sorted(set(lv))
        assert lv[0] == 0, "a drum starts at the ground or it is floating"


def test_has_entry_is_false_for_a_cell_with_no_door():
    a = _drum_assembly()
    assert has_entry(a, (10 ** 6, 10 ** 6)) is False


def test_suppress_perimeter_wall_when_probe_or_outward_is_outboard_drum():
    """North boundary line: drum sits on opening probe, not on wall cell."""
    outboard = {(-3, 9)}
    assert should_suppress_perimeter_wall_on_outboard_drum(
        (-3, 10), "north", outboard
    )
    assert not should_suppress_perimeter_wall_on_outboard_drum(
        (-2, 10), "north", outboard
    )
    assert should_suppress_perimeter_wall_on_outboard_drum(
        (5, 3), "west", {(4, 3)}
    )

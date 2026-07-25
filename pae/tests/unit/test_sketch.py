"""Sketch input — hand the engine an outline, let it solve the building.

These lock the property that matters: an ARBITRARY shape builds. Before this, the only
footprints were five named kinds, so every other building had to be a hardcoded preset
in Python — which is how the project turned into a catalogue of fixed scenes.
"""

from __future__ import annotations

import pytest

from pae.sketch import (
    SketchError,
    built_cells,
    parse_sketch,
    rect_cover,
    sketch_to_spec,
)

# Solid footprint: an L-shaped hall with a tower at one corner and a marked stair.
L_PLAN = """
T#########
##########
###S######
##########
####  ####
####  ####
"""


def test_parse_flips_rows_so_first_line_is_far_side():
    """People draw plans top-down; +Y is north. The first line typed is highest Y."""
    marks = parse_sketch("##\n#S")
    assert (1, 0) in marks["stair"]          # bottom-right of the drawing
    assert (0, 1) in marks["building"]       # top-left


def test_unknown_character_is_loud():
    with pytest.raises(SketchError) as exc:
        parse_sketch("##\n#?")
    assert "?" in str(exc.value)


def test_empty_sketch_rejected():
    with pytest.raises(SketchError):
        parse_sketch("   \n\n")


def test_sketch_with_no_building_rejected():
    with pytest.raises(SketchError):
        parse_sketch("....\n....")


def test_rect_cover_is_exact_and_non_overlapping():
    cells = {(x, y) for x in range(4) for y in range(3)} | {(4, 0)}
    rects = rect_cover(cells)
    covered = set()
    for x0, y0, x1, y1 in rects:
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                assert (x, y) not in covered, "rectangles must not overlap"
                covered.add((x, y))
    assert covered == cells


def test_rect_cover_is_deterministic():
    """(spec, seed) -> identical building depends on this being stable."""
    cells = {(x, y) for x in range(5) for y in range(4)} - {(2, 2)}
    assert rect_cover(set(cells)) == rect_cover(set(cells))


def test_sketch_marks_become_spec_intent():
    spec = sketch_to_spec(L_PLAN, name="t", storeys=3)
    assert spec.footprint.kind == "cells"
    assert spec.footprint.cells, "mask must reach the spec"
    assert len(spec.towers) == 1, "T should become a tower"
    assert spec.circulation.stair_cells, "S should pin a stair cell"
    assert len(spec.storey_use) == 3


def test_unmarked_sketch_lets_the_solver_choose_the_stair():
    """The whole point: mark only what you care about."""
    spec = sketch_to_spec("####\n####\n####", name="t", storeys=2)
    assert spec.circulation.stair_cells == []


def test_arbitrary_sketch_actually_builds():
    """The property this module exists for: a shape nobody hardcoded still assembles."""
    from pae.pipeline import run_through_assemble

    spec = sketch_to_spec(L_PLAN, name="sketched", storeys=3, seed=5)
    _massing, _plan, assembly, report = run_through_assemble(spec)
    assert assembly is not None
    assert report.ok, [f.message for f in report.failures[:3]]
    assert assembly.placements, "an arbitrary footprint must produce geometry"
    kinds = {p.kind for p in assembly.placements}
    assert "wall" in kinds and "floor" in kinds and "roof" in kinds


def test_sketch_footprint_matches_what_was_drawn():
    spec = sketch_to_spec(L_PLAN, name="t", storeys=1)
    drawn = built_cells(parse_sketch(L_PLAN))
    assert set(spec.footprint.cells) == drawn

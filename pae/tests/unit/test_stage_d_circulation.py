"""Master Plan Stage D — per-level region stair allocation (L/U / StructureSpec)."""

from __future__ import annotations

from pae.assemble import _monumental_flight_pads
from pae.pipeline import run_through_assemble
from pae.sketch import sketch_to_spec
from pae.solver import DEFERRED_STAIR_KINDS, solve
from pae.structure_spec import LevelSpec, StructureSpec
from pae.validate import _check_stair_flight_stack


U3_SKETCH = """
########
########
##    ##
##    ##
##    ##
##    ##
"""

L3_SKETCH = """
##########
##########
###     ##
###     ##
####  ####
####  ####
"""


def test_unmarked_u_three_storey_expands_connector_well():
    spec = sketch_to_spec(U3_SKETCH, name="u3", storeys=3, seed=5)
    assert spec.circulation.stair_cells == []
    massing, mreport = solve(spec)
    assert mreport.ok, [f.message for f in mreport.failures]
    assert len(massing.stair_cells) >= 8, massing.stair_cells
    assert _monumental_flight_pads(massing.stair_cells) is not None
    _, _, assembly, areport = run_through_assemble(spec)
    assert areport.ok, [f.message for f in areport.failures[:5]]
    assert _check_stair_flight_stack(assembly) == []


def test_unmarked_l_three_storey_expands_connector_well():
    spec = sketch_to_spec(L3_SKETCH, name="l3", storeys=3, seed=5)
    massing, mreport = solve(spec)
    assert mreport.ok, [f.message for f in mreport.failures]
    assert len(massing.stair_cells) >= 8, massing.stair_cells
    _, _, assembly, areport = run_through_assemble(spec)
    assert areport.ok, [f.message for f in areport.failures[:5]]
    assert _check_stair_flight_stack(assembly) == []


def test_structure_spec_partial_upper_level_stair_in_intersection():
    """U with L1 omitting east leg — stair well must live in the shared bar."""
    structure = StructureSpec(
        name="u_partial3",
        style="townhouse",
        seed=5,
        levels=[
            LevelSpec(sketch=U3_SKETCH, height_units=1),
            LevelSpec(
                sketch="####  \n####  \n##    \n##    \n##    \n##    \n",
                height_units=1,
            ),
            LevelSpec(sketch=U3_SKETCH, height_units=1),
        ],
        stair_kind="straight",
        roof_kind="flat",
    )
    massing, _, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures[:5]]
    assert len(massing.stair_cells) >= 8
    pads = _monumental_flight_pads(massing.stair_cells)
    assert pads is not None
    # Well must not sit only in the omitted east leg (x >= 4 on upper level).
    for cell in massing.stair_cells:
        assert cell[0] <= 3, f"stair well cell {cell} outside L1 built mask"
    assert _check_stair_flight_stack(assembly) == []


def test_grand_imperial_stair_kinds_fail_closed_at_solver():
    assert "grand" in DEFERRED_STAIR_KINDS
    assert "imperial" in DEFERRED_STAIR_KINDS
    from dataclasses import replace

    from pae.spec import m2_two_storey_stair_spec

    spec = replace(
        m2_two_storey_stair_spec(),
        circulation=replace(m2_two_storey_stair_spec().circulation, stair_kind="grand"),
    )
    massing, report = solve(spec)
    assert massing is None
    assert not report.ok
    assert any(f.check == "stair_kind" and f.critical for f in report.failures)

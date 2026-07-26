"""Master Plan Stage C — roof as column height field (D3-9).

Ridge height must come from the structure, not from rect_cover / wing slices.
A sketched U must produce one ridge family, not three heights.
"""

from __future__ import annotations

import pytest

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.pipeline import run_through_assemble
from pae.primitives.roofs import (
    column_top_levels,
    eaves_height_units_at_level,
    roof_height_field_bands,
    roof_rise_cm,
    structure_ridge_span_modules,
)
from pae.sketch import sketch_to_spec
from pae.spec import RoofSpec, m4_u_plan_spec
from pae.structure_spec import LevelSpec, StructureSpec
from pae.validate import validate

# Classic U: 4-bay legs + 2-bay bridge — rect_cover yields three plates whose
# short spans differ (2 vs 4). Pre-Stage-C ridge heights split ~590 / 1150.
SKETCHED_U = """
####  ####
####  ####
####  ####
####  ####
############
############
"""


def _assembly(spec):
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True, [f.message for f in stage_report.failures]
    return assembly


def test_column_top_levels_picks_highest_built():
    l0 = {(0, 0), (1, 0), (0, 1), (1, 1)}
    l1 = {(0, 0), (1, 0)}  # north row omitted → steps
    top = column_top_levels([l0, l1])
    assert top[(0, 0)] == 1
    assert top[(0, 1)] == 0


def test_structure_ridge_span_is_max_short_not_per_slice():
    """D3-9: bridge short=2 must not set a lower ridge than legs short=4."""
    spans = [(0, 0, 11, 1), (0, 2, 3, 5), (8, 2, 11, 5)]
    assert structure_ridge_span_modules(spans) == 4


def test_height_field_bands_step_where_columns_step():
    l0 = {(x, y) for x in range(4) for y in range(3)}
    l1 = {(x, y) for x in range(4) for y in range(1)}  # south bar only
    bands = roof_height_field_bands([l0, l1], height_units=(1, 1))
    assert len(bands) == 2
    eaves = sorted(b.eaves_height_units for b in bands)
    assert eaves == [1.0, 2.0]
    low = next(b for b in bands if b.eaves_height_units == 1.0)
    high = next(b for b in bands if b.eaves_height_units == 2.0)
    assert (0, 2) in low.cells
    assert (0, 0) in high.cells


def test_eaves_height_units_honours_tall_level():
    assert eaves_height_units_at_level(0, (1, 3)) == 1.0
    assert eaves_height_units_at_level(1, (1, 3)) == 4.0


def test_sketched_u_single_ridge_family():
    """Acceptance: sketched U → one ridge height family (not 590/1150 split)."""
    spec = sketch_to_spec(
        SKETCHED_U,
        name="sketched_u_roof",
        storeys=1,
        seed=5,
        roof_kind="pitched",
        roof_pitch=1.4,
    )
    assembly = _assembly(spec)
    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    assert len(slopes) >= 1
    ridge_heights = {round(p.size_cm[2], 1) for p in slopes}
    assert len(ridge_heights) == 1, f"expected one ridge family, got {ridge_heights}"

    # Structure ridge = max short-span (4) → rise from 4 modules, not 2.
    expected = roof_rise_cm(1.4, 4 * MODULE_CM) + FLOOR_T_CM
    assert next(iter(ridge_heights)) == pytest.approx(expected, abs=0.6)

    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]


def test_sketched_u_hip_single_ridge_family():
    spec = sketch_to_spec(
        SKETCHED_U,
        name="sketched_u_hip",
        storeys=1,
        seed=5,
        roof_kind="hip",
        roof_pitch=1.0,
    )
    assembly = _assembly(spec)
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    assert len(hips) >= 2
    ridge_heights = {round(p.size_cm[2], 1) for p in hips}
    assert len(ridge_heights) == 1, f"expected one hip ridge family, got {ridge_heights}"
    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]


def test_m4_u_pitched_still_one_ridge_and_validates():
    """Uniform wing_depth U already shared a ridge; height field must keep that."""
    from dataclasses import replace

    spec = replace(m4_u_plan_spec(), roof=RoofSpec(kind="pitched", pitch=1.0))
    assembly = _assembly(spec)
    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    assert slopes
    assert len({round(p.size_cm[2], 1) for p in slopes}) == 1
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    assert len(valleys) == 2
    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]


def test_stepped_structure_emits_two_eaves_bands():
    """Upper level omits one U leg → roof steps (two eaves levels)."""
    # Same footprint pattern as Stage B green path (test_structure_level_spec).
    l0 = (
        "######\n"
        "######\n"
        "##  ##\n"
        "#S  ##\n"
        "##  ##\n"
        "##  ##\n"
    )
    l1 = (
        "####  \n"
        "####  \n"
        "##    \n"
        "##    \n"
        "##    \n"
        "##    \n"
    )
    structure = StructureSpec(
        name="stepped_u_roof",
        style="townhouse",
        seed=5,
        roof_kind="pitched",
        roof_pitch=1.0,
        stair_kind="straight",
        levels=[
            LevelSpec(sketch=l0, height_units=1),
            LevelSpec(sketch=l1, height_units=1),
        ],
    )
    assembly = _assembly(structure)
    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    assert slopes
    levels = {p.level for p in slopes}
    assert 0 in levels and 1 in levels, f"expected stepped eaves levels, got {levels}"
    for lvl in levels:
        zs = {round(p.size_cm[2], 1) for p in slopes if p.level == lvl}
        assert len(zs) == 1, f"level {lvl} ridge family split: {zs}"
    # Stage B still has storey_egress gaps on partial upper footprints; do not
    # assert full validate here — ridge stepping is the Stage C claim.

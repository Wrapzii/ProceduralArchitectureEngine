"""S-011 steep pitch + S-012 hip roof + S-019 L/U valley stub."""

from __future__ import annotations

import pytest

from pae.contract import EAVE_OVERHANG_CM, FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.pipeline import run_through_assemble
from pae.primitives.catalog import get, piece_ids
from pae.primitives.roofs import (
    STEEP_PITCH_MIN as ROOFS_STEEP_MIN,
    roof_hip_height_cm,
    roof_rise_cm,
    roof_valley_height_cm,
    roof_valley_seams,
)
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    STEEP_PITCH_MIN,
    load_spec,
    m11_hip_roof_spec,
    m4_l_plan_spec,
    m4_u_plan_spec,
)
from pae.validate import validate


def _assembly_from_spec(spec: BuildingSpec):
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True, [f.message for f in stage_report.failures]
    return assembly


def _with_roof(spec: BuildingSpec, roof: RoofSpec) -> BuildingSpec:
    return BuildingSpec(
        name=spec.name,
        style=spec.style,
        footprint=spec.footprint,
        storeys=spec.storeys,
        storey_use=spec.storey_use,
        towers=spec.towers,
        roof=roof,
        circulation=spec.circulation,
        openings=spec.openings,
        seed=spec.seed,
        ground_slab=spec.ground_slab,
    )


def test_roof_hip_in_catalog():
    assert "roof_hip" in piece_ids()
    hip = get("roof_hip")
    assert hip.kind == "roof"
    assert "hip" in hip.tags
    assert hip.footprint_modules == (1, 1)


def test_roof_valley_in_catalog():
    assert "roof_valley" in piece_ids()
    valley = get("roof_valley")
    assert valley.kind == "roof"
    assert "valley" in valley.tags
    assert "stub" in valley.tags
    assert valley.footprint_modules == (1, 1)


def test_m11_hip_roof_spec_factory():
    spec = m11_hip_roof_spec()
    assert spec.name == "m11_hip_roof"
    assert spec.footprint.bays_x == 4
    assert spec.footprint.bays_y == 4
    assert spec.roof.kind == "hip"
    assert spec.roof.pitch == 1.0


def test_m11_hip_roof_assembles_and_validates():
    assembly = _assembly_from_spec(m11_hip_roof_spec())
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    assert len(hips) == 1
    hip = hips[0]
    assert hip.level == 0
    assert hip.offset_cm[2] == pytest.approx(STOREY_CM)
    modules = 4
    expected_x = modules * MODULE_CM + 2 * EAVE_OVERHANG_CM
    expected_z = roof_hip_height_cm(1.0, span_modules_x=modules, span_modules_y=modules)
    assert hip.size_cm[0] == pytest.approx(expected_x)
    assert hip.size_cm[1] == pytest.approx(expected_x)
    assert hip.size_cm[2] == pytest.approx(expected_z)
    assert not any(p.asset_id == "roof_valley" for p in assembly.placements)

    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]
    assert report.ok is True


def test_steep_pitch_spec_accepts_s011_range():
    spec, _ = load_spec(
        {
            "name": "steep_chapel",
            "style": "gothic_academy",
            "footprint": {"kind": "rect", "bays_x": 3, "bays_y": 6},
            "storeys": 1,
            "storey_use": ["chapel"],
            "roof": {"kind": "pitched", "pitch": 1.9},
        }
    )
    assert spec is not None
    assert spec.roof.pitch >= STEEP_PITCH_MIN
    assert STEEP_PITCH_MIN == ROOFS_STEEP_MIN


def test_steep_pitch_pitched_roof_uses_spec_pitch():
    """S-011 — assemble must scale pitched roof height from spec.roof.pitch."""
    steep_pitch = 1.7
    shallow_pitch = 0.9
    base = dict(
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        circulation=CirculationSpec(),
        openings=OpeningPolicy(skip_ground_windows=True),
        seed=0,
        ground_slab=True,
    )
    steep_spec = BuildingSpec(
        name="steep", roof=RoofSpec(kind="pitched", pitch=steep_pitch), **base
    )
    shallow_spec = BuildingSpec(
        name="shallow", roof=RoofSpec(kind="pitched", pitch=shallow_pitch), **base
    )
    steep_asm = _assembly_from_spec(steep_spec)
    shallow_asm = _assembly_from_spec(shallow_spec)
    steep_slope = next(
        p for p in steep_asm.placements if p.asset_id == "roof_pitched_slope"
    )
    shallow_slope = next(
        p for p in shallow_asm.placements if p.asset_id == "roof_pitched_slope"
    )
    span_modules = 3
    steep_rise = roof_rise_cm(steep_pitch, span_modules * MODULE_CM) + FLOOR_T_CM
    shallow_rise = roof_rise_cm(shallow_pitch, span_modules * MODULE_CM) + FLOOR_T_CM
    assert steep_slope.size_cm[2] == pytest.approx(steep_rise)
    assert shallow_slope.size_cm[2] == pytest.approx(shallow_rise)
    assert steep_slope.size_cm[2] > shallow_slope.size_cm[2]
    assert steep_pitch >= STEEP_PITCH_MIN


def test_steep_pitch_hip_roof_uses_spec_pitch():
    """S-011 + S-012 — hip peak height tracks steep vs shallow pitch."""
    steep_pitch = 1.8
    shallow_pitch = 0.95
    base = dict(
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        circulation=CirculationSpec(),
        openings=OpeningPolicy(skip_ground_windows=True),
        seed=0,
        ground_slab=True,
    )
    steep = _assembly_from_spec(
        BuildingSpec(name="steep_hip", roof=RoofSpec(kind="hip", pitch=steep_pitch), **base)
    )
    shallow = _assembly_from_spec(
        BuildingSpec(
            name="shallow_hip", roof=RoofSpec(kind="hip", pitch=shallow_pitch), **base
        )
    )
    steep_hip = next(p for p in steep.placements if p.asset_id == "roof_hip")
    shallow_hip = next(p for p in shallow.placements if p.asset_id == "roof_hip")
    assert steep_hip.size_cm[2] == pytest.approx(
        roof_hip_height_cm(steep_pitch, span_modules_x=4, span_modules_y=4)
    )
    assert shallow_hip.size_cm[2] == pytest.approx(
        roof_hip_height_cm(shallow_pitch, span_modules_x=4, span_modules_y=4)
    )
    assert steep_hip.size_cm[2] > shallow_hip.size_cm[2]


def test_valley_seams_detect_l_and_u_abutments():
    l_spans = [(0, 0, 7, 1), (0, 2, 1, 7)]
    l_seams = roof_valley_seams(l_spans)
    assert len(l_seams) == 1
    assert l_seams[0].axis == "x"
    assert l_seams[0].run0 == 0 and l_seams[0].run1 == 1
    assert l_seams[0].cross_hi == 2

    u_spans = [(0, 0, 7, 1), (0, 2, 1, 7), (6, 2, 7, 7)]
    u_seams = roof_valley_seams(u_spans)
    assert len(u_seams) == 2
    assert {s.cross_hi for s in u_seams} == {2}
    assert sorted((s.run0, s.run1) for s in u_seams) == [(0, 1), (6, 7)]


def test_l_plan_hip_places_valleys():
    """S-019 — L hip gets per-wing hips plus a valley stub on the abutment."""
    spec = _with_roof(m4_l_plan_spec(), RoofSpec(kind="hip", pitch=1.0))
    assembly = _assembly_from_spec(spec)
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    assert len(hips) >= 2, "L-plan hip expects per-wing hips"
    assert len(valleys) == 1
    valley = valleys[0]
    assert valley.size_cm[2] == pytest.approx(roof_valley_height_cm(1.0))
    assert valley.size_cm[0] == pytest.approx(2 * MODULE_CM)
    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]


def test_u_plan_hip_places_valleys():
    """S-019 — U hip gets three wing hips and two valley stubs."""
    spec = _with_roof(m4_u_plan_spec(), RoofSpec(kind="hip", pitch=1.05))
    assembly = _assembly_from_spec(spec)
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    assert len(hips) == 3
    assert len(valleys) == 2
    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]


def test_l_plan_pitched_places_per_wing_and_valley():
    """S-019 — pitched L also splits per wing and gets a valley stub."""
    spec = _with_roof(m4_l_plan_spec(), RoofSpec(kind="pitched", pitch=1.2))
    assembly = _assembly_from_spec(spec)
    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    assert len(slopes) >= 2
    assert len(valleys) == 1


def test_fortress_compound_hip_roofs_no_gable_stack():
    """Fortress keep + cloisters use one hip per wing — no gable infill overlap."""
    from pae.compound import build_fortress_compound

    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    gables = [p for p in assembly.placements if p.asset_id == "roof_gable_infill"]
    assert len(hips) >= 3
    assert not gables

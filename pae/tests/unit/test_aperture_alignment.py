"""Roadmap §1.4 — vertically stacked openings share a plan centre line."""

from __future__ import annotations

from pae.assembly_types import Aperture, Assembly, SolidPlacement
from pae.compound import build_compound
from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM, rotation_offset_cm
from pae.pipeline import run_through_assemble
from pae.spec import m2_two_storey_stair_spec, m8_entrances_spec
from pae.validate import APERTURE_ALIGNMENT_TOL_CM, validate


def _aligned_stack_assembly(*, misaligned_cm: float = 0.0) -> Assembly:
    floor_z = 0.0
    column = ((1, 1), (0, 1))
    centre_x = MODULE_CM + MODULE_CM * 0.5
    centre_y = MODULE_CM * 1.5
    upper_x = centre_x + misaligned_cm
    apertures = [
        Aperture(
            piece_id="door_l0",
            kind="door",
            wall_piece_id="wall_l0",
            level=0,
            sill_z_cm=floor_z,
            floor_z_cm=floor_z,
            interior_cell=column[0],
            exterior_cell=column[1],
            world_xyz=(centre_x, centre_y, floor_z),
        ),
        Aperture(
            piece_id="door_l1",
            kind="door",
            wall_piece_id="wall_l1",
            level=1,
            sill_z_cm=STOREY_CM,
            floor_z_cm=STOREY_CM,
            interior_cell=column[0],
            exterior_cell=column[1],
            world_xyz=(upper_x, centre_y, STOREY_CM),
        ),
    ]
    return Assembly(placements=[], apertures=apertures, storeys=2)


def test_aligned_stack_has_no_aperture_alignment_failures():
    _, report = validate(_aligned_stack_assembly())
    hits = [f for f in report.failures if f.check == "aperture_alignment"]
    assert hits == []


def test_misaligned_stack_reports_aperture_alignment():
    offset = APERTURE_ALIGNMENT_TOL_CM + MODULE_CM * 0.25
    _, report = validate(_aligned_stack_assembly(misaligned_cm=offset))
    hits = [f for f in report.failures if f.check == "aperture_alignment"]
    assert len(hits) == 1
    assert hits[0].piece_id == "door_l1"
    assert hits[0].critical is False
    assert str(offset)[:3] in hits[0].message or f"{offset:.1f}" in hits[0].message


def test_tolerance_uses_module_constant():
    assert APERTURE_ALIGNMENT_TOL_CM == TOL_CM


def test_m8_and_m2_assemblies_have_no_aperture_alignment_warnings():
    for spec_fn in (m8_entrances_spec, m2_two_storey_stair_spec):
        _, _, assembly, _ = run_through_assemble(spec_fn())
        _, report = validate(assembly)
        hits = [f for f in report.failures if f.check == "aperture_alignment"]
        assert hits == [], [f.message for f in hits]


def test_compound_balcony_doors_without_aperture_records_are_checked():
    assembly, _, _ = build_compound()
    doors = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and ("door" in p.asset_id or "gate" in p.asset_id)
    ]
    assert any(p.level > 0 for p in doors)
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == "aperture_alignment"]
    assert hits == [], [f.message for f in hits]


def test_wall_placement_stack_without_aperture_records():
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    offset = rotation_offset_cm(0, sx, sy) + (0.0,)
    placements = []
    for level in (0, 1):
        placements.append(
            SolidPlacement(
                piece_id=f"door_l{level}",
                asset_id="wall_door",
                kind="wall",
                cell=(0, 1),
                level=level,
                yaw=0,
                offset_cm=offset,
                size_cm=(sx, sy, sz),
                tags=frozenset({"wall"}),
            )
        )
    assembly = Assembly(placements=placements, storeys=2)
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == "aperture_alignment"]
    assert hits == []

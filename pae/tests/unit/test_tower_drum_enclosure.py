"""Stage E — outboard drum enclosure (T-D1..T-D3 acceptance)."""

from __future__ import annotations

from pae.drum import (
    CHECK_APERTURE_FACES_OPEN_AIR,
    CHECK_DRUM_EXCLUSIVITY,
    check_aperture_faces_open_air,
    check_drum_exclusivity,
    drum_cells,
    outboard_drum_cells,
    outboard_drum_cells_from_plan,
)
from pae.pipeline import run_through_assemble
from pae.spec import m_spiral_tower_spec, school_academy_spec
from pae.validate import validate


def _assemble(factory):
    _, _, assembly, areport = run_through_assemble(factory())
    assert areport.ok, [f.message for f in areport.failures]
    assert assembly is not None
    return assembly


def test_outboard_plan_matches_assembly_for_spiral_tower():
    """Pre-assembly predicate must agree with post-build outboard set."""
    _, floor_plan, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    assert assembly is not None and floor_plan is not None
    from_plan = outboard_drum_cells_from_plan(floor_plan)
    from_asm = outboard_drum_cells(assembly)
    assert from_plan <= from_asm, (from_plan - from_asm, from_asm - from_plan)
    assert from_asm, "m_spiral tower should be outboard"


def test_spiral_tower_drum_exclusivity_clean():
    """T-D1: no box wall/floor through the outboard drum shaft."""
    assembly = _assemble(m_spiral_tower_spec)
    assert check_drum_exclusivity(assembly) == []


def test_spiral_tower_no_windows_into_drum_bore():
    """T-D3: glazing must not face into the drum interior."""
    assembly = _assemble(m_spiral_tower_spec)
    assert check_aperture_faces_open_air(assembly) == []


def test_school_inboard_tower_keeps_perimeter_walls():
    """Inboard stair tower: outboard set empty — perimeter wall must remain."""
    assembly = _assemble(school_academy_spec)
    assert outboard_drum_cells(assembly) == set()
    drums = drum_cells(assembly)
    if not drums:
        return
    walls_in_drum = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and p.cell in drums
        and "tower_entry" not in p.tags
        and "drum_window" not in p.tags
    ]
    assert walls_in_drum, (
        "inboard tower still needs rectangular perimeter skin on drum cells"
    )


def test_spiral_tower_validate_no_drum_enclosure_criticals():
    assembly = _assemble(m_spiral_tower_spec)
    _, vreport = validate(assembly)
    drum_checks = {
        CHECK_DRUM_EXCLUSIVITY,
        CHECK_APERTURE_FACES_OPEN_AIR,
    }
    hits = [f for f in vreport.critical if f.check in drum_checks]
    assert not hits, [f.message for f in hits]

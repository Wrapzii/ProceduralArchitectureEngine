"""Wall face exclusivity — cloister arcade must not stack on plain walls (D3-9)."""

from __future__ import annotations

from pae.assembly_types import Assembly
from pae.compound import build_fortress_compound
from pae.spec import m4_courtyard_spec
from pae.tests.fixtures.cloister_wall_stack import cloister_stack_pair
from pae.tests.unit.test_trim_site_compound import _assemble
from pae.trim import TrimOptions, trim
from pae.validate import validate
from pae.wall_faces import (
    CHECK_WALL_FACE_EXCLUSIVE,
    check_wall_face_exclusive,
    coplanar_wall_overlap,
    count_coplanar_wall_stacks,
    repair_wall_face_stacks,
)


def test_coplanar_wall_plain_plus_arcade_fires_wall_face_exclusive():
    plain, arcade = cloister_stack_pair()
    assert coplanar_wall_overlap(plain, arcade)
    hits = check_wall_face_exclusive(Assembly(placements=[plain, arcade]))
    assert hits, "stacked court-facing skins must fail closed"
    assert all(f.check == CHECK_WALL_FACE_EXCLUSIVE and f.critical for f in hits)


def test_repair_strips_redundant_plain_wall_behind_arcade():
    plain, arcade = cloister_stack_pair()
    poisoned = Assembly(placements=[plain, arcade])
    fixed = repair_wall_face_stacks(poisoned)
    plains = [p for p in fixed.placements if p.asset_id == "wall_plain"]
    arcs = [p for p in fixed.placements if p.asset_id == "wall_arcade"]
    assert not plains
    assert len(arcs) == 1
    assert check_wall_face_exclusive(fixed) == []


def test_m4_courtyard_trim_has_no_stacked_wall_skins():
    trimmed, report = trim(
        _assemble(m4_courtyard_spec()),
        TrimOptions(
            colonnade=True,
            arcade_piece="wall_arcade",
            buttresses=False,
            roofline=False,
            railings=False,
            parapets=False,
        ),
    )
    assert report.ok
    assert count_coplanar_wall_stacks(trimmed) == 0
    assert check_wall_face_exclusive(trimmed) == []


def test_fortress_west_cloister_has_no_stacked_court_walls():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    west_walls = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and p.level == 0
        and (
            "west_cloister" in p.tags
            or "building:west_cloister" in p.tags
            or "west_cloister" in p.piece_id
        )
    ]
    stacks = count_coplanar_wall_stacks(assembly, placements=west_walls)
    assert stacks == 0, f"west cloister coplanar wall stacks: {stacks}"
    assert check_wall_face_exclusive(assembly) == []


def test_validate_surfaces_wall_face_exclusive():
    plain, arcade = cloister_stack_pair()
    asm = Assembly(placements=[plain, arcade])
    _, vreport = validate(asm)
    assert any(
        f.check == CHECK_WALL_FACE_EXCLUSIVE and f.critical for f in vreport.critical
    )

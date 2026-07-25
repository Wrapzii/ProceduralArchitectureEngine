"""School academy expansion — Waves 1–5 gates (import-safe, no Blender)."""

from __future__ import annotations

from pae.assemble import assemble
from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.solver import solve
from pae.spec import (
    load_style,
    m1_box_house_spec,
    school_academy_dict,
    school_academy_spec,
)
from pae.validate import validate


def test_school_academy_spec_named_non_overlapping_volumes():
    spec = school_academy_spec()
    massing, report = solve(spec)
    assert report.ok, [f.message for f in report.failures]
    assert massing is not None
    roles = {v.role for v in massing.volumes}
    assert "hall" in roles
    assert "admin" in roles
    assert "classroom_wing" in roles
    assert "courtyard" in roles
    enclosed = [v for v in massing.volumes if v.role != "courtyard"]
    for i, a in enumerate(enclosed):
        for b in enclosed[i + 1 :]:
            assert not a.overlaps(b), f"{a.id} overlaps {b.id}"


def test_school_academy_dict_round_trip():
    raw = school_academy_dict()
    assert raw["footprint"]["kind"] == "school"
    assert raw["circulation"]["stair_kind"] == "switchback"
    from pae.spec import load_spec

    spec, report = load_spec(raw)
    assert report.ok, [f.message for f in report.failures]
    assert spec.footprint.kind == "school"


def test_school_switchback_stairwell_is_2x2():
    spec = school_academy_spec()
    massing, mreport = solve(spec)
    assert mreport.ok
    assert massing.stair_kind == "switchback"
    assert len(massing.stair_cells) == 4
    xs = {c[0] for c in massing.stair_cells}
    ys = {c[1] for c in massing.stair_cells}
    assert len(xs) == 2 and len(ys) == 2

    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]
    ground = floor_plan.storeys[0]
    for c in massing.stair_cells:
        assert ground.get(*c) == CellRole.STAIR
    # Top storey of the well must be VOID (character exit). Intermediate
    # storeys may remain STAIR for the continuing flight.
    top = floor_plan.storeys[-1]
    for c in massing.stair_cells:
        assert top.get(*c) == CellRole.VOID


def test_school_has_corridor_and_classrooms_with_doors():
    spec = school_academy_spec()
    massing, _ = solve(spec)
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]
    assert len(floor_plan.corridor_cells) >= 2
    assert len(floor_plan.classroom_cells) >= 4
    door_parts = [p for p in floor_plan.interior_partitions if p[4]]
    assert len(door_parts) >= 4


def test_school_validate_ok_with_trim_pipeline():
    spec = school_academy_spec()
    _m, _p, assembly, report = run_through_validate_trim(spec)
    assert report.ok, [(f.check, f.message) for f in report.critical]
    assert assembly.placements
    # Switchback mesh present.
    stair_ids = {p.asset_id for p in assembly.placements if p.kind == "stair"}
    assert "stair_switchback" in stair_ids
    # Trim folded in — at least one trim-tagged piece on a 3-storey academy.
    trim_ids = {
        p.asset_id
        for p in assembly.placements
        if "trim" in set(getattr(p, "tags", ()) or ())
    }
    assert trim_ids, "expected trim pieces after validate→trim"


def test_gothic_style_drives_window_wall_assets():
    school = school_academy_spec()
    town = m1_box_house_spec()
    _, _, school_asm, _ = run_through_assemble(school)
    _, _, town_asm, _ = run_through_assemble(town)
    school_walls = {
        p.asset_id for p in school_asm.placements if p.kind == "wall" and "window" in p.asset_id
    }
    town_walls = {
        p.asset_id for p in town_asm.placements if p.kind == "wall" and "window" in p.asset_id
    }
    assert "wall_window_lancet" in school_walls or "wall_window_gothic_traceried" in school_walls
    assert "wall_window" in town_walls
    assert school_walls != town_walls


def test_gallery_includes_school_factory():
    from pae.blender_build import _gallery_factories

    labels = [lbl for lbl, _c, _f in _gallery_factories()]
    assert "school" in labels
    assert labels[:6] == ["m1", "m2", "m3", "m4_l", "m4_u", "m4_c"]

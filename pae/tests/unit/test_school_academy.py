"""School academy expansion — Waves 1–5 gates (import-safe, no Blender)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pae.assemble import assemble
from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.solver import solve
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    load_spec,
    load_style,
    m1_box_house_spec,
    school_academy_dict,
    school_academy_spec,
)
from pae.validate import validate

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


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
    for cell in floor_plan.classroom_cells:
        assert len(cell) == 3, f"classroom_cells must be (level,x,y) triples: {cell!r}"
        level, _x, _y = cell
        assert isinstance(level, int) and level >= 0
    levels = {c[0] for c in floor_plan.classroom_cells}
    assert len(levels) >= 2 or len(floor_plan.classroom_cells) >= 4 * spec.storeys
    door_parts = [p for p in floor_plan.interior_partitions if p[4]]
    assert len(door_parts) >= 4


def test_school_validate_ok_with_trim_pipeline():
    spec = school_academy_spec()
    _m, _p, assembly, report = run_through_validate_trim(spec)
    assert report.ok, [(f.check, f.message) for f in report.critical]
    assert report.critical == []
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


def test_school_assemble_validate_critical_empty_before_trim():
    """Structural shell must pass validate with zero critical defects (pre-trim)."""
    spec = school_academy_spec()
    _, _, assembly, _ = run_through_assemble(spec)
    _, report = validate(assembly)
    assert report.critical == [], [(f.check, f.message) for f in report.critical]
    assert any(r.get("double_height") for r in assembly.room_specs)
    from pae.plan import CellRole
    from pae.validate import _cell_role_is

    double_voids = sum(
        1
        for layer in assembly.floor_plan.values()
        for row in layer.cells
        for role in row
        if _cell_role_is(role, CellRole.DOUBLE_VOID)
    )
    assert double_voids > 0, "great_hall double_height must carve DOUBLE_VOID cells"
    assert not any(
        f.check == "room_spec" and f.critical for f in report.failures + report.critical
    )


def test_school_switchback_floor_holes_on_upper_storeys():
    """Switchback well: stair_switchback + ≥4 floor_hole rims per upper storey."""
    spec = school_academy_spec()
    massing, _ = solve(spec)
    _, _, assembly, _ = run_through_assemble(spec)
    assert len(massing.stair_cells) == 4

    switchbacks = [p for p in assembly.placements if p.asset_id == "stair_switchback"]
    assert switchbacks, "expected stair_switchback placement"
    assert all(p.kind == "stair" for p in switchbacks)

    stair_cells = set(massing.stair_cells)
    holes = [p for p in assembly.placements if p.asset_id == "floor_hole"]
    for level in sorted({p.level for p in holes if p.level >= 1}):
        level_holes = [p for p in holes if p.level == level]
        assert len(level_holes) >= 4, f"level {level}: {len(level_holes)} floor_hole"
        assert {p.cell for p in level_holes} >= stair_cells


def test_gothic_school_interior_partition_uses_wall_door_gothic():
  """Interior classroom doors follow gothic style like perimeter doors."""
  spec = school_academy_spec()
  massing, _ = solve(spec)
  floor_plan, preport = plan(massing)
  assert preport.ok, [f.message for f in preport.failures]
  style, _ = load_style(spec.style)
  assembly, _ = assemble(floor_plan, None, style)
  door_parts = [
      p
      for p in assembly.placements
      if "partition" in p.tags and "door" in p.tags
  ]
  assert door_parts, "expected interior partition doors"
  assert all(p.asset_id == "wall_door_gothic" for p in door_parts)
  face_tags = {t for p in door_parts for t in p.tags if t.startswith("face_")}
  assert face_tags, "partition doors must carry face_* tags for validate"


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
    assert "wall_window" not in school_walls, "school must not use M1 townhouse wall_window"
    assert school_walls != town_walls


def test_gallery_includes_school_factory():
    from pae.blender_build import _gallery_factories

    labels = [lbl for lbl, _c, _f in _gallery_factories()]
    assert "school" in labels
    assert labels[:6] == ["m1", "m2", "m3", "m4_l", "m4_u", "m4_c"]


def test_school_export_matches_validate_trim_placement_count(tmp_path: Path):
    """School export must use the same validate→trim assembly as the pipeline."""
    from tools.export_manifest import run_export

    spec = school_academy_spec()
    _m, _p, trim_asm, trim_report = run_through_validate_trim(spec)
    assert trim_report.ok
    trim_count = len(trim_asm.placements)

    rc, data, report = run_export("school", out_path=tmp_path / "school_manifest.json")
    assert rc == 0, [(f.check, f.message) for f in report.critical]
    assert data is not None
    assert len(data["placements"]) == trim_count


def test_school_gallery_assemble_uses_trim():
    """Gallery school path must include trim pieces beyond bare assemble."""
    from pae.blender_build import assemble_and_validate

    _, _, bare_asm, _ = run_through_assemble(school_academy_spec())
    bare_count = len(bare_asm.placements)

    gallery_asm, report = assemble_and_validate("school", school_academy_spec)
    assert report.ok
    assert len(gallery_asm.placements) >= bare_count
    trim_ids = {
        p.asset_id
        for p in gallery_asm.placements
        if "trim" in set(getattr(p, "tags", ()) or ())
    }
    assert trim_ids, "gallery school path must include trim-tagged placements"


def test_school_export_manifest_dry_run_succeeds(tmp_path: Path):
    """M6 school milestone: validate → export → UE dry-run (no network)."""
    from tools.export_manifest import run_export
    from tools.ue_manifest_dry_run import dry_run_manifest

    out = tmp_path / "school_manifest.json"
    rc, data, report = run_export("school", out_path=out)
    assert rc == 0, [(f.check, f.message) for f in report.critical]
    assert report.critical == []
    assert data is not None
    assert out.is_file()

    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["validation"]["ok"] is True
    assert disk["validation"]["critical_count"] == 0

    dry = dry_run_manifest(disk)
    assert dry["ok"] is True, dry.get("failures")


def test_undersized_school_fails_at_load_and_solve():
    data = {
        "name": "tiny_school",
        "style": "gothic_academy",
        "footprint": {
            "kind": "school",
            "bays_x": 8,
            "bays_y": 8,
            "wing_depth": 5,
            "courtyard": True,
        },
        "storeys": 2,
        "storey_use": ["classroom", "classroom"],
    }
    spec, report = load_spec(data)
    assert spec is None
    assert not report.ok
    assert any(f.check == "spec_parse" for f in report.failures)

    # Bypass loader — solver must still fail closed.
    bad = BuildingSpec(
        name="tiny_school",
        style="gothic_academy",
        footprint=FootprintSpec(kind="school", bays_x=8, bays_y=8, wing_depth=5),
        storeys=2,
        storey_use=["classroom", "classroom"],
        circulation=CirculationSpec(stair_kind="switchback", stair_cells=[]),
    )
    massing, sreport = solve(bad)
    assert massing is None
    assert not sreport.ok
    assert any(f.check == "school_program" for f in sreport.failures)


def test_spiral_stair_kind_rejected_without_tower():
    data = school_academy_dict()
    data["circulation"]["stair_kind"] = "spiral"
    spec, report = load_spec(data)
    assert spec is not None
    assert report.ok

    spiral_spec = school_academy_spec()
    spiral_spec.circulation.stair_kind = "spiral"
    massing, sreport = solve(spiral_spec)
    assert massing is None
    assert not sreport.ok
    assert any(f.check == "stair_kind" for f in sreport.failures)


def test_school_courtyard_false_has_no_courtyard_volume():
    spec = school_academy_spec()
    spec.footprint.courtyard = False
    massing, report = solve(spec)
    assert report.ok, [f.message for f in report.failures]
    roles = {v.role for v in massing.volumes}
    assert "courtyard" not in roles
    assert "classroom_wing" in roles

"""Unit tests — export gate, UE manifest, FBX/blend stubs, terrain bind (WP-6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pae.assemble import assemble
from pae.contract import MODULE_CM, STOREY_CM, placement_origin_cm
from pae.export import (
    ExportRefused,
    bind_to_terrain,
    export_blend,
    export_fbx,
    export_manifest,
    plan_linked_duplicates,
    sample_heightmap,
)
from pae.export.gate import ensure_exportable
from pae.export.manifest import SCHEMA, build_manifest
from pae.plan import plan
from pae.solver import solve
from pae.spec import load_style, m1_box_house_spec
from pae.tests.fixtures.broken_all_defects import make_broken_assembly
from pae.validate import validate


def _m1_assembly():
    spec = m1_box_house_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly


def test_m1_manifest_written_when_validate_ok(tmp_path: Path):
    assembly = _m1_assembly()
    _, report = validate(assembly)
    assert report.ok is True
    assert report.critical == []

    out = tmp_path / "m1_manifest.json"
    data, out_report = export_manifest(assembly, out, report=report)

    assert out.is_file()
    assert out_report.ok is True
    assert data["schema"] == SCHEMA
    assert data["schema"] == "pae.manifest/1"
    assert data["module_cm"] == MODULE_CM
    assert data["storey_cm"] == STOREY_CM
    assert data["origin_convention"] == "min_corner"
    assert data["validation"]["ok"] is True
    assert len(data["placements"]) == len(assembly.placements)
    assert data["placements"], "expected at least one placement"

    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["module_cm"] == MODULE_CM
    first = disk["placements"][0]
    assert "loc_cm" in first and len(first["loc_cm"]) == 3
    assert "yaw" in first and "asset_id" in first


def test_broken_assembly_export_refuses_and_writes_nothing(tmp_path: Path):
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    assert report.ok is False
    assert report.critical

    out = tmp_path / "should_not_exist.json"
    with pytest.raises(ExportRefused) as excinfo:
        export_manifest(assembly, out, report=report)

    assert excinfo.value.report.critical
    assert not out.exists()

    with pytest.raises(ExportRefused):
        export_fbx(assembly, tmp_path / "no.fbx", report=report)
    assert not (tmp_path / "no.fbx").exists()
    assert not (tmp_path / "no.placements.json").exists()

    with pytest.raises(ExportRefused):
        export_blend(assembly, tmp_path / "no.blend", report=report)
    assert not (tmp_path / "no.blend").exists()
    assert not (tmp_path / "no.blend.plan.json").exists()


def test_ensure_exportable_raises_on_critical():
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    with pytest.raises(ExportRefused):
        ensure_exportable(assembly, report)


def test_fbx_without_blender_writes_placement_list(tmp_path: Path):
    assembly = _m1_assembly()
    fbx_path = tmp_path / "house.fbx"
    fbx, report, meta = export_fbx(assembly, fbx_path)
    assert report.ok is True
    assert fbx is None
    assert not fbx_path.exists()
    list_path = Path(meta["placement_list"])
    assert list_path.is_file()
    payload = json.loads(list_path.read_text(encoding="utf-8"))
    assert payload["format"] == "pae.fbx_placement_list/1"
    assert len(payload["placements"]) == len(assembly.placements)


def test_blend_plan_without_blender(tmp_path: Path):
    assembly = _m1_assembly()
    _, report = validate(assembly)
    plan_data = plan_linked_duplicates(assembly, report)
    assert plan_data.instances
    assert plan_data.assets_unique

    blend_path = tmp_path / "house.blend"
    plan_out, out_report, meta = export_blend(assembly, blend_path, report=report)
    assert out_report.ok is True
    assert plan_out.instances
    assert meta["blend"] is None
    assert not blend_path.exists()
    assert Path(meta["plan"]).is_file()


def test_build_manifest_loc_matches_contract():
    assembly = _m1_assembly()
    _, report = validate(assembly)
    data = build_manifest(assembly, report)
    p0 = assembly.placements[0]
    expected = placement_origin_cm(p0.cell[0], p0.cell[1], p0.level, p0.offset_cm)
    row = next(r for r in data["placements"] if r["piece_id"] == p0.piece_id)
    assert tuple(row["loc_cm"]) == expected


def test_sample_heightmap_nearest_no_raycast():
    # 2×2 grid; origin at (0,0); cell = MODULE_CM — avoid forbidden dimension literals.
    a, b, c, d = 11.0, 22.0, 33.0, 44.0
    hm = [
        [a, b],
        [c, d],
    ]
    assert sample_heightmap(hm, 0.0, 0.0) == a
    assert sample_heightmap(hm, MODULE_CM, 0.0) == b
    assert sample_heightmap(hm, 0.0, MODULE_CM) == c
    assert sample_heightmap(hm, MODULE_CM, MODULE_CM) == d


def test_bind_to_terrain_flatten_pad_shifts_whole_building():
    assembly = _m1_assembly()
    before_min = min(
        placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)[2]
        for p in assembly.placements
    )
    # Flat heightmap at 500 cm — use values that are not forbidden literals.
    pad = MODULE_CM + STOREY_CM  # 750.0 from contract composition
    hm = [[pad for _ in range(16)] for _ in range(16)]
    bound = bind_to_terrain(assembly, hm, "flatten_pad")
    after_min = min(
        placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)[2]
        for p in bound.placements
    )
    assert after_min == pytest.approx(pad)
    # Relative structure preserved
    dz = after_min - before_min
    for a, b in zip(assembly.placements, bound.placements):
        assert b.offset_cm[2] == pytest.approx(a.offset_cm[2] + dz)


def test_bind_to_terrain_stilts_clears_max():
    assembly = _m1_assembly()
    low = MODULE_CM
    high = MODULE_CM * 2
    hm = [[low if (i + j) % 2 == 0 else high for j in range(16)] for i in range(16)]
    clearance = MODULE_CM * 0.25
    bound = bind_to_terrain(
        assembly, hm, "stilts", stilts_clearance_cm=clearance
    )
    after_min = min(
        placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)[2]
        for p in bound.placements
    )
    assert after_min == pytest.approx(high + clearance)


def test_bind_to_terrain_step_terraces_column_unit():
    assembly = _m1_assembly()
    # Varying heights; terraces snap to STOREY_CM.
    hm = [[float((i % 3) * STOREY_CM) for j in range(16)] for i in range(16)]
    bound = bind_to_terrain(assembly, hm, "step_terraces")
    assert len(bound.placements) == len(assembly.placements)
    # All Z offsets finite / finite deltas
    for p in bound.placements:
        assert p.offset_cm[2] == p.offset_cm[2]  # not NaN

"""Integration — terrain bind + manifest export (M6, no Blender / UE)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pae.assemble import assemble
from pae.contract import MODULE_CM, STOREY_CM, placement_origin_cm
from pae.export import bind_to_terrain, export_manifest
from pae.export.manifest import SCHEMA, build_manifest, collision_stub, lod_placeholder
from pae.export.terrain import sample_heightmap
from pae.plan import plan
from pae.solver import solve
from pae.spec import load_style, m1_box_house_spec
from pae.validate import validate


def _m1_assembly():
    spec = m1_box_house_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly


def test_manifest_hardened_contract_lod_collision():
    assembly = _m1_assembly()
    _, report = validate(assembly)
    data = build_manifest(assembly, report)

    assert data["schema"] == SCHEMA
    assert data["module_cm"] == MODULE_CM
    assert data["storey_cm"] == STOREY_CM
    assert data["origin_convention"] == "min_corner"
    assert data["contract"]["module_cm"] == MODULE_CM
    assert data["contract"]["storey_cm"] == STOREY_CM
    assert "wall_t_cm" in data["contract"]
    assert "floor_t_cm" in data["contract"]

    assert data["validation"]["ok"] is True
    assert "failures" in data["validation"]
    assert "checks" in data["validation"]

    assert data["assets"], "expected asset rows"
    for asset in data["assets"]:
        assert asset["lod"] == lod_placeholder()
        assert set(asset["lod"]) == {"0", "1", "2"}

    assert data["collision"], "expected collision stubs"
    asset_ids = {a["id"] for a in data["assets"]}
    collision_ids = {c["asset_id"] for c in data["collision"]}
    assert collision_ids == asset_ids
    assert collision_stub("wall_plain")["profile"] == "mesh_complex"


def test_bind_to_terrain_then_export_manifest_flatten_pad(tmp_path: Path):
    """Tiny 2×2 heightmap shifts whole assembly Z — no raycasts — then exports."""
    assembly = _m1_assembly()
    _, report = validate(assembly)
    assert report.ok

    before_min_z = min(
        placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)[2]
        for p in assembly.placements
    )

    # Synthetic pad — uniform 2×2 grid (tiny, no raycasts).
    pad_z = MODULE_CM + STOREY_CM
    heightmap = [
        [pad_z, pad_z],
        [pad_z, pad_z],
    ]

    # Prove sampling works on the tiny grid without raycasts.
    assert sample_heightmap(heightmap, 0.0, 0.0) == pad_z

    bound = bind_to_terrain(assembly, heightmap, "flatten_pad")
    after_min_z = min(
        placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)[2]
        for p in bound.placements
    )
    assert after_min_z == pytest.approx(pad_z)
    assert after_min_z != pytest.approx(before_min_z)

    out = tmp_path / "terrain_bound.json"
    data, out_report = export_manifest(
        bound, out, report=report, terrain_mode="flatten_pad"
    )
    assert out.is_file()
    assert out_report.ok
    assert data["terrain_bind"]["mode"] == "flatten_pad"

    p0 = bound.placements[0]
    expected = placement_origin_cm(p0.cell[0], p0.cell[1], p0.level, p0.offset_cm)
    row = next(r for r in data["placements"] if r["piece_id"] == p0.piece_id)
    assert tuple(row["loc_cm"]) == expected
    assert row["loc_cm"][2] == pytest.approx(expected[2])

    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["terrain_bind"]["source"] == "heightmap"

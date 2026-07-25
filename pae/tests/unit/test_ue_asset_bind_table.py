"""Unit tests — UE asset bind table generator (UE_BIND)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM  # noqa: E402
from pae.export.manifest import SCHEMA  # noqa: E402
from tools.ue_asset_bind_table import (  # noqa: E402
    ASSET_BIND_SCHEMA,
    asset_bind_out_path,
    build_asset_bind_table,
    collect_asset_ids_from_manifest,
    collect_asset_ids_from_spawn_table,
    manifest_to_bindings,
    run_asset_bind_table,
    suggested_content_path,
    spawn_table_to_bindings,
    write_asset_bind_table,
)
from tools.ue_spawn_table import SPAWN_TABLE_SCHEMA, build_spawn_table  # noqa: E402


def _minimal_good_manifest() -> dict:
    return {
        "schema": SCHEMA,
        "module_cm": MODULE_CM,
        "storey_cm": STOREY_CM,
        "origin_convention": "min_corner",
        "contract": {
            "module_cm": MODULE_CM,
            "storey_cm": STOREY_CM,
            "wall_t_cm": WALL_T_CM,
            "floor_t_cm": FLOOR_T_CM,
        },
        "assets": [
            {"id": "wall_plain", "fbx": "", "lod": {"0": "", "1": "", "2": ""}},
            {"id": "floor", "fbx": "", "lod": {"0": "", "1": "", "2": ""}},
        ],
        "placements": [
            {
                "asset_id": "wall_plain",
                "piece_id": "wall_test_0",
                "loc_cm": [0, 0, 0],
                "yaw": 0,
                "cell": [0, 0],
                "level": 0,
            },
        ],
        "collision": [
            {
                "asset_id": "wall_plain",
                "profile": "mesh_complex",
                "ue_collision_preset": "BlockAll",
            },
            {
                "asset_id": "floor",
                "profile": "mesh_complex",
                "ue_collision_preset": "OverlapAll",
            },
        ],
        "validation": {
            "ok": True,
            "critical_count": 0,
            "warning_count": 0,
            "failures": [],
            "checks": {},
        },
    }


def test_suggested_content_path_under_pae():
    path = suggested_content_path("wall_plain", "m1")
    assert path == "/Game/RE/PAE/M1/SM_wall_plain.SM_wall_plain"


def test_suggested_content_path_milestone_segment():
    path = suggested_content_path("roof_flat", "m4_l")
    assert path.startswith("/Game/RE/PAE/M4_L/")


def test_collect_asset_ids_from_manifest_prefers_assets_array():
    ids = collect_asset_ids_from_manifest(_minimal_good_manifest())
    assert ids == ["floor", "wall_plain"]


def test_manifest_to_bindings_shape():
    bindings = manifest_to_bindings(_minimal_good_manifest(), milestone="m1")
    assert len(bindings) == 2
    wall = next(b for b in bindings if b["asset_id"] == "wall_plain")
    assert wall["suggested_content_path"] == "/Game/RE/PAE/M1/SM_wall_plain.SM_wall_plain"
    assert wall["lod0"] == wall["suggested_content_path"]
    assert wall["collision_profile"] == "BlockAll"
    floor = next(b for b in bindings if b["asset_id"] == "floor")
    assert floor["collision_profile"] == "OverlapAll"


def test_spawn_table_to_bindings():
    manifest = _minimal_good_manifest()
    spawn = build_spawn_table(
        manifest,
        milestone="m1",
        source_manifest="m1_manifest.json",
    )
    bindings = spawn_table_to_bindings(spawn, milestone="m1", manifest=manifest)
    ids = collect_asset_ids_from_spawn_table(spawn)
    assert ids == ["wall_plain"]
    assert len(bindings) == 1
    assert bindings[0]["asset_id"] == "wall_plain"


def test_build_asset_bind_table_refuses_validation_not_ok():
    manifest = _minimal_good_manifest()
    manifest["validation"]["ok"] = False
    with pytest.raises(ValueError, match="validation.ok must be true"):
        build_asset_bind_table(
            manifest,
            milestone="m1",
            source_manifest="m1_manifest.json",
        )


def test_build_asset_bind_table_shape():
    table = build_asset_bind_table(
        _minimal_good_manifest(),
        milestone="m1",
        source_manifest="Saved/exports/m1_manifest.json",
    )
    assert table["schema"] == ASSET_BIND_SCHEMA
    assert table["milestone"] == "m1"
    assert table["bind_count"] == 2
    assert len(table["bindings"]) == 2
    assert set(table["bindings"][0]) == {
        "asset_id",
        "suggested_content_path",
        "lod0",
        "collision_profile",
    }


def test_write_and_run_asset_bind_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    manifest_path = exports / "m1_manifest.json"
    manifest_path.write_text(json.dumps(_minimal_good_manifest(), indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "tools.ue_asset_bind_table.manifest_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_manifest.json",
    )
    monkeypatch.setattr(
        "tools.ue_asset_bind_table.asset_bind_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_asset_bind.json",
    )
    monkeypatch.setattr(
        "tools.ue_asset_bind_table.spawn_table_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_spawn_table.json",
    )

    table = run_asset_bind_table("m1", auto_export=False, root=tmp_path)
    out_json = exports / "m1_asset_bind.json"
    assert out_json.is_file()
    assert table["bind_count"] == 2

    write_asset_bind_table(table, exports / "custom_bind.json")
    disk = json.loads((exports / "custom_bind.json").read_text(encoding="utf-8"))
    assert disk["schema"] == ASSET_BIND_SCHEMA


def test_run_asset_bind_table_uses_spawn_table_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    manifest = _minimal_good_manifest()
    (exports / "m1_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    spawn = build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")
    (exports / "m1_spawn_table.json").write_text(json.dumps(spawn, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "tools.ue_asset_bind_table.manifest_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_manifest.json",
    )
    monkeypatch.setattr(
        "tools.ue_asset_bind_table.asset_bind_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_asset_bind.json",
    )
    monkeypatch.setattr(
        "tools.ue_asset_bind_table.spawn_table_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_spawn_table.json",
    )

    table = run_asset_bind_table("m1", auto_export=False, root=tmp_path)
    assert table["source_spawn_table"] == "Saved/exports/m1_spawn_table.json"
    assert table["bind_count"] == 1
    assert table["bindings"][0]["asset_id"] == "wall_plain"


def test_cli_milestone_subprocess_writes_output():
    manifest_path = ROOT / "Saved" / "exports" / "m1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("m1_manifest.json not present in workspace")

    out_json = ROOT / "Saved" / "exports" / "_pytest_m1_asset_bind.json"
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "ue_asset_bind_table.py"),
                "--milestone",
                "m1",
                "--no-auto-export",
                "--out",
                str(out_json),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert out_json.is_file()
        table = json.loads(out_json.read_text(encoding="utf-8"))
        assert table["schema"] == ASSET_BIND_SCHEMA
        assert table["bind_count"] > 0
        assert all(
            b["suggested_content_path"].startswith("/Game/RE/PAE/")
            for b in table["bindings"]
        )
    finally:
        out_json.unlink(missing_ok=True)


def test_cli_on_repo_m1_when_manifest_present():
    manifest_path = ROOT / "Saved" / "exports" / "m1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("m1_manifest.json not present in workspace")

    out_path = asset_bind_out_path("m1")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "ue_asset_bind_table.py"),
            "--milestone",
            "m1",
            "--no-auto-export",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    table = json.loads(out_path.read_text(encoding="utf-8"))
    assert table["bind_count"] > 0

"""Unit tests — UE spawn table generator (M6_HANDOFF)."""

from __future__ import annotations

import csv
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
from tools.ue_spawn_table import (  # noqa: E402
    SPAWN_TABLE_SCHEMA,
    build_spawn_table,
    manifest_to_spawn_rows,
    run_spawn_table,
    spawn_table_out_path,
    write_spawn_table,
    write_spawn_table_csv,
)


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
        "assets": [{"id": "wall_plain", "fbx": "", "lod": {"0": "", "1": "", "2": ""}}],
        "placements": [
            {
                "asset_id": "wall_plain",
                "piece_id": "wall_test_0",
                "loc_cm": [100.0, 200.5, -3.0],
                "yaw": 90,
                "cell": [0, 0],
                "level": 0,
            },
            {
                "asset_id": "wall_plain",
                "piece_id": "wall_test_1",
                "loc_cm": [400, 0, 0],
                "yaw": 0,
                "cell": [1, 0],
                "level": 0,
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


def test_manifest_to_spawn_rows_strips_debug_fields():
    rows = manifest_to_spawn_rows(_minimal_good_manifest())
    assert len(rows) == 2
    assert rows[0] == {
        "asset_id": "wall_plain",
        "loc_cm": [100.0, 200.5, -3.0],
        "yaw": 90,
        "piece_id": "wall_test_0",
    }
    assert set(rows[0]) == {"asset_id", "loc_cm", "yaw", "piece_id"}


def test_build_spawn_table_refuses_validation_not_ok():
    manifest = _minimal_good_manifest()
    manifest["validation"]["ok"] = False
    with pytest.raises(ValueError, match="validation.ok must be true"):
        build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")


def test_build_spawn_table_shape():
    table = build_spawn_table(
        _minimal_good_manifest(),
        milestone="m1",
        source_manifest="Saved/exports/m1_manifest.json",
    )
    assert table["schema"] == SPAWN_TABLE_SCHEMA
    assert table["milestone"] == "m1"
    assert table["row_count"] == 2
    assert len(table["rows"]) == 2
    assert table["source_manifest"] == "Saved/exports/m1_manifest.json"


def test_write_spawn_table_and_csv(tmp_path: Path):
    table = build_spawn_table(
        _minimal_good_manifest(),
        milestone="m3",
        source_manifest="m3_manifest.json",
    )
    json_path = tmp_path / "m3_spawn_table.json"
    csv_path = tmp_path / "m3_spawn_table.csv"
    write_spawn_table(table, json_path)
    write_spawn_table_csv(table, csv_path)

    disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert disk["row_count"] == 2

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["asset_id"] == "wall_plain"
    assert float(rows[0]["loc_cm_x"]) == 100.0
    assert int(rows[0]["yaw"]) == 90
    assert rows[0]["piece_id"] == "wall_test_0"


def test_run_spawn_table_from_manifest_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    manifest_path = exports / "m1_manifest.json"
    manifest_path.write_text(json.dumps(_minimal_good_manifest(), indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "tools.ue_spawn_table.manifest_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_manifest.json",
    )
    monkeypatch.setattr(
        "tools.ue_spawn_table.spawn_table_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_spawn_table.json",
    )
    monkeypatch.setattr(
        "tools.ue_spawn_table.spawn_table_csv_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_spawn_table.csv",
    )

    table = run_spawn_table(
        "m1",
        write_csv=True,
        auto_export=False,
        root=tmp_path,
    )
    out_json = exports / "m1_spawn_table.json"
    out_csv = exports / "m1_spawn_table.csv"
    assert out_json.is_file()
    assert out_csv.is_file()
    assert table["row_count"] == 2


def test_run_spawn_table_refuses_bad_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    bad = _minimal_good_manifest()
    bad["validation"]["ok"] = False
    (exports / "m1_manifest.json").write_text(json.dumps(bad, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "tools.ue_spawn_table.manifest_out_path",
        lambda milestone, root=ROOT: exports / f"{milestone}_manifest.json",
    )

    with pytest.raises(ValueError, match="validation.ok must be true"):
        run_spawn_table("m1", auto_export=False, root=tmp_path)


def test_cli_milestone_subprocess_writes_outputs():
    manifest_path = ROOT / "Saved" / "exports" / "m1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("m1_manifest.json not present in workspace")

    out_json = ROOT / "Saved" / "exports" / "_pytest_m1_spawn_table.json"
    out_csv = ROOT / "Saved" / "exports" / "_pytest_m1_spawn_table.csv"
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "ue_spawn_table.py"),
                "--milestone",
                "m1",
                "--no-auto-export",
                "--out",
                str(out_json),
                "--csv",
                "--csv-out",
                str(out_csv),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert out_json.is_file()
        assert out_csv.is_file()
        table = json.loads(out_json.read_text(encoding="utf-8"))
        assert table["schema"] == SPAWN_TABLE_SCHEMA
        assert table["row_count"] > 0
    finally:
        out_json.unlink(missing_ok=True)
        out_csv.unlink(missing_ok=True)


def test_cli_on_repo_m1_when_manifest_present():
    manifest_path = ROOT / "Saved" / "exports" / "m1_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("m1_manifest.json not present in workspace")

    out_path = spawn_table_out_path("m1")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "ue_spawn_table.py"),
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
    assert table["row_count"] > 0
    assert all(set(row) == {"asset_id", "loc_cm", "yaw", "piece_id"} for row in table["rows"])

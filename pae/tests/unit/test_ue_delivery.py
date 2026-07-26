"""Unit tests — Stage L filesystem delivery pipeline (MP-WS11)."""

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
from pae.export.delivery import (  # noqa: E402
    DELIVERY_SCHEMA,
    check_artifact_consistency,
    delivery_out_path,
    run_milestone_delivery,
)
from pae.export.manifest import SCHEMA  # noqa: E402
from pae.export.spawn_groups import group_rows_by_asset_id  # noqa: E402
from tools.ue_asset_bind_table import build_asset_bind_table  # noqa: E402
from tools.ue_spawn_table import (  # noqa: E402
    SPAWN_TABLE_SCHEMA,
    build_spawn_table,
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
        "assets": [
            {"id": "wall_plain", "fbx": "", "lod": {"0": "", "1": "", "2": ""}},
            {"id": "floor", "fbx": "", "lod": {"0": "", "1": "", "2": ""}},
        ],
        "placements": [
            {
                "asset_id": "wall_plain",
                "piece_id": "wall_a",
                "loc_cm": [0.0, 0.0, 0.0],
                "yaw": 0,
                "cell": [0, 0],
                "level": 0,
            },
            {
                "asset_id": "wall_plain",
                "piece_id": "wall_b",
                "loc_cm": [MODULE_CM, 0.0, 0.0],
                "yaw": 90,
                "cell": [1, 0],
                "level": 0,
            },
            {
                "asset_id": "floor",
                "piece_id": "floor_a",
                "loc_cm": [0.0, 0.0, -10.0],
                "yaw": 0,
                "cell": [0, 0],
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


def test_group_rows_by_asset_id_groups_and_counts():
    rows = [
        {"asset_id": "floor", "loc_cm": [0, 0, 0], "yaw": 0, "piece_id": "f1"},
        {"asset_id": "wall_plain", "loc_cm": [1, 0, 0], "yaw": 90, "piece_id": "w1"},
        {"asset_id": "wall_plain", "loc_cm": [2, 0, 0], "yaw": 0, "piece_id": "w2"},
    ]
    groups = group_rows_by_asset_id(rows)
    assert [g["asset_id"] for g in groups] == ["floor", "wall_plain"]
    wall = next(g for g in groups if g["asset_id"] == "wall_plain")
    assert wall["instance_count"] == 2
    assert len(wall["instances"]) == 2
    assert wall["instances"][0]["piece_id"] == "w1"


def test_build_spawn_table_v2_includes_ism_groups():
    manifest = _minimal_good_manifest()
    table = build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")
    assert table["schema"] == SPAWN_TABLE_SCHEMA
    assert table["row_count"] == 3
    assert table["ism_group_count"] == 2
    assert len(table["ism_groups"]) == 2
    wall_group = next(g for g in table["ism_groups"] if g["asset_id"] == "wall_plain")
    assert wall_group["instance_count"] == 2


def test_check_artifact_consistency_accepts_aligned_artifacts():
    manifest = _minimal_good_manifest()
    spawn = build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")
    bind = build_asset_bind_table(
        manifest,
        milestone="m1",
        source_manifest="m1_manifest.json",
        spawn_table=spawn,
        source_spawn_table="m1_spawn_table.json",
    )
    result = check_artifact_consistency(manifest, spawn, bind)
    assert result["ok"] is True
    assert result["failures"] == []
    assert result["ism_group_count"] == 2


def test_check_artifact_consistency_reports_loc_drift():
    manifest = _minimal_good_manifest()
    spawn = build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")
    spawn["rows"][0]["loc_cm"] = [999.0, 0.0, 0.0]
    bind = build_asset_bind_table(
        manifest,
        milestone="m1",
        source_manifest="m1_manifest.json",
        spawn_table=spawn,
    )
    result = check_artifact_consistency(manifest, spawn, bind)
    assert result["ok"] is False
    assert any("loc_cm drift" in msg for msg in result["failures"])


def test_check_artifact_consistency_reports_missing_bind():
    manifest = _minimal_good_manifest()
    spawn = build_spawn_table(manifest, milestone="m1", source_manifest="m1_manifest.json")
    bind = build_asset_bind_table(
        manifest,
        milestone="m1",
        source_manifest="m1_manifest.json",
        spawn_table=spawn,
    )
    bind["bindings"] = [b for b in bind["bindings"] if b["asset_id"] != "floor"]
    result = check_artifact_consistency(manifest, spawn, bind)
    assert result["ok"] is False
    assert any("without bind entry" in msg for msg in result["failures"])


def test_run_milestone_delivery_fail_closed_on_bad_manifest(tmp_path: Path):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    bad = _minimal_good_manifest()
    bad["validation"]["ok"] = False
    bad["validation"]["critical_count"] = 1
    (exports / "m1_manifest.json").write_text(json.dumps(bad, indent=2), encoding="utf-8")

    report, rc = run_milestone_delivery(
        "m1",
        root=tmp_path,
        force_export=False,
    )
    assert rc == 1
    assert report["ok"] is False
    assert report["stages"]["dry_run"]["ok"] is False
    summary = delivery_out_path("m1", tmp_path)
    assert summary.is_file()


def test_run_milestone_delivery_full_chain(tmp_path: Path):
    report, rc = run_milestone_delivery("m1", root=tmp_path, force_export=True)
    assert rc == 0, report.get("failures")
    assert report["ok"] is True
    assert report["schema"] == DELIVERY_SCHEMA
    exports = tmp_path / "Saved" / "exports"
    assert (exports / "m1_manifest.json").is_file()
    assert (exports / "m1_spawn_table.json").is_file()
    assert (exports / "m1_asset_bind.json").is_file()
    assert (exports / "m1_delivery.json").is_file()
    spawn = json.loads((exports / "m1_spawn_table.json").read_text(encoding="utf-8"))
    assert spawn["schema"] == SPAWN_TABLE_SCHEMA
    assert spawn["ism_group_count"] > 0


@pytest.mark.parametrize("milestone", ["m1", "m3"])
def test_cli_delivery_subprocess(milestone: str):
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "ue_delivery.py"),
            "--milestone",
            milestone,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    summary = ROOT / "Saved" / "exports" / f"{milestone}_delivery.json"
    assert summary.is_file()
    report = json.loads(summary.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["schema"] == DELIVERY_SCHEMA
    assert report["counts"]["spawn_rows"] == report["counts"]["placements"]
    assert report["counts"]["ism_groups"] > 0

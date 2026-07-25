"""Unit tests — UE manifest dry-run consumer (M6_DRYRUN)."""

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
from tools.ue_manifest_dry_run import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    dry_run_manifest,
    run_dry_run,
    write_report,
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
                "loc_cm": [0.0, 0.0, 0.0],
                "yaw": 90,
                "cell": [0, 0],
                "level": 0,
            }
        ],
        "validation": {
            "ok": True,
            "critical_count": 0,
            "warning_count": 0,
            "failures": [],
            "checks": {},
        },
    }


def test_dry_run_accepts_minimal_good_manifest():
    report = dry_run_manifest(_minimal_good_manifest())
    assert report["ok"] is True
    assert report["placement_count"] == 1
    assert report["asset_count"] == 1
    assert report["failures"] == []


@pytest.mark.parametrize(
    "mutator, expected_substring",
    [
        (lambda m: m.update({"schema": "wrong/1"}), "schema must be"),
        (lambda m: m.pop("assets"), "missing required field: assets"),
        (
            lambda m: m["placements"][0].update({"yaw": 45}),
            "yaw must be one of",
        ),
        (
            lambda m: m["placements"][0].update({"loc_cm": [0.0, 0.0]}),
            "loc_cm must be three numeric values",
        ),
        (
            lambda m: m["placements"][0].update({"asset_id": "missing_asset"}),
            "not in assets[]",
        ),
        (lambda m: m["validation"].update({"ok": False}), "validation.ok must be true"),
        (
            lambda m: m["validation"].update({"critical_count": 1}),
            "validation.critical_count must be 0",
        ),
    ],
)
def test_dry_run_rejects_bad_manifest(mutator, expected_substring: str):
    manifest = _minimal_good_manifest()
    mutator(manifest)
    report = dry_run_manifest(manifest)
    assert report["ok"] is False
    assert any(expected_substring in msg for msg in report["failures"])


def test_dry_run_accepts_yaw_zero_and_float_loc(tmp_path: Path):
    manifest = _minimal_good_manifest()
    manifest["placements"][0]["yaw"] = 0
    manifest["placements"][0]["loc_cm"] = [100, 200.5, -3.0]
    report = dry_run_manifest(manifest)
    assert report["ok"] is True


def test_run_dry_run_writes_report(tmp_path: Path):
    manifest_path = tmp_path / "good.json"
    report_path = tmp_path / "m6_dry_run_report.json"
    manifest_path.write_text(json.dumps(_minimal_good_manifest(), indent=2), encoding="utf-8")

    report = run_dry_run(
        manifest_path,
        report_path=report_path,
        auto_export=False,
    )
    assert report["ok"] is True
    assert report_path.is_file()
    disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert disk["ok"] is True
    assert disk["placement_count"] == 1


def test_run_dry_run_missing_non_default_fails_closed(tmp_path: Path):
    missing = tmp_path / "nope.json"
    report_path = tmp_path / "report.json"
    with pytest.raises(FileNotFoundError):
        run_dry_run(missing, report_path=report_path, auto_export=False)


def test_cli_on_repo_m1_manifest():
    if not DEFAULT_MANIFEST_PATH.is_file():
        pytest.skip("m1_manifest.json not present in workspace")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "ue_manifest_dry_run.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report_path = ROOT / "Saved" / "exports" / "m6_dry_run_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["placement_count"] > 0
    assert report["asset_count"] > 0


def test_write_report_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "nested" / "m6_dry_run_report.json"
    write_report({"ok": False, "placement_count": 0, "asset_count": 0, "failures": ["x"]}, out)
    assert out.is_file()

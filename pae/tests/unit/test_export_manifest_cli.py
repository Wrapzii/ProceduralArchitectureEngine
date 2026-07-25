"""Unit tests — generalized manifest export CLI (EXPORT_ALL)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.export import ExportRefused, export_manifest  # noqa: E402
from pae.export.manifest import SCHEMA  # noqa: E402
from pae.tests.fixtures.broken_all_defects import make_broken_assembly  # noqa: E402
from pae.validate import validate  # noqa: E402
from tools.export_manifest import (  # noqa: E402
    MILESTONE_SPECS,
    build_assembly,
    main as export_main,
    manifest_out_path,
    milestone_from_manifest_path,
    run_export,
)
from tools.ue_manifest_dry_run import (  # noqa: E402
    dry_run_manifest,
    resolve_manifest_path,
    run_dry_run,
)


@pytest.mark.parametrize("milestone", sorted(MILESTONE_SPECS))
def test_run_export_writes_valid_manifest(tmp_path: Path, milestone: str):
    out = tmp_path / f"{milestone}_manifest.json"
    rc, data, report = run_export(milestone, out_path=out)
    assert rc == 0, report.critical
    assert data is not None
    assert out.is_file()
    assert report.ok is True
    assert report.critical == []

    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["schema"] == SCHEMA
    assert disk["validation"]["ok"] is True
    assert disk["validation"]["critical_count"] == 0
    assert disk["placements"]
    assert disk["assets"]

    dry = dry_run_manifest(disk)
    assert dry["ok"] is True, dry["failures"]


def test_export_refuses_critical_defects(tmp_path: Path):
    assembly = make_broken_assembly()
    _, report = validate(assembly)
    assert report.ok is False
    out = tmp_path / "broken.json"
    with pytest.raises(ExportRefused):
        export_manifest(assembly, out, report=report)
    assert not out.exists()


def test_milestone_from_manifest_path():
    assert milestone_from_manifest_path(Path("m3_manifest.json")) == "m3"
    assert milestone_from_manifest_path(Path("m4_l_manifest.json")) == "m4_l"
    assert milestone_from_manifest_path(Path("custom.json")) is None


def test_manifest_out_path_matches_convention():
    assert manifest_out_path("m2").name == "m2_manifest.json"
    assert manifest_out_path("m4_u").parent.name == "exports"


@pytest.mark.parametrize("milestone", ["m1", "m2", "m3", "m4_l", "m4_u", "m4_c"])
def test_build_assembly_has_placements(milestone: str):
    assembly = build_assembly(milestone)
    assert assembly.placements


def test_export_cli_unknown_milestone():
    with pytest.raises(SystemExit) as exc:
        export_main(["--milestone", "m99"])
    assert exc.value.code == 2


def test_export_m1_wrapper_invokes_m1(tmp_path: Path):
    out = tmp_path / "m1_manifest.json"
    rc, data, _ = run_export("m1", out_path=out)
    assert rc == 0
    assert data is not None

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "export_m1_manifest.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "m1_manifest.json" in proc.stdout or proc.returncode == 0


def test_dry_run_milestone_flag_auto_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exports = tmp_path / "Saved" / "exports"
    exports.mkdir(parents=True)
    report_path = exports / "m6_dry_run_report.json"
    m3_path = exports / "m3_manifest.json"
    assert not m3_path.is_file()

    monkeypatch.chdir(tmp_path)
    # Patch ROOT resolution by using explicit path via run_dry_run API.
    rc_export, data, _ = run_export("m3", out_path=m3_path)
    assert rc_export == 0
    report = run_dry_run(m3_path, report_path=report_path, auto_export=False)
    assert report["ok"] is True
    assert report["placement_count"] == len(data["placements"])


def test_resolve_manifest_path_milestone():
    path = resolve_manifest_path(None, "m4_c")
    assert path.name == "m4_c_manifest.json"


def test_resolve_manifest_path_rejects_both():
    with pytest.raises(ValueError, match="not both"):
        resolve_manifest_path("foo.json", "m1")


@pytest.mark.parametrize("milestone", ["m1", "m3"])
def test_export_then_dry_run_integration(tmp_path: Path, milestone: str):
    """M6 dry-run can prove exported m1 and m3 manifests spawn-ready."""
    out = tmp_path / f"{milestone}_manifest.json"
    rc, data, report = run_export(milestone, out_path=out)
    assert rc == 0, report.critical

    dry = dry_run_manifest(json.loads(out.read_text(encoding="utf-8")))
    assert dry["ok"] is True
    assert dry["placement_count"] == len(data["placements"])
    assert dry["asset_count"] == len(data["assets"])


def test_dry_run_cli_milestone_subprocess(tmp_path: Path):
    out = tmp_path / "m1_manifest.json"
    rc, _, _ = run_export("m1", out_path=out)
    assert rc == 0

    report_path = tmp_path / "m6_dry_run_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "ue_manifest_dry_run.py"),
            str(out),
            "--report",
            str(report_path),
            "--no-auto-export",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True

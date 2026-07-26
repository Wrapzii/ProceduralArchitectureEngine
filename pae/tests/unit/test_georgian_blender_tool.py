"""Unit tests for tools/build_georgian_townhouse_blender.py (dry-run, no bpy)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_dry_run_main_writes_summary(tmp_path, monkeypatch):
    from tools.build_georgian_townhouse_blender import main

    out_json = tmp_path / "summary.json"
    code = main(
        [
            "--dry-run",
            "--export-json",
            "--summary-json",
            str(out_json),
            "--seed",
            "99",
            "--storeys",
            "2",
            "--wealth",
            "2",
            "--row-context",
            "freestanding",
        ]
    )
    assert code == 0
    assert out_json.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["params"]["seed"] == 99
    assert data["summary"]["placement_count"] > 0
    assert data["summary"]["stair_count"] >= 0
    assert data["summary"]["report_ok"] is True
    assert "shared_door_id" in data["summary"]
    assert "shared_stair_id" in data["summary"]


def test_summarize_assembly_fields():
    from pae.facade_grammar import FacadeParams, build_from_params
    from tools.build_georgian_townhouse_blender import summarize_assembly

    params = FacadeParams(
        seed=7,
        frontage_m=8.0,
        depth_m=8.0,
        storeys=2,
        wealth=2,
        row_context="freestanding",
    )
    _m, _p, assembly, report, _out = build_from_params(
        params, validate_assembly=False
    )
    summary = summarize_assembly(assembly, report, params)
    assert summary["bays_x"] >= 2
    assert summary["placement_count"] == len(assembly.placements)
    assert summary["shared_door_id"]
    assert summary["shared_stair_id"]


def test_preview_rgba_for_placement():
    from tools.build_georgian_townhouse_blender import preview_rgba_for_placement

    wall = preview_rgba_for_placement("wall_window", "wall", 3)
    floor = preview_rgba_for_placement("floor", "floor", 3)
    assert len(wall) == 4
    assert len(floor) == 4
    assert wall != floor


def test_parse_args_defaults():
    from tools.build_georgian_townhouse_blender import parse_args

    args = parse_args([])
    assert args.archetype == "georgian_merchant"
    assert args.dry_run is False
    assert args.row_context == "freestanding"


def test_have_bpy_false_without_blender():
    from tools.build_georgian_townhouse_blender import _have_bpy

    assert _have_bpy() is False


@pytest.mark.parametrize(
    "row_context",
    ["freestanding", "end_left", "end_right", "mid"],
)
def test_dry_run_all_row_contexts(row_context):
    from tools.build_georgian_townhouse_blender import main

    code = main(
        [
            "--dry-run",
            "--storeys",
            "2",
            "--wealth",
            "2",
            "--row-context",
            row_context,
        ]
    )
    assert code == 0

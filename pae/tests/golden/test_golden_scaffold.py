"""Golden-image scaffolding tests (§10.2) — M1 baseline = placement hash + tiny stub PNG."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pae.tests.golden.compare import (
    PIXEL_DIFF_THRESHOLD,
    GoldenCompareError,
    blender_available,
    compare_png_files,
    compare_rgba_buffers,
    pixel_diff_fraction,
    render_or_stub,
    solid_rgba,
    write_stub_png,
)
from pae.tests.property.determinism import hash_assembly

BASELINES = Path(__file__).resolve().parent / "baselines"
M1_META = BASELINES / "m1_box_house.meta.json"


def test_threshold_is_two_percent():
    assert PIXEL_DIFF_THRESHOLD == pytest.approx(0.02)


def test_identical_buffers_pass():
    w, h = 32, 32
    buf = solid_rgba(w, h, (10, 20, 30, 255))
    assert compare_rgba_buffers(buf, buf, width=w, height=h) == 0.0


def test_full_diff_fails_threshold():
    w, h = 16, 16
    a = solid_rgba(w, h, (0, 0, 0, 255))
    b = solid_rgba(w, h, (255, 255, 255, 255))
    frac = pixel_diff_fraction(a, b, width=w, height=h)
    assert frac == 1.0
    with pytest.raises(GoldenCompareError) as ei:
        compare_rgba_buffers(a, b, width=w, height=h)
    assert ei.value.fraction > PIXEL_DIFF_THRESHOLD


def test_small_diff_within_two_percent():
    """Change < 2 % of pixels → pass."""
    w, h = 100, 100
    a = bytearray(solid_rgba(w, h, (0, 0, 0, 255)))
    b = bytearray(a)
    # Flip 1 pixel (0.01 %) — well under 2 %
    b[0], b[1], b[2] = 255, 255, 255
    frac = compare_rgba_buffers(bytes(a), bytes(b), width=w, height=h)
    assert frac < PIXEL_DIFF_THRESHOLD


def test_stub_png_roundtrip(tmp_path: Path):
    w, h = 8, 8
    color = (40, 50, 60, 255)
    p = write_stub_png(tmp_path / "stub.png", w, h, solid_rgba(w, h, color))
    assert p.is_file()
    # Compare against itself via file path API
    assert compare_png_files(p, p) == 0.0


def test_render_or_stub_without_blender(tmp_path: Path):
    out = render_or_stub(
        building_id="box_house_m1",
        camera_name="Cam_Front",
        out_path=tmp_path / "box_house_m1_Cam_Front.png",
    )
    assert out.is_file()
    # Without Blender we always get a stub; baseline placeholder may be written next
    assert not blender_available() or out.exists()


def test_baseline_placeholder_dir_exists():
    """Scaffolding: baselines/ holds approved meta + tiny stub PNG."""
    assert BASELINES.is_dir()
    assert M1_META.is_file()
    keep = BASELINES / ".gitkeep"
    assert keep.is_file() or any(BASELINES.iterdir())


def test_m1_placement_hash_matches_baseline():
    """Pin M1 assembly by placement-list hash (prefer hash over large PNG binaries)."""
    from pae.assemble import assemble
    from pae.plan import plan
    from pae.solver import solve
    from pae.spec import load_style, m1_box_house_spec
    from pae.validate import validate

    meta = json.loads(M1_META.read_text(encoding="utf-8"))
    spec = m1_box_house_spec(seed=int(meta["seed"]))
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    _, report = validate(assembly)
    assert report.ok, report.critical

    digest = hash_assembly(
        assembly.placements,
        asset_db_version=str(meta["asset_db_version"]),
        seed=spec.seed,
    )
    assert len(assembly.placements) == int(meta["n_placements"])
    assert digest == meta["placement_hash"]


def test_box_house_front_matches_baseline(tmp_path: Path):
    """Tiny stub PNG baseline (CI-safe); full matplotlib shot lives under Saved/."""
    baseline = BASELINES / "box_house_m1_Cam_Front.png"
    assert baseline.is_file(), "missing approved tiny stub baseline PNG"
    meta = json.loads(M1_META.read_text(encoding="utf-8"))
    stub = meta["stub_png"]
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == stub["sha256"]

    actual = render_or_stub(
        building_id="box_house_m1",
        camera_name="Cam_Front",
        out_path=tmp_path / "actual.png",
        stub_size=(int(stub["width"]), int(stub["height"])),
    )
    compare_png_files(actual, baseline)

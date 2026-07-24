"""Self-check: magic_number_grep finds no violations on a clean tree."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_grep_module():
    root = Path(__file__).resolve().parents[3]
    path = root / "tools" / "magic_number_grep.py"
    spec = importlib.util.spec_from_file_location("magic_number_grep", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, root


def test_allowlist_includes_contract():
    mod, _ = _load_grep_module()
    assert "pae/contract.py" in mod.ALLOWLIST_FILES


def test_scan_clean_on_repo_root():
    mod, root = _load_grep_module()
    hits = mod.scan(root)
    assert hits == [], f"unexpected magic numbers: {hits}"


def test_scan_detects_planted_literal(tmp_path: Path):
    mod, _ = _load_grep_module()
    bad = tmp_path / "pae" / "evil.py"
    bad.parent.mkdir(parents=True)
    # Avoid a contiguous MODULE-sized float token in *this* source file.
    literal = "400" + ".0"
    bad.write_text(f"x = {literal}\n", encoding="utf-8")
    hits = mod.scan(tmp_path)
    assert any("evil.py" in h[0] for h in hits)


def test_angle_deg_thirty_is_exempt(tmp_path: Path):
    mod, _ = _load_grep_module()
    src = tmp_path / "pae" / "shade.py"
    src.parent.mkdir(parents=True)
    src.write_text("def f(angle_deg: float = 30.0):\n    return angle_deg\n", encoding="utf-8")
    assert mod.scan(tmp_path) == []

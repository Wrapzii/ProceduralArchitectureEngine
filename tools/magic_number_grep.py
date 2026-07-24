#!/usr/bin/env python3
"""Fail CI when forbidden dimension literals appear outside allowlisted files.

Forbidden (grid contract — must live in pae/contract.py only):
  400.0  MODULE_CM
  350.0  STOREY_CM
  60.0   WALL_T_CM
  30.0   FLOOR_T_CM

Usage:
  python tools/magic_number_grep.py
  python tools/magic_number_grep.py --root .
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Patterns must match float literals used as hard-coded dimensions.
FORBIDDEN = (
    re.compile(r"(?<![\d.])400\.0(?![\d])"),
    re.compile(r"(?<![\d.])350\.0(?![\d])"),
    re.compile(r"(?<![\d.])60\.0(?![\d])"),
    re.compile(r"(?<![\d.])30\.0(?![\d])"),
)

# Paths relative to repo root, always allowed.
ALLOWLIST_FILES = {
    "pae/contract.py",
    # Locks the canonical values against contract imports (§2 smoke).
    "pae/tests/unit/test_contract_smoke.py",
    # WP-4: deliberately plants world-cm fields so load_spec rejects them.
    "pae/tests/unit/test_spec.py",
    # This scanner encodes the forbidden literals as search patterns.
    "tools/magic_number_grep.py",
}

# Prefix allowlist (posix) — justified WP-2 measured-size fixtures / assertions.
ALLOWLIST_PREFIXES = (
    "pae/tests/unit/test_assets_",
)

# Directory name parts skipped entirely.
SKIP_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "pae.egg-info",
    "dist",
    "build",
    ".eggs",
}

# Line looks like a non-dimension use of 30.0 (degrees), not FLOOR_T_CM.
_ANGLE_DEG = re.compile(r"angle_deg\s*[:=]")


def _rel_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_allowlisted(rel_s: str) -> bool:
    if rel_s in ALLOWLIST_FILES:
        return True
    return any(rel_s.startswith(prefix) for prefix in ALLOWLIST_PREFIXES)


def _should_skip_path(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    if set(rel.parts) & SKIP_DIR_PARTS:
        return True
    if _is_allowlisted(rel.as_posix()):
        return True
    return False


def _strip_comment(line: str) -> str:
    """Remove full-line / trailing `#` comments (not inside strings — good enough for CI)."""
    in_s = None
    for i, ch in enumerate(line):
        if in_s:
            if ch == in_s and (i == 0 or line[i - 1] != "\\"):
                in_s = None
            continue
        if ch in ("'", '"'):
            in_s = ch
            continue
        if ch == "#":
            return line[:i]
    return line


def _line_exempt(line: str) -> bool:
    if "noqa: pae-magic" in line:
        return True
    code = _strip_comment(line)
    if not any(p.search(code) for p in FORBIDDEN):
        return True
    # Shade-angle defaults are degrees, not FLOOR_T_CM (WP-3 bpy_util).
    if _ANGLE_DEG.search(code) and FORBIDDEN[3].search(code):
        others = [p for p in FORBIDDEN[:3] if p.search(code)]
        if not others:
            return True
    return False


def scan(root: Path) -> list[tuple[str, int, str]]:
    """Return list of (relpath, lineno, line) violations."""
    hits: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*.py")):
        if _should_skip_path(path, root):
            continue
        rel = _rel_posix(path, root)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"warn: skip {rel}: {exc}", file=sys.stderr)
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _line_exempt(line):
                continue
            code = _strip_comment(line)
            for pat in FORBIDDEN:
                if pat.search(code):
                    hits.append((rel, i, line.rstrip()))
                    break
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: parent of tools/)",
    )
    args = parser.parse_args(argv)
    root = args.root
    if root is None:
        root = Path(__file__).resolve().parent.parent
    root = root.resolve()

    hits = scan(root)
    if not hits:
        print("magic_number_grep: OK (no forbidden dimension literals outside allowlist)")
        return 0

    print("magic_number_grep: FAIL — hard-coded dimensions outside allowlist:", file=sys.stderr)
    print(
        "  Import from pae.contract (MODULE_CM / STOREY_CM / WALL_T_CM / FLOOR_T_CM).",
        file=sys.stderr,
    )
    for rel, lineno, line in hits:
        print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
    print(
        f"\n{len(hits)} violation(s). "
        f"Allowlist files: {sorted(ALLOWLIST_FILES)}; "
        f"prefixes: {list(ALLOWLIST_PREFIXES)}",
        file=sys.stderr,
    )
    return 1


# Back-compat alias for tests
ALLOWLIST = ALLOWLIST_FILES


if __name__ == "__main__":
    raise SystemExit(main())

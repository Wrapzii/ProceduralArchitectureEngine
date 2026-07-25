"""Showcase — ten buildings, all of which must validate.

This is a capability gate: if the engine can no longer produce these, something regressed.
"""

from __future__ import annotations

import pytest

from pae.showcase import build_all, builds


def test_ten_builds_are_defined():
    assert len(builds()) == 10
    assert len({b.key for b in builds()}) == 10


@pytest.mark.parametrize("entry", build_all(), ids=lambda e: e[0].key)
def test_showcase_entry_validates(entry):
    b, assembly, report, stats = entry
    assert assembly is not None, f"{b.key} failed to assemble"
    assert report.ok, [f.message for f in report.critical]
    assert stats["total"] > 100, f"{b.key} suspiciously small: {stats}"


def test_showcase_exercises_every_kit_family():
    """The point of the showcase is coverage — if a family never appears, say so."""
    seen = set()
    for _b, assembly, _r, _s in build_all():
        if assembly is None:
            continue
        seen |= {p.kind for p in assembly.placements}
    for kind in ("wall", "floor", "roof", "stair", "band", "barrier",
                 "roofline", "column", "surface", "tower_arc"):
        assert kind in seen, f"showcase never places a {kind}"

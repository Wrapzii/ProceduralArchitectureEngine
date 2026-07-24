"""Validation stage (§7) — WP-1 owns this module.

Acceptance: report.ok is True and report.critical is empty.
Export must refuse to run when critical defects exist.
"""

from __future__ import annotations

from typing import Any, Tuple

from pae.report import Report


def validate(assembly: Any) -> Tuple[Any, Report]:
    """Validate an assembly. Returns (assembly, report).

    WP-1: implement dangling ends, vertical support, collinear gaps,
    interpenetration, enclosure flood, floor coverage, stair reachability,
    run fit, aperture sanity. Test-first against broken fixtures.
    """
    raise NotImplementedError("WP-1: implement validate.py")

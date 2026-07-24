"""Shared export validation gate (§7 acceptance / §8).

Export refuses when ``report.ok`` is False or ``report.critical`` is non-empty.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pae.assembly_types import Assembly
from pae.report import Report
from pae.validate import validate


class ExportRefused(RuntimeError):
    """Raised when an assembly has critical validation defects."""

    def __init__(self, report: Report):
        self.report = report
        n = len(report.critical)
        super().__init__(f"export refused: {n} critical defect(s)")


def ensure_exportable(
    assembly: Assembly,
    report: Optional[Report] = None,
) -> Report:
    """Return a passing report, or raise :class:`ExportRefused`.

    If *report* is omitted, runs ``pae.validate.validate``.
    """
    if report is None:
        _, report = validate(assembly)
    if (not report.ok) or report.critical:
        raise ExportRefused(report)
    return report


def validate_for_export(assembly: Assembly) -> Tuple[Assembly, Report]:
    """Convenience: validate and refuse on critical defects."""
    assembly, report = validate(assembly)
    ensure_exportable(assembly, report)
    return assembly, report

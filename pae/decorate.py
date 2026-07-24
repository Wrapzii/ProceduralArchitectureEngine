"""Decoration stage — props deferred to WP-8."""

from __future__ import annotations

from typing import Tuple

from pae.assembly_types import Assembly
from pae.report import Report


def decorate(assembly: Assembly) -> Tuple[Assembly, Report]:
    """Pass-through until WP-8 adds decorative props."""
    return assembly, Report.from_failures([])

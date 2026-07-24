"""Decoration stage — WP-5 / WP-8 props."""

from __future__ import annotations

from typing import Any, Tuple

from pae.report import Report


def decorate(assembly: Any) -> Tuple[Any, Report]:
    raise NotImplementedError("WP-5/WP-8: implement decorate.py")

"""Floor plan (§5.2) — WP-4."""

from __future__ import annotations

from enum import Enum
from typing import Any, Tuple

from pae.report import Report


class CellRole(Enum):
    EXTERIOR = 0
    INTERIOR = 1
    WALL_LINE = 2
    DOOR = 3
    STAIR = 4
    VOID = 5
    COURTYARD = 6


def plan(massing: Any) -> Tuple[Any, Report]:
    raise NotImplementedError("WP-4: implement plan.py")

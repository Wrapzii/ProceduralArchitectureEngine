"""Assembly stage (§6) — WP-5. Only place for geometry creation (+ primitives)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from pae.report import Report


@dataclass
class Placement:
    asset_id: str
    cell: Tuple[int, int]
    level: int
    yaw: int
    offset_cm: Tuple[float, float, float]


def assemble(floor_plan: Any, asset_db: Any, style: Any) -> Tuple[Any, Report]:
    raise NotImplementedError("WP-5: implement assemble.py")

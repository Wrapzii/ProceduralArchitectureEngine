"""BuildingSpec loader (§3) — WP-4 owns this module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from pae.report import Report


@dataclass
class FootprintSpec:
    kind: str  # rect | L | U | courtyard | compound
    bays_x: int
    bays_y: int
    wing_depth: int = 2
    courtyard: bool = False


@dataclass
class TowerSpec:
    cell: Tuple[int, int]
    storeys: int
    attached_to: str = "corner"  # wall | corner


@dataclass
class RoofSpec:
    kind: str = "flat"  # flat | pitched
    pitch: float = 1.0


@dataclass
class CirculationSpec:
    stair_kind: str = "straight"  # straight | spiral
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class OpeningPolicy:
    windows_per_bay: int = 1
    doors_ground: int = 1
    skip_ground_windows: bool = False


@dataclass
class BuildingSpec:
    name: str
    style: str
    footprint: FootprintSpec
    storeys: int
    storey_use: List[str]
    towers: List[TowerSpec] = field(default_factory=list)
    roof: RoofSpec = field(default_factory=RoofSpec)
    circulation: CirculationSpec = field(default_factory=CirculationSpec)
    openings: OpeningPolicy = field(default_factory=OpeningPolicy)
    seed: int = 0


def load_spec(data: dict) -> Tuple[BuildingSpec, Report]:
    """Load and reject any world-coordinate fields. WP-4 implements."""
    raise NotImplementedError("WP-4: implement spec loader")

"""Abstract assembly model consumed by validate.py (§6–§7).

Pure data — no Blender meshes. WP-5 assemble.py will emit these structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pae.plan import CellRole


@dataclass
class SolidPlacement:
    """One placed module with measured axis-aligned bounds in local space."""

    piece_id: str
    asset_id: str
    kind: str  # wall | floor | roof | stair | ground | prop | ...
    cell: Tuple[int, int]
    level: int
    yaw: int  # 0 | 90 | 180 | 270
    offset_cm: Tuple[float, float, float]
    size_cm: Tuple[float, float, float]  # measured local AABB (sx, sy, sz)
    rotates_about_center: bool = False
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass
class FloorPlanLayer:
    """Single-storey cell grid — source of truth for roles (§5.2)."""

    level: int
    width: int
    height: int
    origin_cell: Tuple[int, int]  # grid (0,0) world cell
    cells: List[List[CellRole]]

    def role_at(self, cx: int, cy: int) -> Optional[CellRole]:
        lx = cx - self.origin_cell[0]
        ly = cy - self.origin_cell[1]
        if lx < 0 or ly < 0 or lx >= self.width or ly >= self.height:
            return None
        return self.cells[ly][lx]


@dataclass
class CirculationEdge:
    """Stair (or ramp) connecting two storeys."""

    piece_id: str
    from_level: int
    to_level: int


@dataclass
class WallRun:
    """Collinear wall pieces sharing plane / axis / level (§7.3, §7.8)."""

    run_id: str
    level: int
    axis: str  # "x" | "y"
    plane_cm: float  # fixed coordinate on the perpendicular axis
    piece_ids: List[str]
    start_cm: float
    end_cm: float


@dataclass
class Aperture:
    """Door or window opening hosted in a wall (§7.9)."""

    piece_id: str
    kind: str  # door | window
    wall_piece_id: str
    level: int
    sill_z_cm: float
    floor_z_cm: float
    interior_cell: Tuple[int, int]
    exterior_cell: Tuple[int, int]
    world_xyz: Tuple[float, float, float]


@dataclass
class StyleAperturePolicy:
    """Per-style sill band for windows (§7.9)."""

    window_sill_min_cm: float = 80.0
    window_sill_max_cm: float = 120.0


@dataclass
class Assembly:
    placements: List[SolidPlacement]
    floor_plan: Dict[int, FloorPlanLayer] = field(default_factory=dict)
    circulation: List[CirculationEdge] = field(default_factory=list)
    wall_runs: List[WallRun] = field(default_factory=list)
    apertures: List[Aperture] = field(default_factory=list)
    storeys: int = 1
    aperture_policy: StyleAperturePolicy = field(default_factory=StyleAperturePolicy)
    room_specs: List[dict] = field(default_factory=list)
    #: Typology for ``stair_typology_match`` (house / industrial / academy / …).
    building_class: str = "generic"
    stair_kind: str = "straight"
    #: True when footprint could host a 2×2 monumental well.
    wide_stair_well_available: bool = False

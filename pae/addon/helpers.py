"""Pure helpers for the PAE Blender add-on (import-safe without bpy)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pae.report import Failure, Report
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
)

OBJECT_NAME_PREFIX = "PAE_"
CM_PER_M = 100.0

FOOTPRINT_KINDS: Tuple[str, ...] = ("rect", "L", "U", "courtyard", "compound")
PIPELINE_STAGES: Tuple[str, ...] = ("solve", "plan", "assemble", "validate")


def list_style_ids() -> List[str]:
    """Style preset ids from ``pae/styles/*.json``."""
    styles_dir = Path(__file__).resolve().parent.parent / "styles"
    return sorted(p.stem for p in styles_dir.glob("*.json") if p.is_file())


def piece_id_to_object_name(piece_id: str) -> str:
    return f"{OBJECT_NAME_PREFIX}{piece_id}"


def object_name_to_piece_id(name: str) -> Optional[str]:
    if name.startswith(OBJECT_NAME_PREFIX):
        return name[len(OBJECT_NAME_PREFIX) :]
    return None


def defect_to_select_id(failure: Failure) -> Optional[str]:
    """Map a validation failure to the Blender object piece id (if any)."""
    if failure.piece_id:
        return failure.piece_id
    return None


def frame_camera_from_world_point(
    target_xyz: Tuple[float, float, float],
    *,
    distance_cm: float = 800.0,
    azimuth_deg: float = 45.0,
    elevation_deg: float = 35.0,
) -> Dict[str, Tuple[float, float, float]]:
    """Camera location that looks at *target_xyz* (Blender Z-up, centimetres).

    Returns ``location`` and ``target`` in cm. bpy bridge converts to metres.
    """
    tx, ty, tz = target_xyz
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    horiz = distance_cm * math.cos(el)
    dx = horiz * math.cos(az)
    dy = horiz * math.sin(az)
    dz = distance_cm * math.sin(el)
    return {
        "location": (tx + dx, ty + dy, tz + dz),
        "target": target_xyz,
    }


def frame_camera_from_bounds(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
    *,
    margin: float = 1.25,
) -> Dict[str, Tuple[float, float, float]]:
    """Frame the centre of an axis-aligned bounds box."""
    cx = (bb_min[0] + bb_max[0]) * 0.5
    cy = (bb_min[1] + bb_max[1]) * 0.5
    cz = (bb_min[2] + bb_max[2]) * 0.5
    span = max(
        bb_max[0] - bb_min[0],
        bb_max[1] - bb_min[1],
        bb_max[2] - bb_min[2],
        1.0,
    )
    return frame_camera_from_world_point(
        (cx, cy, cz),
        distance_cm=span * margin,
    )


def cm_to_blender_location(xyz_cm: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """PAE world cm → Blender object location (metres)."""
    return (xyz_cm[0] / CM_PER_M, xyz_cm[1] / CM_PER_M, xyz_cm[2] / CM_PER_M)


@dataclass(frozen=True)
class ValidateDrawItem:
    index: int
    check: str
    message: str
    piece_id: Optional[str]
    select_id: Optional[str]
    world_xyz: Optional[Tuple[float, float, float]]
    critical: bool


@dataclass(frozen=True)
class ValidateDrawGroup:
    severity: str  # "critical" | "warning"
    label: str
    items: Tuple[ValidateDrawItem, ...]


def build_validate_draw_groups(report: Report) -> Tuple[ValidateDrawGroup, ...]:
    """Panel draw data — failures grouped by severity, stable indices."""
    groups: List[ValidateDrawGroup] = []
    for severity, label, failures in (
        ("critical", "Critical", report.critical),
        ("warning", "Warnings", report.warnings),
    ):
        items: List[ValidateDrawItem] = []
        for index, failure in enumerate(report.failures):
            if severity == "critical" and not failure.critical:
                continue
            if severity == "warning" and failure.critical:
                continue
            items.append(
                ValidateDrawItem(
                    index=index,
                    check=failure.check,
                    message=failure.message,
                    piece_id=failure.piece_id,
                    select_id=defect_to_select_id(failure),
                    world_xyz=failure.world_xyz,
                    critical=failure.critical,
                )
            )
        if items:
            groups.append(ValidateDrawGroup(severity=severity, label=label, items=tuple(items)))
    return tuple(groups)


def build_spec_from_ui(
    *,
    name: str,
    style: str,
    storeys: int,
    bays_x: int,
    bays_y: int,
    footprint_kind: str,
    seed: int,
    wing_depth: int = 2,
    courtyard: bool = False,
) -> BuildingSpec:
    """Build ``BuildingSpec`` from add-on property values (§3)."""
    return BuildingSpec(
        name=name or "pae_building",
        style=style,
        footprint=FootprintSpec(
            kind=footprint_kind,
            bays_x=max(1, bays_x),
            bays_y=max(1, bays_y),
            wing_depth=max(1, wing_depth),
            courtyard=courtyard or footprint_kind == "courtyard",
        ),
        storeys=max(1, storeys),
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=2,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def export_gate_allows(report: Optional[Report]) -> bool:
    """Export refuses when validation has critical defects (§8 / §10)."""
    if report is None:
        return False
    return report.ok and len(report.critical) == 0


def export_gate_message(report: Optional[Report]) -> str:
    if report is None:
        return "Run Validate after Generate — no report cached."
    if report.ok:
        return "Validation passed — export allowed."
    n = len(report.critical)
    return f"Export blocked: {n} critical defect(s). Fix or re-generate."


def bl_info_metadata() -> Dict[str, object]:
    """Registration metadata testable without bpy."""
    from pae.addon import bl_info

    return dict(bl_info)

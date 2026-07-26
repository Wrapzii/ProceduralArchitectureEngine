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
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    SUPPORTED_ROOF_KINDS,
    SUPPORTED_STAIR_KINDS,
)

OBJECT_NAME_PREFIX = "PAE_"
CM_PER_M = 100.0

FOOTPRINT_KINDS: Tuple[str, ...] = ("rect", "L", "U", "courtyard", "compound", "school")
PIPELINE_STAGES: Tuple[str, ...] = ("solve", "plan", "assemble", "validate")
ROOF_KINDS: Tuple[str, ...] = tuple(sorted(SUPPORTED_ROOF_KINDS))
STAIR_KINDS: Tuple[str, ...] = tuple(sorted(SUPPORTED_STAIR_KINDS))
ENTRANCE_ROLES: Tuple[str, ...] = (
    "grand",
    "main",
    "side",
    "service",
    "postern",
    "gate",
    "balcony",
    "internal",
    "upper_exterior",
)
FACADE_SIDES: Tuple[str, ...] = ("south", "north", "east", "west")


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
    roof_kind: str = "flat",
    roof_pitch: float = 1.0,
    stair_kind: str = "straight",
    wall_height_storeys: float = 0.0,
    doors_ground: int = 1,
    windows_per_bay: int = 1,
    entrance_enabled: bool = False,
    entrance_role: str = "main",
    entrance_facade: str = "south",
    entrance_ensemble: bool = False,
) -> BuildingSpec:
    """Build ``BuildingSpec`` from add-on property values (§3)."""
    rk = (roof_kind or "flat").lower()
    if rk not in SUPPORTED_ROOF_KINDS:
        rk = "flat"
    sk = (stair_kind or "straight").lower()
    if sk not in SUPPORTED_STAIR_KINDS:
        sk = "straight"
    entrances: List[EntranceSpec] = []
    if entrance_enabled:
        role = entrance_role if entrance_role in ENTRANCE_ROLES else "main"
        facade = entrance_facade if entrance_facade in FACADE_SIDES else "south"
        entrances.append(
            EntranceSpec(
                role=role,
                facade=facade,
                ensemble=entrance_ensemble,
            )
        )
    whs: Optional[float] = None
    if wall_height_storeys and wall_height_storeys >= 1.0:
        whs = float(wall_height_storeys)
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
        roof=RoofSpec(kind=rk, pitch=max(0.5, min(2.5, float(roof_pitch)))),
        circulation=CirculationSpec(stair_kind=sk, stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=max(0, windows_per_bay),
            doors_ground=max(0, doors_ground),
            windows_ground=2,
            skip_ground_windows=False,
        ),
        entrances=entrances,
        seed=seed,
        ground_slab=True,
        wall_height_storeys=whs,
    )


def ui_values_from_spec(spec: BuildingSpec) -> Dict[str, object]:
    """Map a ``BuildingSpec`` onto add-on property field values."""
    ent = spec.entrances[0] if spec.entrances else None
    return {
        "building_name": spec.name,
        "style": spec.style,
        "storeys": spec.storeys,
        "bays_x": spec.footprint.bays_x,
        "bays_y": spec.footprint.bays_y,
        "footprint_kind": spec.footprint.kind,
        "seed": spec.seed,
        "wing_depth": spec.footprint.wing_depth,
        "courtyard": spec.footprint.courtyard,
        "roof_kind": spec.roof.kind,
        "roof_pitch": spec.roof.pitch,
        "stair_kind": spec.circulation.stair_kind,
        "wall_height_storeys": spec.wall_height_storeys or 0.0,
        "doors_ground": spec.openings.doors_ground,
        "windows_per_bay": spec.openings.windows_per_bay,
        "entrance_enabled": ent is not None,
        "entrance_role": ent.role if ent else "main",
        "entrance_facade": ent.facade if ent and ent.facade else "south",
        "entrance_ensemble": bool(ent.ensemble) if ent else False,
    }


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

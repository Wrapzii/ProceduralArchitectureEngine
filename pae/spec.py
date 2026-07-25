"""BuildingSpec loader (§3) — WP-4.

Specs are declarative and in bays/modules. The loader rejects any LLM JSON that
contains world coordinates or centimetre placement fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pae.report import Failure, Report

# Keys / patterns that imply world placement or centimetre coordinates.
# Style JSON may use *_cm for band heights; BuildingSpec JSON must not.
_FORBIDDEN_KEY_RE = re.compile(
    r"(?i)^("
    r"x|y|z|pos|position|location|origin|placement|coordinate|coordinates|"
    r"translation|offset|world_.*|.*_world|"
    r".*_cm|.*_m|metres?|meters?|centimetres?|centimeters?"
    r")$"
)

_STYLES_DIR = Path(__file__).resolve().parent / "styles"

# Auto-placed circulation kinds. Spiral uses same-cell stacking (tower well).
SUPPORTED_STAIR_KINDS = frozenset({"straight", "switchback", "wide", "spiral"})
SUPPORTED_ROOF_KINDS = frozenset({"flat", "pitched", "hip"})
ROOF_PITCH_MIN = 0.5
ROOF_PITCH_MAX = 2.5
STEEP_PITCH_MIN = 1.6  # S-011 anime-fantasy silhouette

ROOM_KINDS = frozenset(
    {"classroom", "hall", "chapel", "library", "dormitory", "kitchen", "store"}
)

ENTRANCE_ROLES = frozenset(
    {
        "grand",
        "main",
        "side",
        "service",
        "postern",
        "gate",
        "balcony",
        "internal",
        "upper_exterior",  # Phase 9.2 — door on storey N opening to outside air
    }
)
ENTRANCE_FACADES = frozenset({"south", "north", "east", "west"})


@dataclass
class FootprintSpec:
    kind: str  # rect | L | U | courtyard | compound | school
    bays_x: int
    bays_y: int
    wing_depth: int = 2
    courtyard: bool = False


@dataclass
class TowerSpec:
    """Tower attachment in *cell* space (never world cm)."""

    cell: Tuple[int, int]
    storeys: int
    attached_to: str = "corner"  # wall | corner


@dataclass
class RoofSpec:
    kind: str = "flat"  # flat | pitched | hip
    pitch: float = 1.0


@dataclass
class CirculationSpec:
    stair_kind: str = "straight"  # straight | switchback | wide | spiral (tower / 1-cell)
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class OpeningPolicy:
    windows_per_bay: int = 1
    doors_ground: int = 1
    windows_ground: Optional[int] = None  # exact count override (e.g. M1 = 2)
    skip_ground_windows: bool = False


EntranceRole = str  # grand | main | side | service | postern | gate | balcony | internal | upper_exterior


@dataclass
class EntranceSpec:
    """Declarative entrance — role drives piece choice; facade/bay place it.

    Every declared entrance is a *passage breach*: assemble must place a door or
    gate leaf (never a bare hole). Enforced by ``no_bare_aperture`` (roadmap §1.5).

    When ``ensemble`` is True (Phase 1.3), assemble expands the entrance into a
    greybox composition: arch leaf + exterior steps + flanking columns, and twin
    interior stairs when the building has ≥2 storeys and free interior cells.

    Phase 9.2: ``role="upper_exterior"`` with ``storey >= 1`` declares a door that
    opens to outside air. It must pair with an exterior landing
    (``upper_entrance_landing`` / ``aperture_reachability``).
    """

    role: EntranceRole
    facade: Optional[str] = None  # south | north | east | west
    bay: Optional[int] = None  # 0-based index along the facade run
    ensemble: bool = False
    storey: int = 0  # 0 = ground; upper_exterior requires >= 1


@dataclass
class RoomSpec:
    """Programmed room intent — geometry resolved in plan/assemble."""

    name: str
    kind: str  # classroom | hall | chapel | library | dormitory | kitchen | store
    area_bays: Optional[int] = None
    double_height: bool = False


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
    entrances: List[EntranceSpec] = field(default_factory=list)
    seed: int = 0
    # Intent only — geometry emitted by assemble (WP-5).
    ground_slab: bool = True
    rooms: List[RoomSpec] = field(default_factory=list)


def _scan_forbidden_keys(node: Any, path: str = "") -> List[str]:
    """Return human-readable paths of forbidden world/cm keys."""
    hits: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if _FORBIDDEN_KEY_RE.match(str(key)):
                hits.append(child)
            hits.extend(_scan_forbidden_keys(value, child))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            hits.extend(_scan_forbidden_keys(value, f"{path}[{i}]"))
    return hits


def _as_int_pair(value: Any, label: str) -> Tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be a [x, y] cell pair")
    return (int(value[0]), int(value[1]))


def _school_footprint_min_depth(fp_bays_x: int, fp_bays_y: int, wing_depth: int) -> int:
    """Effective wing depth for school program (matches solver ``_place_school_academy``)."""
    return max(
        4,
        min(wing_depth if wing_depth else 5, min(fp_bays_x, fp_bays_y) // 2 or 4),
    )


def _validate_school_footprint(
    bays_x: int, bays_y: int, wing_depth: int
) -> Optional[str]:
    """Return error message when school cannot emit classroom_wing volumes."""
    depth = _school_footprint_min_depth(bays_x, bays_y, wing_depth)
    min_span = 2 * depth + 1
    if bays_x < min_span or bays_y < min_span:
        return (
            f"school footprint too small for wing_depth={depth}: "
            f"need bays_x and bays_y >= {min_span}, got {bays_x}x{bays_y}"
        )
    mid_h = bays_y - 2 * depth
    if mid_h < 2:
        return (
            f"school footprint cannot fit classroom wings: "
            f"mid_h={mid_h} < 2 (bays_y={bays_y}, depth={depth})"
        )
    return None


def _parse_footprint(raw: dict) -> FootprintSpec:
    kind = str(raw.get("kind", "rect"))
    if kind not in ("rect", "L", "U", "courtyard", "compound", "school"):
        raise ValueError(f"unknown footprint kind: {kind}")
    bays_x = int(raw["bays_x"])
    bays_y = int(raw["bays_y"])
    if bays_x < 1 or bays_y < 1:
        raise ValueError("bays_x and bays_y must be >= 1")
    wing_depth = int(raw.get("wing_depth", 2))
    courtyard = bool(raw.get("courtyard", kind == "courtyard"))
    if kind == "school":
        err = _validate_school_footprint(bays_x, bays_y, wing_depth)
        if err:
            raise ValueError(err)
    return FootprintSpec(
        kind=kind,
        bays_x=bays_x,
        bays_y=bays_y,
        wing_depth=wing_depth,
        courtyard=courtyard,
    )


def _parse_towers(raw: Any) -> List[TowerSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("towers must be a list")
    out: List[TowerSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("tower entries must be objects")
        attached = str(item.get("attached_to", "corner"))
        if attached not in ("wall", "corner"):
            raise ValueError(f"tower.attached_to must be wall|corner, got {attached}")
        out.append(
            TowerSpec(
                cell=_as_int_pair(item["cell"], "tower.cell"),
                storeys=int(item["storeys"]),
                attached_to=attached,
            )
        )
    return out


def _parse_roof(raw: Any) -> RoofSpec:
    if raw is None:
        return RoofSpec()
    if not isinstance(raw, dict):
        raise ValueError("roof must be an object")
    kind = str(raw.get("kind", "flat"))
    pitch = float(raw.get("pitch", 1.0))
    if kind not in SUPPORTED_ROOF_KINDS:
        supported = ", ".join(sorted(SUPPORTED_ROOF_KINDS))
        raise ValueError(f"unsupported roof kind '{kind}' — supported: {supported}")
    if not (ROOF_PITCH_MIN <= pitch <= ROOF_PITCH_MAX):
        raise ValueError(
            f"roof pitch {pitch} out of range [{ROOF_PITCH_MIN}, {ROOF_PITCH_MAX}]"
        )
    return RoofSpec(kind=kind, pitch=pitch)


def _parse_circulation(raw: Any) -> CirculationSpec:
    if raw is None:
        return CirculationSpec()
    if not isinstance(raw, dict):
        raise ValueError("circulation must be an object")
    cells_raw = raw.get("stair_cells") or []
    cells = [_as_int_pair(c, "stair_cells") for c in cells_raw]
    stair_kind = str(raw.get("stair_kind", "straight")).lower()
    if stair_kind not in SUPPORTED_STAIR_KINDS:
        supported = ", ".join(sorted(SUPPORTED_STAIR_KINDS))
        raise ValueError(
            f"unsupported stair_kind '{stair_kind}' — supported: {supported}"
        )
    return CirculationSpec(
        stair_kind=stair_kind,
        stair_cells=cells,
    )


def _parse_rooms(raw: Any) -> List[RoomSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("rooms must be a list")
    out: List[RoomSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("room entries must be objects")
        kind = str(item.get("kind", "")).lower()
        if kind not in ROOM_KINDS:
            kinds = ", ".join(sorted(ROOM_KINDS))
            raise ValueError(f"room.kind must be one of {kinds}, got {kind!r}")
        area_raw = item.get("area_bays")
        area_bays = None if area_raw is None else int(area_raw)
        out.append(
            RoomSpec(
                name=str(item.get("name", kind)),
                kind=kind,
                area_bays=area_bays,
                double_height=bool(item.get("double_height", False)),
            )
        )
    return out


def _parse_openings(raw: Any) -> OpeningPolicy:
    if raw is None:
        return OpeningPolicy()
    if not isinstance(raw, dict):
        raise ValueError("openings must be an object")
    windows_ground = raw.get("windows_ground")
    return OpeningPolicy(
        windows_per_bay=int(raw.get("windows_per_bay", 1)),
        doors_ground=int(raw.get("doors_ground", 1)),
        windows_ground=None if windows_ground is None else int(windows_ground),
        skip_ground_windows=bool(raw.get("skip_ground_windows", False)),
    )


def _parse_entrances(raw: Any) -> List[EntranceSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("entrances must be a list")
    out: List[EntranceSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"entrances[{i}] must be an object")
        role = str(item.get("role", "")).lower()
        if role not in ENTRANCE_ROLES:
            known = ", ".join(sorted(ENTRANCE_ROLES))
            raise ValueError(f"entrances[{i}].role must be one of {known}, got {role!r}")
        facade_raw = item.get("facade")
        facade = None if facade_raw is None else str(facade_raw).lower()
        if facade is not None and facade not in ENTRANCE_FACADES:
            known = ", ".join(sorted(ENTRANCE_FACADES))
            raise ValueError(
                f"entrances[{i}].facade must be one of {known}, got {facade!r}"
            )
        bay_raw = item.get("bay")
        bay = None if bay_raw is None else int(bay_raw)
        if bay is not None and bay < 0:
            raise ValueError(f"entrances[{i}].bay must be >= 0")
        ensemble = bool(item.get("ensemble", False))
        storey_raw = item.get("storey", 0)
        storey = int(storey_raw)
        if storey < 0:
            raise ValueError(f"entrances[{i}].storey must be >= 0")
        if role == "upper_exterior":
            if "storey" not in item:
                storey = 1
            elif storey < 1:
                raise ValueError(
                    f"entrances[{i}].storey must be >= 1 for role upper_exterior"
                )
        out.append(
            EntranceSpec(
                role=role,
                facade=facade,
                bay=bay,
                ensemble=ensemble,
                storey=storey,
            )
        )
    return out


def load_spec(data: dict) -> Tuple[Optional[BuildingSpec], Report]:
    """Load BuildingSpec from LLM/UI JSON.

    Rejects any world-coordinate or centimetre placement fields (hard failure).
    """
    failures: List[Failure] = []
    if not isinstance(data, dict):
        failures.append(
            Failure(
                check="spec_type",
                message="BuildingSpec JSON must be an object",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    forbidden = _scan_forbidden_keys(data)
    if forbidden:
        for path in forbidden:
            failures.append(
                Failure(
                    check="spec_no_world_coords",
                    message=(
                        f"forbidden world/cm placement field at '{path}' — "
                        "specs use bays/cells only"
                    ),
                    world_xyz=None,
                )
            )
        return None, Report.from_failures(failures)

    try:
        footprint = _parse_footprint(data.get("footprint") or {})
        storeys = int(data["storeys"])
        if storeys < 1:
            raise ValueError("storeys must be >= 1")
        storey_use = list(data.get("storey_use") or [])
        if not storey_use:
            storey_use = ["hall"] * storeys
        while len(storey_use) < storeys:
            storey_use.append(storey_use[-1] if storey_use else "hall")
        spec = BuildingSpec(
            name=str(data.get("name", "unnamed")),
            style=str(data.get("style", "townhouse")),
            footprint=footprint,
            storeys=storeys,
            storey_use=storey_use[:storeys],
            towers=_parse_towers(data.get("towers")),
            roof=_parse_roof(data.get("roof")),
            circulation=_parse_circulation(data.get("circulation")),
            openings=_parse_openings(data.get("openings")),
            entrances=_parse_entrances(data.get("entrances")),
            seed=int(data.get("seed", 0)),
            ground_slab=bool(data.get("ground_slab", True)),
            rooms=_parse_rooms(data.get("rooms")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(
            Failure(
                check="spec_parse",
                message=f"failed to parse BuildingSpec: {exc}",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    return spec, Report.from_failures([])


def load_spec_json(text: str) -> Tuple[Optional[BuildingSpec], Report]:
    """Parse a JSON string then load_spec."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="spec_json",
                    message=f"invalid JSON: {exc}",
                    world_xyz=None,
                )
            ]
        )
    return load_spec(data)


def load_style(style_id: str) -> Tuple[Optional[Dict[str, Any]], Report]:
    """Load a style preset from pae/styles/<id>.json via StylePack bridge."""
    from pae.style_pack import load_style_pack

    pack, report = load_style_pack(style_id)
    if pack is None:
        return None, report
    return pack.to_legacy_dict(), report


def m1_box_house_spec(*, seed: int = 1) -> BuildingSpec:
    """Factory for Milestone 1 — one-storey 4×3 box house.

    Intent only: 1 door, 2 windows, flat roof, ground slab.
    Assembly geometry is WP-5.
    """
    return BuildingSpec(
        name="m1_box_house",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
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


def m2_two_storey_stair_spec(*, seed: int = 2) -> BuildingSpec:
    """Factory for Milestone 2 — two-storey 4×3 box with straight stair.

    Solver auto-places a 2-module straight run; plan marks VOID above the
    stair top; assembly emits ``stair_straight`` + ``floor_hole``.
    """
    return BuildingSpec(
        name="m2_two_storey_stair",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
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


def m2_two_storey_stair_dict(*, seed: int = 2) -> dict:
    """JSON-serialisable form of the M2 factory (for loader round-trips)."""
    spec = m2_two_storey_stair_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m1_box_house_dict(*, seed: int = 1) -> dict:
    """JSON-serialisable form of the M1 factory (for loader round-trips)."""
    spec = m1_box_house_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m3_keep_tower_spec(*, seed: int = 3) -> BuildingSpec:
    """Factory for Milestone 3 — keep with pitched roof + wall-attached round tower.

    Does not alter M1/M2 factories. Tower sits on the west wall (edge abut, not
    diagonal corner) so plan circulation stays 4-connected; arcs still share one
    cell (§2.2 centred exception).
    """
    return BuildingSpec(
        name="m3_keep_tower",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[TowerSpec(cell=(-1, 0), storeys=3, attached_to="wall")],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        seed=seed,
        ground_slab=True,
    )


def m3_keep_tower_dict(*, seed: int = 3) -> dict:
    """JSON-serialisable form of the M3 factory."""
    spec = m3_keep_tower_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [
            {
                "cell": list(t.cell),
                "storeys": t.storeys,
                "attached_to": t.attached_to,
            }
            for t in spec.towers
        ],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m11_hip_roof_spec(*, seed: int = 11) -> BuildingSpec:
    """Factory for Milestone 11 — 4×4 rect with four-slope hip roof (S-012)."""
    return BuildingSpec(
        name="m11_hip_roof",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="hip", pitch=1.0),
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


def m11_hip_roof_dict(*, seed: int = 11) -> dict:
    """JSON-serialisable form of the M11 hip-roof factory."""
    spec = m11_hip_roof_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m_spiral_tower_spec(*, seed: int = 31) -> BuildingSpec:
    """Milestone 3.1 — keep + wall tower with helical spiral in the drum.

    Solver auto-places a single tower cell; assemble emits 4×
    ``stair_spiral_quarter`` per storey climb (yaw 0/90/180/270).
    """
    spec = m3_keep_tower_spec(seed=seed)
    return BuildingSpec(
        name="m_spiral_tower",
        style=spec.style,
        footprint=spec.footprint,
        storeys=spec.storeys,
        storey_use=list(spec.storey_use),
        towers=list(spec.towers),
        roof=spec.roof,
        circulation=CirculationSpec(stair_kind="spiral", stair_cells=[]),
        openings=spec.openings,
        seed=spec.seed,
        ground_slab=spec.ground_slab,
    )


def m_spiral_tower_dict(*, seed: int = 31) -> dict:
    """JSON-serialisable form of the spiral tower factory."""
    spec = m_spiral_tower_spec(seed=seed)
    data = m3_keep_tower_dict(seed=seed)
    data["name"] = spec.name
    data["circulation"]["stair_kind"] = "spiral"
    return data


def m4_l_plan_spec(*, seed: int = 4) -> BuildingSpec:
    """Factory for Milestone 4 — L-shaped cloister wing (8×8, wing_depth=2).

    South bar + west leg; re-entrant inner face gets inhabited walls in assemble.
    """
    return BuildingSpec(
        name="m4_l_plan",
        style="townhouse",
        footprint=FootprintSpec(kind="L", bays_x=8, bays_y=8, wing_depth=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_u_plan_spec(*, seed: int = 5) -> BuildingSpec:
    """Factory for Milestone 4 — U-shaped plan (8×8, wing_depth=2).

    South bar + west/east legs; open court to the north (exterior, not courtyard role).
    """
    return BuildingSpec(
        name="m4_u_plan",
        style="townhouse",
        footprint=FootprintSpec(kind="U", bays_x=8, bays_y=8, wing_depth=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_courtyard_spec(*, seed: int = 6) -> BuildingSpec:
    """Factory for Milestone 4 — ring plan with open courtyard (8×8, wing_depth=2).

    Courtyard cells are outside the enclosed envelope; no roof/floor over the hole.
    """
    return BuildingSpec(
        name="m4_courtyard",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="courtyard", bays_x=8, bays_y=8, wing_depth=2, courtyard=True
        ),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_l_plan_dict(*, seed: int = 4) -> dict:
    """JSON-serialisable form of the M4 L factory."""
    spec = m4_l_plan_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m4_u_plan_dict(*, seed: int = 5) -> dict:
    """JSON-serialisable form of the M4 U factory."""
    spec = m4_u_plan_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m4_courtyard_dict(*, seed: int = 6) -> dict:
    """JSON-serialisable form of the M4 courtyard factory."""
    spec = m4_courtyard_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def school_academy_spec(*, seed: int = 70) -> BuildingSpec:
    """Giant academy massing — named hall / classroom wings / admin + courtyard.

    Uses footprint kind ``school`` (solver emits program roles). Default circulation
    is a switchback stairwell (2×2). Storey use biases classroom partitioning.
    """
    classroom_count = 8
    return BuildingSpec(
        name="school_academy",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="school",
            bays_x=16,
            bays_y=14,
            wing_depth=5,
            courtyard=True,
        ),
        storeys=3,
        storey_use=["classroom", "classroom", "classroom"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.05),
        circulation=CirculationSpec(stair_kind="switchback", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=2,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        rooms=[
            RoomSpec(name="great_hall", kind="hall", double_height=True),
            RoomSpec(
                name="classrooms",
                kind="classroom",
                area_bays=classroom_count,
            ),
        ],
    )


def castle_curtain_wall_spec(
    name: str,
    length_bays: int,
    *,
    storeys: int = 2,
    depth_bays: int = 3,
    seed: int = 40,
) -> BuildingSpec:
    """Thin curtain-wall run — shallow bar, ``wall_plain`` envelope, no towers.

    Default ``depth_bays=3`` is the minimum depth the solver can stairserve for two
    storeys on a straight run. Trimmed with ``parapet_solid`` and ``battlement`` when
    built via :func:`pae.compound.build_castle_curtain_compound`.
    """
    return BuildingSpec(
        name=name,
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=length_bays, bays_y=depth_bays),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        seed=seed,
        ground_slab=True,
    )


def castle_gatehouse_spec(*, seed: int = 41) -> BuildingSpec:
    """Twin-tower gate block with a south ``gate`` entrance (``wall_gate_arch``)."""
    return BuildingSpec(
        name="castle_gatehouse",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[
            TowerSpec(cell=(0, 0), storeys=3, attached_to="corner"),
            TowerSpec(cell=(3, 0), storeys=3, attached_to="corner"),
        ],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=0,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[EntranceSpec(role="gate", facade="south")],
        seed=seed,
        ground_slab=True,
    )


@dataclass(frozen=True)
class CastleBaileySpec:
    """Layout knobs for :func:`pae.compound.build_castle_curtain_compound`."""

    curtain_length_bays: int = 8
    curtain_storeys: int = 2
    gatehouse_seed: int = 41
    west_curtain_seed: int = 42
    east_curtain_seed: int = 43


def castle_bailey_spec() -> CastleBaileySpec:
    """Default inner-ward curtain + gatehouse preset (Phase 4.1–4.2 greybox)."""
    return CastleBaileySpec()


def m8_entrances_spec(*, seed: int = 8) -> BuildingSpec:
    """Factory for Milestone 8 — declarative entrance roles on south/north facades.

    Grand carriage arch on the south front; service postern on the north rear.
    When ``entrances`` is non-empty, legacy ``openings.doors_ground`` is ignored.
    """
    return BuildingSpec(
        name="m8_entrances",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=6, bays_y=5),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="grand", facade="south"),
            EntranceSpec(role="service", facade="north"),
        ],
        seed=seed,
        ground_slab=True,
    )


def m9_grand_ensemble_spec(*, seed: int = 9) -> BuildingSpec:
    """Milestone 9 — grand entrance ensemble (Phase 1.3 greybox stub).

    South ``grand`` entrance with ``ensemble=True`` expands to arch + steps +
    flanking columns (and twin interior stairs when feasible). Service door
    remains a plain leaf without ensemble expansion.
    """
    return BuildingSpec(
        name="m9_grand_ensemble",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=8, bays_y=6),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(
            stair_kind="straight",
            # Keep the hall stair off the south grand bay so twin ensemble
            # flights can occupy the inward flanks (Phase 1.3).
            stair_cells=[(6, 3), (6, 4)],
        ),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="grand", facade="south", ensemble=True),
            EntranceSpec(role="service", facade="north", ensemble=False),
        ],
        seed=seed,
        ground_slab=True,
    )


def school_academy_dict(*, seed: int = 70) -> dict:
    """JSON-serialisable form of the school academy factory."""
    spec = school_academy_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
        "rooms": [
            {
                "name": r.name,
                "kind": r.kind,
                "area_bays": r.area_bays,
                "double_height": r.double_height,
            }
            for r in spec.rooms
        ],
    }

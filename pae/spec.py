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


@dataclass
class FootprintSpec:
    kind: str  # rect | L | U | courtyard | compound
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
    windows_ground: Optional[int] = None  # exact count override (e.g. M1 = 2)
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
    # Intent only — geometry emitted by assemble (WP-5).
    ground_slab: bool = True


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


def _parse_footprint(raw: dict) -> FootprintSpec:
    kind = str(raw.get("kind", "rect"))
    if kind not in ("rect", "L", "U", "courtyard", "compound"):
        raise ValueError(f"unknown footprint kind: {kind}")
    bays_x = int(raw["bays_x"])
    bays_y = int(raw["bays_y"])
    if bays_x < 1 or bays_y < 1:
        raise ValueError("bays_x and bays_y must be >= 1")
    wing_depth = int(raw.get("wing_depth", 2))
    courtyard = bool(raw.get("courtyard", kind == "courtyard"))
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
    return RoofSpec(
        kind=str(raw.get("kind", "flat")),
        pitch=float(raw.get("pitch", 1.0)),
    )


def _parse_circulation(raw: Any) -> CirculationSpec:
    if raw is None:
        return CirculationSpec()
    if not isinstance(raw, dict):
        raise ValueError("circulation must be an object")
    cells_raw = raw.get("stair_cells") or []
    cells = [_as_int_pair(c, "stair_cells") for c in cells_raw]
    return CirculationSpec(
        stair_kind=str(raw.get("stair_kind", "straight")),
        stair_cells=cells,
    )


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
            seed=int(data.get("seed", 0)),
            ground_slab=bool(data.get("ground_slab", True)),
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
    """Load a style preset from pae/styles/<id>.json."""
    path = _STYLES_DIR / f"{style_id}.json"
    if not path.is_file():
        return None, Report.from_failures(
            [
                Failure(
                    check="style_missing",
                    message=f"style preset not found: {style_id}",
                    world_xyz=None,
                )
            ]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="style_load",
                    message=f"failed to load style {style_id}: {exc}",
                    world_xyz=None,
                )
            ]
        )
    if not isinstance(data, dict) or data.get("id") != style_id:
        return None, Report.from_failures(
            [
                Failure(
                    check="style_id",
                    message=f"style id mismatch in {path.name}",
                    world_xyz=None,
                )
            ]
        )
    return data, Report.from_failures([])


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

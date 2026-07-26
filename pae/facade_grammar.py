"""CITY&BEYOND-style slider → BuildingSpec facade grammar for Georgian townhouses.

Parametric shell + facade grammar: metres and wealth sliders compile to bays/modules
via :data:`pae.contract.MODULE_CM`, with shared piece IDs from :mod:`pae.shared_ids`
for exterior and interior fitout.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, FrozenSet, Optional, Tuple

from pae.contract import MODULE_CM
from pae.report import Report
from pae.shared_ids import resolve_shared
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
)

_ROW_CONTEXTS = frozenset({"freestanding", "end_left", "end_right", "mid"})

# Default bay counts when metre sliders are zero (auto).
_DEFAULT_FRONTAGE_BAYS = 3
_DEFAULT_DEPTH_BAYS = 2


@dataclass
class FacadeParams:
    """Slider bundle for a Georgian merchant townhouse facade."""

    seed: int = 1812
    archetype: str = "georgian_merchant"  # style id
    palette_family: str = "cream_render"
    frontage_m: float = 10.0  # 0 = auto
    depth_m: float = 8.0  # 0 = auto
    storeys: int = 4  # 0 = auto → 3
    wealth: int = 3  # -1 = auto → 2
    weathering: float = -1.0  # -1 = auto
    lit_windows: float = 0.4
    row_context: str = "end_left"  # freestanding|end_left|end_right|mid


def resolve_wealth(wealth: int) -> int:
    """Wealth tier used by grammar — ``-1`` auto-selects 2."""
    if wealth < 0:
        return 2
    return max(1, min(5, int(wealth)))


def resolve_storeys(storeys: int) -> int:
    """Storey count — ``0`` auto-selects 3."""
    if storeys <= 0:
        return 3
    return max(1, int(storeys))


def resolve_weathering(weathering: float, *, wealth: int) -> float:
    """Weathering amount in ``[0, 1]`` — ``-1`` scales lightly with wealth."""
    if weathering >= 0.0:
        return max(0.0, min(1.0, float(weathering)))
    # Auto: modest wear on humble rows, cleaner merchant fronts at high wealth.
    tier = resolve_wealth(wealth)
    return max(0.0, min(1.0, 0.55 - tier * 0.08))


def metres_to_bays(metres: float) -> int:
    """Convert metres to module bays (ceil)."""
    if metres <= 0.0:
        return 0
    return max(1, int(math.ceil(metres * 100.0 / MODULE_CM)))


def party_wall_faces(row_context: str) -> FrozenSet[str]:
    """Facades that are party walls (no street-facing openings) for a row position."""
    ctx = (row_context or "").strip().lower()
    if ctx == "freestanding":
        return frozenset()
    if ctx == "end_left":
        return frozenset({"west"})
    if ctx == "end_right":
        return frozenset({"east"})
    if ctx == "mid":
        return frozenset({"east", "west"})
    raise ValueError(
        f"row_context must be one of {sorted(_ROW_CONTEXTS)}, got {row_context!r}"
    )


def _windows_per_bay(wealth: int) -> int:
    tier = resolve_wealth(wealth)
    if tier >= 4:
        return 2
    return 1


def _stair_kind(wealth: int, bays_x: int, bays_y: int) -> str:
    tier = resolve_wealth(wealth)
    stair_id = resolve_shared("stair", tier, "main")
    if stair_id == "stair_switchback" and min(bays_x, bays_y) >= 2:
        return "switchback"
    return "straight"


def params_to_spec(params: FacadeParams) -> BuildingSpec:
    """Compile slider params → declarative BuildingSpec (bays/modules only)."""
    wealth = resolve_wealth(params.wealth)
    storeys = resolve_storeys(params.storeys)
    bays_x = metres_to_bays(params.frontage_m) or _DEFAULT_FRONTAGE_BAYS
    bays_y = metres_to_bays(params.depth_m) or _DEFAULT_DEPTH_BAYS
    windows_per_bay = _windows_per_bay(wealth)
    stair_kind = _stair_kind(wealth, bays_x, bays_y)

    # Party-wall faces are west/east in a south-facing row; entrances stay on south.
    blind = party_wall_faces(params.row_context)
    entrances = [EntranceSpec(role="main", facade="south")]
    if "north" not in blind and params.row_context == "freestanding":
        entrances.append(EntranceSpec(role="service", facade="north"))

    building_class = "house" if storeys <= 3 and max(bays_x, bays_y) <= 6 else "generic"

    return BuildingSpec(
        name=f"{params.archetype}_{params.seed}",
        style=params.archetype,
        footprint=FootprintSpec(kind="rect", bays_x=bays_x, bays_y=bays_y),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        roof=RoofSpec(kind="auto", pitch=1.05),
        circulation=CirculationSpec(stair_kind=stair_kind, stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=windows_per_bay,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        entrances=entrances,
        seed=int(params.seed),
        ground_slab=True,
        building_class=building_class,
    )


def _palette_wall(palette_family: str, wealth: int) -> str:
    family = (palette_family or "cream_render").strip().lower()
    if family in ("cream_render", "cream", "render"):
        return resolve_shared("material", wealth, "exterior_wall")
    return resolve_shared("material", wealth, "exterior_wall")


def params_to_style_overrides(params: FacadeParams) -> Dict[str, Any]:
    """Style-pack overrides for materials, weathering, and shell detail by wealth."""
    wealth = resolve_wealth(params.wealth)
    wear = resolve_weathering(params.weathering, wealth=wealth)
    window_tag = resolve_shared("window", wealth, "exterior")
    door_tag = resolve_shared("door", wealth, "main")

    shell: Dict[str, Any] = {
        "stoop": True,
        "doorcase": "plain" if wealth < 3 else "grand",
        "chimney_stub": wealth >= 3,
        "window_sills": True,
        "pilasters": wealth >= 3,
        "forecourt": params.row_context != "mid",
    }

    return {
        "materials": {
            "wall": _palette_wall(params.palette_family, wealth),
            "roof": resolve_shared("material", wealth, "roof"),
            "trim": resolve_shared("material", wealth, "trim"),
        },
        "window": {
            "tag": window_tag,
            "per_bay": _windows_per_bay(wealth),
            "skip_ground": False,
        },
        "door": {"tag": door_tag},
        "detail": {
            "weathering": wear >= 0.35,
            "density": min(0.95, 0.55 + wealth * 0.08),
            "mid_string": wealth >= 2,
            "verticals_every_bays": 1 if wealth < 4 else 2,
        },
        "shell": shell,
        "substitutions": {
            window_tag: "wall_window_mullioned"
            if "sash" in window_tag
            else "wall_window_cross",
            door_tag: "wall_door_double" if door_tag == "door_georgian" else "wall_door",
        },
    }


def export_params_json(params: FacadeParams) -> str:
    """Serialize slider params (Copy Parameters JSON equivalent)."""
    payload = asdict(params)
    payload["party_wall_faces"] = sorted(party_wall_faces(params.row_context))
    payload["resolved_wealth"] = resolve_wealth(params.wealth)
    payload["resolved_storeys"] = resolve_storeys(params.storeys)
    payload["resolved_weathering"] = resolve_weathering(
        params.weathering, wealth=params.wealth
    )
    return json.dumps(payload, indent=2, sort_keys=True)


def params_from_json(text: str) -> FacadeParams:
    """Deserialize slider params from JSON (roundtrip helper for tests/tools)."""
    data = json.loads(text)
    allowed = {f.name for f in fields(FacadeParams)}
    kwargs = {k: data[k] for k in allowed if k in data}
    return FacadeParams(**kwargs)


def build_from_params(
    params: FacadeParams,
    *,
    validate_assembly: bool = True,
    apply_style_shell: bool = True,
    apply_detail: bool = True,
    **kwargs: Any,
) -> Tuple[Any, Any, Any, Report, FacadeParams]:
    """Run assemble → style shell → detail for compiled facade params.

    Returns ``(massing, floor_plan, assembly, report, params)``.

    Per-slider style overrides from :func:`params_to_style_overrides` are resolved
    for tooling; assembly consumes the authored ``georgian_merchant`` pack on disk.
    """
    from pae.style_pipeline import assemble_with_style_shell_and_detail

    spec = params_to_spec(params)

    massing, floor_plan, assembly, report = assemble_with_style_shell_and_detail(
        spec,
        seed=params.seed,
        validate_assembly=validate_assembly,
        apply_style_shell=apply_style_shell,
        apply_detail=apply_detail,
        **kwargs,
    )
    return massing, floor_plan, assembly, report, params


__all__ = [
    "FacadeParams",
    "build_from_params",
    "export_params_json",
    "metres_to_bays",
    "params_from_json",
    "params_to_spec",
    "params_to_style_overrides",
    "party_wall_faces",
    "resolve_storeys",
    "resolve_weathering",
    "resolve_wealth",
]

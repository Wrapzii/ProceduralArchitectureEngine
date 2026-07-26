"""CITY&BEYOND-style slider → BuildingSpec facade grammar for Georgian townhouses.

Parametric shell + facade grammar: metres and wealth sliders compile to bays/modules
via :data:`pae.contract.MODULE_CM`, with shared piece IDs from :mod:`pae.shared_ids`
for exterior and interior fitout.
"""

from __future__ import annotations

import json
import math
import random
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

# Archetypes wired to the continuous shell path (style JSON under pae/styles/).
SHELL_ARCHETYPES: Tuple[str, ...] = (
    "georgian_merchant",
    "townhouse",
    "civic",
    "manor",
    "rustic",
    "medieval",
)

# Default wealth tier per archetype when slider is -1 (auto).
_ARCHETYPE_DEFAULT_WEALTH: Dict[str, int] = {
    "georgian_merchant": 3,
    "townhouse": 2,
    "civic": 4,
    "manor": 5,
    "rustic": 1,
    "medieval": 2,
}

# Palette family hints per archetype (overridden by explicit slider).
_ARCHETYPE_DEFAULT_PALETTE: Dict[str, str] = {
    "georgian_merchant": "cream_render",
    "townhouse": "timber_plaster",
    "civic": "stone_ashlar",
    "manor": "stone_ashlar",
    "rustic": "timber_plaster",
    "medieval": "stone_ashlar",
}

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
    storeys: int = 2  # 0 = auto → 3; 2 fits default 10×8 m plot
    wealth: int = 2  # -1 = auto → 2
    weathering: float = -1.0  # -1 = auto
    lit_windows: float = 0.4
    row_context: str = "freestanding"  # freestanding|end_left|end_right|mid


def resolve_wealth(wealth: int, *, archetype: str = "georgian_merchant") -> int:
    """Wealth tier used by grammar — ``-1`` auto-selects per archetype."""
    if wealth < 0:
        arch = (archetype or "georgian_merchant").strip().lower()
        return _ARCHETYPE_DEFAULT_WEALTH.get(arch, 2)
    return max(1, min(5, int(wealth)))


def facade_rng(seed: int, *tags: str) -> random.Random:
    """Deterministic RNG for shell variation — ``(seed, archetype, …)``."""
    h = int(seed) & 0xFFFFFFFF
    for tag in tags:
        h = (h * 1_000_003) ^ (hash(tag) & 0xFFFFFFFF)
    return random.Random(h)


@dataclass(frozen=True)
class ShellStyleConfig:
    """Archetype style-pack hints consumed by the continuous shell builder."""

    archetype: str
    roof_pitch: float
    roof_kind: str
    window_w_frac: float
    window_h_frac: float
    window_sill_frac: float
    default_wealth: int
    palette_family: str


def load_archetype_shell_config(
    archetype: str,
    *,
    wealth: int = -1,
    palette_family: str = "",
) -> ShellStyleConfig:
    """Load palette, roof pitch, and window fractions from the style pack."""
    from pae.style_pack import load_style_pack, resolve_roof_kind, resolve_roof_pitch

    arch = (archetype or "georgian_merchant").strip().lower()
    if arch not in SHELL_ARCHETYPES:
        arch = "georgian_merchant"
    pack, _report = load_style_pack(arch)
    pitch = resolve_roof_pitch(pack)
    roof_kind = resolve_roof_kind(pack)
    per_bay = max(1, int(pack.window.per_bay))
    # Window ratio scales with pack density and pitch (S-008 proportion hook).
    w_frac = min(0.72, 0.44 + per_bay * 0.05 + (pitch - 1.0) * 0.04)
    h_frac = min(0.68, 0.48 + per_bay * 0.04)
    sill_frac = 0.20 if arch in ("civic", "medieval") else 0.22
    if arch == "rustic":
        w_frac = 0.42
        h_frac = 0.50
        sill_frac = 0.18
    elif arch == "civic":
        w_frac = 0.50
        h_frac = 0.40
    elif arch == "manor":
        w_frac = 0.58
        h_frac = 0.55
    resolved_wealth = resolve_wealth(wealth, archetype=arch)
    pal = (palette_family or "").strip().lower()
    if not pal:
        pal = _ARCHETYPE_DEFAULT_PALETTE.get(arch, "cream_render")
    return ShellStyleConfig(
        archetype=arch,
        roof_pitch=pitch,
        roof_kind=roof_kind,
        window_w_frac=w_frac,
        window_h_frac=h_frac,
        window_sill_frac=sill_frac,
        default_wealth=resolved_wealth,
        palette_family=pal,
    )


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


def footprint_allows_switchback(bays_x: int, bays_y: int) -> bool:
    """Switchback needs a 2×2 well plus margin — at least 4×3 bays."""
    return bays_x >= 4 and bays_y >= 3


def resolve_stair_id(
    wealth: int,
    bays_x: int,
    bays_y: int,
    *,
    storeys: int = 1,
) -> str:
    """Pick stair piece id — straight on small/low plots, switchback when tall/wide."""
    resolved_storeys = resolve_storeys(storeys) if storeys <= 0 else max(1, int(storeys))
    wants_switchback = resolved_storeys >= 3 or (
        bays_x >= 4 and bays_y >= 3
    )
    if wants_switchback and footprint_allows_switchback(bays_x, bays_y):
        return "stair_switchback"
    stair_id = resolve_shared("stair", resolve_wealth(wealth), "main")
    if stair_id == "stair_switchback" and not footprint_allows_switchback(
        bays_x, bays_y
    ):
        return "stair_straight"
    if not wants_switchback:
        return "stair_straight"
    return stair_id


def _stair_kind(wealth: int, bays_x: int, bays_y: int, *, storeys: int = 1) -> str:
    stair_id = resolve_stair_id(wealth, bays_x, bays_y, storeys=storeys)
    return "switchback" if stair_id == "stair_switchback" else "straight"


def params_to_spec(params: FacadeParams) -> BuildingSpec:
    """Compile slider params → declarative BuildingSpec (bays/modules only)."""
    shell_cfg = load_archetype_shell_config(
        params.archetype,
        wealth=params.wealth,
        palette_family=params.palette_family,
    )
    wealth = resolve_wealth(params.wealth, archetype=shell_cfg.archetype)
    storeys = resolve_storeys(params.storeys)
    bays_x = metres_to_bays(params.frontage_m) or _DEFAULT_FRONTAGE_BAYS
    bays_y = metres_to_bays(params.depth_m) or _DEFAULT_DEPTH_BAYS
    windows_per_bay = _windows_per_bay(wealth)
    stair_kind = _stair_kind(wealth, bays_x, bays_y, storeys=storeys)

    # Party-wall faces are west/east in a south-facing row; entrances stay on south.
    blind = party_wall_faces(params.row_context)
    entrances = [EntranceSpec(role="main", facade="south")]
    if "north" not in blind and params.row_context == "freestanding":
        entrances.append(EntranceSpec(role="service", facade="north"))

    building_class = "house" if storeys <= 3 and max(bays_x, bays_y) <= 6 else "generic"
    roof_kind = shell_cfg.roof_kind if wealth >= 2 else "flat"

    return BuildingSpec(
        name=f"{params.archetype}_{params.seed}",
        style=shell_cfg.archetype,
        footprint=FootprintSpec(kind="rect", bays_x=bays_x, bays_y=bays_y),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        roof=RoofSpec(kind=roof_kind, pitch=shell_cfg.roof_pitch),
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
    shell_cfg = load_archetype_shell_config(
        params.archetype,
        wealth=params.wealth,
        palette_family=params.palette_family,
    )
    wealth = resolve_wealth(params.wealth, archetype=shell_cfg.archetype)
    wear = resolve_weathering(params.weathering, wealth=wealth)
    window_tag = resolve_shared("window", wealth, "exterior")
    door_tag = resolve_shared("door", wealth, "main")

    from pae.style_pack import load_style_pack

    pack, _ = load_style_pack(shell_cfg.archetype)
    pack_shell = asdict(pack.shell) if pack.shell else {}

    shell: Dict[str, Any] = {
        "stoop": bool(pack_shell.get("stoop", True)),
        "doorcase": "plain" if wealth < 3 else str(pack_shell.get("doorcase", "grand")),
        "chimney_stub": wealth >= 3 and bool(pack_shell.get("chimney_stub", True)),
        "window_sills": bool(pack_shell.get("window_sills", True)),
        "pilasters": wealth >= 5 or (wealth >= 3 and bool(pack_shell.get("pilasters", False))),
        "forecourt": False,
        "balcony": False,
        "patio": False,
        "jetty": False,
        "cornice_band": wealth >= 3,
        "doorcase_surround": wealth >= 3,
        "corner_pilasters": wealth >= 5,
        "shop_window_wide": wealth >= 3,
    }

    return {
        "archetype": shell_cfg.archetype,
        "shell_style": asdict(shell_cfg),
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
    mode: str = "shell",
    validate_assembly: bool = True,
    apply_style_shell: bool = True,
    apply_detail: bool = True,
    **kwargs: Any,
) -> Tuple[Any, Any, Any, Report, FacadeParams]:
    """Build facade assembly from slider params.

    ``mode="shell"`` (default) delegates to
    :func:`pae.building_builder.build_building` — the public Procedural
    Building entry. ``mode="modular"`` is **legacy debug only** (per-cell
    ``assemble.py`` wall farm); not for demos or user-facing builds.

    Returns ``(massing, floor_plan, assembly, report, params)``.
    """
    if mode == "modular":
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

    from pae.building_builder import build_building

    return build_building(
        params,
        validate_assembly=validate_assembly,
        **kwargs,
    )


__all__ = [
    "FacadeParams",
    "SHELL_ARCHETYPES",
    "ShellStyleConfig",
    "build_from_params",
    "export_params_json",
    "facade_rng",
    "footprint_allows_switchback",
    "load_archetype_shell_config",
    "metres_to_bays",
    "params_from_json",
    "params_to_spec",
    "params_to_style_overrides",
    "party_wall_faces",
    "resolve_stair_id",
    "resolve_storeys",
    "resolve_weathering",
    "resolve_wealth",
]

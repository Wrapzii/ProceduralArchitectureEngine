"""Canonical piece and material IDs shared by exterior facade grammar and interior fitout.

Exterior cream-render walls map to interior plaster; stair and door IDs are reused on
both faces so modular stairs/doors stay consistent through the shell.
"""

from __future__ import annotations

from typing import Dict, Final, Tuple

# --- Canonical string IDs ---------------------------------------------------

STAIRS: Final[Tuple[str, ...]] = (
    "stair_switchback",
    "stair_straight",
    "stair_landing",
)

DOORS: Final[Tuple[str, ...]] = (
    "door_georgian",
    "door_plain",
    "door_service",
)

WINDOWS: Final[Tuple[str, ...]] = (
    "window_sash_6over6",
    "window_sash_ground",
    "window_cross",
)

TRIM: Final[Tuple[str, ...]] = (
    "trim_cornice",
    "trim_plinth",
    "trim_string",
    "trim_pilaster",
)

MATERIALS: Final[Tuple[str, ...]] = (
    "mat_cream_render",
    "mat_slate",
    "mat_timber_oak",
    "mat_plaster_interior",
    "mat_floor_board",
)

_ALL_KINDS: Final[frozenset[str]] = frozenset(
    {"stair", "door", "window", "trim", "material"}
)

# Wealth tier tables — index 0 unused; tiers 1..5 escalate richness.
_STAIR_BY_WEALTH: Dict[int, str] = {
    1: "stair_straight",
    2: "stair_straight",
    3: "stair_switchback",
    4: "stair_switchback",
    5: "stair_switchback",
}

_DOOR_BY_WEALTH: Dict[str, Dict[int, str]] = {
    "main": {
        1: "door_plain",
        2: "door_plain",
        3: "door_georgian",
        4: "door_georgian",
        5: "door_georgian",
    },
    "exterior": {
        1: "door_plain",
        2: "door_plain",
        3: "door_georgian",
        4: "door_georgian",
        5: "door_georgian",
    },
    "interior": {
        1: "door_plain",
        2: "door_plain",
        3: "door_plain",
        4: "door_georgian",
        5: "door_georgian",
    },
    "service": {
        1: "door_service",
        2: "door_service",
        3: "door_service",
        4: "door_plain",
        5: "door_georgian",
    },
}

_WINDOW_BY_WEALTH: Dict[str, Dict[int, str]] = {
    "upper": {
        1: "window_cross",
        2: "window_cross",
        3: "window_sash_6over6",
        4: "window_sash_6over6",
        5: "window_sash_6over6",
    },
    "ground": {
        1: "window_cross",
        2: "window_sash_ground",
        3: "window_sash_ground",
        4: "window_sash_6over6",
        5: "window_sash_6over6",
    },
    "exterior": {
        1: "window_cross",
        2: "window_sash_ground",
        3: "window_sash_6over6",
        4: "window_sash_6over6",
        5: "window_sash_6over6",
    },
}

_TRIM_BY_WEALTH: Dict[str, Dict[int, str]] = {
    "cornice": {1: "trim_plinth", 2: "trim_string", 3: "trim_cornice", 4: "trim_cornice", 5: "trim_cornice"},
    "plinth": {1: "trim_plinth", 2: "trim_plinth", 3: "trim_plinth", 4: "trim_plinth", 5: "trim_plinth"},
    "string": {1: "trim_plinth", 2: "trim_string", 3: "trim_string", 4: "trim_string", 5: "trim_string"},
    "pilaster": {1: "trim_plinth", 2: "trim_string", 3: "trim_pilaster", 4: "trim_pilaster", 5: "trim_pilaster"},
    "default": {1: "trim_plinth", 2: "trim_string", 3: "trim_cornice", 4: "trim_cornice", 5: "trim_pilaster"},
}

_MATERIAL_BY_WEALTH: Dict[str, Dict[int, str]] = {
    "exterior_wall": {
        1: "mat_cream_render",
        2: "mat_cream_render",
        3: "mat_cream_render",
        4: "mat_cream_render",
        5: "mat_cream_render",
    },
    "interior_wall": {
        1: "mat_plaster_interior",
        2: "mat_plaster_interior",
        3: "mat_plaster_interior",
        4: "mat_plaster_interior",
        5: "mat_plaster_interior",
    },
    "roof": {1: "mat_slate", 2: "mat_slate", 3: "mat_slate", 4: "mat_slate", 5: "mat_slate"},
    "trim": {
        1: "mat_timber_oak",
        2: "mat_timber_oak",
        3: "mat_timber_oak",
        4: "mat_timber_oak",
        5: "mat_timber_oak",
    },
    "floor": {
        1: "mat_floor_board",
        2: "mat_floor_board",
        3: "mat_floor_board",
        4: "mat_floor_board",
        5: "mat_floor_board",
    },
}

# Exterior wall cream → interior plaster (and other paired lookups).
_EXTERIOR_TO_INTERIOR_MATERIAL: Dict[str, str] = {
    "mat_cream_render": "mat_plaster_interior",
    "mat_timber_oak": "mat_floor_board",
}


def _clamp_wealth(wealth: int) -> int:
    """Normalize wealth — ``-1`` auto-selects tier 2."""
    if wealth < 0:
        return 2
    return max(1, min(5, int(wealth)))


def _pick(table: Dict[int, str], wealth: int) -> str:
    tier = _clamp_wealth(wealth)
    if tier in table:
        return table[tier]
    # Fall back to highest defined tier at or below requested wealth.
    for t in range(tier, 0, -1):
        if t in table:
            return table[t]
    return next(iter(table.values()))


def resolve_shared(kind: str, wealth: int, role: str) -> str:
    """Pick a canonical shared ID for *kind* at *wealth* tier (``-1`` → 2).

    *role* disambiguates doors/windows/trim (e.g. ``main``, ``ground``, ``pilaster``).
    """
    key = (kind or "").strip().lower()
    role_key = (role or "default").strip().lower()
    if key not in _ALL_KINDS:
        raise ValueError(f"unknown shared kind {kind!r} — expected one of {sorted(_ALL_KINDS)}")

    if key == "stair":
        return _pick(_STAIR_BY_WEALTH, wealth)
    if key == "door":
        table = _DOOR_BY_WEALTH.get(role_key) or _DOOR_BY_WEALTH["main"]
        return _pick(table, wealth)
    if key == "window":
        table = _WINDOW_BY_WEALTH.get(role_key) or _WINDOW_BY_WEALTH["exterior"]
        return _pick(table, wealth)
    if key == "trim":
        table = _TRIM_BY_WEALTH.get(role_key) or _TRIM_BY_WEALTH["default"]
        return _pick(table, wealth)
    if key == "material":
        if role_key == "interior_wall":
            exterior = resolve_shared("material", wealth, "exterior_wall")
            return interior_material_for_exterior(exterior)
        table = _MATERIAL_BY_WEALTH.get(role_key) or _MATERIAL_BY_WEALTH["exterior_wall"]
        return _pick(table, wealth)
    raise ValueError(f"unhandled shared kind {kind!r}")


def interior_material_for_exterior(exterior_material_id: str) -> str:
    """Map an exterior wall material ID to its interior counterpart."""
    return _EXTERIOR_TO_INTERIOR_MATERIAL.get(exterior_material_id, "mat_plaster_interior")


__all__ = [
    "DOORS",
    "MATERIALS",
    "STAIRS",
    "TRIM",
    "WINDOWS",
    "interior_material_for_exterior",
    "resolve_shared",
]

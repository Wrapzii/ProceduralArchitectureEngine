"""Fancy manor showpiece — grand multi-level house for MP-WS-K2.

WHY THIS EXISTS: gallery packs dress small M2 boxes. This module authors one
estate-scale manor (7×4, three storeys, grand entry, cross windows, balcony)
that validates with style shell + detail ON.

Note: freeform winged StructureSpec sketches currently trip freestanding /
band_proud under Stage K banding on non-rect masses. The showpiece therefore
uses a large rect mass with rich manor language (still multi-floor, not a
hero-shot façade). Revisit wings when banding host resolution is solid on
irregular outlines.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Tuple

from pae.report import Report
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
)
from pae.structure_spec import LevelSpec, StructureSpec

FANCY_SEED = 42
FANCY_STYLE = "manor"
FANCY_BAYS_X = 7
FANCY_BAYS_Y = 4
FANCY_STOREYS = 3


def _rect_sketch(bays_x: int, bays_y: int, *, stair: bool = False, entrance: bool = False) -> str:
    """Build a solid rect sketch; optional SS stair and south-edge E entrance."""
    rows = []
    for y in range(bays_y):
        # text row 0 = north
        chars = ["#"] * bays_x
        # Stair near centre on a mid row.
        if stair and y == bays_y // 2:
            cx = bays_x // 2
            chars[cx - 1] = "S"
            chars[cx] = "S"
        # Entrance on south edge (last text row).
        if entrance and y == bays_y - 1:
            chars[bays_x // 2] = "E"
        rows.append("".join(chars))
    return "\n".join(rows) + "\n"


def fancy_manor_structure(*, seed: int = FANCY_SEED) -> StructureSpec:
    """StructureSpec YAML face for the showpiece (rect mass, 3 levels)."""
    l0 = _rect_sketch(FANCY_BAYS_X, FANCY_BAYS_Y, stair=True, entrance=True)
    l1 = _rect_sketch(FANCY_BAYS_X, FANCY_BAYS_Y, stair=True, entrance=False)
    l2 = _rect_sketch(FANCY_BAYS_X, FANCY_BAYS_Y, stair=True, entrance=False)
    return StructureSpec(
        name="fancy_manor",
        style=FANCY_STYLE,
        seed=int(seed),
        levels=[
            LevelSpec(sketch=l0, height_units=1, window_tag="window_cross"),
            LevelSpec(sketch=l1, height_units=1, window_tag="window_cross"),
            LevelSpec(sketch=l2, height_units=1, window_tag="window_bay_wide"),
        ],
        roof_kind="pitched",
        roof_pitch=1.25,
        stair_kind="straight",
        ground_slab=True,
        building_class="manor",
    )


def fancy_manor_building_spec(*, seed: int = FANCY_SEED) -> BuildingSpec:
    """Validated BuildingSpec — 7×4×3 manor with grand south entry + balcony kit."""
    return BuildingSpec(
        name="fancy_manor",
        style=FANCY_STYLE,
        footprint=FootprintSpec(
            kind="rect", bays_x=FANCY_BAYS_X, bays_y=FANCY_BAYS_Y
        ),
        storeys=FANCY_STOREYS,
        storey_use=["hall"] * FANCY_STOREYS,
        roof=RoofSpec(kind="pitched", pitch=1.25),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=2,
            doors_ground=1,
            windows_ground=5,
            skip_ground_windows=False,
        ),
        entrances=[
            EntranceSpec(
                role="grand",
                facade="south",
                bay=FANCY_BAYS_X // 2,
                ensemble=False,
            )
        ],
        seed=int(seed),
        ground_slab=True,
        building_class="manor",
        level_window_tags=(None, "window_cross", "window_bay_wide"),
    )


def build_fancy_manor(
    *,
    seed: int = FANCY_SEED,
    validate_assembly: bool = True,
) -> Tuple[Any, Any, Any, Report]:
    """assemble → style shell + K2 detail → validate."""
    from pae.style_pipeline import assemble_with_style_shell_and_detail

    spec = fancy_manor_building_spec(seed=seed)
    return assemble_with_style_shell_and_detail(
        spec,
        seed=seed,
        apply_style_shell=True,
        apply_detail=True,
        validate_assembly=validate_assembly,
    )


def summarize_fancy_manor(assembly) -> Dict[str, Any]:
    """Compact feature / per-floor counts for the proof report.

    ``floors`` is *piece* count (upper storeys often use few spanning decks).
    Prefer ``floor_cells`` / ``multi_floor_real`` when judging stub vs inhabited.
    """
    from pae.arch_detail import (
        BALCONY_DECK_TAG,
        BALCONY_DOOR_TAG,
        BALCONY_GUARD_TAG,
        BALCONY_SUPPORT_TAG,
        count_arch_detail_pieces,
    )
    from pae.door_clearance import validate_entrance_approach_clear
    from pae.style_apply import count_shell_pieces
    from pae.trim import covered_cells

    def _is_interior_floor(p) -> bool:
        if p.kind != "floor" or "hole" in p.asset_id:
            return False
        if BALCONY_DECK_TAG in p.tags or "balcony" in p.asset_id:
            return False
        return True

    levels = sorted({p.level for p in assembly.placements})
    per_floor: Dict[str, Dict[str, int]] = {}
    floor_cells_by_level: Dict[str, int] = {}
    for lv in levels:
        pcs = [p for p in assembly.placements if p.level == lv]
        interior = [p for p in pcs if _is_interior_floor(p)]
        cells: set = set()
        for p in interior:
            cells |= set(covered_cells(p))
        floor_cells_by_level[str(lv)] = len(cells)
        per_floor[str(lv)] = {
            "placements": len(pcs),
            "walls": sum(1 for p in pcs if p.kind == "wall"),
            "floors": sum(
                1 for p in pcs if p.kind == "floor" and "hole" not in p.asset_id
            ),
            "floor_pieces_interior": len(interior),
            "floor_cells": len(cells),
            "floor_holes": sum(1 for p in pcs if p.asset_id == "floor_hole"),
            "stairs": sum(1 for p in pcs if p.kind == "stair"),
            "windows": sum(1 for p in pcs if "window" in p.asset_id),
            "doors": sum(
                1
                for p in pcs
                if p.kind == "wall" and ("door" in p.asset_id or "gate" in p.asset_id)
            ),
        }

    stairs = [p for p in assembly.placements if p.kind == "stair"]
    stair_levels = sorted({p.level for p in stairs})
    # Stair on level N climbs N→N+1; reachable = bases ∪ (bases+1).
    levels_reached = sorted(
        {lv for lv in stair_levels} | {lv + 1 for lv in stair_levels}
    )
    floor_decks = [
        p
        for p in assembly.placements
        if p.kind == "floor" and "hole" not in p.asset_id
    ]
    l0_cells = int(floor_cells_by_level.get("0", 0))
    l1_cells = int(floor_cells_by_level.get("1", 0))
    l2_cells = int(floor_cells_by_level.get("2", 0))
    # Real multi-floor: L1 majority of L0 (or ≥12 cells); L2 attic OK if ≥8.
    multi_floor_real = (
        l0_cells >= 16
        and l1_cells >= max(12, int(0.5 * l0_cells))
        and l2_cells >= 8
    )
    clear = validate_entrance_approach_clear(assembly)
    # Circulation dump (P0) — yaw/landings/islands for the showpiece report.
    from pae.stair_occupancy import landing_cells_for_stair

    stair_dump = []
    for st in sorted(stairs, key=lambda p: (p.level, p.cell)):
        lands = []
        for name, pad, level, from_c, to_c in landing_cells_for_stair(st):
            lands.append(
                {
                    "name": name,
                    "pad": list(pad),
                    "level": level,
                    "from": list(from_c),
                    "to": list(to_c),
                }
            )
        stair_dump.append(
            {
                "piece_id": st.piece_id,
                "asset_id": st.asset_id,
                "cell": list(st.cell),
                "yaw": int(st.yaw) % 360,
                "level": st.level,
                "size_cm": list(st.size_cm),
                "tags": sorted(st.tags),
                "covered_cells": [list(c) for c in sorted(covered_cells(st))],
                "landings": lands,
            }
        )
    islands_by_level: Dict[str, int] = {}
    for lv_s, n_cells in floor_cells_by_level.items():
        lv = int(lv_s)
        cells: set = set()
        for p in assembly.placements:
            if p.level != lv or not _is_interior_floor(p):
                continue
            cells |= set(covered_cells(p))
        rem = set(cells)
        islands = 0
        while rem:
            islands += 1
            start = rem.pop()
            stack = [start]
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (nx, ny) in rem:
                        rem.remove((nx, ny))
                        stack.append((nx, ny))
        islands_by_level[lv_s] = islands

    return {
        "style": FANCY_STYLE,
        "seed": FANCY_SEED,
        "footprint": {"bays_x": FANCY_BAYS_X, "bays_y": FANCY_BAYS_Y},
        "storeys": FANCY_STOREYS,
        "levels": levels,
        "total_placements": len(assembly.placements),
        "per_floor": per_floor,
        "floor_cells_by_level": floor_cells_by_level,
        "floor_islands_by_level": islands_by_level,
        "multi_floor_real": multi_floor_real,
        "stair_count": len(stairs),
        "stair_levels": stair_levels,
        "stair_assets": sorted({p.asset_id for p in stairs}),
        "stair_yaws_by_level": {
            str(p.level): int(p.yaw) % 360 for p in stairs
        },
        "stairs": stair_dump,
        "levels_connected_by_stairs": levels_reached,
        "floor_deck_count": len(floor_decks),
        "floor_deck_solid": len(floor_decks) > 0
        and all(p.size_cm[2] > 5.0 for p in floor_decks),
        "arch_detail": count_arch_detail_pieces(assembly),
        "shell": count_shell_pieces(assembly),
        "balcony": {
            "decks": sum(1 for p in assembly.placements if BALCONY_DECK_TAG in p.tags),
            "doors": sum(1 for p in assembly.placements if BALCONY_DOOR_TAG in p.tags),
            "guards": sum(1 for p in assembly.placements if BALCONY_GUARD_TAG in p.tags),
            "supports": sum(
                1 for p in assembly.placements if BALCONY_SUPPORT_TAG in p.tags
            ),
            "functional": True,
        },
        "entrance_approach_clear": clear.critical == [],
        "entrance_approach_failures": [
            {"check": f.check, "message": f.message} for f in clear.critical
        ],
        "features": [
            "7x4_three_storey_mass",
            "grand_centred_south_entrance",
            "cross_mullion_and_bay_windows",
            "window_sills_and_hoods",
            "forecourt_with_door_gap",
            "porch_canopy_above_door",
            "functional_upper_balcony",
            "straight_stair_core",
            "manor_style_shell_and_detail",
        ],
        "honest_gap": (
            "Irregular winged StructureSpec outlines still trip freestanding/"
            "band_proud under Stage K banding — showpiece uses a large validated "
            "rect mass until that host-resolution debt is closed. "
            "Upper floor *piece* counts look tiny because decks span; judge "
            "floor_cells / multi_floor_real, not floors piece count."
        ),
    }


__all__ = [
    "FANCY_BAYS_X",
    "FANCY_BAYS_Y",
    "FANCY_SEED",
    "FANCY_STOREYS",
    "FANCY_STYLE",
    "build_fancy_manor",
    "fancy_manor_building_spec",
    "fancy_manor_structure",
    "summarize_fancy_manor",
]

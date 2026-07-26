"""Continuous facade shell — solid exterior panels with grammar-cut openings.

Builds a CITY&BEYOND-style box shell from :class:`pae.facade_grammar.FacadeParams`
without per-cell modular exterior wall kits. Interior partition grids are never
emitted as outer skin; only a stair well and optional inset corridor wall live
inside the footprint.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    rotation_offset_cm,
)
from pae.facade_grammar import (
    FacadeParams,
    params_to_spec,
    params_to_style_overrides,
    party_wall_faces,
    resolve_wealth,
)
from pae.primitives.roofs import (
    DEFAULT_ROOF_PITCH,
    roof_eave_offset_cm,
    roof_eave_overhang_per_side,
    roof_flat_span_size_cm,
    roof_gable_end_offset_cm,
    roof_gable_end_size_cm,
    roof_rise_cm,
)
from pae.report import Report
from pae.shared_ids import resolve_shared
from pae.spec import BuildingSpec

# Shell mesh ids — Blender builds axis-aligned boxes from placement ``size_cm``.
SHELL_WALL_ASSET = "shell_wall_solid"
SHELL_FLOOR_ASSET = "shell_floor_slab"
SHELL_ROOF_ASSET = "shell_roof_slope"
SHELL_INTERIOR_WALL_ASSET = "shell_wall_interior"

_SHELL_TAG = frozenset({"facade_shell"})
_EXTERIOR_TAG = frozenset({"facade_shell", "exterior"})
_INTERIOR_TAG = frozenset({"facade_shell", "interior"})

_FACE_YAW = {"west": 0, "east": 180, "south": 270, "north": 90}

# Style tag → kit asset (matches georgian_merchant substitutions).
_TAG_TO_ASSET = {
    "window_sash_6over6": "wall_window_mullioned",
    "window_sash_ground": "wall_window",
    "window_cross": "wall_window_cross",
    "door_georgian": "wall_door_double",
    "door_plain": "wall_door",
    "door_service": "wall_door_plain",
}


def is_shell_placement(p: SolidPlacement) -> bool:
    """True when Blender should mesh this placement as a sized shell box."""
    aid = getattr(p, "asset_id", "") or ""
    if aid.startswith("shell_"):
        return True
    return "facade_shell" in getattr(p, "tags", frozenset())


def _next_id(counters: Dict[str, int], prefix: str) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    n = counters[prefix]
    return prefix if n == 1 else f"{prefix}_{n}"


def _wall_offset_cm(face: str, yaw: int, size_cm: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """East/north tuck thickness inward (matches assemble ``_boundary_wall_offset_cm``)."""
    sx, sy, _ = size_cm
    ox, oy = rotation_offset_cm(yaw, sx, sy, rotates_about_center=False)
    face = face.lower()
    if face == "east":
        ox -= WALL_T_CM
    elif face == "north":
        oy -= WALL_T_CM
    return (ox, oy, 0.0)


def _footprint_cm(bays_x: int, bays_y: int) -> Tuple[float, float]:
    return bays_x * MODULE_CM, bays_y * MODULE_CM


def _stair_anchor_and_cells(
    stair_id: str, bays_x: int, bays_y: int
) -> Tuple[Tuple[int, int], int, List[Tuple[int, int]]]:
    """Pick an interior stair anchor and occupied cells (inside footprint)."""
    if stair_id == "stair_switchback" and bays_x >= 4 and bays_y >= 3:
        ax, ay = max(1, bays_x - 3), 1
        cells = [(ax + i, ay + j) for i in range(2) for j in range(2)]
        return (ax, ay), 0, cells
    # stair_straight — 2×1 run along +X, tucked against north interior.
    ax = max(0, min(1, bays_x - 2))
    ay = max(1, bays_y - 2)
    cells = [(ax, ay), (ax + 1, ay)]
    return (ax, ay), 0, cells


def _opening_asset(style_overrides: dict, *, kind: str, level: int) -> str:
    if kind == "door":
        tag = style_overrides.get("door", {}).get("tag", "door_plain")
        return _TAG_TO_ASSET.get(tag, "wall_door")
    win = style_overrides.get("window", {})
    tag = win.get("tag", "window_cross")
    if level == 0:
        ground_tag = resolve_shared("window", resolve_wealth(0), "ground")
        tag = win.get("ground_tag", ground_tag) if "ground_tag" in win else tag
    return _TAG_TO_ASSET.get(tag, "wall_window")


def _place_continuous_wall(
    *,
    face: str,
    level: int,
    run_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    bays_x: int,
    bays_y: int,
    blind: bool,
) -> None:
    yaw = _FACE_YAW[face]
    size_cm = (WALL_T_CM, run_cm, STOREY_CM)
    if face == "west":
        cell = (0, 0)
    elif face == "east":
        cell = (bays_x, 0)
    elif face == "south":
        cell = (0, 0)
    else:
        cell = (0, bays_y)
    offset = _wall_offset_cm(face, yaw, size_cm)
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}"})
    if blind:
        tags = tags | frozenset({"party_wall", "blind"})
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_wall_{face}_L{level}"),
            asset_id=SHELL_WALL_ASSET,
            kind="wall",
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=size_cm,
            tags=tags,
        )
    )


def _place_floor_slab(
    *,
    level: int,
    width_cm: float,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_L{level}"),
            asset_id=SHELL_FLOOR_ASSET,
            kind="floor",
            cell=(0, 0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(width_cm, depth_cm, FLOOR_T_CM),
            tags=_SHELL_TAG | frozenset({"spanning_floor"}),
        )
    )


def _place_stair_hole(
    *,
    level: int,
    hole_cells: Sequence[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    if not hole_cells:
        return
    xs = [c[0] for c in hole_cells]
    ys = [c[1] for c in hole_cells]
    hx, hy = min(xs), min(ys)
    hw = max(xs) - hx + 1
    hh = max(ys) - hy + 1
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_hole_L{level}"),
            asset_id="floor_hole",
            kind="hole",
            cell=(hx, hy),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(hw * MODULE_CM, hh * MODULE_CM, FLOOR_T_CM),
            tags=_SHELL_TAG,
        )
    )


def _place_spanning_floor_deck(
    *,
    level: int,
    width_cm: float,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Upper-storey deck using catalog ``floor`` id so Blender punches holes."""
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_floor_deck_L{level}"),
            asset_id="floor",
            kind="floor",
            cell=(0, 0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(width_cm, depth_cm, FLOOR_T_CM),
            tags=_SHELL_TAG | frozenset({"spanning_floor"}),
        )
    )


def _place_opening_on_face(
    *,
    face: str,
    bay: int,
    level: int,
    asset_id: str,
    kind: str,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    bays_x: int,
    bays_y: int,
) -> None:
    yaw = _FACE_YAW[face]
    size_cm = (WALL_T_CM, MODULE_CM, STOREY_CM)
    if face == "west":
        cell = (0, bay)
    elif face == "east":
        cell = (bays_x, bay)
    elif face == "south":
        cell = (bay, 0)
    else:
        cell = (bay, bays_y)
    offset = _wall_offset_cm(face, yaw, size_cm)
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}", kind})
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_{kind}_{face}_L{level}_B{bay}"),
            asset_id=asset_id,
            kind="wall",
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=size_cm,
            tags=tags,
        )
    )


def _place_stair(
    *,
    stair_id: str,
    anchor: Tuple[int, int],
    yaw: int,
    level: int,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    from pae.primitives.catalog import catalog_by_id

    cat = catalog_by_id()
    desc = cat.get(stair_id)
    if desc is None:
        return
    sx, sy, sz = desc.size_cm
    ox, oy = rotation_offset_cm(yaw, sx, sy, rotates_about_center=desc.rotates_about_center)
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_stair_L{level}"),
            asset_id=stair_id,
            kind="stair",
            cell=anchor,
            level=level,
            yaw=yaw,
            offset_cm=(ox, oy, 0.0),
            size_cm=desc.size_cm,
            rotates_about_center=desc.rotates_about_center,
            tags=_INTERIOR_TAG | frozenset({"stair"}),
        )
    )


def _place_interior_corridor_wall(
    *,
    level: int,
    inset_cell_x: int,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Single partition inset from the west party line — fully inside the shell."""
    run_cm = depth_cm - 2.0 * WALL_T_CM
    if run_cm < MODULE_CM * 0.5:
        return
    size_cm = (WALL_T_CM, run_cm, STOREY_CM)
    yaw = 0
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, f"shell_corridor_L{level}"),
            asset_id=SHELL_INTERIOR_WALL_ASSET,
            kind="wall",
            cell=(inset_cell_x, 0),
            level=level,
            yaw=yaw,
            offset_cm=(WALL_T_CM, WALL_T_CM, 0.0),
            size_cm=size_cm,
            tags=_INTERIOR_TAG | frozenset({"partition", "face_west"}),
        )
    )


def _place_pitched_roof(
    *,
    level: int,
    bays_x: int,
    bays_y: int,
    pitch: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    rx0, ry0, rx1, ry1 = 0, 0, bays_x - 1, bays_y - 1
    roof_spans = [(rx0, ry0, rx1, ry1)]
    west, east, south, north = roof_eave_overhang_per_side(
        rx0, ry0, rx1, ry1, roof_spans
    )
    eave_ox, eave_oy, _ = roof_eave_offset_cm(overhang_west=west, overhang_south=south)
    modules_x = bays_x
    modules_y = bays_y
    ridge_along_x = modules_x >= modules_y
    span_x = modules_x * MODULE_CM
    span_y = modules_y * MODULE_CM
    ridge_modules = max(1, min(modules_x, modules_y))
    full_rise = roof_rise_cm(pitch, ridge_modules * MODULE_CM)
    gable_height = full_rise + FLOOR_T_CM
    deck_x = span_x + west + east
    deck_y = span_y + south + north
    roof_z = STOREY_CM

    if ridge_along_x:
        for x in (rx0, rx1):
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_roof_gable"),
                    asset_id="roof_gable_infill",
                    kind="roof",
                    cell=(x, ry0),
                    level=level,
                    yaw=0,
                    offset_cm=(
                        *roof_gable_end_offset_cm(
                            ridge_along_x=True, is_low_end=(x == rx0)
                        )[:2],
                        roof_z,
                    ),
                    size_cm=roof_gable_end_size_cm(
                        ridge_along_x=True,
                        span_x_cm=span_x,
                        span_y_cm=span_y,
                        gable_height=gable_height,
                    ),
                    tags=_SHELL_TAG,
                )
            )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope"),
                asset_id="roof_pitched_slope",
                kind="roof",
                cell=(rx0, ry0),
                level=level,
                yaw=0,
                offset_cm=(eave_ox, eave_oy, roof_z),
                size_cm=(deck_x, deck_y, gable_height),
                tags=_SHELL_TAG,
            )
        )
    else:
        for y in (ry0, ry1):
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_roof_gable"),
                    asset_id="roof_gable_infill",
                    kind="roof",
                    cell=(rx0, y),
                    level=level,
                    yaw=0,
                    offset_cm=(
                        *roof_gable_end_offset_cm(
                            ridge_along_x=False, is_low_end=(y == ry0)
                        )[:2],
                        roof_z,
                    ),
                    size_cm=roof_gable_end_size_cm(
                        ridge_along_x=False,
                        span_x_cm=span_x,
                        span_y_cm=span_y,
                        gable_height=gable_height,
                    ),
                    tags=_SHELL_TAG,
                )
            )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope"),
                asset_id="roof_pitched_slope",
                kind="roof",
                cell=(rx0, ry0),
                level=level,
                yaw=0,
                offset_cm=(eave_ox, eave_oy, roof_z),
                size_cm=(deck_x, deck_y, gable_height),
                tags=_SHELL_TAG,
            )
        )


def _street_faces(row_context: str, blind: FrozenSet[str]) -> Tuple[str, ...]:
    faces: List[str] = ["south"]
    if "north" not in blind and row_context == "freestanding":
        faces.append("north")
    return tuple(faces)


def build_shell_assembly(
    params: FacadeParams,
    spec: Optional[BuildingSpec] = None,
) -> Tuple[Assembly, Report]:
    """Build a continuous shell :class:`Assembly` from facade sliders."""
    spec = spec or params_to_spec(params)
    bays_x = spec.footprint.bays_x
    bays_y = spec.footprint.bays_y
    storeys = spec.storeys
    wealth = resolve_wealth(params.wealth)
    blind = party_wall_faces(params.row_context)
    style_overrides = params_to_style_overrides(params)
    windows_per_bay = style_overrides.get("window", {}).get("per_bay", 1)
    pitch = float(getattr(spec.roof, "pitch", DEFAULT_ROOF_PITCH) or DEFAULT_ROOF_PITCH)

    width_cm, depth_cm = _footprint_cm(bays_x, bays_y)
    stair_id = resolve_shared("stair", wealth, "main")
    anchor, stair_yaw, stair_cells = _stair_anchor_and_cells(stair_id, bays_x, bays_y)
    door_bay = max(0, min(bays_x - 1, bays_x // 2))
    street_faces = _street_faces(params.row_context, blind)

    placements: List[SolidPlacement] = []
    counters: Dict[str, int] = {}

    for level in range(storeys):
        if level == 0:
            _place_floor_slab(
                level=level,
                width_cm=width_cm,
                depth_cm=depth_cm,
                placements=placements,
                counters=counters,
            )
        else:
            _place_spanning_floor_deck(
                level=level,
                width_cm=width_cm,
                depth_cm=depth_cm,
                placements=placements,
                counters=counters,
            )
            _place_stair_hole(
                level=level,
                hole_cells=stair_cells,
                placements=placements,
                counters=counters,
            )

        for face in ("west", "east", "south", "north"):
            run_cm = depth_cm if face in ("west", "east") else width_cm
            _place_continuous_wall(
                face=face,
                level=level,
                run_cm=run_cm,
                placements=placements,
                counters=counters,
                bays_x=bays_x,
                bays_y=bays_y,
                blind=face in blind,
            )

        # Ground door on south street face.
        if level == 0:
            door_asset = _opening_asset(style_overrides, kind="door", level=0)
            _place_opening_on_face(
                face="south",
                bay=door_bay,
                level=level,
                asset_id=door_asset,
                kind="door",
                placements=placements,
                counters=counters,
                bays_x=bays_x,
                bays_y=bays_y,
            )

        # Windows on street faces only — never on party walls.
        win_asset = _opening_asset(style_overrides, kind="window", level=level)
        for face in street_faces:
            if face in blind:
                continue
            for bay in range(bays_x):
                for _w in range(max(1, int(windows_per_bay))):
                    _place_opening_on_face(
                        face=face,
                        bay=bay,
                        level=level,
                        asset_id=win_asset,
                        kind="window",
                        placements=placements,
                        counters=counters,
                        bays_x=bays_x,
                        bays_y=bays_y,
                    )

        # Interior corridor partition (inset from west unless west is street).
        inset_x = 1 if "west" not in blind else min(2, max(1, bays_x - 2))
        _place_interior_corridor_wall(
            level=level,
            inset_cell_x=inset_x,
            depth_cm=depth_cm,
            placements=placements,
            counters=counters,
        )

    # Stairs between storeys.
    for level in range(storeys - 1):
        _place_stair(
            stair_id=stair_id,
            anchor=anchor,
            yaw=stair_yaw,
            level=level,
            placements=placements,
            counters=counters,
        )

    _place_pitched_roof(
        level=storeys - 1,
        bays_x=bays_x,
        bays_y=bays_y,
        pitch=pitch,
        placements=placements,
        counters=counters,
    )

    assembly = Assembly(
        placements=placements,
        storeys=storeys,
        building_class=spec.building_class,
        stair_kind=stair_id.replace("stair_", ""),
    )
    return assembly, Report.from_failures([])


def count_exterior_shell_walls(assembly: Assembly) -> int:
    """Count continuous exterior shell wall panels (not per-bay kit walls)."""
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET and "exterior" in p.tags
    )


def count_window_placements(assembly: Assembly, face: str) -> int:
    return sum(
        1
        for p in assembly.placements
        if "window" in p.tags and f"face_{face}" in p.tags
    )


__all__ = [
    "SHELL_FLOOR_ASSET",
    "SHELL_INTERIOR_WALL_ASSET",
    "SHELL_ROOF_ASSET",
    "SHELL_WALL_ASSET",
    "build_shell_assembly",
    "count_exterior_shell_walls",
    "count_window_placements",
    "is_shell_placement",
]

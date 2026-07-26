"""Continuous facade shell — solid exterior panels with grammar-cut openings.

Builds a CITY&BEYOND-style box shell from :class:`pae.facade_grammar.FacadeParams`
without per-cell modular exterior wall kits. Interior partition grids and
balcony/patio/jetty dress are never emitted on this path.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    EAVE_OVERHANG_CM,
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    rotation_offset_cm,
)
from pae.primitives.roofs import DEFAULT_ROOF_PITCH, roof_rise_cm
from pae.facade_grammar import (
    FacadeParams,
    ShellStyleConfig,
    facade_rng,
    load_archetype_shell_config,
    params_to_spec,
    params_to_style_overrides,
    party_wall_faces,
    resolve_stair_plan,
    resolve_wealth,
)
from pae.report import Report
from pae.shared_ids import resolve_shared
from pae.spec import BuildingSpec

# Shell mesh ids — Blender builds axis-aligned boxes from placement ``size_cm``.
SHELL_WALL_ASSET = "shell_wall_solid"
SHELL_OPENING_CUTTER_ASSET = "shell_opening_cutter"
SHELL_FLOOR_ASSET = "shell_floor_slab"
SHELL_ROOF_ASSET = "shell_roof_slab"
SHELL_ROOF_SLOPE_ASSET = "shell_roof_slope"
SHELL_GABLE_ASSET = "shell_gable_end"
SHELL_ROOF_THICK_CM = FLOOR_T_CM
SHELL_ROOF_PITCH = DEFAULT_ROOF_PITCH
_GABLE_THICK_CM = WALL_T_CM
SHELL_INTERIOR_WALL_ASSET = "shell_wall_interior"

# Opening cutter padding — pierces both wall skins for boolean / panel punch.
_CUTTER_PAD_X_FRAC = 0.25
_CUTTER_PAD_YZ_CM = 0.5
SHELL_DOOR_ASSET = "shell_door"
SHELL_WINDOW_FRAME_ASSET = "shell_window_frame"
SHELL_WINDOW_GLASS_ASSET = "shell_window_glass"
SHELL_WINDOW_MUNTIN_ASSET = "shell_window_muntin"
SHELL_STAIR_RAIL_ASSET = "shell_stair_rail"
SHELL_CHIMNEY_ASSET = "shell_chimney_stub"
SHELL_TRIM_ASSET = "shell_trim_band"
SHELL_PILASTER_ASSET = "shell_pilaster_strip"
SHELL_DOORCASE_ASSET = "shell_doorcase_trim"

_SHELL_TAG = frozenset({"facade_shell"})
_EXTERIOR_TAG = frozenset({"facade_shell", "exterior"})
_INTERIOR_TAG = frozenset({"facade_shell", "interior"})

_FACE_YAW = {"west": 0, "east": 180, "south": 270, "north": 90}

# Georgian aperture fractions of a bay / storey (not full modular wall kits).
_WINDOW_W_FRAC = 0.55
_WINDOW_H_FRAC = 0.58
_WINDOW_SILL_FRAC = 0.22  # of STOREY — sill height above floor
_DOOR_W_FRAC = 0.42
_DOOR_H_FRAC = 0.78
_PLINTH_FRAC = 0.16
_CORNICE_FRAC = 0.10
_FRAME_T_FRAC = 0.08  # of WALL_T — door leaf depth in the opening
_FRAME_BAR_CM = 10.0  # jamb / sill / head stick thickness (~8–12 cm)
_GLASS_DEPTH_CM = 1.5  # thin glazing plane — must not fill the opening
_MUNTIN_T_FRAC = 0.045  # of WALL_T — thin Georgian cross bars
_SHAFT_WALL_HEIGHT_FRAC = 0.82  # shaft partitions — leave headroom into the well
_CHIMNEY_W_FRAC = 0.18  # of MODULE — roof stub footprint
_CHIMNEY_H_FRAC = 0.42  # of STOREY — short stack above ridge
_SHOP_WINDOW_SCALE = 1.22  # ground-floor shop window widen at wealth ≥ 3


@dataclass(frozen=True)
class ShellVariation:
    """Seed-driven shell grammar choices (S-010 determinism)."""

    door_bay: int
    window_skip: FrozenSet[Tuple[str, int, int]]  # (face, level, bay)
    chimney_count: int
    chimney_anchors: Tuple[Tuple[float, float], ...]  # roof-deck XY cm
    cornice_height_frac: float  # string course height as fraction of storey
    shop_window_scale: float  # 1.0 or wider for merchant ground floor


def _wealth_window_skip_rate(wealth: int, *, archetype: str = "") -> float:
    """Higher wealth → denser glazing rhythm."""
    tier = resolve_wealth(wealth, archetype=archetype or "georgian_merchant")
    return {1: 0.38, 2: 0.22, 3: 0.14, 4: 0.10, 5: 0.06}.get(tier, 0.14)


def _wealth_chimney_count(wealth: int, *, style_allows: bool, archetype: str = "") -> int:
    tier = resolve_wealth(wealth, archetype=archetype or "georgian_merchant")
    if not style_allows or tier < 3:
        return 0
    if tier >= 5:
        return 2
    return 1


def derive_shell_variation(
    params: FacadeParams,
    *,
    bays_x: int,
    bays_y: int,
    storeys: int,
    glazed_faces: Sequence[str],
    style_overrides: dict,
    shell_cfg: ShellStyleConfig,
) -> ShellVariation:
    """Deterministic facade variation from ``params.seed`` (S-010)."""
    rng = facade_rng(params.seed, params.archetype, "shell_variation")
    wealth = resolve_wealth(params.wealth, archetype=shell_cfg.archetype)

    if bays_x <= 1:
        door_bay = 0
    else:
        center = bays_x // 2
        spread = max(1, min(2, bays_x // 3))
        lo = max(0, center - spread)
        hi = min(bays_x - 1, center + spread)
        door_bay = rng.randint(lo, hi)

    skip_rate = _wealth_window_skip_rate(wealth, archetype=shell_cfg.archetype)
    window_skip: Set[Tuple[str, int, int]] = set()
    for face in glazed_faces:
        bay_count = bays_y if face in ("west", "east") else bays_x
        for level in range(storeys):
            if face == "south" and level == 0:
                continue
            for bay in range(bay_count):
                if bay == door_bay and face == "south" and level == 0:
                    continue
                if rng.random() < skip_rate:
                    window_skip.add((face, level, bay))

    chimney_allowed = bool(style_overrides.get("shell", {}).get("chimney_stub", False))
    chimney_count = _wealth_chimney_count(
        wealth, style_allows=chimney_allowed, archetype=shell_cfg.archetype
    )
    width_cm = bays_x * MODULE_CM
    depth_cm = bays_y * MODULE_CM
    anchors: List[Tuple[float, float]] = []
    for i in range(chimney_count):
        ax = rng.uniform(MODULE_CM * 0.8, width_cm - MODULE_CM * 1.2)
        ay = rng.uniform(MODULE_CM * 0.6, depth_cm - MODULE_CM * 1.0)
        if chimney_count == 2 and i == 1:
            ax = max(ax, width_cm * 0.55)
        anchors.append((ax, ay))

    cornice_lo = 0.06 if wealth < 3 else 0.08
    cornice_hi = 0.12 if wealth < 5 else 0.14
    cornice_height_frac = rng.uniform(cornice_lo, cornice_hi)

    shop_scale = (
        _SHOP_WINDOW_SCALE
        if wealth >= 3 and style_overrides.get("shell", {}).get("shop_window_wide")
        else 1.0
    )

    return ShellVariation(
        door_bay=door_bay,
        window_skip=frozenset(window_skip),
        chimney_count=chimney_count,
        chimney_anchors=tuple(anchors),
        cornice_height_frac=cornice_height_frac,
        shop_window_scale=shop_scale,
    )


def _effective_window_fracs(
    shell_cfg: ShellStyleConfig,
    wealth: int,
) -> Tuple[float, float, float]:
    """Archetype base fractions scaled by wealth tier."""
    tier = resolve_wealth(wealth, archetype=shell_cfg.archetype)
    w = shell_cfg.window_w_frac
    h = shell_cfg.window_h_frac
    sill = shell_cfg.window_sill_frac
    if tier <= 1:
        w *= 0.82
        h *= 0.88
    elif tier >= 5:
        w = min(0.72, w * 1.10)
        h = min(0.66, h * 1.06)
    elif tier >= 4:
        w = min(0.68, w * 1.05)
    return (w, h, sill)


def is_shell_placement(p: SolidPlacement) -> bool:
    """True when Blender should mesh this as a sized shell box / punched wall.

    Stairs, holes, and catalog floor decks must NEVER take this path — tagging
    them ``facade_shell`` used to produce a solid 8×8×3.5 m brown box that
    plugged the stairwell (no treads) and sealed the punched floor opening
    with its top face (looked like "no hole").
    """
    kind = getattr(p, "kind", None)
    aid = getattr(p, "asset_id", "") or ""
    if kind in {"stair", "hole"}:
        return False
    if aid.startswith("stair_") or aid in {"floor_hole", "floor"}:
        return False
    if aid.startswith("shell_"):
        return True
    return "facade_shell" in getattr(p, "tags", frozenset())


def is_facade_shell_assembly(assembly: Assembly) -> bool:
    """True when *assembly* was built by :func:`build_shell_assembly` (shell-only path)."""
    placements = getattr(assembly, "placements", None) or ()
    if not placements:
        return False
    return any(is_shell_placement(p) for p in placements)


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


def _inverse_rotate_local_xy(wx: float, wy: float, yaw: int) -> Tuple[float, float]:
    """Inverse of :func:`pae.contract.rotate_local_xy` (yaw about min-corner)."""
    if yaw == 0:
        return (wx, wy)
    if yaw == 90:
        return (wy, -wx)
    if yaw == 180:
        return (-wx, -wy)
    if yaw == 270:
        return (-wy, wx)
    raise ValueError(f"yaw must be 0/90/180/270, got {yaw}")


def _shell_world_offset_cm(
    face: str,
    yaw: int,
    panel_size_cm: Tuple[float, float, float],
    local_extra: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Map shell-local (thickness, along-face, up) → world ``offset_cm`` on a face panel."""
    from pae.contract import rotate_local_xy

    panel_base = _wall_offset_cm(face, yaw, panel_size_cm)
    wx, wy = rotate_local_xy(
        local_extra[0],
        local_extra[1],
        yaw,
        panel_size_cm[0],
        panel_size_cm[1],
    )
    return (
        panel_base[0] + wx,
        panel_base[1] + wy,
        panel_base[2] + local_extra[2],
    )


def _footprint_cm(bays_x: int, bays_y: int) -> Tuple[float, float]:
    return bays_x * MODULE_CM, bays_y * MODULE_CM


def _stair_anchor_and_cells(
    plan,
    bays_x: int,
    bays_y: int,
) -> Tuple[Tuple[int, int], int, List[Tuple[int, int]]]:
    """Place the stair well from a :class:`~pae.facade_grammar.StairPlan`."""
    well_w, well_d = plan.well_bays
    yaw = int(plan.yaw)

    if plan.scale_class == "house":
        # North bay with side neighbours when possible — top exits sideways.
        if bays_x >= 3:
            ax = min(max(1, bays_x - 2), bays_x - 1)
        else:
            ax = max(0, bays_x - 1)
        ay = max(0, bays_y - 1)
        return (ax, ay), yaw, [(ax, ay)]

    ax = max(0, bays_x - well_w)
    ay = max(0, bays_y - well_d)
    if bays_y > well_d:
        ay = bays_y - well_d
    # Corridor straight along +X: prefer a free bay west of the bottom.
    if plan.scale_class == "corridor" and well_w == 2 and bays_x >= 4:
        ax = min(ax, max(1, bays_x - well_w))
    cells = [
        (ax + i, ay + j) for i in range(well_w) for j in range(well_d)
    ]
    return (ax, ay), yaw, cells


def stairwell_blocked_bays(
    stair_cells: Sequence[Tuple[int, int]],
    *,
    bays_x: int,
    bays_y: int,
) -> Dict[str, FrozenSet[int]]:
    """Facade bay indices whose *interior* is the stair shaft.

    A normal living-room sash must not land on these bays — the well occupies
    that cell, so a full window would look into stairs / be blocked by flights.
    """
    blocked: Dict[str, set] = {
        "south": set(),
        "north": set(),
        "east": set(),
        "west": set(),
    }
    if bays_x < 1 or bays_y < 1:
        return {k: frozenset() for k in blocked}
    for cx, cy in stair_cells:
        if cy <= 0:
            blocked["south"].add(int(cx))
        if cy >= bays_y - 1:
            blocked["north"].add(int(cx))
        if cx <= 0:
            blocked["west"].add(int(cy))
        if cx >= bays_x - 1:
            blocked["east"].add(int(cy))
    return {face: frozenset(bays) for face, bays in blocked.items()}


def stair_well_exterior_faces(
    stair_cells: Sequence[Tuple[int, int]],
    *,
    bays_x: int,
    bays_y: int,
) -> FrozenSet[str]:
    """Shell faces where the stair well already sits on the exterior skin.

    Interior shaft partitions on those faces duplicate the facade and plug
    window openings from the inside.
    """
    faces: Set[str] = set()
    if bays_x < 1 or bays_y < 1:
        return frozenset()
    for cx, cy in stair_cells:
        if cy <= 0:
            faces.add("south")
        if cy >= bays_y - 1:
            faces.add("north")
        if cx <= 0:
            faces.add("west")
        if cx >= bays_x - 1:
            faces.add("east")
    return frozenset(faces)


def _door_bay_clear_of_stair(
    preferred: int,
    *,
    bays_x: int,
    stair_blocked_south: FrozenSet[int],
) -> int:
    """Keep the main door off stairwell bays on the south elevation."""
    candidates = list(range(bays_x))
    # Prefer centre-ish order starting from preferred.
    ordered = sorted(candidates, key=lambda b: (abs(b - preferred), b))
    for bay in ordered:
        if bay not in stair_blocked_south:
            return bay
    return max(0, min(bays_x - 1, preferred))


def _place_shell_box(
    *,
    piece_prefix: str,
    asset_id: str,
    face: str,
    level: int,
    cell: Tuple[int, int],
    size_cm: Tuple[float, float, float],
    offset_extra: Tuple[float, float, float],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
    kind: str = "wall",
    panel_size_cm: Optional[Tuple[float, float, float]] = None,
) -> None:
    yaw = _FACE_YAW[face]
    panel = panel_size_cm or size_cm
    offset = _shell_world_offset_cm(face, yaw, panel, offset_extra)
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, piece_prefix),
            asset_id=asset_id,
            kind=kind,
            cell=cell,
            level=level,
            yaw=yaw,
            offset_cm=offset,
            size_cm=size_cm,
            tags=tags,
        )
    )


def _face_run_and_origin(
    face: str, bays_x: int, bays_y: int, width_cm: float, depth_cm: float
) -> Tuple[float, int, Tuple[int, int]]:
    """Return (run_cm, bay_count, origin_cell) for a facade face."""
    if face in ("west", "east"):
        return depth_cm, bays_y, ((0, 0) if face == "west" else (bays_x, 0))
    return width_cm, bays_x, ((0, 0) if face == "south" else (0, bays_y))


def _opening_spec(
    *,
    face: str,
    bay: int,
    level: int,
    door_bay: int,
    bay_count: int,
    variation: ShellVariation,
    shell_cfg: ShellStyleConfig,
    wealth: int,
    stair_blocked: FrozenSet[int] = frozenset(),
) -> Optional[Tuple[str, float, float, float]]:
    """Return (kind, width_cm, height_cm, sill_z_cm) or None if solid pier bay.

    Stairwell facade bays stay solid — no room sash into the shaft, and no
    small ``stair_light`` either (those read as the wrong window next to a
    full sash and still fight stair / shaft geometry).
    """
    if bay in stair_blocked:
        return None
    if (face, level, bay) in variation.window_skip:
        return None
    w_frac, h_frac, sill_frac = _effective_window_fracs(shell_cfg, wealth)
    if face == "south" and level == 0 and bay == door_bay:
        w = MODULE_CM * _DOOR_W_FRAC
        h = STOREY_CM * _DOOR_H_FRAC
        return ("door", w, h, 0.0)
    w = MODULE_CM * w_frac
    h = STOREY_CM * h_frac
    if (
        face == "south"
        and level == 0
        and variation.shop_window_scale > 1.0
        and bay != door_bay
    ):
        w = min(MODULE_CM * 0.88, w * variation.shop_window_scale)
    sill = STOREY_CM * sill_frac
    return ("window", w, h, sill)


def _face_offset_extra(
    offset_cm: Tuple[float, float, float],
    face: str,
    yaw: int,
    size_cm: Tuple[float, float, float],
    *,
    panel_size_cm: Optional[Tuple[float, float, float]] = None,
) -> Tuple[float, float, float]:
    """Shell-local offset (thickness, along-face, up) from a world ``offset_cm``."""
    panel = panel_size_cm or size_cm
    base = _wall_offset_cm(face, yaw, panel)
    dx = offset_cm[0] - base[0]
    dy = offset_cm[1] - base[1]
    dz = offset_cm[2] - base[2]
    lx, ly = _inverse_rotate_local_xy(dx, dy, yaw)
    return (lx, ly, dz)


def shell_cutter_hole_yz_cm(
    wall: SolidPlacement,
    cutter: SolidPlacement,
) -> Tuple[float, float, float, float]:
    """Opening rectangle ``(y0, y1, z0, z1)`` in wall-local mesh coordinates."""
    face = next(t[5:] for t in wall.tags if t.startswith("face_"))
    cut_extra = _face_offset_extra(
        cutter.offset_cm, face, cutter.yaw, cutter.size_cm, panel_size_cm=wall.size_cm
    )
    y0 = cut_extra[1]
    z0 = cut_extra[2]
    return (y0, y0 + cutter.size_cm[1], z0, z0 + cutter.size_cm[2])


def _place_opening_cutter(
    *,
    piece_prefix: str,
    face: str,
    level: int,
    cell: Tuple[int, int],
    open_y0: float,
    open_w: float,
    sill_z: float,
    open_h: float,
    kind: str,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
    panel_size_cm: Tuple[float, float, float],
) -> None:
    pad_x = WALL_T_CM * _CUTTER_PAD_X_FRAC
    pad_yz = _CUTTER_PAD_YZ_CM
    _place_shell_box(
        piece_prefix=piece_prefix,
        asset_id=SHELL_OPENING_CUTTER_ASSET,
        face=face,
        level=level,
        cell=cell,
        size_cm=(
            WALL_T_CM + 2.0 * pad_x,
            open_w + 2.0 * pad_yz,
            open_h + 2.0 * pad_yz,
        ),
        offset_extra=(-pad_x, open_y0 - pad_yz, sill_z - pad_yz),
        placements=placements,
        counters=counters,
        tags=tags
        | frozenset(
            {
                "opening_cutter",
                "non_rendering_aperture_proxy",
                kind,
            }
        ),
        kind="hole",
        panel_size_cm=panel_size_cm,
    )


def _place_hollow_window_frame(
    *,
    face: str,
    level: int,
    origin: Tuple[int, int],
    open_y0: float,
    open_w: float,
    open_h: float,
    sill_z: float,
    frame_bar: float,
    frame_depth: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
    panel_size_cm: Tuple[float, float, float],
) -> None:
    """Four thin sticks (jambs, sill, head) — opening centre stays empty."""
    bar = frame_bar
    depth = frame_depth
    base_x = (WALL_T_CM - depth) * 0.5
    frame_tags = tags | frozenset({"window", "opening", "frame_bar"})
    common = dict(
        face=face,
        level=level,
        cell=origin,
        placements=placements,
        counters=counters,
        tags=frame_tags,
        kind="prop",
        panel_size_cm=panel_size_cm,
        asset_id=SHELL_WINDOW_FRAME_ASSET,
    )
    _place_shell_box(
        piece_prefix=f"shell_frame_l_{face}_L{level}",
        size_cm=(depth, bar, open_h),
        offset_extra=(base_x, open_y0, sill_z),
        **common,
    )
    _place_shell_box(
        piece_prefix=f"shell_frame_r_{face}_L{level}",
        size_cm=(depth, bar, open_h),
        offset_extra=(base_x, open_y0 + open_w - bar, sill_z),
        **common,
    )
    _place_shell_box(
        piece_prefix=f"shell_frame_sill_{face}_L{level}",
        size_cm=(depth, open_w, bar),
        offset_extra=(base_x, open_y0, sill_z),
        **common,
    )
    _place_shell_box(
        piece_prefix=f"shell_frame_head_{face}_L{level}",
        size_cm=(depth, open_w, bar),
        offset_extra=(base_x, open_y0, sill_z + open_h - bar),
        **common,
    )


def _place_window_glass(
    *,
    face: str,
    level: int,
    origin: Tuple[int, int],
    open_y0: float,
    open_w: float,
    open_h: float,
    sill_z: float,
    frame_bar: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
    panel_size_cm: Tuple[float, float, float],
) -> None:
    """Thin semi-transparent glazing plane inset inside the frame rim."""
    inner_w = max(20.0, open_w - 2.0 * frame_bar)
    inner_h = max(20.0, open_h - 2.0 * frame_bar)
    glass_depth = _GLASS_DEPTH_CM
    _place_shell_box(
        piece_prefix=f"shell_glass_{face}_L{level}",
        asset_id=SHELL_WINDOW_GLASS_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(glass_depth, inner_w, inner_h),
        offset_extra=(
            (WALL_T_CM - glass_depth) * 0.5,
            open_y0 + frame_bar,
            sill_z + frame_bar,
        ),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"window", "opening", "glass"}),
        kind="window",
        panel_size_cm=panel_size_cm,
    )


def _place_window_muntins(
    *,
    face: str,
    level: int,
    origin: Tuple[int, int],
    open_center: float,
    open_y0: float,
    open_w: float,
    open_h: float,
    sill_z: float,
    frame_t: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    tags: FrozenSet[str],
) -> None:
    """Cheap Georgian cross — one vertical + one horizontal bar in the sash."""
    muntin_t = max(2.5, WALL_T_CM * _MUNTIN_T_FRAC)
    inset_w = open_w * 0.88
    inset_h = open_h * 0.88
    depth = max(2.5, frame_t * 0.55)
    base_x = (WALL_T_CM - depth) * 0.5
    y_inset = open_y0 + open_w * 0.06
    z_inset = sill_z + open_h * 0.06
    _place_shell_box(
        piece_prefix=f"shell_muntin_v_{face}_L{level}",
        asset_id=SHELL_WINDOW_MUNTIN_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(depth, muntin_t, inset_h),
        offset_extra=(base_x, open_center - muntin_t * 0.5, z_inset),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"muntin", "window"}),
        kind="prop",
    )
    _place_shell_box(
        piece_prefix=f"shell_muntin_h_{face}_L{level}",
        asset_id=SHELL_WINDOW_MUNTIN_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=(depth, inset_w, muntin_t),
        offset_extra=(base_x, y_inset, sill_z + open_h * 0.5 - muntin_t * 0.5),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"muntin", "window"}),
        kind="prop",
    )


def _place_glazed_face(
    *,
    face: str,
    level: int,
    bays_x: int,
    bays_y: int,
    width_cm: float,
    depth_cm: float,
    door_bay: int,
    variation: ShellVariation,
    shell_cfg: ShellStyleConfig,
    wealth: int,
    style_overrides: dict,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    stair_blocked: FrozenSet[int] = frozenset(),
) -> None:
    """One solid shell wall per face/storey; cutters punch openings in Blender."""
    run_cm, bay_count, origin = _face_run_and_origin(
        face, bays_x, bays_y, width_cm, depth_cm
    )
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}"})
    frame_t = max(4.0, WALL_T_CM * _FRAME_T_FRAC)
    panel_size_cm = (WALL_T_CM, run_cm, STOREY_CM)

    _place_shell_box(
        piece_prefix=f"shell_wall_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=origin,
        size_cm=panel_size_cm,
        offset_extra=(0.0, 0.0, 0.0),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"boolean_parent", "shell_wall_panel"}),
        panel_size_cm=panel_size_cm,
    )

    shell_flags = style_overrides.get("shell", {})
    if shell_flags.get("cornice_band") and level == 0:
        band_h = max(8.0, STOREY_CM * variation.cornice_height_frac)
        band_z = STOREY_CM - band_h
        trim_depth = max(3.0, WALL_T_CM * 0.35)
        _place_shell_box(
            piece_prefix=f"shell_cornice_{face}_L{level}",
            asset_id=SHELL_TRIM_ASSET,
            face=face,
            level=level,
            cell=origin,
            size_cm=(trim_depth, run_cm, band_h),
            offset_extra=((WALL_T_CM - trim_depth) * 0.5, 0.0, band_z),
            placements=placements,
            counters=counters,
            tags=tags | frozenset({"cornice", "string_course", "trim"}),
            kind="prop",
            panel_size_cm=panel_size_cm,
        )

    if shell_flags.get("corner_pilasters") and face in ("south", "north"):
        pil_w = max(10.0, MODULE_CM * 0.14)
        pil_depth = max(4.0, WALL_T_CM * 0.55)
        for label, along in (("w", 0.0), ("e", run_cm - pil_w)):
            _place_shell_box(
                piece_prefix=f"shell_pilaster_{face}_L{level}_{label}",
                asset_id=SHELL_PILASTER_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(pil_depth, pil_w, STOREY_CM * 0.92),
                offset_extra=((WALL_T_CM - pil_depth) * 0.5, along, STOREY_CM * 0.04),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"pilaster", "trim", "corner"}),
                kind="prop",
                panel_size_cm=panel_size_cm,
            )

    door_open_y0: Optional[float] = None
    door_open_w: Optional[float] = None
    door_open_h: Optional[float] = None

    for bay in range(bay_count):
        bay_start = bay * MODULE_CM
        opening = _opening_spec(
            face=face,
            bay=bay,
            level=level,
            door_bay=door_bay,
            bay_count=bay_count,
            variation=variation,
            shell_cfg=shell_cfg,
            wealth=wealth,
            stair_blocked=stair_blocked,
        )
        if opening is None:
            continue

        kind, open_w, open_h, sill_z = opening
        sill_z = max(0.0, sill_z)
        head_z = min(STOREY_CM, sill_z + open_h)
        open_h = max(40.0, head_z - sill_z)
        open_center = bay_start + MODULE_CM * 0.5
        open_y0 = open_center - open_w * 0.5

        _place_opening_cutter(
            piece_prefix=f"shell_cut_{face}_L{level}_B{bay}",
            face=face,
            level=level,
            cell=origin,
            open_y0=open_y0,
            open_w=open_w,
            sill_z=sill_z,
            open_h=open_h,
            kind=kind,
            placements=placements,
            counters=counters,
            tags=tags,
            panel_size_cm=panel_size_cm,
        )

        if kind in ("window", "stair_light"):
            frame_bar = max(8.0, min(12.0, _FRAME_BAR_CM))
            frame_depth = max(4.0, WALL_T_CM * _FRAME_T_FRAC)
            open_tags = tags | frozenset({"window", "opening", kind})
            if kind == "stair_light":
                open_tags = open_tags | frozenset({"stairwell", "stair_light"})
            _place_hollow_window_frame(
                face=face,
                level=level,
                origin=origin,
                open_y0=open_y0,
                open_w=open_w,
                open_h=open_h,
                sill_z=sill_z,
                frame_bar=frame_bar,
                frame_depth=frame_depth,
                placements=placements,
                counters=counters,
                tags=open_tags,
                panel_size_cm=panel_size_cm,
            )
            _place_window_glass(
                face=face,
                level=level,
                origin=origin,
                open_y0=open_y0,
                open_w=open_w,
                open_h=open_h,
                sill_z=sill_z,
                frame_bar=frame_bar,
                placements=placements,
                counters=counters,
                tags=open_tags,
                panel_size_cm=panel_size_cm,
            )
        elif kind == "door":
            door_t = max(4.0, frame_t)
            _place_shell_box(
                piece_prefix=f"shell_door_{face}_L{level}",
                asset_id=SHELL_DOOR_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(door_t, open_w * 0.94, open_h * 0.98),
                offset_extra=(
                    (WALL_T_CM - door_t) * 0.5,
                    open_y0 + open_w * 0.03,
                    0.0,
                ),
                placements=placements,
                counters=counters,
                tags=tags | frozenset({"door", "opening"}),
                kind="prop",
                panel_size_cm=panel_size_cm,
            )
            door_open_y0 = open_y0
            door_open_w = open_w
            door_open_h = open_h

    if (
        shell_flags.get("doorcase_surround")
        and face == "south"
        and level == 0
        and door_open_y0 is not None
        and door_open_w is not None
        and door_open_h is not None
    ):
        surround = max(8.0, _FRAME_BAR_CM)
        depth = max(4.0, WALL_T_CM * 0.45)
        base_x = (WALL_T_CM - depth) * 0.5
        case_tags = tags | frozenset({"doorcase", "trim", "door"})
        for suffix, sy, sw, sh, sz in (
            ("l", door_open_y0 - surround, surround, door_open_h + 2 * surround, 0.0),
            (
                "r",
                door_open_y0 + door_open_w,
                surround,
                door_open_h + 2 * surround,
                0.0,
            ),
            ("head", door_open_y0 - surround, door_open_w + 2 * surround, surround, door_open_h),
        ):
            _place_shell_box(
                piece_prefix=f"shell_doorcase_{suffix}_{face}_L{level}",
                asset_id=SHELL_DOORCASE_ASSET,
                face=face,
                level=level,
                cell=origin,
                size_cm=(depth, sw, sh),
                offset_extra=(base_x, sy, sz),
                placements=placements,
                counters=counters,
                tags=case_tags,
                kind="prop",
                panel_size_cm=panel_size_cm,
            )


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
    """Party / blind face — one continuous cream panel per storey."""
    if face == "west":
        cell = (0, 0)
    elif face == "east":
        cell = (bays_x, 0)
    elif face == "south":
        cell = (0, 0)
    else:
        cell = (0, bays_y)
    tags = _EXTERIOR_TAG | frozenset({f"face_{face}"})
    if blind:
        tags = tags | frozenset({"party_wall", "blind"})
    _place_shell_box(
        piece_prefix=f"shell_wall_{face}_L{level}",
        asset_id=SHELL_WALL_ASSET,
        face=face,
        level=level,
        cell=cell,
        size_cm=(WALL_T_CM, run_cm, STOREY_CM),
        offset_extra=(0.0, 0.0, 0.0),
        placements=placements,
        counters=counters,
        tags=tags | frozenset({"shell_wall_panel"}),
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


def _place_stair(
    *,
    stair_id: str,
    anchor: Tuple[int, int],
    yaw: int,
    level: int,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    size_cm: Optional[Tuple[float, float, float]] = None,
) -> None:
    from pae.primitives.catalog import catalog_by_id

    cat = catalog_by_id()
    desc = cat.get(stair_id)
    if desc is None:
        return
    sx, sy, sz = size_cm or desc.size_cm
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
            size_cm=(sx, sy, sz),
            rotates_about_center=desc.rotates_about_center,
            tags=_INTERIOR_TAG | frozenset({"stair"}),
        )
    )


def _stair_well_bbox_cells(
    cells: Sequence[Tuple[int, int]],
) -> Tuple[int, int, int, int]:
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return min(xs), min(ys), max(xs), max(ys)


def _place_stair_shaft_walls(
    *,
    level: int,
    stair_cells: Sequence[Tuple[int, int]],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    open_faces: FrozenSet[str] = frozenset({"south"}),
    bays_x: int = 1,
    bays_y: int = 1,
) -> None:
    """Interior shaft partitions only — never on exterior skins or approach faces.

    When the well sits on the north/east/west facade, that face already has the
    shell wall (+ openings). A second shaft slab there doubles the skin and
    blocks windows from inside.
    """
    if not stair_cells:
        return
    min_x, min_y, max_x, max_y = _stair_well_bbox_cells(stair_cells)
    well_w = (max_x - min_x + 1) * MODULE_CM
    well_d = (max_y - min_y + 1) * MODULE_CM
    shaft_h = STOREY_CM * _SHAFT_WALL_HEIGHT_FRAC
    tags = _INTERIOR_TAG | frozenset({"stair_shaft", "partition", "plaster"})
    skip = {f.lower() for f in open_faces} | {
        f.lower()
        for f in stair_well_exterior_faces(
            stair_cells, bays_x=bays_x, bays_y=bays_y
        )
    }

    if "north" not in skip:
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, f"shell_shaft_n_L{level}"),
                asset_id=SHELL_INTERIOR_WALL_ASSET,
                kind="wall",
                cell=(min_x, max_y),
                level=level,
                yaw=0,
                offset_cm=(0.0, MODULE_CM - WALL_T_CM, 0.0),
                size_cm=(well_w, WALL_T_CM, shaft_h),
                tags=tags | frozenset({"face_north"}),
            )
        )
    if "west" not in skip:
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, f"shell_shaft_w_L{level}"),
                asset_id=SHELL_INTERIOR_WALL_ASSET,
                kind="wall",
                cell=(min_x, min_y),
                level=level,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(WALL_T_CM, well_d, shaft_h),
                tags=tags | frozenset({"face_west"}),
            )
        )
    if "east" not in skip:
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, f"shell_shaft_e_L{level}"),
                asset_id=SHELL_INTERIOR_WALL_ASSET,
                kind="wall",
                cell=(max_x, min_y),
                level=level,
                yaw=0,
                offset_cm=(MODULE_CM - WALL_T_CM, 0.0, 0.0),
                size_cm=(WALL_T_CM, well_d, shaft_h),
                tags=tags | frozenset({"face_east"}),
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
    width_cm: float,
    depth_cm: float,
    bays_x: int,
    bays_y: int,
    blind: FrozenSet[str],
    placements: List[SolidPlacement],
    counters: Dict[str, int],
    pitch: float = SHELL_ROOF_PITCH,
) -> None:
    """Two shell slope boxes + gable end caps — no catalog ``roof_pitched_slope``."""
    oh = EAVE_OVERHANG_CM
    roof_z = STOREY_CM
    ridge_along_x = bays_x >= bays_y
    tags_roof = _SHELL_TAG | frozenset({"pitched"})

    if ridge_along_x:
        span_cm = depth_cm
        rise = roof_rise_cm(pitch, span_cm)
        peak_z = rise + SHELL_ROOF_THICK_CM
        run_cm = width_cm + 2.0 * oh
        half_span = depth_cm * 0.5
        slope_depth = half_span + oh

        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope_s"),
                asset_id=SHELL_ROOF_SLOPE_ASSET,
                kind="roof",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(-oh, -oh, roof_z),
                size_cm=(run_cm, slope_depth, peak_z),
                tags=tags_roof | frozenset({"slope_south"}),
            )
        )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope_n"),
                asset_id=SHELL_ROOF_SLOPE_ASSET,
                kind="roof",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(-oh, half_span - oh, roof_z),
                size_cm=(run_cm, slope_depth, peak_z),
                tags=tags_roof | frozenset({"slope_north"}),
            )
        )
        gable_run = depth_cm + 2.0 * oh
        if "west" not in blind:
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_gable_w"),
                    asset_id=SHELL_GABLE_ASSET,
                    kind="roof",
                    cell=(0, 0),
                    level=level,
                    yaw=0,
                    offset_cm=(-oh, -oh, roof_z),
                    size_cm=(_GABLE_THICK_CM, gable_run, peak_z),
                    tags=tags_roof | frozenset({"gable_west"}),
                )
            )
        if "east" not in blind:
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_gable_e"),
                    asset_id=SHELL_GABLE_ASSET,
                    kind="roof",
                    cell=(0, 0),
                    level=level,
                    yaw=0,
                    offset_cm=(width_cm + oh - _GABLE_THICK_CM, -oh, roof_z),
                    size_cm=(_GABLE_THICK_CM, gable_run, peak_z),
                    tags=tags_roof | frozenset({"gable_east"}),
                )
            )
    else:
        span_cm = width_cm
        rise = roof_rise_cm(pitch, span_cm)
        peak_z = rise + SHELL_ROOF_THICK_CM
        run_cm = depth_cm + 2.0 * oh
        half_span = width_cm * 0.5
        slope_width = half_span + oh

        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope_w"),
                asset_id=SHELL_ROOF_SLOPE_ASSET,
                kind="roof",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(-oh, -oh, roof_z),
                size_cm=(slope_width, run_cm, peak_z),
                tags=tags_roof | frozenset({"slope_west"}),
            )
        )
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_roof_slope_e"),
                asset_id=SHELL_ROOF_SLOPE_ASSET,
                kind="roof",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(half_span - oh, -oh, roof_z),
                size_cm=(slope_width, run_cm, peak_z),
                tags=tags_roof | frozenset({"slope_east"}),
            )
        )
        gable_run = width_cm + 2.0 * oh
        if "south" not in blind:
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_gable_s"),
                    asset_id=SHELL_GABLE_ASSET,
                    kind="roof",
                    cell=(0, 0),
                    level=level,
                    yaw=0,
                    offset_cm=(-oh, -oh, roof_z),
                    size_cm=(gable_run, _GABLE_THICK_CM, peak_z),
                    tags=tags_roof | frozenset({"gable_south"}),
                )
            )
        if "north" not in blind:
            placements.append(
                SolidPlacement(
                    piece_id=_next_id(counters, "shell_gable_n"),
                    asset_id=SHELL_GABLE_ASSET,
                    kind="roof",
                    cell=(0, 0),
                    level=level,
                    yaw=0,
                    offset_cm=(-oh, depth_cm + oh - _GABLE_THICK_CM, roof_z),
                    size_cm=(gable_run, _GABLE_THICK_CM, peak_z),
                    tags=tags_roof | frozenset({"gable_north"}),
                )
            )


def _place_flat_roof(
    *,
    level: int,
    width_cm: float,
    depth_cm: float,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Simple flat shell roof slab — humble / civic read."""
    placements.append(
        SolidPlacement(
            piece_id=_next_id(counters, "shell_roof_slab"),
            asset_id=SHELL_ROOF_ASSET,
            kind="roof",
            cell=(0, 0),
            level=level,
            yaw=0,
            offset_cm=(0.0, 0.0, STOREY_CM),
            size_cm=(width_cm, depth_cm, SHELL_ROOF_THICK_CM),
            tags=_SHELL_TAG | frozenset({"roof_slab", "flat"}),
        )
    )


def _place_chimney_stubs(
    *,
    level: int,
    bays_x: int,
    bays_y: int,
    width_cm: float,
    depth_cm: float,
    style_overrides: dict,
    variation: ShellVariation,
    roof_pitch: float,
    roof_kind: str,
    placements: List[SolidPlacement],
    counters: Dict[str, int],
) -> None:
    """Short masonry stacks on the roof deck — seed-placed shell boxes."""
    if variation.chimney_count <= 0:
        return
    if not style_overrides.get("shell", {}).get("chimney_stub", False):
        return
    w = MODULE_CM * _CHIMNEY_W_FRAC
    h = STOREY_CM * _CHIMNEY_H_FRAC
    ridge_along_x = bays_x >= bays_y
    span_cm = depth_cm if ridge_along_x else width_cm
    if roof_kind == "flat":
        roof_z = STOREY_CM
    else:
        roof_z = STOREY_CM + roof_rise_cm(roof_pitch, span_cm)
    tags = _SHELL_TAG | frozenset({"chimney", "roofline"})
    for ax, ay in variation.chimney_anchors[: variation.chimney_count]:
        placements.append(
            SolidPlacement(
                piece_id=_next_id(counters, "shell_chimney"),
                asset_id=SHELL_CHIMNEY_ASSET,
                kind="prop",
                cell=(0, 0),
                level=level,
                yaw=0,
                offset_cm=(ax, ay, roof_z),
                size_cm=(w, w, h),
                tags=tags,
            )
        )


def _glazed_faces(blind: FrozenSet[str]) -> Tuple[str, ...]:
    """Every non-party face gets punched openings (terrace end walls included)."""
    return tuple(f for f in ("south", "north", "east", "west") if f not in blind)


def build_shell_assembly(
    params: FacadeParams,
    spec: Optional[BuildingSpec] = None,
) -> Tuple[Assembly, Report]:
    """Build a continuous shell :class:`Assembly` from facade sliders."""
    spec = spec or params_to_spec(params)
    bays_x = spec.footprint.bays_x
    bays_y = spec.footprint.bays_y
    storeys = spec.storeys
    shell_cfg = load_archetype_shell_config(
        params.archetype,
        wealth=params.wealth,
        palette_family=params.palette_family,
    )
    wealth = resolve_wealth(params.wealth, archetype=shell_cfg.archetype)
    blind = party_wall_faces(params.row_context)
    style_overrides = params_to_style_overrides(params)
    roof_blind = blind

    width_cm, depth_cm = _footprint_cm(bays_x, bays_y)
    stair_plan = resolve_stair_plan(wealth, bays_x, bays_y, storeys=storeys)
    stair_id = stair_plan.asset_id
    anchor, stair_yaw, stair_cells = _stair_anchor_and_cells(
        stair_plan, bays_x, bays_y
    )
    stair_open_faces = stair_plan.open_faces
    stair_size_cm = stair_plan.size_cm
    stair_blocked = stairwell_blocked_bays(
        stair_cells, bays_x=bays_x, bays_y=bays_y
    )
    glazed = _glazed_faces(blind)
    variation = derive_shell_variation(
        params,
        bays_x=bays_x,
        bays_y=bays_y,
        storeys=storeys,
        glazed_faces=glazed,
        style_overrides=style_overrides,
        shell_cfg=shell_cfg,
    )
    door_bay = _door_bay_clear_of_stair(
        variation.door_bay,
        bays_x=bays_x,
        stair_blocked_south=stair_blocked.get("south", frozenset()),
    )
    roof_kind = shell_cfg.roof_kind if wealth >= 2 else "flat"
    if wealth <= 1:
        roof_kind = "flat"
    roof_pitch = shell_cfg.roof_pitch

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
            if face in blind:
                _place_continuous_wall(
                    face=face,
                    level=level,
                    run_cm=run_cm,
                    placements=placements,
                    counters=counters,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    blind=True,
                )
            elif face in glazed:
                _place_glazed_face(
                    face=face,
                    level=level,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    width_cm=width_cm,
                    depth_cm=depth_cm,
                    door_bay=door_bay,
                    variation=variation,
                    shell_cfg=shell_cfg,
                    wealth=wealth,
                    style_overrides=style_overrides,
                    placements=placements,
                    counters=counters,
                    stair_blocked=stair_blocked.get(face, frozenset()),
                )
            else:
                _place_continuous_wall(
                    face=face,
                    level=level,
                    run_cm=run_cm,
                    placements=placements,
                    counters=counters,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    blind=False,
                )

        _place_stair_shaft_walls(
            level=level,
            stair_cells=stair_cells,
            placements=placements,
            counters=counters,
            open_faces=stair_open_faces,
            bays_x=bays_x,
            bays_y=bays_y,
        )

    for level in range(storeys - 1):
        _place_stair(
            stair_id=stair_id,
            anchor=anchor,
            yaw=stair_yaw,
            level=level,
            placements=placements,
            counters=counters,
            size_cm=stair_size_cm,
        )

    if roof_kind == "flat":
        _place_flat_roof(
            level=storeys - 1,
            width_cm=width_cm,
            depth_cm=depth_cm,
            placements=placements,
            counters=counters,
        )
    else:
        _place_pitched_roof(
            level=storeys - 1,
            width_cm=width_cm,
            depth_cm=depth_cm,
            bays_x=bays_x,
            bays_y=bays_y,
            blind=roof_blind,
            placements=placements,
            counters=counters,
            pitch=roof_pitch,
        )
    _place_chimney_stubs(
        level=storeys - 1,
        bays_x=bays_x,
        bays_y=bays_y,
        width_cm=width_cm,
        depth_cm=depth_cm,
        style_overrides=style_overrides,
        variation=variation,
        roof_pitch=roof_pitch,
        roof_kind=roof_kind,
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
    """Count exterior shell wall panels (one cream panel per face per storey)."""
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET
        and "exterior" in p.tags
        and "shell_wall_panel" in p.tags
    )


def count_face_shell_wall_panels(assembly: Assembly, face: str) -> int:
    """Shell wall panels on one facade face (boolean_parent on glazed faces)."""
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WALL_ASSET
        and f"face_{face}" in p.tags
        and "shell_wall_panel" in p.tags
    )


def count_pier_pieces(assembly: Assembly, face: Optional[str] = None) -> int:
    """Pier/spandrel grammar pieces — zero when using single-panel shell."""
    pieces = [p for p in assembly.placements if "pier" in p.tags]
    if face is not None:
        pieces = [p for p in pieces if f"face_{face}" in p.tags]
    return len(pieces)


def count_opening_cutters(assembly: Assembly, face: Optional[str] = None) -> int:
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_OPENING_CUTTER_ASSET
        and (face is None or f"face_{face}" in p.tags)
    )


def count_modular_window_kits(assembly: Assembly) -> int:
    """Legacy modular wall-window kits must not appear on the shell facade."""
    kit_ids = {
        "wall_window",
        "wall_window_cross",
        "wall_window_mullioned",
        "wall_window_plain",
        "wall_door",
        "wall_door_double",
        "wall_door_plain",
        "wall_door_gothic",
    }
    return sum(1 for p in assembly.placements if p.asset_id in kit_ids)


def count_shell_doors(assembly: Assembly, face: str = "south") -> int:
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_DOOR_ASSET and f"face_{face}" in p.tags
    )


def count_chimney_stubs(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if p.asset_id == SHELL_CHIMNEY_ASSET)


def count_stair_placements(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if p.kind == "stair")


def count_floor_holes(assembly: Assembly) -> int:
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == "floor_hole" and p.kind == "hole"
    )


def count_interior_corridor_walls(assembly: Assembly) -> int:
    """Legacy inset corridor partitions — must not appear in shell mode."""
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_INTERIOR_WALL_ASSET
        and "stair_shaft" not in p.tags
        and str(p.piece_id).startswith("shell_corridor")
    )


def count_style_shell_props(assembly: Assembly) -> int:
    """Balcony/patio/jetty/forecourt style-pack props must not appear in shell mode."""
    forbidden = (
        "balcony",
        "patio",
        "jetty",
        "forecourt",
        "balcony_deck",
        "porch_slab",
    )
    return sum(
        1
        for p in assembly.placements
        if p.asset_id in forbidden
        or any(t in p.tags for t in ("balcony", "patio", "jetty", "forecourt"))
    )


def count_window_glass_placements(assembly: Assembly) -> int:
    return sum(
        1
        for p in assembly.placements
        if p.asset_id == SHELL_WINDOW_GLASS_ASSET
    )


def count_window_frame_bars(assembly: Assembly, face: Optional[str] = None) -> int:
    pieces = [
        p
        for p in assembly.placements
        if p.asset_id == SHELL_WINDOW_FRAME_ASSET and "frame_bar" in p.tags
    ]
    if face is not None:
        pieces = [p for p in pieces if f"face_{face}" in p.tags]
    return len(pieces)


def count_stair_shaft_pieces(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if "stair_shaft" in p.tags)


def count_muntin_placements(assembly: Assembly) -> int:
    return sum(
        1 for p in assembly.placements if p.asset_id == SHELL_WINDOW_MUNTIN_ASSET
    )


def count_shell_roof_slopes(assembly: Assembly) -> int:
    return sum(
        1 for p in assembly.placements if p.asset_id == SHELL_ROOF_SLOPE_ASSET
    )


def count_shell_gable_ends(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if p.asset_id == SHELL_GABLE_ASSET)


def shell_roof_placements(assembly: Assembly) -> List[SolidPlacement]:
    """All shell roof pieces (slopes + gables) for bounds / silhouette tests."""
    roof_ids = {SHELL_ROOF_SLOPE_ASSET, SHELL_GABLE_ASSET, SHELL_ROOF_ASSET}
    return [p for p in assembly.placements if p.asset_id in roof_ids or p.kind == "roof"]


def count_window_placements(assembly: Assembly, face: str) -> int:
    return sum(
        1
        for p in assembly.placements
        if "window" in p.tags and f"face_{face}" in p.tags
    )


__all__ = [
    "SHELL_CHIMNEY_ASSET",
    "SHELL_DOOR_ASSET",
    "SHELL_FLOOR_ASSET",
    "SHELL_INTERIOR_WALL_ASSET",
    "SHELL_OPENING_CUTTER_ASSET",
    "SHELL_GABLE_ASSET",
    "SHELL_ROOF_ASSET",
    "SHELL_ROOF_SLOPE_ASSET",
    "SHELL_STAIR_RAIL_ASSET",
    "SHELL_WALL_ASSET",
    "SHELL_WINDOW_FRAME_ASSET",
    "SHELL_WINDOW_GLASS_ASSET",
    "SHELL_WINDOW_MUNTIN_ASSET",
    "ShellVariation",
    "build_shell_assembly",
    "derive_shell_variation",
    "count_chimney_stubs",
    "count_exterior_shell_walls",
    "count_face_shell_wall_panels",
    "count_floor_holes",
    "count_interior_corridor_walls",
    "count_modular_window_kits",
    "count_muntin_placements",
    "count_opening_cutters",
    "count_pier_pieces",
    "count_shell_doors",
    "count_shell_gable_ends",
    "count_shell_roof_slopes",
    "count_stair_placements",
    "count_stair_shaft_pieces",
    "count_style_shell_props",
    "count_window_frame_bars",
    "count_window_glass_placements",
    "count_window_placements",
    "is_facade_shell_assembly",
    "is_shell_placement",
    "shell_cutter_hole_yz_cm",
    "shell_roof_placements",
    "stairwell_blocked_bays",
    "stair_well_exterior_faces",
]

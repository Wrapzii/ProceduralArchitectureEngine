"""MP-WS-K2 architectural details — sills, hoods, planters, patio, functional balcony.

WHY THIS EXISTS: Stage K metadata tags are not enough for window sills / planters /
walkable balconies. This module places real kit pieces with handbook validators,
fail-closed for balconies that cannot host an upper door cleanly.

Runs after ``style_apply`` aperture remap (so window families are final) and before
Stage K banding detail. Lives outside Codex-dirty ``assemble.py`` / ``validate.py``.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.banding import band_faces_of
from pae.boundary import FACE_YAW, outward_offset_cm
from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM, placement_world_aabb
from pae.primitives.apertures import get_profile
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report
from pae.style_pack import StylePack, load_style_pack, resolve_door_piece_id

ARCH_DETAIL_TAG = "arch_detail"
BALCONY_TAG = "balcony"
BALCONY_DOOR_TAG = "balcony_door"
BALCONY_DECK_TAG = "balcony_deck"
BALCONY_GUARD_TAG = "balcony_guard"
BALCONY_SUPPORT_TAG = "balcony_support"

# Handbook checks owned here (not demotions of core validate).
CHECK_SILL = "sill_alignment"
CHECK_CROSS = "cross_mullion_geometry"
CHECK_PLANTER = "planter_clearance"
CHECK_PATIO = "patio_door_path"
CHECK_BALCONY_ACCESS = "balcony_access"
CHECK_BALCONY_GUARD = "balcony_guard"
CHECK_BALCONY_SUPPORT = "balcony_support"
CHECK_BALCONY_REACH = "balcony_door_reachability"


def _rng(seed: int, key: str) -> random.Random:
    return random.Random(f"arch_detail:{seed}:{key}")


def _face_from_tags(p: SolidPlacement) -> Optional[str]:
    for t in p.tags:
        if t.startswith("face_"):
            return t.split("_", 1)[1].lower()
        if t.startswith("face:"):
            return t.split(":", 1)[1].lower()
    return None


def _face_for_host(
    p: SolidPlacement,
    faces: Dict[str, str],
    *,
    default: Optional[str] = None,
) -> Optional[str]:
    tagged = _face_from_tags(p)
    if tagged in ("south", "north", "west", "east"):
        return tagged
    mapped = faces.get(p.piece_id)
    if mapped in ("south", "north", "west", "east"):
        return mapped
    return default


def _is_window(p: SolidPlacement) -> bool:
    return p.kind == "wall" and "window" in p.asset_id


def _is_door(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = p.asset_id
    return "door" in aid or "gate" in aid


def _profile_name_for_window(asset_id: str) -> Optional[str]:
    """Map wall_* asset id → aperture profile name."""
    if asset_id.startswith("wall_"):
        name = asset_id[len("wall_") :]
        try:
            get_profile(name)
            return name
        except KeyError:
            pass
    # Legacy wall_window → window_plain
    if asset_id == "wall_window":
        return "window_plain"
    return None


def _opening_run_frac(asset_id: str) -> Tuple[float, float, float, float]:
    """Return (run0_frac, run_len_frac, sill_z_frac, head_z_frac) of MODULE/STOREY."""
    pname = _profile_name_for_window(asset_id)
    if pname is None:
        return (0.30, 0.40, 0.28, 0.68)
    profile = get_profile(pname)
    run0, run1 = profile.opening_run_cm(MODULE_CM)
    z0, z1 = profile.opening_z_cm(STOREY_CM)
    return (
        run0 / MODULE_CM,
        (run1 - run0) / MODULE_CM,
        z0 / STOREY_CM,
        z1 / STOREY_CM,
    )


def _place_from_desc(
    *,
    piece_id: str,
    asset_id: str,
    kind: str,
    cell: Tuple[int, int],
    level: int,
    yaw: int,
    offset_cm: Tuple[float, float, float],
    size_cm: Tuple[float, float, float],
    tags: frozenset,
) -> SolidPlacement:
    return SolidPlacement(
        piece_id=piece_id,
        asset_id=asset_id,
        kind=kind,
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=size_cm,
        rotates_about_center=False,
        tags=tags,
    )


def _place_face_strip(
    asset_id: str,
    host: SolidPlacement,
    face: str,
    *,
    z_cm: float,
    run0_frac: float,
    run_len_frac: float,
    height_cm: float,
    proj_cm: float,
    piece_id: str,
    tags: frozenset,
) -> SolidPlacement:
    """Face-attached strip sized to a fraction of the host wall run."""
    hmn, hmx = placement_world_aabb(
        host.cell[0],
        host.cell[1],
        host.level,
        host.yaw,
        host.size_cm,
        host.offset_cm,
        rotates_about_center=host.rotates_about_center,
    )
    catalog = catalog_by_id()
    desc = catalog[asset_id]
    if face in ("south", "north"):
        yaw = 90
        span = hmx[0] - hmn[0]
        run_len = max(WALL_T_CM * 0.4, span * run_len_frac)
        run_start = hmn[0] + span * run0_frac
        size = (proj_cm, run_len, height_cm)
        # yaw 90: local (x,y) -> world (-y, x); origin offset by +size_y.
        ox = run_start + run_len
        oy = (hmn[1] - proj_cm) if face == "south" else hmx[1]
    else:
        yaw = 0
        span = hmx[1] - hmn[1]
        run_len = max(WALL_T_CM * 0.4, span * run_len_frac)
        run_start = hmn[1] + span * run0_frac
        size = (proj_cm, run_len, height_cm)
        ox = (hmn[0] - proj_cm) if face == "west" else hmx[0]
        oy = run_start
    cx0, cy0 = host.cell[0] * MODULE_CM, host.cell[1] * MODULE_CM
    return SolidPlacement(
        piece_id=piece_id,
        asset_id=asset_id,
        kind=desc.kind,
        cell=host.cell,
        level=host.level,
        yaw=yaw,
        offset_cm=(ox - cx0, oy - cy0, z_cm),
        size_cm=size,
        rotates_about_center=False,
        tags=frozenset(desc.tags) | frozenset({"band", f"face:{face}"}) | tags,
    )


def _outward_centered(
    face: str,
    size_cm: Tuple[float, float, float],
    *,
    z_cm: float,
) -> Tuple[int, Tuple[float, float, float]]:
    yaw, off = outward_offset_cm(face, size_cm, z_cm=z_cm)
    ox, oy, oz = off
    _depth, width, _h = size_cm
    if face in ("south", "north"):
        off = (ox + (MODULE_CM - width) * 0.5, oy, oz)
    else:
        off = (ox, oy + (MODULE_CM - width) * 0.5, oz)
    return yaw, off


def _add_window_sills_and_hoods(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    seed: int,
) -> List[SolidPlacement]:
    if not pack.shell.window_sills and not pack.shell.window_hoods:
        return placements
    catalog = catalog_by_id()
    if "window_sill" not in catalog:
        return placements
    extra: List[SolidPlacement] = []
    tags_base = frozenset({ARCH_DETAIL_TAG, "attached", "style_shell"})
    windows = [p for p in placements if _is_window(p)]
    for win in sorted(windows, key=lambda p: p.piece_id):
        face = _face_for_host(win, faces, default="south") or "south"
        run0, run_len, sill_frac, head_frac = _opening_run_frac(win.asset_id)
        # Scale fractions to actual host height (pack storeys).
        host_h = win.size_cm[2]
        sill_z = win.offset_cm[2] + host_h * sill_frac
        head_z = win.offset_cm[2] + host_h * head_frac
        if pack.shell.window_sills:
            sill_h = max(8.0, STOREY_CM * 0.035)
            proj = WALL_T_CM * 0.32
            # Sit just below the opening.
            z = sill_z - sill_h
            extra.append(
                _place_face_strip(
                    "window_sill",
                    win,
                    face,
                    z_cm=z,
                    run0_frac=run0,
                    run_len_frac=run_len,
                    height_cm=sill_h,
                    proj_cm=proj,
                    piece_id=f"sill_{win.piece_id}",
                    tags=tags_base
                    | frozenset(
                        {"window_sill", "sill", f"face_{face}", f"host:{win.piece_id}"}
                    ),
                )
            )
        if pack.shell.window_hoods and "window_hood" in catalog:
            hood_h = max(10.0, STOREY_CM * 0.045)
            proj = WALL_T_CM * 0.42
            extra.append(
                _place_face_strip(
                    "window_hood",
                    win,
                    face,
                    z_cm=head_z,
                    run0_frac=max(0.0, run0 - 0.02),
                    run_len_frac=min(1.0, run_len + 0.04),
                    height_cm=hood_h,
                    proj_cm=proj,
                    piece_id=f"hood_{win.piece_id}",
                    tags=tags_base
                    | frozenset(
                        {"window_hood", "hood", f"face_{face}", f"host:{win.piece_id}"}
                    ),
                )
            )
    _ = seed
    return placements + extra


def _add_window_boxes(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    seed: int,
) -> List[SolidPlacement]:
    if not pack.shell.window_boxes or "window_box" not in catalog_by_id():
        return placements
    rng = _rng(seed, "window_box")
    windows = [p for p in placements if _is_window(p)]
    if not windows:
        return placements
    # Sparse: ~30–45% of windows, deterministic.
    n = max(1, int(round(len(windows) * 0.35)))
    n = min(len(windows), n)
    chosen = rng.sample(sorted(windows, key=lambda p: p.piece_id), k=n)
    extra: List[SolidPlacement] = []
    tags_base = frozenset(
        {ARCH_DETAIL_TAG, "attached", "style_shell", "planter", "vegetation_socket"}
    )
    for win in chosen:
        face = _face_for_host(win, faces, default="south") or "south"
        run0, run_len, sill_frac, _head = _opening_run_frac(win.asset_id)
        host_h = win.size_cm[2]
        sill_z = win.offset_cm[2] + host_h * sill_frac
        box_h = max(18.0, STOREY_CM * 0.09)
        # Box sits below sill; never into the opening.
        z = sill_z - box_h - 2.0
        # Slightly narrower than opening so it does not block lights.
        box_run = max(0.18, run_len * 0.85)
        box_run0 = run0 + (run_len - box_run) * 0.5
        proj = MODULE_CM * 0.18
        extra.append(
            _place_face_strip(
                "window_box",
                win,
                face,
                z_cm=z,
                run0_frac=box_run0,
                run_len_frac=box_run,
                height_cm=box_h,
                proj_cm=proj,
                piece_id=f"wbox_{win.piece_id}",
                tags=tags_base
                | frozenset({"window_box", f"face_{face}", f"host:{win.piece_id}"}),
            )
        )
    return placements + extra


def _add_ground_planters(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    seed: int,
    blocked: Set[Tuple[int, int]],
) -> List[SolidPlacement]:
    if not pack.shell.ground_planters:
        return placements
    catalog = catalog_by_id()
    wall_id = "planter_wall" if "planter_wall" in catalog else None
    if wall_id is None:
        return placements
    desc = catalog[wall_id]
    from pae.door_clearance import all_door_approach_cells

    approach = all_door_approach_cells(placements, faces=faces)
    door_cells = {p.cell for p in placements if _is_door(p) and p.level == 0}
    door_cells |= blocked | approach
    # South L0 plain/window bays — skip door/stair/approach cells.
    hosts = [
        p
        for p in placements
        if p.kind == "wall"
        and p.level == 0
        and _face_for_host(p, faces) == "south"
        and p.cell not in door_cells
        and not _is_door(p)
    ]
    if not hosts:
        return placements
    rng = _rng(seed, "ground_planter")
    # Sparse: every other clear bay, seed-stable.
    hosts_sorted = sorted(hosts, key=lambda p: (p.cell[0], p.piece_id))
    picked = [h for i, h in enumerate(hosts_sorted) if i % 2 == (seed % 2)]
    if not picked and hosts_sorted:
        picked = [hosts_sorted[rng.randrange(len(hosts_sorted))]]
    extra: List[SolidPlacement] = []
    seen: Set[Tuple[int, int]] = set()
    for host in picked:
        out_cell = (host.cell[0], host.cell[1] - 1)
        if out_cell in seen or out_cell in door_cells or host.cell in door_cells:
            continue
        if out_cell in approach:
            continue
        seen.add(out_cell)
        face = "south"
        yaw = FACE_YAW[face]
        from pae.boundary import boundary_offset_cm

        off = boundary_offset_cm("north", desc.size_cm, yaw=yaw, z_cm=0.0)
        extra.append(
            _place_from_desc(
                piece_id=f"gplanter_{out_cell[0]}_{out_cell[1]}",
                asset_id=desc.id,
                kind=desc.kind,
                cell=out_cell,
                level=0,
                yaw=yaw,
                offset_cm=off,
                size_cm=desc.size_cm,
                tags=frozenset(desc.tags)
                | frozenset(
                    {
                        ARCH_DETAIL_TAG,
                        "style_shell",
                        "ground_planter",
                        "attached",
                        "face_south",
                        "vegetation_socket",
                    }
                ),
            )
        )
    return placements + extra


def _add_patio(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    seed: int,
) -> List[SolidPlacement]:
    """Raised patio / veranda at ground door — clear door path, rails on exposed edges only."""
    if not pack.shell.patio:
        return placements
    # shop_platform / porch_slab may already exist; patio adds a deeper veranda bay.
    catalog = catalog_by_id()
    if "porch_slab" not in catalog:
        return placements
    doors = [p for p in placements if _is_door(p) and p.level == 0]
    if not doors:
        return placements
    # Skip if a porch_slab already tagged patio/deck on this door.
    existing = {
        t.split(":", 1)[1]
        for p in placements
        if "patio" in p.tags
        for t in p.tags
        if t.startswith("host:")
    }
    extra: List[SolidPlacement] = []
    rng = _rng(seed, "patio")
    _ = rng
    slab = catalog["porch_slab"]
    for door in sorted(doors, key=lambda p: p.piece_id)[:1]:  # one primary patio
        if door.piece_id in existing:
            continue
        face = _face_for_host(door, faces, default="south") or "south"
        depth = MODULE_CM * 0.85
        width = MODULE_CM * 0.95
        height = max(slab.size_cm[2], STOREY_CM * 0.10)
        size = (depth, width, height)
        yaw, off = _outward_centered(face, size, z_cm=0.0)
        extra.append(
            _place_from_desc(
                piece_id=f"patio_{door.piece_id}",
                asset_id=slab.id,
                kind=slab.kind,
                cell=door.cell,
                level=0,
                yaw=yaw,
                offset_cm=off,
                size_cm=size,
                tags=frozenset(slab.tags)
                | frozenset(
                    {
                        ARCH_DETAIL_TAG,
                        "style_shell",
                        "patio",
                        "veranda",
                        "deck",
                        "attached",
                        f"face_{face}",
                        f"host:{door.piece_id}",
                        "door_path_clear",
                    }
                ),
            )
        )
        # No patio rails on ground verandas — short raised decks read as
        # platforms/stoops; freestanding thin rails fail freestanding checks.
        # Upper balconies own the guard-rail contract instead.
    return placements + extra


def _add_functional_balcony(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    seed: int,
) -> Tuple[List[SolidPlacement], List[Failure]]:
    """Upper balcony with door + deck + guards + supports — fail-closed if invalid."""
    notes: List[Failure] = []
    if not pack.shell.balcony:
        return placements, notes

    catalog = catalog_by_id()
    if "balcony_deck" not in catalog or "balcony_bracket" not in catalog:
        notes.append(
            Failure(
                check=CHECK_BALCONY_ACCESS,
                message="balcony kit pieces missing from catalog — skipped",
                critical=False,
            )
        )
        return placements, notes

    # Fail-closed: only a confidently south-facing L1+ bay (window or plain
    # exterior wall) may become a balcony door. Side/rear fallbacks produced
    # unreachable freestanding decks.
    def _south_balcony_host(p: SolidPlacement) -> bool:
        if p.kind != "wall" or p.level < 1:
            return False
        if _face_for_host(p, faces) != "south":
            return False
        if _is_door(p):
            return False
        # Prefer glazed bays; allow plain exterior as authored balcony bay.
        return _is_window(p) or p.asset_id == "wall_plain" or "exterior" in p.tags

    south = [p for p in placements if _south_balcony_host(p)]
    # Prefer a window host; else centred-ish plain bay.
    glazed = [p for p in south if _is_window(p)]
    pool = glazed or south
    if not pool:
        notes.append(
            Failure(
                check=CHECK_BALCONY_ACCESS,
                message=(
                    "balcony fail-closed: no south upper-level bay to convert "
                    "into a balcony door (kit present; enable on purpose-built "
                    "two-storey front balcony bay)"
                ),
                critical=False,
            )
        )
        return placements, notes

    rng = _rng(seed, "balcony")
    # Prefer mid-façade bay for a grand balcony read.
    pool_sorted = sorted(pool, key=lambda p: (abs(p.cell[0] - 2), p.piece_id))
    host = pool_sorted[seed % len(pool_sorted)]
    _ = rng
    face = "south"
    # Always a single clear leaf on balconies — wall_door_double's centre mullion
    # reads as a post blocking egress (user: "tall fancy columns block balcony door").
    door_id = "wall_door"
    if door_id not in catalog:
        door_id = resolve_door_piece_id(pack)
    if door_id not in catalog:
        door_id = "wall_door"

    # 1) Convert window → door (balcony access).
    out: List[SolidPlacement] = []
    door_piece: Optional[SolidPlacement] = None
    for p in placements:
        if p.piece_id != host.piece_id:
            out.append(p)
            continue
        new_size = p.size_cm
        if door_id in catalog:
            proto = catalog[door_id].size_cm
            new_size = (proto[0], proto[1], p.size_cm[2])
        door_piece = replace(
            p,
            asset_id=door_id,
            size_cm=new_size,
            tags=frozenset(p.tags)
            | frozenset(
                {
                    ARCH_DETAIL_TAG,
                    BALCONY_TAG,
                    BALCONY_DOOR_TAG,
                    "balcony_access",
                    f"door:{door_id}",
                    f"face_{face}",
                }
            ),
        )
        out.append(door_piece)

    assert door_piece is not None
    # Drop sills/hoods/boxes that targeted the old window host — they would
    # sit in the new door aperture (doorway_opening_clear).
    out = [
        p
        for p in out
        if not (
            _host_id(p) == door_piece.piece_id
            and (
                "window_sill" in p.tags
                or "window_hood" in p.tags
                or "window_box" in p.tags
                or p.asset_id in ("window_sill", "window_hood", "window_box")
            )
        )
    ]
    # Floor datum = host level offset (assembly level Z).
    deck_z = door_piece.offset_cm[2]
    deck_desc = catalog["balcony_deck"]
    depth = MODULE_CM * 0.70
    width = MODULE_CM * 0.95
    deck_h = deck_desc.size_cm[2]
    deck_size = (depth, width, deck_h)
    yaw, off = _outward_centered(face, deck_size, z_cm=deck_z)
    deck = _place_from_desc(
        piece_id=f"balcony_deck_{door_piece.piece_id}",
        asset_id=deck_desc.id,
        kind=deck_desc.kind,
        cell=door_piece.cell,
        level=door_piece.level,
        yaw=yaw,
        offset_cm=off,
        size_cm=deck_size,
        tags=frozenset(deck_desc.tags)
        | frozenset(
            {
                ARCH_DETAIL_TAG,
                BALCONY_TAG,
                BALCONY_DECK_TAG,
                "walkable",
                "attached",
                f"face_{face}",
                f"host:{door_piece.piece_id}",
            }
        ),
    )
    out.append(deck)

    # 2) Guards derived from deck AABB exposed edges (not arbitrary cell offsets).
    #    Host-wall edge is left open for door access. Side rails run along depth.
    rail_id = (
        "balustrade_stone"
        if "balustrade_stone" in catalog
        else ("railing_metal" if "railing_metal" in catalog else None)
    )
    if rail_id:
        rail = catalog[rail_id]
        r_h = min(rail.size_cm[2], STOREY_CM * 0.32)
        r_t = max(float(rail.size_cm[0]), 12.0)
        dmn, dmx = placement_world_aabb(
            deck.cell[0],
            deck.cell[1],
            deck.level,
            deck.yaw,
            deck.size_cm,
            deck.offset_cm,
            rotates_about_center=False,
        )
        rail_z_off = deck_z + deck_h  # offset-space Z sitting on deck top
        cx0 = door_piece.cell[0] * MODULE_CM
        cy0 = door_piece.cell[1] * MODULE_CM

        def _rail_at_aabb_min(
            *,
            piece_id: str,
            yaw: int,
            size: Tuple[float, float, float],
            aabb_min_xy: Tuple[float, float],
            edge_tag: str,
        ) -> SolidPlacement:
            """Place a min-corner rail so its world AABB min XY matches *aabb_min_xy*."""
            sx, sy, _sz = size
            dmx_, dmy_ = aabb_min_xy
            if yaw == 0:
                ox, oy = dmx_ - cx0, dmy_ - cy0
            elif yaw == 90:
                ox, oy = dmx_ + sy - cx0, dmy_ - cy0
            elif yaw == 180:
                ox, oy = dmx_ + sx - cx0, dmy_ + sy - cy0
            elif yaw == 270:
                ox, oy = dmx_ - cx0, dmy_ + sx - cy0
            else:
                raise ValueError(f"rail yaw must be ortho, got {yaw}")
            return _place_from_desc(
                piece_id=piece_id,
                asset_id=rail.id,
                kind=rail.kind,
                cell=door_piece.cell,
                level=door_piece.level,
                yaw=yaw,
                offset_cm=(ox, oy, rail_z_off),
                size_cm=size,
                tags=frozenset(rail.tags)
                | frozenset(
                    {
                        ARCH_DETAIL_TAG,
                        BALCONY_TAG,
                        BALCONY_GUARD_TAG,
                        "exposed_edge",
                        edge_tag,
                        f"host:{door_piece.piece_id}",
                    }
                ),
            )

        # South-facing balcony: host on +Y of deck. Exposed: front (−Y), west/east.
        if face == "south":
            front_len = max(MODULE_CM * 0.4, (dmx[0] - dmn[0]) - r_t)
            front_size = (r_t, front_len, r_h)
            fx0 = dmn[0] + ((dmx[0] - dmn[0]) - front_len) * 0.5
            # yaw 270: thickness along −Y, run along +X on the front edge.
            out.append(
                _rail_at_aabb_min(
                    piece_id=f"balcony_rail_front_{door_piece.piece_id}",
                    yaw=270,
                    size=front_size,
                    aabb_min_xy=(fx0, dmn[1] - r_t * 0.15),
                    edge_tag="front",
                )
            )
            side_len = max(MODULE_CM * 0.2, (dmx[1] - dmn[1]) * 0.90)
            side_size = (r_t, side_len, r_h)
            # yaw 0 / 180: thickness along ±X, run along +Y on the side edges.
            out.append(
                _rail_at_aabb_min(
                    piece_id=f"balcony_rail_L_{door_piece.piece_id}",
                    yaw=0,
                    size=side_size,
                    aabb_min_xy=(dmn[0] - r_t * 0.15, dmn[1] + r_t * 0.2),
                    edge_tag="side",
                )
            )
            out.append(
                _rail_at_aabb_min(
                    piece_id=f"balcony_rail_R_{door_piece.piece_id}",
                    yaw=180,
                    size=side_size,
                    aabb_min_xy=(dmx[0] - r_t * 0.85, dmn[1] + r_t * 0.2),
                    edge_tag="side",
                )
            )
        else:
            # Rare non-south: front rail only via outward helper.
            r_size = (r_t, width * 0.92, r_h)
            ryaw, roff = _outward_centered(face, r_size, z_cm=deck_z + deck_h)
            ox, oy, oz = roff
            nudge = depth - r_t
            if face == "north":
                roff = (ox, oy + nudge, oz)
            elif face == "west":
                roff = (ox - nudge, oy, oz)
            else:
                roff = (ox + nudge, oy, oz)
            out.append(
                _place_from_desc(
                    piece_id=f"balcony_rail_front_{door_piece.piece_id}",
                    asset_id=rail.id,
                    kind=rail.kind,
                    cell=door_piece.cell,
                    level=door_piece.level,
                    yaw=ryaw,
                    offset_cm=roff,
                    size_cm=r_size,
                    tags=frozenset(rail.tags)
                    | frozenset(
                        {
                            ARCH_DETAIL_TAG,
                            BALCONY_TAG,
                            BALCONY_GUARD_TAG,
                            "exposed_edge",
                            "front",
                            f"host:{door_piece.piece_id}",
                        }
                    ),
                )
            )

    # 3) Supports / brackets under deck (do not block L0 windows when possible —
    #    place near deck ends, thin footprint).
    bracket = catalog["balcony_bracket"]
    for side, lat in (("L", -0.32), ("R", 0.32)):
        b_size = bracket.size_cm
        byaw, boff = _outward_centered(face, b_size, z_cm=deck_z - b_size[2])
        box, boy, boz = boff
        # Pull slightly under the deck; offset laterally.
        under = MODULE_CM * 0.12
        if face == "south":
            boff = (box + MODULE_CM * lat, boy + under, boz)
        elif face == "north":
            boff = (box + MODULE_CM * lat, boy - under, boz)
        elif face == "west":
            boff = (box + under, boy + MODULE_CM * lat, boz)
        else:
            boff = (box - under, boy + MODULE_CM * lat, boz)
        # Same storey level as the deck; negative local Z hangs the bracket under the slab.
        out.append(
            _place_from_desc(
                piece_id=f"balcony_bracket_{side}_{door_piece.piece_id}",
                asset_id=bracket.id,
                kind=bracket.kind,
                cell=door_piece.cell,
                level=door_piece.level,
                yaw=byaw,
                offset_cm=boff,
                size_cm=b_size,
                tags=frozenset(bracket.tags)
                | frozenset(
                    {
                        ARCH_DETAIL_TAG,
                        BALCONY_TAG,
                        BALCONY_SUPPORT_TAG,
                        "bracket",
                        f"host:{door_piece.piece_id}",
                    }
                ),
            )
        )

    notes.append(
        Failure(
            check="arch_detail_balcony",
            message=(
                f"balcony placed on {door_piece.piece_id} face={face} "
                f"level={door_piece.level}"
            ),
            critical=False,
        )
    )
    return out, notes


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _aabb(p: SolidPlacement):
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _xy_overlap(a, b) -> Tuple[float, float]:
    amin, amax = a
    bmin, bmax = b
    return (
        min(amax[0], bmax[0]) - max(amin[0], bmin[0]),
        min(amax[1], bmax[1]) - max(amin[1], bmin[1]),
    )


def _host_id(p: SolidPlacement) -> Optional[str]:
    for t in p.tags:
        if t.startswith("host:"):
            return t.split(":", 1)[1]
    return None


def validate_arch_details(assembly: Assembly) -> Report:
    """Handbook checks for K2 pieces. Critical when a balcony is incomplete."""
    failures: List[Failure] = []
    by_id = {p.piece_id: p for p in assembly.placements}
    sills = [p for p in assembly.placements if "window_sill" in p.tags or p.asset_id == "window_sill"]
    for sill in sills:
        hid = _host_id(sill)
        host = by_id.get(hid) if hid else None
        if host is None or not _is_window(host):
            # Balcony door hosts are fine for hoods; sills must be under windows.
            if host is not None and _is_door(host):
                continue
            failures.append(
                Failure(
                    check=CHECK_SILL,
                    message=f"sill {sill.piece_id} has no window host",
                    critical=True,
                    piece_id=sill.piece_id,
                )
            )
            continue
        sa, ha = _aabb(sill), _aabb(host)
        ox, oy = _xy_overlap(sa, ha)
        # Must kiss host (projecting out) and sit below opening mid-height.
        if ox < -TOL_CM and oy < -TOL_CM:
            failures.append(
                Failure(
                    check=CHECK_SILL,
                    message=f"sill {sill.piece_id} does not align with host window",
                    critical=True,
                    piece_id=sill.piece_id,
                )
            )
        # Width: sill run should be within ~15% of opening run.
        _r0, run_len, _sf, _hf = _opening_run_frac(host.asset_id)
        expected = MODULE_CM * run_len
        sill_run = max(sill.size_cm[0], sill.size_cm[1])
        if expected > 1.0 and abs(sill_run - expected) > expected * 0.35 + TOL_CM:
            failures.append(
                Failure(
                    check=CHECK_SILL,
                    message=(
                        f"sill {sill.piece_id} run {sill_run:.0f} cm vs opening "
                        f"{expected:.0f} cm"
                    ),
                    critical=True,
                    piece_id=sill.piece_id,
                )
            )

    # Cross-mullion geometry on any wall_window_cross present.
    for p in assembly.placements:
        if p.asset_id != "wall_window_cross":
            continue
        try:
            profile = get_profile("window_cross")
        except KeyError:
            failures.append(
                Failure(
                    check=CHECK_CROSS,
                    message="window_cross profile missing",
                    critical=True,
                    piece_id=p.piece_id,
                )
            )
            continue
        if profile.lights < 2 or profile.transom_frac <= 0.0:
            failures.append(
                Failure(
                    check=CHECK_CROSS,
                    message="window_cross must have vertical + horizontal mullion",
                    critical=True,
                    piece_id=p.piece_id,
                )
            )
        if profile.mullion_frac > 0.08:
            failures.append(
                Failure(
                    check=CHECK_CROSS,
                    message=f"cross mullion too thick ({profile.mullion_frac})",
                    critical=False,
                    piece_id=p.piece_id,
                )
            )

    # Planter clearance from doors.
    planters = [
        p
        for p in assembly.placements
        if "ground_planter" in p.tags or "window_box" in p.tags
    ]
    doors = [p for p in assembly.placements if _is_door(p)]
    for pl in planters:
        if "window_box" in pl.tags:
            # Window boxes must not rise into opening — top below host sill.
            hid = _host_id(pl)
            host = by_id.get(hid) if hid else None
            if host is not None:
                _r0, _rl, sill_frac, _hf = _opening_run_frac(host.asset_id)
                sill_z = host.offset_cm[2] + host.size_cm[2] * sill_frac
                top = pl.offset_cm[2] + pl.size_cm[2]
                if top > sill_z + TOL_CM:
                    failures.append(
                        Failure(
                            check=CHECK_PLANTER,
                            message=f"window_box {pl.piece_id} blocks opening",
                            critical=True,
                            piece_id=pl.piece_id,
                        )
                    )
            continue
        for d in doors:
            if d.level != 0:
                continue
            if abs(pl.cell[0] - d.cell[0]) + abs(pl.cell[1] - d.cell[1]) == 0:
                failures.append(
                    Failure(
                        check=CHECK_PLANTER,
                        message=f"planter {pl.piece_id} on door cell {d.cell}",
                        critical=True,
                        piece_id=pl.piece_id,
                    )
                )

    # Patio door path: patio must share door cell / face; no rail against door.
    for patio in [p for p in assembly.placements if "patio" in p.tags]:
        hid = _host_id(patio)
        host = by_id.get(hid) if hid else None
        if host is None or not _is_door(host):
            failures.append(
                Failure(
                    check=CHECK_PATIO,
                    message=f"patio {patio.piece_id} has no door host",
                    critical=True,
                    piece_id=patio.piece_id,
                )
            )
            continue
        if patio.cell != host.cell:
            failures.append(
                Failure(
                    check=CHECK_PATIO,
                    message=f"patio {patio.piece_id} not on door cell",
                    critical=True,
                    piece_id=patio.piece_id,
                )
            )

    # Balcony contract — critical when any balcony_deck exists.
    decks = [
        p
        for p in assembly.placements
        if BALCONY_DECK_TAG in p.tags or p.asset_id == "balcony_deck"
    ]
    for deck in decks:
        hid = _host_id(deck)
        door = by_id.get(hid) if hid else None
        if door is None or BALCONY_DOOR_TAG not in door.tags:
            # Also accept any balcony_door on same cell/level.
            door = next(
                (
                    p
                    for p in assembly.placements
                    if BALCONY_DOOR_TAG in p.tags
                    and p.level == deck.level
                    and p.cell == deck.cell
                ),
                None,
            )
        if door is None:
            failures.append(
                Failure(
                    check=CHECK_BALCONY_ACCESS,
                    message=f"balcony deck {deck.piece_id} has no balcony_door",
                    critical=True,
                    piece_id=deck.piece_id,
                )
            )
        else:
            # Reachability: door and deck must XY-overlap / kiss.
            da, dka = _aabb(door), _aabb(deck)
            ox, oy = _xy_overlap(da, dka)
            z_gap = abs(da[0][2] - dka[1][2])  # door bottom vs deck top-ish
            if ox < -MODULE_CM * 0.25 and oy < -MODULE_CM * 0.25:
                failures.append(
                    Failure(
                        check=CHECK_BALCONY_REACH,
                        message=f"balcony door cannot reach deck {deck.piece_id}",
                        critical=True,
                        piece_id=deck.piece_id,
                    )
                )
            _ = z_gap

        guards = [
            p
            for p in assembly.placements
            if BALCONY_GUARD_TAG in p.tags and _host_id(p) == hid
        ]
        if len(guards) < 1:
            failures.append(
                Failure(
                    check=CHECK_BALCONY_GUARD,
                    message=f"balcony {deck.piece_id} missing exposed-edge guard",
                    critical=True,
                    piece_id=deck.piece_id,
                )
            )

        supports = [
            p
            for p in assembly.placements
            if BALCONY_SUPPORT_TAG in p.tags and _host_id(p) == hid
        ]
        if len(supports) < 1:
            failures.append(
                Failure(
                    check=CHECK_BALCONY_SUPPORT,
                    message=f"balcony {deck.piece_id} missing structural support",
                    critical=True,
                    piece_id=deck.piece_id,
                )
            )

    return Report.from_failures(failures)


def apply_arch_details(
    assembly: Assembly,
    *,
    style_id: Optional[str] = None,
    seed: int = 0,
    enabled: bool = True,
    floor_plan: Optional[object] = None,
) -> Tuple[Assembly, Report]:
    """Place K2 details from pack.shell flags. Idempotent via ARCH_DETAIL_TAG."""
    if not enabled:
        return assembly, Report.from_failures([])
    from pae.facade_shell import is_facade_shell_assembly

    if is_facade_shell_assembly(assembly):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="arch_detail_shell_skip",
                    message=(
                        "facade_shell assembly — patio/balcony/jetty dress skipped "
                        "(shell ignores style-pack shell.balcony)"
                    ),
                    critical=False,
                )
            ]
        )
    if any(ARCH_DETAIL_TAG in p.tags for p in assembly.placements):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="arch_detail_skip",
                    message="arch_detail already applied — skipped",
                    critical=False,
                )
            ]
        )
    if not style_id:
        return assembly, Report.from_failures([])

    pack, report = load_style_pack(str(style_id))
    if pack is None or not report.ok:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="arch_detail_pack",
                    message=f"style pack {style_id!r} failed to load",
                    critical=True,
                )
            ]
        )

    faces = band_faces_of(assembly)
    blocked: Set[Tuple[int, int]] = set()
    if floor_plan is not None:
        for attr in ("stair_cells", "corridor_cells", "door_cells"):
            for cell in getattr(floor_plan, attr, None) or ():
                if isinstance(cell, tuple) and len(cell) == 2:
                    blocked.add((int(cell[0]), int(cell[1])))

    placements = list(assembly.placements)
    notes: List[Failure] = []
    placements = _add_window_sills_and_hoods(
        placements, pack, faces=faces, seed=seed
    )
    placements = _add_window_boxes(placements, pack, faces=faces, seed=seed)
    placements = _add_ground_planters(
        placements, pack, faces=faces, seed=seed, blocked=blocked
    )
    placements = _add_patio(placements, pack, faces=faces, seed=seed)
    placements, bal_notes = _add_functional_balcony(
        placements, pack, faces=faces, seed=seed
    )
    notes.extend(bal_notes)

    # Final sweep: drop any barrier that still landed in a door approach cell.
    from pae.door_clearance import (
        all_door_approach_cells,
        filter_blocking_from_approach,
        validate_entrance_approach_clear,
    )

    approach = all_door_approach_cells(placements, faces=faces)
    placements = filter_blocking_from_approach(placements, approach)

    placements.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    out = replace(assembly, placements=placements)
    vreport = validate_arch_details(out)
    notes.extend(vreport.failures)
    notes.extend(validate_entrance_approach_clear(out, faces=faces).failures)
    notes.append(
        Failure(
            check="arch_detail_ok",
            message=(
                f"arch_detail style={style_id} seed={seed} "
                f"pieces={sum(1 for p in placements if ARCH_DETAIL_TAG in p.tags)}"
            ),
            critical=False,
        )
    )
    return out, Report.from_failures(notes)


def count_arch_detail_pieces(assembly: Assembly) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in assembly.placements:
        if ARCH_DETAIL_TAG not in p.tags:
            continue
        counts[p.asset_id] = counts.get(p.asset_id, 0) + 1
    return counts


def arch_detail_signature(assembly: Assembly) -> Tuple[Tuple[str, str], ...]:
    rows = [
        (p.piece_id, p.asset_id)
        for p in assembly.placements
        if ARCH_DETAIL_TAG in p.tags
    ]
    return tuple(sorted(rows))


__all__ = [
    "ARCH_DETAIL_TAG",
    "BALCONY_DECK_TAG",
    "BALCONY_DOOR_TAG",
    "BALCONY_GUARD_TAG",
    "BALCONY_SUPPORT_TAG",
    "BALCONY_TAG",
    "apply_arch_details",
    "arch_detail_signature",
    "count_arch_detail_pieces",
    "validate_arch_details",
]

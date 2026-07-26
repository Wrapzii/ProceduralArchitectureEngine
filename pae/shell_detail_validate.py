"""Style-shell / K2 detail placement contracts + fail-closed validators.

WHY THIS EXISTS: K1/K2 pieces (door surrounds, balcony rails, planters, porch)
shipped with ``critical=[]`` because their checks lived outside ``validate()``
or only looked at cells/tags. Handbook §2 — new pieces owe Placement,
Exclusion, Support, and Use checks. User: balcony rails not on exposed edges;
fancy posts inside doorways; generic validate gave false confidence.

These checks are AABB / aperture based. Tag allow-lists do **not** pass a piece
whose solid intersects a door void or sits off a deck edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    aabb_intersects,
    placement_world_aabb,
)
from pae.report import Failure

Vec3 = Tuple[float, float, float]
AABB = Tuple[Vec3, Vec3]

# ---------------------------------------------------------------------------
# Piece inventory + contracts (Handbook §2 answers condensed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PieceContract:
    """Attachment / clearance contract for one shell or detail asset family."""

    asset_ids: Tuple[str, ...]
    tags_any: Tuple[str, ...]
    host: str
    allowed_yaw: Tuple[int, ...]
    support: str
    forbidden: str
    clearance: str
    edge_mount: str


SHELL_DETAIL_CONTRACTS: Tuple[PieceContract, ...] = (
    PieceContract(
        asset_ids=("band_pilaster", "band_course"),
        tags_any=("door_surround", "jamb", "lintel"),
        host="ground door wall (face_*); never balcony door",
        allowed_yaw=(0, 90, 180, 270),
        support="host wall face (band attach)",
        forbidden="door aperture prism; approach corridor void",
        clearance="jambs in margin outside width_frac; lintel above head_frac",
        edge_mount="N/A — wall face flush, project ≤ WALL_T",
    ),
    PieceContract(
        asset_ids=("porch_roof",),
        tags_any=("canopy", "awning", "above_door"),
        host="ground door wall head",
        allowed_yaw=(0, 90, 180, 270),
        support="attached to host wall above opening",
        forbidden="door aperture prism; ground plane as sole support",
        clearance="bottom ≥ door head; must not fill opening",
        edge_mount="face strip above head",
    ),
    PieceContract(
        asset_ids=("porch_slab", "steps_external", "steps_grand"),
        tags_any=("stoop", "porch", "patio", "steps", "deck", "platform"),
        host="ground door cell, outward",
        allowed_yaw=(0, 90, 180, 270),
        support="ground / plinth",
        forbidden="interior room volume; blocking aperture XY at walk height",
        clearance="may occupy approach cells; must not fill door void",
        edge_mount="outward of host face",
    ),
    PieceContract(
        asset_ids=("forecourt_wall", "planter_wall"),
        tags_any=("forecourt", "ground_planter", "garden_wall"),
        host="exterior south cells; never door approach cells",
        allowed_yaw=(0, 90, 180, 270),
        support="ground",
        forbidden="door approach corridor; door aperture",
        clearance="outside approach_clear_cells",
        edge_mount="outward cell edge",
    ),
    PieceContract(
        asset_ids=("window_sill", "window_hood", "window_box"),
        tags_any=("window_sill", "window_hood", "window_box", "sill", "hood"),
        host="window wall opening",
        allowed_yaw=(0, 90, 180, 270),
        support="host wall / sill line",
        forbidden="door aperture; blocking window lights",
        clearance="sill below glass; hood above head; box below sill",
        edge_mount="outward under/over opening",
    ),
    PieceContract(
        asset_ids=("balcony_deck",),
        tags_any=("balcony_deck",),
        host="balcony_door wall, outward",
        allowed_yaw=(0, 90, 180, 270),
        support="host wall + balcony_bracket supports",
        forbidden="freestanding island without host/brackets",
        clearance="must not plug balcony door void",
        edge_mount="outward centered on door bay",
    ),
    PieceContract(
        asset_ids=("balustrade_stone", "railing_metal", "balustrade"),
        tags_any=("balcony_guard", "exposed_edge"),
        host="balcony_deck exposed edges only",
        allowed_yaw=(0, 90, 180, 270),
        support="deck top edge",
        forbidden="host-wall edge; door access gap; deck interior",
        clearance="no rail across balcony door corridor",
        edge_mount="tangent to exposed deck edge; thickness outward",
    ),
    PieceContract(
        asset_ids=("balcony_bracket",),
        tags_any=("balcony_support", "bracket"),
        host="under balcony_deck + host wall",
        allowed_yaw=(0, 90, 180, 270),
        support="host wall / under deck",
        forbidden="door aperture; L0 walk path clogging beyond thin brackets",
        clearance="under deck; not in door void",
        edge_mount="under deck near ends",
    ),
    PieceContract(
        asset_ids=("stair_straight", "stair_switchback", "stair_wide", "stair_half"),
        tags_any=("stair",),
        host="STAIR well cells / monumental pads",
        allowed_yaw=(0, 90, 180, 270),  # spirals exempt elsewhere
        support="floor / ground at flight base",
        forbidden="diagonal yaw; stacked same-XY flights",
        clearance="floor_hole over full covered_cells; head clearance",
        edge_mount="pad anchor via boundary/rotation_offset",
    ),
)


CHECK_DOORWAY_OPENING_CLEAR = "doorway_opening_clear"
CHECK_BALCONY_RAIL_ON_EDGE = "balcony_rail_on_edge"
CHECK_BALCONY_RAIL_ORIENTATION = "balcony_rail_orientation"
CHECK_BALCONY_ACCESS_GAP = "balcony_access_gap"
CHECK_BALCONY_GUARD_COMPLETE = "balcony_guard_complete"
CHECK_BALCONY_DECK_SUPPORT = "balcony_deck_support"
CHECK_SHELL_ATTACHMENT = "shell_detail_attachment"
CHECK_STAIR_YAW_ORTHO = "stair_yaw_ortho"

# Shell / detail solids that must not occupy a door aperture prism.
_OPENING_BLOCKERS_TAGS = frozenset(
    {
        "door_surround",
        "jamb",
        "lintel",
        "forecourt",
        "ground_planter",
        "garden_wall",
        "balcony_guard",
        "balcony_support",
        "band",
        "style_shell",
        "arch_detail",
        "porch",
        "canopy",
        "awning",
        "pilaster",
        "vertical",
    }
)
_OPENING_BLOCKERS_ASSETS = frozenset(
    {
        "band_pilaster",
        "band_course",
        "forecourt_wall",
        "planter_wall",
        "porch_post",
        "porch_roof",
        "balustrade_stone",
        "railing_metal",
        "balcony_bracket",
        "window_box",
        "window_hood",
        "window_sill",
    }
)
# Walkable approach decks are allowed to kiss the threshold but must not fill
# the aperture interior (checked via deep overlap, not mere contact).
_APPROACH_WALK_ASSETS = frozenset(
    {"porch_slab", "steps_external", "steps_grand", "balcony_deck"}
)


def _aabb(p: SolidPlacement) -> AABB:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _centre(a: AABB) -> Vec3:
    mn, mx = a
    return (
        (mn[0] + mx[0]) * 0.5,
        (mn[1] + mx[1]) * 0.5,
        (mn[2] + mx[2]) * 0.5,
    )


def _is_door_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = p.asset_id
    return "door" in aid or "gate" in aid


def _face_of(p: SolidPlacement) -> str:
    for t in p.tags:
        if t.startswith("face_"):
            return t.split("_", 1)[1]
        if t.startswith("face:"):
            return t.split(":", 1)[1]
    pid = p.piece_id.lower()
    for face in ("south", "north", "east", "west"):
        if face in pid:
            return face
    if int(p.yaw) % 180 == 90:
        return "south"
    return "south"


def _aperture_fracs(asset_id: str) -> Tuple[float, float, float]:
    """Return (width_frac, height_frac, sill_frac) for a door/window wall."""
    try:
        from pae.primitives.apertures import get_profile
        from pae.primitives.catalog import catalog_by_id

        desc = catalog_by_id().get(asset_id)
        profile_name = getattr(desc, "profile", None) if desc is not None else None
        if profile_name:
            prof = get_profile(str(profile_name))
            return (
                float(prof.width_frac),
                float(prof.height_frac),
                float(prof.sill_frac),
            )
    except Exception:
        pass
    if "gate" in asset_id:
        return (0.88, 0.90, 0.0)
    if "double" in asset_id:
        return (0.62, 0.80, 0.0)
    if "door" in asset_id:
        return (0.40, 0.84, 0.0)
    return (0.40, 0.60, 0.30)


def door_aperture_prism(
    door: SolidPlacement,
    *,
    storey_cap_cm: Optional[float] = None,
) -> AABB:
    """Walkable / clear opening prism for a door wall (axis-aligned).

    Multi-storey spanning door walls still open only one storey of leaf height
    unless the asset is a monumental gate. ``storey_cap_cm`` defaults to
    ``STOREY_CM``.
    """
    w_frac, h_frac, sill_frac = _aperture_fracs(door.asset_id)
    mn, mx = _aabb(door)
    # Run along the long wall axis in world XY.
    dx, dy = mx[0] - mn[0], mx[1] - mn[1]
    cap = float(storey_cap_cm if storey_cap_cm is not None else STOREY_CM)
    # Leaf height: one storey for ordinary doors; full span for gates.
    wall_h = mx[2] - mn[2]
    if "gate" in door.asset_id:
        open_h = wall_h * h_frac
    else:
        open_h = min(wall_h, cap) * h_frac
    sill_z = mn[2] + min(wall_h, cap) * sill_frac
    head_z = sill_z + open_h
    # Shrink slightly so kissing jambs outside the void do not false-positive.
    inset = max(TOL_CM * 0.5, 2.0)
    if dx >= dy:
        # Run along X; thickness along Y.
        run0 = mn[0] + dx * (1.0 - w_frac) * 0.5 + inset
        run1 = mx[0] - dx * (1.0 - w_frac) * 0.5 - inset
        t0 = mn[1] - TOL_CM
        t1 = mx[1] + TOL_CM
    else:
        run0 = mn[1] + dy * (1.0 - w_frac) * 0.5 + inset
        run1 = mx[1] - dy * (1.0 - w_frac) * 0.5 - inset
        t0 = mn[0] - TOL_CM
        t1 = mx[0] + TOL_CM
        return (
            (t0, run0, sill_z + inset),
            (t1, run1, head_z - inset),
        )
    return (
        (run0, t0, sill_z + inset),
        (run1, t1, head_z - inset),
    )


def balcony_access_prism(door: SolidPlacement, deck: SolidPlacement) -> AABB:
    """Corridor from balcony door onto the deck (near-host band only).

    Does **not** extend to the front rail — that edge is meant to be guarded.
    """
    dmn, dmx = _aabb(door)
    kmn, kmx = _aabb(deck)
    face = _face_of(door)
    z0 = max(dmn[2], kmn[2]) + TOL_CM
    z1 = min(dmn[2] + min(STOREY_CM, dmx[2] - dmn[2]) * 0.85, kmx[2] + STOREY_CM * 0.5)
    band = MODULE_CM * 0.40
    if face in ("south", "north"):
        x0 = max(dmn[0], kmn[0]) + MODULE_CM * 0.18
        x1 = min(dmx[0], kmx[0]) - MODULE_CM * 0.18
        if face == "south":
            # Host is on the +Y side of the deck; access band hugs that edge.
            y0, y1 = kmx[1] - band, dmx[1] + TOL_CM
        else:
            y0, y1 = dmn[1] - TOL_CM, kmn[1] + band
        return ((x0, y0, z0), (x1, y1, z1))
    y0 = max(dmn[1], kmn[1]) + MODULE_CM * 0.18
    y1 = min(dmx[1], kmx[1]) - MODULE_CM * 0.18
    if face == "west":
        x0, x1 = kmx[0] - band, dmx[0] + TOL_CM
    else:
        x0, x1 = dmn[0] - TOL_CM, kmn[0] + band
    return ((x0, y0, z0), (x1, y1, z1))


def _overlap_volume(a: AABB, b: AABB) -> float:
    (amn, amx), (bmn, bmx) = a, b
    ox = min(amx[0], bmx[0]) - max(amn[0], bmn[0])
    oy = min(amx[1], bmx[1]) - max(amn[1], bmn[1])
    oz = min(amx[2], bmx[2]) - max(amn[2], bmn[2])
    if ox <= 0 or oy <= 0 or oz <= 0:
        return 0.0
    return ox * oy * oz


def _is_opening_blocker(p: SolidPlacement) -> bool:
    if p.asset_id in _OPENING_BLOCKERS_ASSETS:
        return True
    if p.tags & _OPENING_BLOCKERS_TAGS:
        return True
    if "door_surround" in p.tags or "jamb" in p.tags or "lintel" in p.tags:
        return True
    return False


def check_doorway_opening_clear(assembly: Assembly) -> List[Failure]:
    """Critical if any shell/detail solid occupies a door aperture prism."""
    failures: List[Failure] = []
    doors = [p for p in assembly.placements if _is_door_wall(p)]
    for door in doors:
        prism = door_aperture_prism(door)
        pmin, pmax = prism
        if any(pmax[i] <= pmin[i] for i in range(3)):
            continue
        for p in assembly.placements:
            if p.piece_id == door.piece_id:
                continue
            if p.kind in ("floor", "ground", "stair", "roof"):
                continue
            if not _is_opening_blocker(p) and p.asset_id not in _APPROACH_WALK_ASSETS:
                continue
            vol = _overlap_volume(prism, _aabb(p))
            if vol <= 0.0:
                continue
            # Approach slabs may kiss the threshold — only fail if they deeply
            # occupy the opening (more than a thin sill strip).
            if p.asset_id in _APPROACH_WALK_ASSETS:
                if vol < (MODULE_CM * 0.15) ** 3:
                    continue
            failures.append(
                Failure(
                    check=CHECK_DOORWAY_OPENING_CLEAR,
                    message=(
                        f"{p.piece_id} ({p.asset_id}) intersects doorway opening "
                        f"of {door.piece_id} (overlap_cm3≈{vol:.0f})"
                    ),
                    world_xyz=_centre(_aabb(p)),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


def _deck_exposed_edges(
    deck: SolidPlacement, host_face: str
) -> Dict[str, Tuple[str, AABB]]:
    """Named exposed edges → (tangent_axis 'x'|'y', edge slab AABB for mounting)."""
    mn, mx = _aabb(deck)
    t = max(WALL_T_CM * 0.35, 8.0)
    z0, z1 = mn[2] - TOL_CM, mx[2] + STOREY_CM * 0.45
    edges: Dict[str, Tuple[str, AABB]] = {}
    # Always expose the three non-host sides.
    if host_face == "south":
        edges["front"] = ("x", ((mn[0], mn[1] - t, z0), (mx[0], mn[1] + t, z1)))
        edges["west"] = ("y", ((mn[0] - t, mn[1], z0), (mn[0] + t, mx[1], z1)))
        edges["east"] = ("y", ((mx[0] - t, mn[1], z0), (mx[0] + t, mx[1], z1)))
    elif host_face == "north":
        edges["front"] = ("x", ((mn[0], mx[1] - t, z0), (mx[0], mx[1] + t, z1)))
        edges["west"] = ("y", ((mn[0] - t, mn[1], z0), (mn[0] + t, mx[1], z1)))
        edges["east"] = ("y", ((mx[0] - t, mn[1], z0), (mx[0] + t, mx[1], z1)))
    elif host_face == "west":
        edges["front"] = ("y", ((mn[0] - t, mn[1], z0), (mn[0] + t, mx[1], z1)))
        edges["south"] = ("x", ((mn[0], mn[1] - t, z0), (mx[0], mn[1] + t, z1)))
        edges["north"] = ("x", ((mn[0], mx[1] - t, z0), (mx[0], mx[1] + t, z1)))
    else:  # east
        edges["front"] = ("y", ((mx[0] - t, mn[1], z0), (mx[0] + t, mx[1], z1)))
        edges["south"] = ("x", ((mn[0], mn[1] - t, z0), (mx[0], mn[1] + t, z1)))
        edges["north"] = ("x", ((mn[0], mx[1] - t, z0), (mx[0], mx[1] + t, z1)))
    return edges


def _rail_run_axis(p: SolidPlacement) -> str:
    mn, mx = _aabb(p)
    return "x" if (mx[0] - mn[0]) >= (mx[1] - mn[1]) else "y"


def check_balcony_rail_contracts(assembly: Assembly) -> List[Failure]:
    """Rails on exposed deck edges, correct yaw, access gap, completeness."""
    failures: List[Failure] = []
    by_id = {p.piece_id: p for p in assembly.placements}
    decks = [
        p
        for p in assembly.placements
        if "balcony_deck" in p.tags or p.asset_id == "balcony_deck"
    ]
    for deck in decks:
        hid = None
        for t in deck.tags:
            if t.startswith("host:"):
                hid = t.split(":", 1)[1]
                break
        door = by_id.get(hid) if hid else None
        if door is None:
            door = next(
                (
                    p
                    for p in assembly.placements
                    if "balcony_door" in p.tags
                    and p.level == deck.level
                    and p.cell == deck.cell
                ),
                None,
            )
        host_face = _face_of(door) if door is not None else _face_of(deck)
        edges = _deck_exposed_edges(deck, host_face)
        rails = [
            p
            for p in assembly.placements
            if "balcony_guard" in p.tags
            and (
                (hid and f"host:{hid}" in p.tags)
                or (p.cell == deck.cell and p.level == deck.level)
            )
        ]
        if len(rails) < len(edges):
            failures.append(
                Failure(
                    check=CHECK_BALCONY_GUARD_COMPLETE,
                    message=(
                        f"balcony deck {deck.piece_id} needs guards on "
                        f"{sorted(edges)} — found {len(rails)}"
                    ),
                    world_xyz=_centre(_aabb(deck)),
                    piece_id=deck.piece_id,
                    critical=True,
                )
            )

        covered: Set[str] = set()
        for rail in rails:
            yaw = int(round(float(rail.yaw))) % 360
            if yaw % 90 != 0:
                failures.append(
                    Failure(
                        check=CHECK_BALCONY_RAIL_ORIENTATION,
                        message=f"{rail.piece_id} yaw {rail.yaw} not axis-aligned",
                        world_xyz=None,
                        piece_id=rail.piece_id,
                        critical=True,
                    )
                )
                continue
            run = _rail_run_axis(rail)
            matched = None
            best_vol = 0.0
            for name, (axis, edge_aabb) in edges.items():
                vol = _overlap_volume(_aabb(rail), edge_aabb)
                if vol > best_vol:
                    best_vol = vol
                    matched = (name, axis)
            if matched is None or best_vol <= 0.0:
                failures.append(
                    Failure(
                        check=CHECK_BALCONY_RAIL_ON_EDGE,
                        message=(
                            f"{rail.piece_id} is not mounted on an exposed "
                            f"edge of {deck.piece_id}"
                        ),
                        world_xyz=_centre(_aabb(rail)),
                        piece_id=rail.piece_id,
                        critical=True,
                    )
                )
            else:
                name, axis = matched
                covered.add(name)
                if run != axis:
                    failures.append(
                        Failure(
                            check=CHECK_BALCONY_RAIL_ORIENTATION,
                            message=(
                                f"{rail.piece_id} run axis {run} != edge "
                                f"{name} tangent {axis}"
                            ),
                            world_xyz=_centre(_aabb(rail)),
                            piece_id=rail.piece_id,
                            critical=True,
                        )
                    )

            # Host-wall edge forbidden: rail centre of mass near host face.
            dmn, dmx = _aabb(deck)
            rmn, rmx = _aabb(rail)
            rcx = 0.5 * (rmn[0] + rmx[0])
            rcy = 0.5 * (rmn[1] + rmx[1])
            host_band = WALL_T_CM * 1.25
            on_host = False
            if host_face == "south" and rcy > dmx[1] - host_band:
                on_host = True
            elif host_face == "north" and rcy < dmn[1] + host_band:
                on_host = True
            elif host_face == "west" and rcx > dmx[0] - host_band:
                on_host = True
            elif host_face == "east" and rcx < dmn[0] + host_band:
                on_host = True
            if on_host:
                failures.append(
                    Failure(
                        check=CHECK_BALCONY_RAIL_ON_EDGE,
                        message=(
                            f"{rail.piece_id} sits on host-wall edge of "
                            f"{deck.piece_id} (must leave access)"
                        ),
                        world_xyz=_centre(_aabb(rail)),
                        piece_id=rail.piece_id,
                        critical=True,
                    )
                )

        if door is not None:
            access = balcony_access_prism(door, deck)
            for rail in rails:
                if int(round(float(rail.yaw))) % 90 != 0:
                    continue
                vol = _overlap_volume(access, _aabb(rail))
                if vol > (MODULE_CM * 0.08) ** 3:
                    failures.append(
                        Failure(
                            check=CHECK_BALCONY_ACCESS_GAP,
                            message=(
                                f"{rail.piece_id} blocks balcony door access "
                                f"gap on {door.piece_id}"
                            ),
                            world_xyz=_centre(_aabb(rail)),
                            piece_id=rail.piece_id,
                            critical=True,
                        )
                    )
            # Completeness: front + both sides required names.
            need = set(edges)
            if need - covered and len(rails) >= len(need):
                # Rails exist but none matched some edges.
                failures.append(
                    Failure(
                        check=CHECK_BALCONY_GUARD_COMPLETE,
                        message=(
                            f"balcony {deck.piece_id} missing edge guards "
                            f"{sorted(need - covered)}"
                        ),
                        world_xyz=_centre(_aabb(deck)),
                        piece_id=deck.piece_id,
                        critical=True,
                    )
                )
    return failures


def check_balcony_deck_support(assembly: Assembly) -> List[Failure]:
    """Every balcony deck needs ≥1 support/bracket (or explicit wall embed)."""
    failures: List[Failure] = []
    supports = [
        p
        for p in assembly.placements
        if "balcony_support" in p.tags or p.asset_id == "balcony_bracket"
    ]
    for deck in assembly.placements:
        if "balcony_deck" not in deck.tags and deck.asset_id != "balcony_deck":
            continue
        hid = None
        for t in deck.tags:
            if t.startswith("host:"):
                hid = t.split(":", 1)[1]
                break
        mine = [
            s
            for s in supports
            if (hid and f"host:{hid}" in s.tags)
            or (s.cell == deck.cell and s.level == deck.level)
        ]
        if not mine:
            failures.append(
                Failure(
                    check=CHECK_BALCONY_DECK_SUPPORT,
                    message=f"balcony deck {deck.piece_id} has no brackets/supports",
                    world_xyz=_centre(_aabb(deck)),
                    piece_id=deck.piece_id,
                    critical=True,
                )
            )
            continue
        # At least one support must vertically meet the deck underside.
        dmn, dmx = _aabb(deck)
        ok = False
        for s in mine:
            smn, smx = _aabb(s)
            ox = min(dmx[0], smx[0]) - max(dmn[0], smn[0])
            oy = min(dmx[1], smx[1]) - max(dmn[1], smn[1])
            # Support top near deck bottom.
            if ox > -TOL_CM and oy > -TOL_CM and abs(smx[2] - dmn[2]) <= WALL_T_CM * 2:
                ok = True
                break
        if not ok:
            failures.append(
                Failure(
                    check=CHECK_BALCONY_DECK_SUPPORT,
                    message=(
                        f"balcony deck {deck.piece_id} supports do not meet "
                        "deck underside"
                    ),
                    world_xyz=_centre(_aabb(deck)),
                    piece_id=deck.piece_id,
                    critical=True,
                )
            )
    return failures


def check_shell_attachment(assembly: Assembly) -> List[Failure]:
    """Sills/hoods/canopies/planters must kiss a host wall (connection class)."""
    failures: List[Failure] = []
    walls = [p for p in assembly.placements if p.kind == "wall"]
    for p in assembly.placements:
        needs = False
        if p.asset_id in (
            "window_sill",
            "window_hood",
            "window_box",
            "porch_roof",
        ):
            needs = True
        if {"window_sill", "window_hood", "sill", "hood", "canopy", "awning"} & set(
            p.tags
        ):
            needs = True
        if not needs:
            continue
        pa = _aabb(p)
        kissed = False
        for w in walls:
            if w.level != p.level and "porch_roof" not in p.tags and "canopy" not in p.tags:
                # Canopy may sit just above door head on same host level.
                if abs(w.level - p.level) > 0 and w.cell != p.cell:
                    continue
            wa = _aabb(w)
            # Expand wall AABB slightly outward for projection pieces.
            expand = WALL_T_CM + TOL_CM
            wmin = (wa[0][0] - expand, wa[0][1] - expand, wa[0][2] - expand)
            wmax = (wa[1][0] + expand, wa[1][1] + expand, wa[1][2] + expand)
            if aabb_intersects(pa[0], pa[1], wmin, wmax):
                kissed = True
                break
        if not kissed:
            failures.append(
                Failure(
                    check=CHECK_SHELL_ATTACHMENT,
                    message=f"{p.piece_id} ({p.asset_id}) not attached to any host wall",
                    world_xyz=_centre(pa),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


def check_stair_yaw_ortho(assembly: Assembly) -> List[Failure]:
    """Non-spiral stairs must be axis-aligned (0/90/180/270)."""
    failures: List[Failure] = []
    for p in assembly.placements:
        if p.kind != "stair":
            continue
        if "spiral" in p.asset_id or "spiral" in p.tags:
            continue
        yaw = int(round(float(p.yaw))) % 360
        if yaw % 90 != 0:
            failures.append(
                Failure(
                    check=CHECK_STAIR_YAW_ORTHO,
                    message=f"{p.piece_id} yaw {p.yaw} is not axis-aligned",
                    world_xyz=_centre(_aabb(p)),
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
    return failures


def check_shell_detail_contracts(assembly: Assembly) -> List[Failure]:
    """All K1/K2 / style-shell contract checks (wired into ``validate``)."""
    failures: List[Failure] = []
    failures.extend(check_doorway_opening_clear(assembly))
    failures.extend(check_balcony_rail_contracts(assembly))
    failures.extend(check_balcony_deck_support(assembly))
    failures.extend(check_shell_attachment(assembly))
    failures.extend(check_stair_yaw_ortho(assembly))
    # Merge legacy approach + arch_detail reports when pieces are present.
    try:
        from pae.door_clearance import validate_entrance_approach_clear

        failures.extend(validate_entrance_approach_clear(assembly).failures)
    except Exception:
        pass
    try:
        from pae.arch_detail import validate_arch_details

        if any(
            t in p.tags
            for p in assembly.placements
            for t in ("arch_detail", "balcony_deck", "window_sill", "ground_planter")
        ) or any(
            p.asset_id in ("balcony_deck", "window_sill", "window_hood")
            for p in assembly.placements
        ):
            failures.extend(validate_arch_details(assembly).failures)
    except Exception:
        pass
    return failures


__all__ = [
    "SHELL_DETAIL_CONTRACTS",
    "PieceContract",
    "CHECK_DOORWAY_OPENING_CLEAR",
    "CHECK_BALCONY_RAIL_ON_EDGE",
    "CHECK_BALCONY_RAIL_ORIENTATION",
    "CHECK_BALCONY_ACCESS_GAP",
    "CHECK_BALCONY_GUARD_COMPLETE",
    "CHECK_BALCONY_DECK_SUPPORT",
    "CHECK_SHELL_ATTACHMENT",
    "CHECK_STAIR_YAW_ORTHO",
    "door_aperture_prism",
    "balcony_access_prism",
    "check_shell_detail_contracts",
    "check_doorway_opening_clear",
    "check_balcony_rail_contracts",
    "check_balcony_deck_support",
    "check_shell_attachment",
    "check_stair_yaw_ortho",
]

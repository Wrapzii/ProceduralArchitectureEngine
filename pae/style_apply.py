"""Style-apply post-pass — remap apertures + attach style-shell kit entities.

Runs AFTER assemble (and usually before/after Stage K detail). Avoids editing
dirty Codex ``assemble.py``: doors, eaves, skip-ground windows, and new shell
pieces are applied here from the resolved StylePack.

Determinism: every placement derives from ``(style_id, seed)`` + host piece ids.
Same (spec, seed, pack) → identical shell signature.

Placement rules (handbook):
  * Face from ``band_faces_of`` / host AABB — never invent south for every wall.
  * Band/pilaster/doorcase via banding ``_place_on_face`` (kiss host, project out).
  * Skip stair / corridor / door-bay cells for forecourt + corner emphasis.
  * Straight-flight stairs that occupy perimeter wall thickness are clipped by
    ``reconcile_stair_wall_clearance`` (placement fix, not a validator exemption).
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.banding import _place_on_face, band_faces_of
from pae.boundary import FACE_YAW, boundary_offset_cm, outward_offset_cm
from pae.contract import EAVE_OVERHANG_CM, MODULE_CM, WALL_T_CM
from pae.primitives.catalog import catalog_by_id
from pae.primitives.roofs import DEFAULT_ROOF_PITCH, roof_pitched_height_cm
from pae.report import Failure, Report
from pae.style_pack import (
    StylePack,
    load_style_pack,
    resolve_door_piece_id,
    resolve_doorcase_asset,
    resolve_eave_overhang_cm,
    resolve_roof_pitch,
    resolve_window_piece_id,
)

STYLE_APPLY_TAG = "style_apply"
STYLE_SHELL_TAG = "style_shell"
STAIR_CLEAR_TAG = "stair_wall_clearance"

_DOOR_ASSETS = (
    "wall_door",
    "wall_door_plain",
    "wall_door_arched",
    "wall_door_double",
    "wall_door_gothic",
    "wall_gate_arch",
    "wall_gate_arch_grand",
    "wall_gate_arch_pointed",
)
_WINDOW_HINTS = ("window", "arrowslit")


def _rng(seed: int, key: str) -> random.Random:
    return random.Random(f"style_apply:{seed}:{key}")


def _is_door_piece(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = p.asset_id
    return aid in _DOOR_ASSETS or "door" in aid or "gate" in aid


def _is_window_piece(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = p.asset_id
    return any(h in aid for h in _WINDOW_HINTS)


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
    """Resolve outward face: tags → band_faces_of → piece_id hint → default."""
    tagged = _face_from_tags(p)
    if tagged in ("south", "north", "west", "east"):
        return tagged
    mapped = faces.get(p.piece_id)
    if mapped in ("south", "north", "west", "east"):
        return mapped
    pid = p.piece_id.lower()
    for face in ("south", "north", "west", "east"):
        if f"_{face}_" in f"_{pid}_" or pid.startswith(f"wall_{face}_"):
            return face
    return default


def _plan_blocked_cells(
    assembly: Assembly,
    floor_plan: Optional[object] = None,
) -> Set[Tuple[int, int]]:
    """Cells that must not host forecourt / corner shell (stair, corridor, door)."""
    blocked: Set[Tuple[int, int]] = set()
    plan = floor_plan
    if plan is None and not isinstance(assembly.floor_plan, dict):
        plan = assembly.floor_plan
    if plan is not None:
        for attr in ("stair_cells", "corridor_cells", "door_cells"):
            cells = getattr(plan, attr, None) or ()
            for cell in cells:
                if isinstance(cell, tuple) and len(cell) == 2:
                    blocked.add((int(cell[0]), int(cell[1])))
        entrance = getattr(plan, "entrance_cell", None)
        if isinstance(entrance, tuple) and len(entrance) == 2:
            blocked.add((int(entrance[0]), int(entrance[1])))
    # Always treat stair solid cells as blocked (covered_cells, not p.cell alone).
    from pae.trim import covered_cells

    for p in assembly.placements:
        if p.kind == "stair":
            blocked |= set(covered_cells(p))
        if _is_door_piece(p):
            blocked.add(p.cell)
            blocked |= set(covered_cells(p))
    return blocked


def reconcile_stair_wall_clearance(assembly: Assembly) -> Assembly:
    """Clip straight flights that occupy exterior wall thickness.

    Assemble emits multi-module straight stairs whose AABB runs to the far module
    edge and kisses the perimeter wall line. ``wall_stair_penetration`` treats
    that kiss as critical. Shrinking the long run by ``WALL_T_CM`` keeps the
    flight inside the well — a placement correction in this module so we do not
    touch Codex-dirty ``assemble.py`` / ``validate.py``.
    """
    if any(STAIR_CLEAR_TAG in p.tags for p in assembly.placements):
        return assembly

    updated: List[SolidPlacement] = []
    changed = False
    for p in assembly.placements:
        if p.kind != "stair" or "spiral" in p.tags:
            updated.append(p)
            continue
        if p.asset_id not in ("stair_straight", "stair_grand", "stair_monumental"):
            # Still clip generic straight-ish kits whose long axis ≥ 1.5 modules.
            pass
        sx, sy, sz = p.size_cm
        long_run = max(sx, sy)
        if long_run < MODULE_CM * 1.5:
            updated.append(p)
            continue
        if sx >= sy:
            new_size = (max(MODULE_CM, sx - WALL_T_CM), sy, sz)
        else:
            new_size = (sx, max(MODULE_CM, sy - WALL_T_CM), sz)
        if new_size == p.size_cm:
            updated.append(p)
            continue
        changed = True
        updated.append(
            replace(
                p,
                size_cm=new_size,
                tags=frozenset(p.tags) | frozenset({STAIR_CLEAR_TAG}),
            )
        )
    if not changed:
        return assembly
    return replace(assembly, placements=updated)


def _remap_apertures(
    placements: List[SolidPlacement],
    pack: StylePack,
) -> List[SolidPlacement]:
    door_id = resolve_door_piece_id(pack)
    window_id = resolve_window_piece_id(pack)
    catalog = catalog_by_id()
    out: List[SolidPlacement] = []
    for p in placements:
        if _is_door_piece(p):
            # Keep tower / interior / service leaves alone.
            tags = p.tags
            if tags & frozenset(
                {
                    "tower_entry",
                    "interior",
                    "party",
                    "stair_landing_clear",
                    "service",
                    "postern",
                }
            ):
                out.append(p)
                continue
            if "entrance_role_service" in tags or "entrance_role_postern" in tags:
                out.append(p)
                continue
            new_size = p.size_cm
            if door_id in catalog:
                proto = catalog[door_id].size_cm
                # Preserve multi-storey spans; swap XY thickness/run from kit.
                new_size = (proto[0], proto[1], p.size_cm[2])
            out.append(
                replace(
                    p,
                    asset_id=door_id,
                    size_cm=new_size,
                    tags=frozenset(p.tags) | frozenset({STYLE_APPLY_TAG, f"door:{door_id}"}),
                )
            )
            continue
        if _is_window_piece(p):
            if pack.window.skip_ground and p.level == 0:
                # Defensive: blank the ground glazing / slits.
                out.append(
                    replace(
                        p,
                        asset_id="wall_plain",
                        tags=frozenset(p.tags)
                        | frozenset({STYLE_APPLY_TAG, "skip_ground"}),
                    )
                )
                continue
            new_size = p.size_cm
            if window_id in catalog:
                proto = catalog[window_id].size_cm
                new_size = (proto[0], proto[1], p.size_cm[2])
            out.append(
                replace(
                    p,
                    asset_id=window_id,
                    size_cm=new_size,
                    tags=frozenset(p.tags)
                    | frozenset({STYLE_APPLY_TAG, f"window:{window_id}"}),
                )
            )
            continue
        out.append(p)
    return out


def _apply_roof_pitch_and_eaves(
    placements: List[SolidPlacement],
    pack: StylePack,
) -> List[SolidPlacement]:
    target_pitch = resolve_roof_pitch(pack)
    target_oh = resolve_eave_overhang_cm(pack)
    delta_oh = float(target_oh) - float(EAVE_OVERHANG_CM)
    out: List[SolidPlacement] = []
    for p in placements:
        aid = p.asset_id
        if not (p.kind == "roof" or aid.startswith("roof_")):
            out.append(p)
            continue
        sx, sy, sz = p.size_cm
        ox, oy, oz = p.offset_cm
        new_sz = sz
        if aid in ("roof_pitched_slope", "roof_hip", "roof_gable_infill"):
            # Rescale ridge height to pack pitch (assemble may have used a milder pitch).
            base = roof_pitched_height_cm(DEFAULT_ROOF_PITCH)
            target_h = roof_pitched_height_cm(target_pitch)
            if base > 1e-6:
                new_sz = max(FLOOR_LIKE_MIN, sz * (target_h / base))
            else:
                new_sz = target_h
        new_sx, new_sy = sx, sy
        new_ox, new_oy = ox, oy
        if abs(delta_oh) > 0.5 and aid.startswith("roof_"):
            # Grow footprint + shift min-corner so eaves deepen equally.
            new_sx = sx + 2.0 * delta_oh
            new_sy = sy + 2.0 * delta_oh
            new_ox = ox - delta_oh
            new_oy = oy - delta_oh
        out.append(
            replace(
                p,
                size_cm=(new_sx, new_sy, new_sz),
                offset_cm=(new_ox, new_oy, oz),
                tags=frozenset(p.tags)
                | frozenset(
                    {
                        STYLE_APPLY_TAG,
                        f"eave_oh:{int(round(target_oh))}",
                        f"pitch:{target_pitch:.2f}",
                    }
                ),
            )
        )
    return out


# Avoid importing FLOOR_T just for a clamp name.
FLOOR_LIKE_MIN = 20.0


def _south_exterior_host_walls(
    placements: Sequence[SolidPlacement],
    faces: Dict[str, str],
) -> List[SolidPlacement]:
    """South-facing exterior walls at level 0 (approach façade)."""
    hosts: List[SolidPlacement] = []
    for p in placements:
        if p.kind != "wall" or p.level != 0:
            continue
        if "exterior" not in p.tags and "wall" not in p.tags:
            continue
        face = _face_for_host(p, faces)
        if face == "south":
            hosts.append(p)
    if hosts:
        return hosts
    # Fallback: any L0 exterior wall with yaw matching a south run.
    return [
        p
        for p in placements
        if p.kind == "wall"
        and p.level == 0
        and p.yaw in (90, 270)
        and "window" not in p.asset_id
        and _face_for_host(p, faces, default="south") == "south"
    ]


def _door_hosts(placements: Sequence[SolidPlacement]) -> List[SolidPlacement]:
    return [p for p in placements if _is_door_piece(p) and p.level == 0]


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


def _add_forecourt(
    assembly: Assembly,
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    seed: int,
    faces: Dict[str, str],
    blocked: Set[Tuple[int, int]],
) -> List[SolidPlacement]:
    if not pack.shell.forecourt:
        return placements
    catalog = catalog_by_id()
    # Prefer shorter planter walls when pack asks for modest forecourt language.
    wall_id = "planter_wall" if "planter_wall" in catalog else "forecourt_wall"
    if pack.shell.coping and "forecourt_wall" in catalog:
        wall_id = "forecourt_wall"  # taller capped garden / terrace wall
    if wall_id not in catalog:
        return placements
    desc = catalog[wall_id]
    from pae.door_clearance import all_door_approach_cells

    # Hard rule: never place forecourt in door approach corridor (door bay +
    # outward depth + lateral gap). Prefer not placing over demoting checks.
    approach = all_door_approach_cells(placements, faces=faces)
    forbidden: Set[Tuple[int, int]] = set(blocked) | approach
    for d in _door_hosts(placements):
        forbidden.add(d.cell)

    hosts = _south_exterior_host_walls(placements, faces)
    if not hosts:
        return placements

    # Prefer unique cells along the south run, skip door/stair/corridor bays.
    seen: Set[Tuple[int, int]] = set()
    extra: List[SolidPlacement] = []
    rng = _rng(seed, "forecourt")
    for host in sorted(hosts, key=lambda p: (p.cell[0], p.cell[1], p.piece_id)):
        cell = host.cell
        if cell in seen or cell in forbidden:
            continue
        # Place one cell OUTWARD (south → y-1); must not land on approach cells.
        out_cell = (cell[0], cell[1] - 1)
        if out_cell in seen or out_cell in forbidden:
            continue
        seen.add(cell)
        seen.add(out_cell)
        face = "south"
        yaw = FACE_YAW[face]
        # Sit the wall on the north edge of the outward cell (kissing the façade).
        off = boundary_offset_cm("north", desc.size_cm, yaw=yaw, z_cm=0.0)
        _ = rng
        pid = f"forecourt_{out_cell[0]}_{out_cell[1]}_{len(extra)}"
        extra.append(
            _place_from_desc(
                piece_id=pid,
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
                        STYLE_APPLY_TAG,
                        STYLE_SHELL_TAG,
                        "face_south",
                        "attached",
                    }
                ),
            )
        )
    return placements + extra


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
    """Wall-flush trim strip — jamb / lintel / course segment (not a freestanding portal)."""
    from pae.contract import placement_world_aabb

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
        run_len = max(WALL_T_CM * 0.5, span * run_len_frac)
        run_start = hmn[0] + span * run0_frac
        size = (proj_cm, run_len, height_cm)
        ox = run_start + run_len
        oy = (hmn[1] - proj_cm) if face == "south" else hmx[1]
    else:
        yaw = 0
        span = hmx[1] - hmn[1]
        run_len = max(WALL_T_CM * 0.5, span * run_len_frac)
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
    bay_run_cm: float = MODULE_CM,
) -> Tuple[int, Tuple[float, float, float]]:
    """Outward projection centred on the door bay run."""
    yaw, off = outward_offset_cm(face, size_cm, z_cm=z_cm)
    ox, oy, oz = off
    depth, width, _h = size_cm
    if face in ("south", "north"):
        # size = (depth along outward, width along run) after outward yaw.
        off = (ox + (bay_run_cm - width) * 0.5, oy, oz)
    else:
        off = (ox, oy + (bay_run_cm - width) * 0.5, oz)
    _ = depth
    return yaw, off


def _add_doorcase_and_porch(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    seed: int,
    faces: Dict[str, str],
) -> List[SolidPlacement]:
    """Legible entrance from style refs: steps + raised deck + canopy ABOVE door.

    Deleted languages (do not reintroduce):
      * freestanding doorcase_* U-portals on the ground
      * porch_post rails sitting on the stoop

    Kept / added:
      * wall-flush jambs + lintel (door surround at opening)
      * shallow steps (stoop)
      * porch_slab / shop platform (raised deck)
      * porch_roof canopy at door-head height covering the approach
    """
    catalog = catalog_by_id()
    doors = _door_hosts(placements)
    if not doors:
        return placements
    extra: List[SolidPlacement] = []
    rng = _rng(seed, "doorcase")
    _ = rng
    doorcase_id = resolve_doorcase_asset(pack) or "none"
    want_surround = doorcase_id not in ("", "none")
    jamb_w_frac = 0.12
    if "grand" in doorcase_id:
        jamb_w_frac = 0.14
    elif "gothic" in doorcase_id or "arched" in doorcase_id:
        jamb_w_frac = 0.13

    want_steps = bool(pack.shell.stoop or pack.shell.porch_roof or pack.shell.shop_platform)
    want_slab = bool(pack.shell.shop_platform or pack.shell.porch_roof)
    want_canopy = bool(pack.shell.porch_roof)

    for door in sorted(doors, key=lambda p: p.piece_id):
        face = _face_for_host(door, faces, default="south") or "south"
        # One-storey leaf height — never follow multi-storey spanning wall Z
        # (that produced ~11 m jamb columns in the doorway).
        from pae.contract import STOREY_CM as _STOREY

        leaf_h = min(float(door.size_cm[2]), float(_STOREY))
        w_frac = 0.40
        h_frac = 0.84
        try:
            from pae.primitives.apertures import get_profile
            from pae.primitives.catalog import catalog_by_id as _cat

            desc = _cat().get(door.asset_id)
            pname = getattr(desc, "profile", None) if desc is not None else None
            if pname:
                prof = get_profile(str(pname))
                w_frac = float(prof.width_frac)
                h_frac = float(prof.height_frac)
        except Exception:
            if "double" in door.asset_id:
                w_frac, h_frac = 0.62, 0.80
            elif "gate" in door.asset_id:
                w_frac, h_frac = 0.88, 0.90
        door_h = max(WALL_T_CM * 4.0, leaf_h * h_frac)
        margin = max(0.04, (1.0 - w_frac) * 0.5)
        # Jambs must live entirely in the side margins — never in the opening.
        jamb_len = min(jamb_w_frac, margin * 0.85)
        jamb_inset = max(0.01, (margin - jamb_len) * 0.5)
        lintel_h = max(18.0, door_h * 0.10)
        base_z = door.offset_cm[2]
        shell_tags = frozenset(
            {STYLE_APPLY_TAG, STYLE_SHELL_TAG, "attached", f"face_{face}", "entrance"}
        )

        if want_surround and "band_pilaster" in catalog and "band_course" in catalog:
            proj = WALL_T_CM * 0.35
            base_tags = shell_tags | frozenset(
                {"door_surround", f"doorcase:{doorcase_id}"}
            )
            for side, run0 in (
                ("L", jamb_inset),
                ("R", 1.0 - jamb_inset - jamb_len),
            ):
                extra.append(
                    _place_face_strip(
                        "band_pilaster",
                        door,
                        face,
                        z_cm=base_z,
                        run0_frac=run0,
                        run_len_frac=jamb_len,
                        height_cm=door_h,
                        proj_cm=proj,
                        piece_id=f"door_jamb_{side}_{door.piece_id}",
                        tags=base_tags | frozenset({"jamb", "vertical"}),
                    )
                )
            # Lintel spans the opening + jambs, sitting on the head line.
            lintel_run0 = jamb_inset
            lintel_len = 1.0 - 2.0 * jamb_inset
            extra.append(
                _place_face_strip(
                    "band_course",
                    door,
                    face,
                    z_cm=base_z + door_h,
                    run0_frac=lintel_run0,
                    run_len_frac=lintel_len,
                    height_cm=lintel_h,
                    proj_cm=proj * 1.15,
                    piece_id=f"door_lintel_{door.piece_id}",
                    tags=base_tags | frozenset({"lintel", "horizontal"}),
                )
            )

        slab_h = 0.0
        if want_slab and "porch_slab" in catalog:
            slab = catalog["porch_slab"]
            depth = MODULE_CM * (0.62 if pack.shell.shop_platform else 0.50)
            width = MODULE_CM * 0.95
            slab_h = slab.size_cm[2]
            size = (depth, width, slab_h)
            yaw, off = _outward_centered(face, size, z_cm=0.0)
            extra.append(
                _place_from_desc(
                    piece_id=f"porch_slab_{door.piece_id}",
                    asset_id=slab.id,
                    kind=slab.kind,
                    cell=door.cell,
                    level=0,
                    yaw=yaw,
                    offset_cm=off,
                    size_cm=size,
                    tags=frozenset(slab.tags)
                    | shell_tags
                    | frozenset({"porch", "deck", "platform"}),
                )
            )

        if want_steps and "steps_external" in catalog:
            steps = catalog["steps_external"]
            # Steps sit just proud of the slab edge (or door if no slab).
            depth = MODULE_CM * 0.38
            width = MODULE_CM * 0.85
            height = max(steps.size_cm[2], slab_h * 1.05 if slab_h else steps.size_cm[2])
            size = (depth, width, height)
            yaw, off = _outward_centered(face, size, z_cm=0.0)
            # Nudge further out so steps read in front of the deck.
            ox, oy, oz = off
            nudge = MODULE_CM * 0.18
            if face == "south":
                off = (ox, oy - nudge, oz)
            elif face == "north":
                off = (ox, oy + nudge, oz)
            elif face == "west":
                off = (ox - nudge, oy, oz)
            else:
                off = (ox + nudge, oy, oz)
            extra.append(
                _place_from_desc(
                    piece_id=f"stoop_{door.piece_id}",
                    asset_id=steps.id,
                    kind=steps.kind,
                    cell=door.cell,
                    level=0,
                    yaw=yaw,
                    offset_cm=off,
                    size_cm=size,
                    tags=frozenset(steps.tags)
                    | shell_tags
                    | frozenset({"stoop", "approach", "steps"}),
                )
            )

        if want_canopy and "porch_roof" in catalog:
            canopy = catalog["porch_roof"]
            # Deep face-attached band at one-storey door-head Z (never roof-line).
            proj = MODULE_CM * (0.65 if "grand" in doorcase_id else 0.55)
            thick = canopy.size_cm[2]
            canopy_z = base_z + door_h + lintel_h + WALL_T_CM * 0.05 if want_surround else (
                base_z + door_h + WALL_T_CM * 0.10
            )
            placed = _place_face_strip(
                "porch_roof",
                door,
                face,
                z_cm=canopy_z,
                run0_frac=jamb_inset if want_surround else 0.01,
                run_len_frac=(1.0 - 2.0 * jamb_inset) if want_surround else 0.98,
                height_cm=thick,
                proj_cm=proj,
                piece_id=f"porch_roof_{door.piece_id}",
                tags=shell_tags
                | frozenset({"porch", "awning", "canopy", "above_door", "horizontal"}),
            )
            extra.append(placed)
    return placements + extra


def _add_buttress_corners(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    faces: Dict[str, str],
    blocked: Set[Tuple[int, int]],
) -> List[SolidPlacement]:
    """Corner vertical emphasis — ``band_pilaster`` via banding face attach.

    Fortress ``buttress_outward`` is critical for ``buttress`` assets; on M1/M2
    style sketches we want a vertical corner read without that fortress check.
    """
    if not pack.shell.buttress_corners:
        return placements
    catalog = catalog_by_id()
    asset = "band_pilaster" if "band_pilaster" in catalog else None
    if asset is None:
        return placements
    exteriors = [
        p
        for p in placements
        if p.kind == "wall"
        and p.level == 0
        and p.piece_id in faces
        and p.cell not in blocked
    ]
    if not exteriors:
        return placements
    xs = [p.cell[0] for p in exteriors]
    ys = [p.cell[1] for p in exteriors]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    corner_cells = {(x0, y0), (x1, y0), (x0, y1), (x1, y1)}
    # One host per corner cell — prefer the face that reads as the corner edge.
    by_cell: Dict[Tuple[int, int], List[SolidPlacement]] = {}
    for p in exteriors:
        if p.cell in corner_cells:
            by_cell.setdefault(p.cell, []).append(p)
    extra: List[SolidPlacement] = []
    for cell in sorted(by_cell):
        hosts = by_cell[cell]
        # Prefer a host whose face is an exterior cardinal on this corner.
        hosts_sorted = sorted(
            hosts,
            key=lambda p: (
                0 if _face_for_host(p, faces) in ("south", "east", "north", "west") else 1,
                p.piece_id,
            ),
        )
        host = hosts_sorted[0]
        face = _face_for_host(host, faces)
        if face is None:
            continue
        placed = _place_on_face(
            asset,
            host,
            face,
            z_cm=host.offset_cm[2],
            suffix="corner",
            extra_tags=frozenset(
                {
                    STYLE_APPLY_TAG,
                    STYLE_SHELL_TAG,
                    "corner_emphasis",
                    "attached",
                    "vertical",
                    f"face_{face}",
                }
            ),
        )
        # Match host storey height so pack storeys do not leave a floating head.
        sx, sy, _sz = placed.size_cm
        host_h = host.size_cm[2]
        extra.append(
            replace(
                placed,
                piece_id=f"corner_vert_{host.piece_id}",
                size_cm=(sx, sy, host_h),
            )
        )
    return placements + extra


def _add_bargeboard_and_chimney(
    placements: List[SolidPlacement],
    pack: StylePack,
    *,
    seed: int,
    faces: Dict[str, str],
) -> List[SolidPlacement]:
    catalog = catalog_by_id()
    extra: List[SolidPlacement] = []
    gables = [
        p
        for p in placements
        if p.asset_id == "roof_gable_infill" or "gable" in p.asset_id
    ]
    if pack.shell.bargeboard and "bargeboard" in catalog and gables:
        # Band attachment requires a *wall* host — place on the gable-end
        # exterior wall at the roof Z, not on the roof mesh itself.
        end_walls = [
            p
            for p in placements
            if p.kind == "wall"
            and p.piece_id in faces
            and faces[p.piece_id] in ("west", "east")
        ]
        # Prefer topmost wall on each end face.
        by_face: Dict[str, List[SolidPlacement]] = {"west": [], "east": []}
        for w in end_walls:
            by_face[faces[w.piece_id]].append(w)
        for face, walls in by_face.items():
            if not walls:
                continue
            host = sorted(walls, key=lambda p: (-p.level, p.piece_id))[0]
            # Raise to top of host wall (under eaves / gable).
            z_cm = host.offset_cm[2] + max(0.0, host.size_cm[2] - catalog["bargeboard"].size_cm[2])
            placed = _place_on_face(
                "bargeboard",
                host,
                face,
                z_cm=z_cm,
                suffix="barge",
                extra_tags=frozenset(
                    {
                        STYLE_APPLY_TAG,
                        STYLE_SHELL_TAG,
                        f"face_{face}",
                        "attached",
                        "roof_trim",
                    }
                ),
            )
            extra.append(replace(placed, piece_id=f"barge_{face}_{host.piece_id}"))
    if pack.shell.chimney_stub and "chimney_stub" in catalog:
        slopes = [
            p
            for p in placements
            if p.asset_id in ("roof_pitched_slope", "roof_hip")
        ]
        if slopes:
            rng = _rng(seed, "chimney")
            host = sorted(slopes, key=lambda p: p.piece_id)[seed % len(slopes)]
            desc = catalog["chimney_stub"]
            # Sit near ridge: mid footprint, top of roof AABB.
            sx, sy, sz = host.size_cm
            ox, oy, oz = host.offset_cm
            cx = ox + sx * 0.55 - desc.size_cm[0] * 0.5
            cy = oy + sy * 0.45 - desc.size_cm[1] * 0.5
            cz = oz + sz * 0.85
            _ = rng
            extra.append(
                _place_from_desc(
                    piece_id=f"chimney_stub_{host.piece_id}",
                    asset_id=desc.id,
                    kind=desc.kind,
                    cell=host.cell,
                    level=host.level,
                    yaw=0,
                    offset_cm=(cx, cy, cz),
                    size_cm=desc.size_cm,
                    tags=frozenset(desc.tags)
                    | frozenset({STYLE_APPLY_TAG, STYLE_SHELL_TAG, "attached"}),
                )
            )
    return placements + extra


def style_shell_signature(assembly: Assembly) -> Tuple[Tuple[str, str], ...]:
    rows = [
        (p.piece_id, p.asset_id)
        for p in assembly.placements
        if STYLE_SHELL_TAG in p.tags or STYLE_APPLY_TAG in p.tags
    ]
    return tuple(sorted(rows))


def count_shell_pieces(assembly: Assembly) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in assembly.placements:
        if STYLE_SHELL_TAG not in p.tags:
            continue
        counts[p.asset_id] = counts.get(p.asset_id, 0) + 1
    return counts


def apply_style_shell(
    assembly: Assembly,
    *,
    style_id: Optional[str] = None,
    seed: int = 0,
    enabled: bool = True,
    floor_plan: Optional[object] = None,
) -> Tuple[Assembly, Report]:
    """Remap apertures + attach style-shell entities. Idempotent via tag."""
    if not enabled:
        return assembly, Report.from_failures([])
    from pae.facade_shell import is_facade_shell_assembly

    if is_facade_shell_assembly(assembly):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="style_apply_shell_skip",
                    message=(
                        "facade_shell assembly — style_apply / K2 dress skipped "
                        "(use Procedural Building → Generate Building)"
                    ),
                    critical=False,
                )
            ]
        )
    if any(STYLE_APPLY_TAG in p.tags for p in assembly.placements):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="style_apply_skip",
                    message="style_apply already applied — skipped",
                    critical=False,
                )
            ]
        )

    # Always clear stair/wall kisses before adding shell (assemble collateral).
    assembly = reconcile_stair_wall_clearance(assembly)

    if not style_id:
        return assembly, Report.from_failures([])

    pack, report = load_style_pack(str(style_id))
    if pack is None or not report.ok:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="style_apply_pack",
                    message=f"style pack {style_id!r} failed to load",
                    critical=True,
                )
            ]
        )

    if floor_plan is not None:
        working_plan = floor_plan
    else:
        working_plan = None

    faces = band_faces_of(assembly)
    blocked = _plan_blocked_cells(assembly, floor_plan=working_plan)

    placements = list(assembly.placements)
    placements = _remap_apertures(placements, pack)
    placements = _apply_roof_pitch_and_eaves(placements, pack)
    placements = _add_forecourt(
        assembly, placements, pack, seed=seed, faces=faces, blocked=blocked
    )
    placements = _add_doorcase_and_porch(
        placements, pack, seed=seed, faces=faces
    )
    placements = _add_buttress_corners(
        placements, pack, faces=faces, blocked=blocked
    )
    placements = _add_bargeboard_and_chimney(
        placements, pack, seed=seed, faces=faces
    )

    # Stable order for determinism.
    placements.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    out = replace(assembly, placements=placements)

    # MP-WS-K2 architectural details (sills / planters / patio / balcony).
    from pae.arch_detail import apply_arch_details

    out, k2report = apply_arch_details(
        out, style_id=style_id, seed=seed, floor_plan=working_plan
    )
    # Forecourt may have been placed before arch_detail; re-filter approach.
    from pae.door_clearance import (
        all_door_approach_cells,
        filter_blocking_from_approach,
        validate_entrance_approach_clear,
    )

    faces2 = band_faces_of(out)
    approach = all_door_approach_cells(out.placements, faces=faces2)
    filtered = filter_blocking_from_approach(out.placements, approach)
    if len(filtered) != len(out.placements):
        out = replace(out, placements=sorted(
            filtered, key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id)
        ))
    clear_report = validate_entrance_approach_clear(out, faces=faces2)
    notes = [
        Failure(
            check="style_apply_ok",
            message=(
                f"style_apply style={style_id} seed={seed} "
                f"shell={sum(1 for p in out.placements if STYLE_SHELL_TAG in p.tags)}"
            ),
            critical=False,
        )
    ]
    notes.extend(k2report.failures)
    notes.extend(clear_report.failures)
    return out, Report.from_failures(notes)


__all__ = [
    "STYLE_APPLY_TAG",
    "STYLE_SHELL_TAG",
    "STAIR_CLEAR_TAG",
    "apply_style_shell",
    "count_shell_pieces",
    "reconcile_stair_wall_clearance",
    "style_shell_signature",
]

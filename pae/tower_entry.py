"""Hall → spiral/tower stairwell doorway (@VAL_TOWER_DOOR).

Places a ``wall_door_*`` on the drum attach face (tag ``tower_entry``) at ground
and each hall landing storey. Existence lives in ``pae.existence.check_tower_entry_door``.

Handbook §2 seven questions:
  1 Touch — attach-face drum rim kisses the hall envelope
  2 Under — hall/tower floor at that storey
  5 Isolation — no (joins drum via same-cell AABB like drum_window)
  6 Use — walk-through → aperture_reachability treats hall floor as landing
  7 Spec — critical ``tower_entry_door`` when spiral / tower stair present

Do not own newel / drum enclosure (@VAL_SPIRAL_SHELL) or crown rampart
(@VAL_TOWER_RAMPART).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from pae.assembly_types import Aperture, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM
from pae.existence import TOWER_ENTRY_TAG
from pae.solver import Volume

StyleLike = Union[Mapping[str, Any], None]

_TOWER_ENTRY_CHORD_CM = MODULE_CM * 0.5


def _tower_exterior_cell(cell: Tuple[int, int], yaw: int) -> Tuple[int, int]:
    cx, cy = cell
    if yaw == 0:
        return (cx - 1, cy)
    if yaw == 90:
        return (cx, cy + 1)
    if yaw == 180:
        return (cx + 1, cy)
    return (cx, cy - 1)


def _tower_entry_shell_pose(
    drum_xy: Tuple[float, float],
    yaw: int,
    *,
    z_off: float,
    height_cm: float,
    chord_cm: float,
    skip_yaw: Optional[int],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Rim pose matching assemble drum-window overlays (thin/long axes baked)."""
    thick = WALL_T_CM
    half = MODULE_CM * 0.5
    radial = half - thick * 0.5
    dx, dy = drum_xy
    shift = max(0.0, half - chord_cm * 0.5)
    bias_x = 0.0
    bias_y = 0.0
    if skip_yaw in (0, 180) and yaw in (90, 270):
        bias_x = shift if skip_yaw == 0 else -shift
    elif skip_yaw in (90, 270) and yaw in (0, 180):
        bias_y = shift if skip_yaw == 270 else -shift

    if yaw == 0:
        size = (thick, chord_cm, height_cm)
        ox, oy = dx - radial + bias_x, dy + bias_y
    elif yaw == 180:
        size = (thick, chord_cm, height_cm)
        ox, oy = dx + radial + bias_x, dy + bias_y
    elif yaw == 90:
        size = (chord_cm, thick, height_cm)
        ox, oy = dx + bias_x, dy + radial + bias_y
    else:
        size = (chord_cm, thick, height_cm)
        ox, oy = dx + bias_x, dy - radial + bias_y
    return size, (ox, oy, z_off)


def place_tower_entry_doors(
    *,
    vol: Volume,
    cell: Tuple[int, int],
    drum_xy: Tuple[float, float],
    skip_yaw: Optional[int],
    body: Optional[Volume],
    door_asset_id: str,
    door_tags: frozenset,
    aperture_world: Callable[[SolidPlacement, str], Tuple[float, float, float]],
    next_piece_id: Callable,
    placements: List[SolidPlacement],
    apertures: List[Aperture],
    counters: Dict[str, int],
) -> int:
    """Emit hall↔drum doors on the attach face. Returns count placed."""
    if skip_yaw is None or body is None:
        return 0
    aid = door_asset_id
    if "door" not in aid and "gate" not in aid:
        aid = "wall_door"
    n_levels = min(vol.storeys, body.storeys)
    hall_cell = _tower_exterior_cell(cell, skip_yaw)
    # Prefer a passable opening height under the storey slab.
    height = min(350.0, STOREY_CM - FLOOR_T_CM)
    chord = min(_TOWER_ENTRY_CHORD_CM, MODULE_CM * 0.55)
    placed = 0
    for level in range(n_levels):
        size, offset = _tower_entry_shell_pose(
            drum_xy,
            skip_yaw,
            z_off=0.0,
            height_cm=height,
            chord_cm=chord,
            skip_yaw=skip_yaw,
        )
        dpid = next_piece_id(counters, f"tower_entry_{skip_yaw}", cell, level)
        tags = set(door_tags) | {"tower", TOWER_ENTRY_TAG}
        sp = SolidPlacement(
            piece_id=dpid,
            asset_id=aid,
            kind="wall",
            cell=cell,
            level=level,
            yaw=skip_yaw,
            offset_cm=offset,
            size_cm=size,
            rotates_about_center=True,
            tags=frozenset(tags),
        )
        placements.append(sp)
        floor_z = level * STOREY_CM
        world = aperture_world(sp, "door")
        apertures.append(
            Aperture(
                piece_id=f"door_{dpid}",
                kind="door",
                wall_piece_id=dpid,
                level=level,
                sill_z_cm=world[2],
                floor_z_cm=floor_z,
                interior_cell=cell,
                exterior_cell=hall_cell,
                world_xyz=world,
            )
        )
        placed += 1
    return placed


def is_tower_entry_piece(p: SolidPlacement) -> bool:
    return TOWER_ENTRY_TAG in p.tags or p.piece_id.startswith("tower_entry_")


__all__ = [
    "place_tower_entry_doors",
    "is_tower_entry_piece",
    "TOWER_ENTRY_TAG",
]

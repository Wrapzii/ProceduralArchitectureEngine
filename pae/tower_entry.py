"""Hall → spiral/tower stairwell doorway (@VAL_TOWER_DOOR).

Places a ``wall_door_*`` on the drum attach face (tag ``tower_entry``) at ground
and each hall landing storey. Existence lives in ``pae.existence.check_tower_entry_door``.

Handbook §2 seven questions:
  1 Touch — attach-face drum rim kisses the hall envelope
  2 Under — hall/tower floor at that storey
  5 Isolation — no (joins drum via same-cell AABB like drum_window)
  6 Use — walk-through → aperture_reachability treats hall floor as landing;
    aperture_sanity requires *both* sides walkable (hall cell + drum cell), not
    an exterior EXTERIOR/COURTYARD role (this is an interior passage)
  7 Spec — critical ``tower_entry_door`` when spiral / tower stair present

Do not own newel / drum enclosure (@VAL_SPIRAL_SHELL) or crown rampart
(@VAL_TOWER_RAMPART).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from pae.assembly_types import Aperture, SolidPlacement
from pae.contract import (
    DRUM_WINDOW_CHORD_FRAC,
    DRUM_WINDOW_HEIGHT_FRAC,
    DRUM_WINDOW_SILL_FRAC,
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    storey_datum_z_cm,
    tower_entry_door_chord_cm,
    tower_entry_door_height_cm,
)
from pae.existence import TOWER_ENTRY_TAG
from pae.plan import CellRole, FloorPlan
from pae.solver import Volume

StyleLike = Union[Mapping[str, Any], None]

_TOWER_ENTRY_CHORD_CM = tower_entry_door_chord_cm()

# Hall / inhabited roles the door must open onto (not WALL_LINE attach cells).
_HALL_WALKABLE = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.STAIR,
        CellRole.DOOR,
        CellRole.CORRIDOR,
        CellRole.CLASSROOM,
        CellRole.ROOM,
        CellRole.HALL,
        CellRole.SERVICE,
        CellRole.ARCADE,
    }
)
# Drum side: stairwell roles — VOID is the open well at the upper landing.
# WALL_LINE is included because keep/gatehouse attach cells are often planned as
# envelope WALL_LINE even when a round drum owns the cell (habitable tower path).
_DRUM_PASSABLE = frozenset(
    {
        CellRole.STAIR,
        CellRole.DOOR,
        CellRole.VOID,
        CellRole.DOUBLE_VOID,
        CellRole.INTERIOR,
        CellRole.WALL_LINE,
    }
)

# Attach yaw → face of the *hall* perimeter wall that abuts the tower
# (opposite the door's outward normal). Used to BFS into inhabited hall cells.
_HALL_WALL_FACE_FOR_YAW: Dict[int, str] = {
    0: "east",
    90: "south",
    180: "west",
    270: "north",
}

_INWARD_DELTA: Dict[str, Tuple[int, int]] = {
    "west": (1, 0),
    "east": (-1, 0),
    "south": (0, 1),
    "north": (0, -1),
}


def _tower_adjacent_cell(cell: Tuple[int, int], yaw: int) -> Tuple[int, int]:
    """Neighbour on the hall side of the attach face (by wall yaw)."""
    cx, cy = cell
    if yaw == 0:
        return (cx - 1, cy)
    if yaw == 90:
        return (cx, cy + 1)
    if yaw == 180:
        return (cx + 1, cy)
    return (cx, cy - 1)


def _resolve_hall_landing_cell(
    tower_cell: Tuple[int, int],
    yaw: int,
    *,
    role_at: Callable[[int, int], Optional[CellRole]],
) -> Optional[Tuple[int, int]]:
    """Step through WALL_LINE attach cells to a walkable hall bay.

    The naive neighbour of a west-attached tower is often WALL_LINE (the hall
    envelope), not INTERIOR — aperture_sanity then reports
    ``exterior side cell not walkable``. Mirror assemble's perimeter door
    resolver: seed from the abutting wall cell and BFS inward.
    """
    face = _HALL_WALL_FACE_FOR_YAW.get(int(yaw) % 360)
    if face is None:
        return None
    wall_cell = _tower_adjacent_cell(tower_cell, yaw)
    if role_at(*wall_cell) in _HALL_WALKABLE:
        return wall_cell

    inward = _INWARD_DELTA[face]
    perp = (-inward[1], inward[0])
    seeds = {
        (wall_cell[0] + inward[0], wall_cell[1] + inward[1]),
        (
            wall_cell[0] + inward[0] + perp[0],
            wall_cell[1] + inward[1] + perp[1],
        ),
        (
            wall_cell[0] + inward[0] - perp[0],
            wall_cell[1] + inward[1] - perp[1],
        ),
        wall_cell,
    }
    for seed in seeds:
        if role_at(*seed) in _HALL_WALKABLE:
            return seed
    queue: List[Tuple[int, int]] = list(seeds)
    seen = set(seeds)
    while queue:
        cx, cy = queue.pop(0)
        role = role_at(cx, cy)
        if role in _HALL_WALKABLE:
            return (cx, cy)
        if role not in (
            CellRole.WALL_LINE,
            CellRole.DOOR,
            CellRole.VOID,
            CellRole.DOUBLE_VOID,
            CellRole.EXTERIOR,
            None,
        ):
            continue
        for dx, dy in (inward, perp, (-perp[0], -perp[1])):
            nxt = (cx + dx, cy + dy)
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return None


def _tower_entry_shell_pose(
    drum_xy: Tuple[float, float],
    yaw: int,
    *,
    z_off: float,
    height_cm: float,
    chord_cm: float,
    skip_yaw: Optional[int],
    radius_cm: float = MODULE_CM,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Rim pose matching assemble drum-window overlays (thin/long axes baked)."""
    thick = WALL_T_CM
    half = float(radius_cm)
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
    floor_plan: Optional[FloorPlan] = None,
    radius_cm: float = MODULE_CM,
    chord_cm: Optional[float] = None,
) -> int:
    """Emit hall↔drum doors on the attach face. Returns count placed.

    Aperture cells: ``interior_cell`` = drum, ``exterior_cell`` = resolved hall
    landing (not the naive WALL_LINE neighbour). Doors are skipped when either
    side is not passable at that storey — keeps aperture_sanity honest without
    demoting the check.
    """
    if skip_yaw is None or body is None:
        return 0
    aid = door_asset_id
    if "door" not in aid and "gate" not in aid:
        aid = "wall_door"
    n_levels = min(vol.storeys, body.storeys)
    if floor_plan is not None:
        n_levels = min(n_levels, len(floor_plan.storeys))
    # This placement is a complete doorway-bearing wall module, not just the
    # clear leaf. The wall must reach the storey plate so upper doorway modules
    # and landings have continuous bearing; its aperture profile owns the actual
    # clear opening height.
    height = STOREY_CM
    chord = _TOWER_ENTRY_CHORD_CM if chord_cm is None else float(chord_cm)
    placed = 0
    for level in range(n_levels):
        if floor_plan is not None and level < len(floor_plan.storeys):
            grid = floor_plan.storeys[level]

            def role_at(x: int, y: int, _g=grid) -> Optional[CellRole]:
                return _g.get(x, y)

            drum_role = role_at(*cell)
            if drum_role not in _DRUM_PASSABLE:
                continue
            hall_cell = _resolve_hall_landing_cell(
                cell, skip_yaw, role_at=role_at
            )
            if hall_cell is None:
                continue
        else:
            # No plan — keep legacy neighbour (tests that stub without a plan).
            hall_cell = _tower_adjacent_cell(cell, skip_yaw)

        size, offset = _tower_entry_shell_pose(
            drum_xy,
            skip_yaw,
            z_off=0.0,
            height_cm=height,
            chord_cm=chord,
            skip_yaw=skip_yaw,
            radius_cm=radius_cm,
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
        floor_z = storey_datum_z_cm(level)
        world = aperture_world(sp, "door")
        apertures.append(
            Aperture(
                piece_id=f"door_{dpid}",
                kind="door",
                wall_piece_id=dpid,
                level=level,
                sill_z_cm=world[2],
                floor_z_cm=floor_z,
                # Drum = interior side of the passage; hall landing = other side.
                # aperture_sanity treats tower_entry as a through-passage (both
                # sides interior-walkable), not an exterior exit.
                interior_cell=cell,
                exterior_cell=hall_cell,
                world_xyz=world,
            )
        )
        placed += 1
    return placed


def is_tower_entry_piece(p: SolidPlacement) -> bool:
    return TOWER_ENTRY_TAG in p.tags or p.piece_id.startswith("tower_entry_")


CHECK_TOWER_ENTRY_CLEARS_STAIR = "tower_entry_clears_stair"


def check_tower_entry_clears_stair(assembly: "Assembly") -> List["Failure"]:
    """The doorway's inner face must remain outside the stair walking radius."""
    from pae.assembly_types import Assembly
    from pae.contract import TOL_CM
    from pae.existence import placed_tower_entry_doors
    from pae.report import Failure

    failures: List[Failure] = []
    treads = [
        p
        for p in assembly.placements
        if p.asset_id == "stair_spiral_quarter"
    ]
    for door in placed_tower_entry_doors(assembly):
        level_treads = [
            p for p in treads if p.cell == door.cell and p.level == door.level
        ]
        if not level_treads:
            continue
        dx = float(door.offset_cm[0]) - float(level_treads[0].offset_cm[0])
        dy = float(door.offset_cm[1]) - float(level_treads[0].offset_cm[1])
        radial_distance = (dx * dx + dy * dy) ** 0.5
        yaw = int(door.yaw) % 360
        radial_thickness = (
            float(door.size_cm[0]) if yaw in (0, 180) else float(door.size_cm[1])
        )
        inner_face_radius = radial_distance - radial_thickness * 0.5
        stair_outer_radius = max(
            max(float(p.size_cm[0]), float(p.size_cm[1])) for p in level_treads
        )
        if stair_outer_radius + TOL_CM <= inner_face_radius:
            continue
        failures.append(
            Failure(
                check=CHECK_TOWER_ENTRY_CLEARS_STAIR,
                message=(
                    f"tower_entry {door.piece_id} at cell {door.cell} level "
                    f"{door.level} clips spiral walking radius "
                    f"{stair_outer_radius:.1f} cm; doorway inner face is only "
                    f"{inner_face_radius:.1f} cm from the stair axis"
                ),
                world_xyz=None,
                piece_id=door.piece_id,
                critical=True,
            )
        )
    return failures


__all__ = [
    "place_tower_entry_doors",
    "is_tower_entry_piece",
    "TOWER_ENTRY_TAG",
    "CHECK_TOWER_ENTRY_CLEARS_STAIR",
    "check_tower_entry_clears_stair",
    "_resolve_hall_landing_cell",
    "_HALL_WALKABLE",
    "_DRUM_PASSABLE",
]

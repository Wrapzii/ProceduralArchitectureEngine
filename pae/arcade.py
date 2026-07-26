"""Walkable courtyard arcade — a roofed gallery room (Master Plan Stage G).

Per ``Docs/DESIGN_COURTYARD_ARCADE.md``:

* An arcade is a **room**: floor + cover + courtyard-side arch wall.
* It is **not** ``trim._colonnade`` (no floor), **not** bare ``wall_arcade``
  decoration, and **not** ``arch_freestanding``.

Pipeline position: after ``trim``, before ``banding``. This module never touches
party-wall / compound unify paths (owned by @MP-WS5).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
from pae.boundary import FACE_YAW, boundary_offset_cm
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, storey_datum_z_cm
from pae.plan import CellRole
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report
from pae.wall_faces import (
    claimed_wall_arcade_faces,
    face_is_claimed_for_arcade,
    is_wall_arcade,
    repair_wall_face_stacks,
)

Cell = Tuple[int, int]
Face = str

_NEIGHBOURS: Dict[Face, Tuple[int, int]] = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}
_OPPOSITE: Dict[Face, Face] = {
    "south": "north",
    "north": "south",
    "west": "east",
    "east": "west",
}

# Interior roles the arcade walk may reclaim (not classrooms as double-claim —
# classrooms are remapped when they sit on a court-edge bay).
_WALK_SOURCE = frozenset(
    {
        CellRole.INTERIOR,
        CellRole.CORRIDOR,
        CellRole.HALL,
        CellRole.ROOM,
        CellRole.ARCADE,
        CellRole.DOOR,
        CellRole.WALL_LINE,  # court-edge bays are often planned as WALL_LINE
        CellRole.SERVICE,
        CellRole.CLASSROOM,
    }
)


@dataclass(frozen=True)
class ArcadeSpec:
    """A walkable arched gallery along courtyard-facing ranges."""

    depth_bays: int = 1
    levels: Tuple[int, ...] = (0,)
    # Kit id is ``wall_arcade`` (round profile). Design doc alias wall_arcade_round.
    arch_piece: str = "wall_arcade"
    pier_piece: str = "pier_square"
    deck_piece: str = "floor"
    vault: bool = False  # ribbed ceiling — later (Stage G appearance)
    rhythm_bays: int = 1
    faces: Tuple[str, ...] = ()  # empty = every courtyard-facing run
    corner_pier: bool = True


def _courtyard_from_plan(assembly: Assembly) -> Set[Cell]:
    layer = assembly.floor_plan.get(0)
    if layer is None:
        return set()
    court: Set[Cell] = set()
    ox, oy = layer.origin_cell
    for ly in range(layer.height):
        for lx in range(layer.width):
            if layer.cells[ly][lx] == CellRole.COURTYARD:
                court.add((ox + lx, oy + ly))
    return court


def _built_cells_from_plan(assembly: Assembly, level: int) -> Set[Cell]:
    layer = assembly.floor_plan.get(level)
    if layer is None:
        return set()
    built: Set[Cell] = set()
    ox, oy = layer.origin_cell
    skip = frozenset(
        {CellRole.EXTERIOR, CellRole.COURTYARD, CellRole.VOID, CellRole.DOUBLE_VOID}
    )
    for ly in range(layer.height):
        for lx in range(layer.width):
            role = layer.cells[ly][lx]
            if role not in skip:
                built.add((ox + lx, oy + ly))
    return built


def _range_depth_inward(
    built: Set[Cell],
    cell: Cell,
    inward: Tuple[int, int],
) -> int:
    """How many built cells from ``cell`` along ``inward`` (inclusive)."""
    x, y = cell
    dx, dy = inward
    depth = 0
    while (x, y) in built:
        depth += 1
        x, y = x + dx, y + dy
    return depth


def select_arcade_walk_cells(
    assembly: Assembly,
    spec: Optional[ArcadeSpec] = None,
) -> Dict[int, Set[Cell]]:
    """Geometry-only: cells that become the walkable arcade gallery.

    A range face qualifies when:
    1. it is interior-facing (neighbour is courtyard), and
    2. the range is at least ``depth_bays + 1`` deep so a room remains behind.
    Corner cells of two runs are reserved for a solid pier (not claimed as walk).
    """
    spec = spec or ArcadeSpec()
    court = _courtyard_from_plan(assembly)
    if not court:
        return {}

    face_filter = {f.lower() for f in spec.faces} if spec.faces else None
    depth = max(1, int(spec.depth_bays))
    out: Dict[int, Set[Cell]] = {}
    corner_cells: Dict[int, Set[Cell]] = {}

    for level in spec.levels:
        built = _built_cells_from_plan(assembly, level)
        if not built:
            continue
        walk: Set[Cell] = set()
        # Face runs: court cell → adjacent built = court-facing arcade bay.
        face_hits: Dict[Cell, Set[Face]] = {}
        for cx, cy in sorted(court):
            for face, (dx, dy) in _NEIGHBOURS.items():
                if face_filter is not None and face not in face_filter:
                    continue
                bay = (cx + dx, cy + dy)
                if bay not in built:
                    continue
                inward = (dx, dy)  # further into the range from the court edge
                if _range_depth_inward(built, bay, inward) < depth + 1:
                    continue
                face_hits.setdefault(bay, set()).add(face)
                # Walk = first ``depth`` bays from the court edge inward.
                x, y = bay
                for _ in range(depth):
                    if (x, y) not in built:
                        break
                    walk.add((x, y))
                    x, y = x + inward[0], y + inward[1]

        # Corner: cell claimed by two perpendicular court faces → pier, not walk.
        corners: Set[Cell] = set()
        if spec.corner_pier:
            for cell, faces in face_hits.items():
                if len(faces) >= 2:
                    corners.add(cell)
            walk -= corners
        corner_cells[level] = corners
        out[level] = walk

    # Stash corners on a private attribute for arcade() placement.
    select_arcade_walk_cells._last_corners = corner_cells  # type: ignore[attr-defined]
    return out


def _layer_set_role(layer: FloorPlanLayer, cell: Cell, role: CellRole) -> None:
    ox, oy = layer.origin_cell
    lx = cell[0] - ox
    ly = cell[1] - oy
    if 0 <= ly < layer.height and 0 <= lx < layer.width:
        layer.cells[ly][lx] = role


def _has_floor_on_cell(assembly: Assembly, cell: Cell, level: int) -> bool:
    from pae.trim import covered_cells

    for p in assembly.placements:
        if p.level != level or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        if cell in covered_cells(p):
            return True
    return False


def _strip_plain_court_walls(
    placements: Sequence[SolidPlacement],
    *,
    walk: Set[Cell],
    court: Set[Cell],
    level: int,
) -> List[SolidPlacement]:
    """Drop coplanar plain walls on the court face of arcade walk cells.

    ``wall_arcade`` replaces that skin (see ``wall_faces`` D3-9 rule). Doors /
    gates / existing arcade leaves are kept.
    """
    keep: List[SolidPlacement] = []
    for p in placements:
        if p.level != level or p.kind != "wall":
            keep.append(p)
            continue
        if is_wall_arcade(p) or "door" in p.tags or "gate" in p.tags:
            keep.append(p)
            continue
        cell = p.cell
        if cell not in walk:
            keep.append(p)
            continue
        # Court-adjacent walk bay: strip the plain wall that faces the court.
        faces_court = any(
            (cell[0] + dx, cell[1] + dy) in court
            for dx, dy in _NEIGHBOURS.values()
        )
        if faces_court and not is_wall_arcade(p):
            continue
        keep.append(p)
    return keep


def arcade(
    assembly: Assembly,
    spec: Optional[ArcadeSpec] = None,
) -> Tuple[Assembly, Report]:
    """Additive pass: walkable arcade gallery along courtyard faces.

    Returns a new assembly; the input is not mutated. Fail-closed: missing
    courtyard or no qualifying range yields an unchanged assembly with no
    critical (arcade is optional), unless a partial placement would leave
    uncovered walk cells — those become failures.
    """
    spec = spec or ArcadeSpec()
    walk_by_level = select_arcade_walk_cells(assembly, spec)
    corners_by_level: Dict[int, Set[Cell]] = getattr(
        select_arcade_walk_cells, "_last_corners", {}
    )
    if not any(walk_by_level.values()):
        return assembly, Report.from_failures([])

    catalog = catalog_by_id()
    arch_id = spec.arch_piece
    if arch_id == "wall_arcade_round":
        arch_id = "wall_arcade"
    if arch_id not in catalog:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="arcade_arch_piece",
                    message=f"arcade arch_piece {spec.arch_piece!r} not in catalog",
                    world_xyz=None,
                    critical=True,
                )
            ]
        )
    arch_desc = catalog[arch_id]
    pier_desc = catalog.get(spec.pier_piece)
    deck_desc = catalog.get(spec.deck_piece) or catalog.get("floor")

    court = _courtyard_from_plan(assembly)
    placements = list(assembly.placements)
    extra: List[SolidPlacement] = []
    failures: List[Failure] = []
    claimed = claimed_wall_arcade_faces(assembly)
    floor_plan = {
        lvl: replace(
            layer,
            cells=[row[:] for row in layer.cells],
        )
        for lvl, layer in assembly.floor_plan.items()
    }

    for level, walk in sorted(walk_by_level.items()):
        if not walk:
            continue
        layer = floor_plan.get(level)
        placements = _strip_plain_court_walls(
            placements, walk=walk, court=court, level=level
        )

        # Mark ARCADE roles so validators see a room, not an interior room claim.
        if layer is not None:
            for cell in sorted(walk):
                role = layer.role_at(*cell)
                if role in _WALK_SOURCE:
                    # WHY: arcade_no_double_claim — gallery must not stay CLASSROOM.
                    _layer_set_role(layer, cell, CellRole.ARCADE)

        # Walk decks (reuse existing floors; place only when missing).
        for cell in sorted(walk):
            if _has_floor_on_cell(assembly, cell, level):
                continue
            if deck_desc is None:
                failures.append(
                    Failure(
                        check="arcade_covered",
                        message=f"arcade walk cell {cell} L{level} has no deck piece",
                        world_xyz=(
                            cell[0] * MODULE_CM,
                            cell[1] * MODULE_CM,
                            storey_datum_z_cm(level),
                        ),
                        critical=True,
                    )
                )
                continue
            extra.append(
                SolidPlacement(
                    piece_id=f"arcade_deck_{level}_{cell[0]}_{cell[1]}",
                    asset_id=deck_desc.id,
                    kind="floor",
                    cell=cell,
                    level=level,
                    yaw=0,
                    offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                    size_cm=deck_desc.size_cm,
                    rotates_about_center=deck_desc.rotates_about_center,
                    tags=frozenset(
                        {"arcade", "arcade_gallery", "floor", "walk"}
                    ),
                )
            )

        # Arch run on court-facing edge of walk cells.
        arch_seen: Set[Tuple[Cell, Face]] = set()
        for cell in sorted(walk):
            for face, (dx, dy) in _NEIGHBOURS.items():
                if (cell[0] + dx, cell[1] + dy) not in court:
                    continue
                key = (cell, face)
                if key in arch_seen:
                    continue
                arch_seen.add(key)
                outward = face  # face toward courtyard
                if face_is_claimed_for_arcade(
                    claimed, level=level, cell=cell, face=outward
                ):
                    continue
                yaw = FACE_YAW[outward]
                off = boundary_offset_cm(outward, arch_desc.size_cm)
                extra.append(
                    SolidPlacement(
                        piece_id=(
                            f"arcade_arch_{level}_{cell[0]}_{cell[1]}_{face}"
                        ),
                        asset_id=arch_id,
                        kind=arch_desc.kind,
                        cell=cell,
                        level=level,
                        yaw=yaw,
                        offset_cm=off,
                        size_cm=arch_desc.size_cm,
                        rotates_about_center=arch_desc.rotates_about_center,
                        tags=frozenset(
                            {
                                "arcade",
                                "arcade_gallery",
                                "arch",
                                f"face_{face}",
                            }
                        ),
                    )
                )

        # Solid corner pier where two arcade runs would double-claim.
        if spec.corner_pier and pier_desc is not None:
            for cell in sorted(corners_by_level.get(level, ())):
                extra.append(
                    SolidPlacement(
                        piece_id=f"arcade_corner_pier_{level}_{cell[0]}_{cell[1]}",
                        asset_id=spec.pier_piece,
                        kind=pier_desc.kind,
                        cell=cell,
                        level=level,
                        yaw=0,
                        offset_cm=(0.0, 0.0, 0.0),
                        size_cm=pier_desc.size_cm,
                        rotates_about_center=pier_desc.rotates_about_center,
                        tags=frozenset(
                            {"arcade", "arcade_gallery", "corner_pier", "pier"}
                        ),
                    )
                )

    merged = Assembly(
        placements=placements + extra,
        floor_plan=floor_plan,
        circulation=list(assembly.circulation),
        wall_runs=list(assembly.wall_runs),
        apertures=list(assembly.apertures),
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )
    # Prefer arcade wall over any leftover plain coplanar skin.
    merged = repair_wall_face_stacks(merged)
    return merged, Report.from_failures(failures)


__all__ = [
    "ArcadeSpec",
    "arcade",
    "select_arcade_walk_cells",
]

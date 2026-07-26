"""Light-anchor placement (S-068…S-070).

Emits ``kind=light_anchor`` placements with anchor-kind tags (sconce | chandelier |
pendant). Anchors are position hints for UE — no mesh collision required.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
from pae.boundary import FACE_OUTWARD_YAW
from pae.contract import MODULE_CM, STOREY_CM, placement_world_aabb, storey_datum_z_cm
from pae.plan import CellRole
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report

Cell = Tuple[int, int]
Face = str

# Rhythm and height defaults (centimetres / cells).
SCONCE_SPACING_CELLS = 2
SCONCE_HEIGHT_CM = 220.0
CHANDELIER_HEIGHT_CM = STOREY_CM - 50.0
CHANDELIER_MIN_CELLS = 9
PENDANT_HEIGHT_CM = 280.0
WALL_INSET_CM = 8.0

# Compare roles by *name* so placement survives ``reload_pae()`` (plain Enum
# members from a reloaded ``pae.plan`` are not identical to import-time members).
_INTERIOR_ROLE_NAMES = frozenset(
    {"INTERIOR", "CORRIDOR", "CLASSROOM", "DOUBLE_VOID"}
)
_CHANDELIER_ROLE_NAMES = frozenset({"INTERIOR", "DOUBLE_VOID"})
_WALL_HOST_ROLE_NAMES = frozenset(
    {"EXTERIOR", "WALL_LINE", "DOOR", "VOID", "COURTYARD", "STAIR"}
)

_NEIGHBOR_DELTA: Dict[Face, Tuple[int, int]] = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}


def _role_name(role: object) -> str:
    if role is None:
        return "EXTERIOR"
    name = getattr(role, "name", None)
    if isinstance(name, str):
        return name
    return str(role)


def _role_at(layer: FloorPlanLayer, cx: int, cy: int) -> object:
    role = layer.role_at(cx, cy)
    if role is None:
        return CellRole.EXTERIOR
    return role


def _needs_sconce(host: object, neighbor: object) -> bool:
    host_n = _role_name(host)
    neighbor_n = _role_name(neighbor)
    if neighbor_n in _WALL_HOST_ROLE_NAMES:
        return True
    if host_n == "CLASSROOM" and neighbor_n == "CORRIDOR":
        return True
    if host_n == "CORRIDOR" and neighbor_n == "CLASSROOM":
        return True
    if host_n in ("CORRIDOR", "CLASSROOM") and neighbor_n == "INTERIOR":
        return True
    if host_n == "INTERIOR" and neighbor_n in ("CORRIDOR", "CLASSROOM"):
        return True
    return False


def _face_world_point(
    cx: int,
    cy: int,
    level: int,
    face: Face,
    *,
    z_cm: float,
) -> Tuple[float, float, float]:
    """Anchor point on the interior face of a cell edge."""
    base_x = cx * MODULE_CM
    base_y = cy * MODULE_CM
    if face == "south":
        return (base_x + MODULE_CM * 0.5, base_y + WALL_INSET_CM, storey_datum_z_cm(level) + z_cm)
    if face == "north":
        return (
            base_x + MODULE_CM * 0.5,
            (cy + 1) * MODULE_CM - WALL_INSET_CM,
            storey_datum_z_cm(level) + z_cm,
        )
    if face == "west":
        return (base_x + WALL_INSET_CM, base_y + MODULE_CM * 0.5, storey_datum_z_cm(level) + z_cm)
    if face == "east":
        return (
            (cx + 1) * MODULE_CM - WALL_INSET_CM,
            base_y + MODULE_CM * 0.5,
            storey_datum_z_cm(level) + z_cm,
        )
    raise ValueError(f"unknown face {face!r}")


def _world_to_placement(
    wx: float,
    wy: float,
    wz: float,
    *,
    piece_id: str,
    asset_id: str,
    yaw: int,
    tags: FrozenSet[str],
) -> SolidPlacement:
    desc = catalog_by_id()[asset_id]
    cell_x = int(wx // MODULE_CM)
    cell_y = int(wy // MODULE_CM)
    level = int(wz // STOREY_CM)
    offset_cm = (
        wx - cell_x * MODULE_CM,
        wy - cell_y * MODULE_CM,
        wz - storey_datum_z_cm(level),
    )
    return SolidPlacement(
        piece_id=piece_id,
        asset_id=asset_id,
        kind="light_anchor",
        cell=(cell_x, cell_y),
        level=level,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=desc.size_cm,
        rotates_about_center=True,
        tags=desc.tags | tags | frozenset({"light_anchor"}),
    )


def _sconce_candidates(assembly: Assembly) -> List[Tuple[int, Cell, Face]]:
    if not assembly.floor_plan:
        return []
    out: List[Tuple[int, Cell, Face]] = []
    for level, layer in sorted(assembly.floor_plan.items()):
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if _role_name(role) not in _INTERIOR_ROLE_NAMES:
                    continue
                cx, cy = ox + lx, oy + ly
                for face, (dx, dy) in _NEIGHBOR_DELTA.items():
                    nrole = _role_at(layer, cx + dx, cy + dy)
                    if _needs_sconce(role, nrole):
                        out.append((level, (cx, cy), face))
    return out


def _rhythm_filter_sconces(
    candidates: Sequence[Tuple[int, Cell, Face]],
    *,
    spacing_cells: int,
) -> List[Tuple[int, Cell, Face]]:
    """Keep every *spacing_cells* along each collinear wall run."""
    groups: Dict[Tuple[int, Face, int], List[Tuple[int, Cell]]] = {}
    for level, cell, face in candidates:
        cx, cy = cell
        if face in ("south", "north"):
            key = (level, face, cy)
        else:
            key = (level, face, cx)
        groups.setdefault(key, []).append((level, cell))

    picked: List[Tuple[int, Cell, Face]] = []
    spacing = max(1, spacing_cells)
    for (level, face, _fixed), items in sorted(groups.items()):
        if face in ("south", "north"):
            items.sort(key=lambda t: t[1][0])
        else:
            items.sort(key=lambda t: t[1][1])
        for i in range(0, len(items), spacing):
            _, cell = items[i]
            picked.append((level, cell, face))
    return picked


def _interior_components(
    layer: FloorPlanLayer,
    *,
    min_cells: int,
) -> List[Set[Cell]]:
    interior: Set[Cell] = set()
    ox, oy = layer.origin_cell
    for ly in range(layer.height):
        for lx in range(layer.width):
            if _role_name(layer.cells[ly][lx]) in _CHANDELIER_ROLE_NAMES:
                interior.add((ox + lx, oy + ly))
    if len(interior) < min_cells:
        return []

    remaining = set(interior)
    components: List[Set[Cell]] = []
    while remaining:
        start = min(remaining)
        comp: Set[Cell] = set()
        queue: deque[Cell] = deque([start])
        while queue:
            c = queue.popleft()
            if c not in remaining:
                continue
            remaining.remove(c)
            comp.add(c)
            x, y = c
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in remaining:
                    queue.append(n)
        if len(comp) >= min_cells:
            components.append(comp)
    return components


def _chandelier_centroids(
    assembly: Assembly,
    *,
    min_cells: int,
) -> List[Tuple[int, float, float]]:
    if not assembly.floor_plan:
        return []
    out: List[Tuple[int, float, float]] = []
    for level, layer in sorted(assembly.floor_plan.items()):
        for comp in _interior_components(layer, min_cells=min_cells):
            xs = [c[0] for c in comp]
            ys = [c[1] for c in comp]
            wx = (min(xs) + max(xs) + 1) * 0.5 * MODULE_CM
            wy = (min(ys) + max(ys) + 1) * 0.5 * MODULE_CM
            out.append((level, wx, wy))
    return out


def _pendant_points(assembly: Assembly) -> List[Tuple[int, float, float]]:
    if not assembly.floor_plan:
        return []
    out: List[Tuple[int, float, float]] = []
    for level, layer in sorted(assembly.floor_plan.items()):
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                if _role_name(layer.cells[ly][lx]) != "STAIR":
                    continue
                cx, cy = ox + lx, oy + ly
                wx = cx * MODULE_CM + MODULE_CM * 0.5
                wy = cy * MODULE_CM + MODULE_CM * 0.5
                out.append((level, wx, wy))
    return out


def anchor_kind_from_tags(tags: Iterable[str]) -> Optional[str]:
    for kind in ("sconce", "chandelier", "pendant"):
        if kind in tags:
            return kind
    return None


def anchor_loc_cm(p: SolidPlacement) -> Tuple[float, float, float]:
    """World anchor point (centre) for export / validation."""
    mn, mx = placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )
    return (
        (mn[0] + mx[0]) * 0.5,
        (mn[1] + mx[1]) * 0.5,
        (mn[2] + mx[2]) * 0.5,
    )


def apply_light_anchors(
    assembly: Assembly,
    *,
    sconce_spacing_cells: int = SCONCE_SPACING_CELLS,
    chandelier_min_cells: int = CHANDELIER_MIN_CELLS,
) -> Tuple[Assembly, Report]:
    """Place sconces, hall chandeliers, and stair pendants onto *assembly*."""
    if not assembly.floor_plan:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="anchors_no_plan",
                    message="assembly has no floor_plan — cannot place light anchors",
                    critical=False,
                )
            ]
        )

    new_placements: List[SolidPlacement] = list(assembly.placements)
    existing_ids = {p.piece_id for p in new_placements}
    seq = 0

    def _add(p: SolidPlacement) -> None:
        nonlocal seq
        pid = p.piece_id
        while pid in existing_ids:
            seq += 1
            pid = f"{p.piece_id}_{seq}"
        existing_ids.add(pid)
        if pid != p.piece_id:
            p = replace(p, piece_id=pid)
        new_placements.append(p)

    sconce_cells = _rhythm_filter_sconces(
        _sconce_candidates(assembly),
        spacing_cells=sconce_spacing_cells,
    )
    for level, cell, face in sconce_cells:
        cx, cy = cell
        wx, wy, wz = _face_world_point(cx, cy, level, face, z_cm=SCONCE_HEIGHT_CM)
        pid = f"anchor_sconce_{level}_{cx}_{cy}_{face}"
        _add(
            _world_to_placement(
                wx,
                wy,
                wz,
                piece_id=pid,
                asset_id="light_anchor_sconce",
                yaw=FACE_OUTWARD_YAW[face],
                tags=frozenset({"sconce"}),
            )
        )

    for level, wx, wy in _chandelier_centroids(
        assembly, min_cells=chandelier_min_cells
    ):
        wz = storey_datum_z_cm(level) + CHANDELIER_HEIGHT_CM
        pid = f"anchor_chandelier_{level}_{int(wx)}_{int(wy)}"
        _add(
            _world_to_placement(
                wx,
                wy,
                wz,
                piece_id=pid,
                asset_id="light_anchor_chandelier",
                yaw=0,
                tags=frozenset({"chandelier"}),
            )
        )

    for level, wx, wy in _pendant_points(assembly):
        wz = storey_datum_z_cm(level) + PENDANT_HEIGHT_CM
        pid = f"anchor_pendant_{level}_{int(wx)}_{int(wy)}"
        _add(
            _world_to_placement(
                wx,
                wy,
                wz,
                piece_id=pid,
                asset_id="light_anchor_pendant",
                yaw=0,
                tags=frozenset({"pendant"}),
            )
        )

    if not sconce_cells and not _chandelier_centroids(
        assembly, min_cells=chandelier_min_cells
    ):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="anchors_none_placed",
                    message="no sconce or chandelier anchor candidates found",
                    critical=False,
                )
            ]
        )

    return replace(assembly, placements=new_placements), Report.from_failures([])


def validate_anchor_placements(assembly: Assembly) -> List[Failure]:
    """Stub: anchors must overlap a wall face or interior cell (warning-only)."""
    if not assembly.floor_plan:
        return []
    failures: List[Failure] = []
    for p in assembly.placements:
        if p.kind != "light_anchor":
            continue
        ax, ay, az = anchor_loc_cm(p)
        cx = int(ax // MODULE_CM)
        cy = int(ay // MODULE_CM)
        level = p.level
        layer = assembly.floor_plan.get(level)
        if layer is None:
            failures.append(
                Failure(
                    check="anchor_in_void",
                    message=f"{p.piece_id} has no floor_plan layer {level}",
                    world_xyz=(ax, ay, az),
                    piece_id=p.piece_id,
                    critical=False,
                )
            )
            continue

        role_here = _role_at(layer, cx, cy)
        on_interior = _role_name(role_here) in _INTERIOR_ROLE_NAMES
        on_wall = False
        for face, (dx, dy) in _NEIGHBOR_DELTA.items():
            nrole = _role_at(layer, cx + dx, cy + dy)
            if on_interior and _needs_sconce(role_here, nrole):
                on_wall = True
                break
            if _role_name(nrole) in _INTERIOR_ROLE_NAMES and _needs_sconce(
                nrole, role_here or CellRole.EXTERIOR
            ):
                on_wall = True
                break

        if not on_interior and not on_wall:
            failures.append(
                Failure(
                    check="anchor_in_void",
                    message=(
                        f"{p.piece_id} ({anchor_kind_from_tags(p.tags)}) "
                        "centre does not overlap wall face or interior cell"
                    ),
                    world_xyz=(ax, ay, az),
                    piece_id=p.piece_id,
                    critical=False,
                )
            )
    return failures


__all__ = [
    "CHANDELIER_HEIGHT_CM",
    "CHANDELIER_MIN_CELLS",
    "SCONCE_HEIGHT_CM",
    "SCONCE_SPACING_CELLS",
    "anchor_kind_from_tags",
    "anchor_loc_cm",
    "apply_light_anchors",
    "validate_anchor_placements",
]

"""Phase 2.5 interior fit-out greybox — sparse props in programmed rooms only.

Places seed-stable bench / table / crate greybox props on CLASSROOM cells,
ground-floor great-hall INTERIOR cells (school), and castle hall INTERIOR cells
(keep / gatehouse / cloister) that do not touch stairs or corridors.

Handbook §2 seven questions for this family:

  1 touch      props sit on floor slab top (z = storey_datum_z_cm(level))     -> fitout_containment
  2 support    floor slab under cell (inherits floor_coverage)         -> fitout_containment (z)
  3 overlap    must not overlap corridor circulation cells             -> fitout_containment (role)
  4 penetrate  generic interpenetration (props exempt where tagged)    -> interpenetration
  5 isolation  yes — decorative props may stand alone                  -> freestanding exempt via prop tag
  6 use        no walkable surface                                     -> —
  7 requested  greybox stub always places when candidates exist       -> test existence
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
from pae.contract import MODULE_CM
from pae.plan import CellRole
from pae.report import Failure, Report

# Greybox prop catalogue (cm) — min-corner origin, floor-aligned.
GREYBOX_FITOUT_PROPS: Tuple[Tuple[str, Tuple[float, float, float]], ...] = (
    ("fitout_bench", (120.0, 40.0, 45.0)),
    ("fitout_table", (80.0, 80.0, 75.0)),
    ("fitout_crate", (50.0, 50.0, 80.0)),
)

DEFAULT_FITOUT_DENSITY = 0.08
DEFAULT_MAX_FITOUT_PROPS = 12
_FITOUT_TAG = "fitout_greybox"


def _cell_role_is(role: object, expected: CellRole) -> bool:
    if role == expected:
        return True
    value = getattr(role, "value", None)
    return value is not None and value == expected.value


def _layer_role_at(layer: FloorPlanLayer, cx: int, cy: int) -> Optional[CellRole]:
    lx = cx - layer.origin_cell[0]
    ly = cy - layer.origin_cell[1]
    if lx < 0 or ly < 0 or lx >= layer.width or ly >= layer.height:
        return None
    return layer.cells[ly][lx]


def _touches_role(
    layers: Dict[int, FloorPlanLayer],
    level: int,
    cx: int,
    cy: int,
    role: CellRole,
) -> bool:
    layer = layers.get(level)
    if layer is None:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbor = _layer_role_at(layer, cx + dx, cy + dy)
        if neighbor is not None and _cell_role_is(neighbor, role):
            return True
    return False


def _touches_corridor(
    layers: Dict[int, FloorPlanLayer], level: int, cx: int, cy: int
) -> bool:
    return _touches_role(layers, level, cx, cy, CellRole.CORRIDOR)


def _touches_stair(
    layers: Dict[int, FloorPlanLayer], level: int, cx: int, cy: int
) -> bool:
    return _touches_role(layers, level, cx, cy, CellRole.STAIR)


def _is_castle_fitout_target(assembly: Assembly) -> bool:
    """Fortress keep / gatehouse / cloister ranges use hall INTERIOR cells."""
    if getattr(assembly, "building_class", "") == "castle":
        return True
    try:
        from pae.fortress_validate import assembly_is_fortress

        return assembly_is_fortress(assembly)
    except Exception:
        return False


def _has_declared_hall(assembly: Assembly) -> bool:
    return any(
        str(room.get("kind", "")).lower() == "hall" for room in assembly.room_specs
    )


def is_great_hall_cell(
    layers: Dict[int, FloorPlanLayer],
    level: int,
    cell: Tuple[int, int],
    *,
    hall_declared: bool,
    castle_fitout: bool = False,
) -> bool:
    """INTERIOR bay in a hall volume — not corridor/stair circulation."""
    if castle_fitout:
        layer = layers.get(level)
        if layer is None:
            return False
        role = _layer_role_at(layer, cell[0], cell[1])
        if role is None or not _cell_role_is(role, CellRole.INTERIOR):
            return False
        cx, cy = cell
        if _touches_corridor(layers, level, cx, cy):
            return False
        if _touches_stair(layers, level, cx, cy):
            return False
        return True
    if not hall_declared or level != 0:
        return False
    layer = layers.get(level)
    if layer is None:
        return False
    role = _layer_role_at(layer, cell[0], cell[1])
    if role is None or not _cell_role_is(role, CellRole.INTERIOR):
        return False
    return not _touches_corridor(layers, level, cell[0], cell[1])


def is_fitout_cell(
    layers: Dict[int, FloorPlanLayer],
    level: int,
    cell: Tuple[int, int],
    *,
    hall_declared: bool = False,
    castle_fitout: bool = False,
    drum_cells: Optional[Set[Tuple[int, int]]] = None,
) -> bool:
    """True when *cell* may receive a greybox prop.

    Tower drum cells are never candidates — benches/crates inside a spiral
    stairwell are junk (user: crap inside keep towers).
    """
    if drum_cells is not None and cell in drum_cells:
        return False
    layer = layers.get(level)
    if layer is None:
        return False
    role = _layer_role_at(layer, cell[0], cell[1])
    if role is None:
        return False
    if _cell_role_is(role, CellRole.CLASSROOM):
        return True
    return is_great_hall_cell(
        layers,
        level,
        cell,
        hall_declared=hall_declared,
        castle_fitout=castle_fitout,
    )


_FORTRESS_FITOUT_RANGE_NAMES = frozenset(
    {"north_keep", "gatehouse", "west_cloister", "east_cloister"}
)


def _fortress_fitout_range_from_tags(tags: Iterable[str]) -> bool:
    for tag in tags:
        if tag in _FORTRESS_FITOUT_RANGE_NAMES:
            return True
        if tag.startswith("building:"):
            name = tag.split(":", 1)[1]
            if name in _FORTRESS_FITOUT_RANGE_NAMES or "cloister" in name:
                return True
    return False


def _stair_cells_at_level(assembly: Assembly, level: int) -> Set[Tuple[int, int]]:
    from pae.trim import covered_cells

    out: Set[Tuple[int, int]] = set()
    for p in assembly.placements:
        if p.level != level or p.kind != "stair":
            continue
        out |= covered_cells(p)
    return out


def _floor_cells_at_level(assembly: Assembly, level: int) -> Set[Tuple[int, int]]:
    from pae.trim import covered_cells

    out: Set[Tuple[int, int]] = set()
    for p in assembly.placements:
        if p.level != level or p.kind != "floor" or p.asset_id == "floor_hole":
            continue
        out |= covered_cells(p)
    return out


def fitout_placement_allowed(
    assembly: Assembly,
    placement: SolidPlacement,
    *,
    hall_declared: bool,
    castle_fitout: bool,
    drum_cells: Set[Tuple[int, int]],
) -> bool:
    """True when a placed fit-out prop satisfies containment rules."""
    level = placement.level
    cell = placement.cell
    layers = assembly.floor_plan
    layer = layers.get(level)
    role = (
        _layer_role_at(layer, cell[0], cell[1]) if layer is not None else None
    )
    if role is not None:
        return is_fitout_cell(
            layers,
            level,
            cell,
            hall_declared=hall_declared,
            castle_fitout=castle_fitout,
            drum_cells=drum_cells,
        )

    if not castle_fitout or not _fortress_fitout_range_from_tags(placement.tags):
        return False
    if cell in drum_cells:
        return False
    stairs = _stair_cells_at_level(assembly, level)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if (cell[0] + dx, cell[1] + dy) in stairs:
            return False
    return cell in _floor_cells_at_level(assembly, level)


def fitout_candidate_cells(
    assembly: Assembly,
) -> List[Tuple[int, Tuple[int, int]]]:
    """Sorted (level, cell) list eligible for interior fit-out props."""
    if not assembly.floor_plan:
        return []
    hall_declared = _has_declared_hall(assembly)
    castle_fitout = _is_castle_fitout_target(assembly)
    drum_cells: Set[Tuple[int, int]] = set()
    try:
        from pae.drum import drum_cells as _drum_cells

        drum_cells = _drum_cells(assembly)
    except Exception:
        drum_cells = {
            p.cell
            for p in assembly.placements
            if p.kind in ("tower_arc", "tower_cap")
        }
    cells: List[Tuple[int, Tuple[int, int]]] = []
    for level in sorted(assembly.floor_plan.keys()):
        layer = assembly.floor_plan[level]
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                cx, cy = ox + lx, oy + ly
                if is_fitout_cell(
                    assembly.floor_plan,
                    level,
                    (cx, cy),
                    hall_declared=hall_declared,
                    castle_fitout=castle_fitout,
                    drum_cells=drum_cells,
                ):
                    cells.append((level, (cx, cy)))
    return cells


def _prop_offset_cm(size_cm: Tuple[float, float, float]) -> Tuple[float, float, float]:
    sx, sy, _sz = size_cm
    ox = max(0.0, (MODULE_CM - sx) * 0.5)
    oy = max(0.0, (MODULE_CM - sy) * 0.5)
    return (ox, oy, 0.0)


def _select_cells(
    candidates: Sequence[Tuple[int, Tuple[int, int]]],
    *,
    seed: int,
    density: float,
    max_props: int,
) -> List[Tuple[int, Tuple[int, int]]]:
    if not candidates:
        return []
    density = max(0.0, min(1.0, density))
    n = min(max_props, max(0, int(round(len(candidates) * density))))
    if n == 0 and density > 0.0 and candidates:
        n = min(max_props, min(3, len(candidates)))
    if n <= 0:
        return []
    rng = random.Random(seed)
    return sorted(rng.sample(list(candidates), k=min(n, len(candidates))))


def fitout_greybox(
    assembly: Assembly,
    *,
    seed: int = 0,
    density: float = DEFAULT_FITOUT_DENSITY,
    max_props: int = DEFAULT_MAX_FITOUT_PROPS,
) -> Tuple[Assembly, Report]:
    """Place greybox bench/table/crate props on classroom and great-hall cells."""
    candidates = fitout_candidate_cells(assembly)
    if not candidates:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="fitout_no_cells",
                    message=(
                        "no classroom, great_hall, or castle interior cells for fit-out"
                    ),
                    critical=False,
                )
            ]
        )

    chosen = _select_cells(
        candidates, seed=seed, density=density, max_props=max_props
    )
    if not chosen:
        return assembly, Report.from_failures([])

    new_placements: List[SolidPlacement] = list(assembly.placements)
    existing_ids = {p.piece_id for p in new_placements}
    props = GREYBOX_FITOUT_PROPS

    for i, (level, cell) in enumerate(chosen):
        asset_id, size = props[i % len(props)]
        pid = f"fitout_{asset_id}_{level}_{cell[0]}_{cell[1]}"
        if pid in existing_ids:
            pid = f"{pid}_{i}"
        existing_ids.add(pid)
        new_placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=asset_id,
                kind="prop",
                cell=cell,
                level=level,
                yaw=0,
                offset_cm=_prop_offset_cm(size),
                size_cm=size,
                rotates_about_center=False,
                tags=frozenset({"prop", "decorative", _FITOUT_TAG}),
            )
        )

    return replace(assembly, placements=new_placements), Report.from_failures([])


__all__ = [
    "DEFAULT_FITOUT_DENSITY",
    "DEFAULT_MAX_FITOUT_PROPS",
    "GREYBOX_FITOUT_PROPS",
    "fitout_candidate_cells",
    "fitout_greybox",
    "fitout_placement_allowed",
    "is_fitout_cell",
    "is_great_hall_cell",
]

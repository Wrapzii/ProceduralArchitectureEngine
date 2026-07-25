"""Phase 2.5 interior fit-out greybox — sparse props in programmed rooms only.

Places seed-stable bench / table / crate greybox props on CLASSROOM cells and
ground-floor great-hall INTERIOR cells (not corridors, voids, or circulation).

Handbook §2 seven questions for this family:

  1 touch      props sit on floor slab top (z = level * STOREY_CM)     -> fitout_containment
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
from typing import Dict, List, Optional, Sequence, Set, Tuple

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


def _touches_corridor(
    layers: Dict[int, FloorPlanLayer], level: int, cx: int, cy: int
) -> bool:
    layer = layers.get(level)
    if layer is None:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbor = _layer_role_at(layer, cx + dx, cy + dy)
        if neighbor is not None and _cell_role_is(neighbor, CellRole.CORRIDOR):
            return True
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
) -> bool:
    """Ground-floor INTERIOR bay in the hall volume (not a classroom-wing spine)."""
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
) -> bool:
    layer = layers.get(level)
    if layer is None:
        return False
    role = _layer_role_at(layer, cell[0], cell[1])
    if role is None:
        return False
    if _cell_role_is(role, CellRole.CLASSROOM):
        return True
    return is_great_hall_cell(layers, level, cell, hall_declared=hall_declared)


def fitout_candidate_cells(
    assembly: Assembly,
) -> List[Tuple[int, Tuple[int, int]]]:
    """Sorted (level, cell) list eligible for interior fit-out props."""
    if not assembly.floor_plan:
        return []
    hall_declared = _has_declared_hall(assembly)
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
                    message="no classroom or great_hall cells for fit-out",
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
    "is_fitout_cell",
    "is_great_hall_cell",
]

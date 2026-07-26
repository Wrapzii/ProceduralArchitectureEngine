"""Decoration stage (M5) — sparse, seed-stable props from AssetDB tags.

Assembles structural kit pieces only; decorate queries the DB by tag and places
confirmed decorative assets on interior cells. Adding a measured + confirmed
Comfy asset to the DB is enough — no assemble / solver code change (§11 M5, §9).
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, FloorPlanLayer, SolidPlacement
from pae.assets.query import DEFAULT_DECOR_TAGS, list_decorative_for_generator
from pae.contract import MODULE_CM
from pae.plan import CellRole
from pae.report import Failure, Report

AssetDBLike = Any

# Fraction of interior cells that may receive a prop (sparse).
DEFAULT_DENSITY = 0.12
# Hard cap so tiny footprints still get at most a few props.
DEFAULT_MAX_PROPS = 8


def _interior_cells(layers: dict[int, FloorPlanLayer]) -> List[Tuple[int, Tuple[int, int]]]:
    """Sorted (level, cell) list of INTERIOR roles — seed-stable order."""
    cells: List[Tuple[int, Tuple[int, int]]] = []
    for level in sorted(layers.keys()):
        layer = layers[level]
        ox, oy = layer.origin_cell
        for ly in range(layer.height):
            for lx in range(layer.width):
                role = layer.cells[ly][lx]
                if role in (
                    CellRole.INTERIOR,
                    CellRole.CORRIDOR,
                    CellRole.CLASSROOM,
                    CellRole.ROOM,
                    CellRole.HALL,
                    CellRole.SERVICE,
                    CellRole.ARCADE,
                ):
                    cells.append((level, (ox + lx, oy + ly)))
    return cells


def _prop_offset_cm(size_cm: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Centre prop footprint in the cell on the floor plane (z=0 = floor top)."""
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
        n = 1
    if n <= 0:
        return []
    rng = random.Random(seed)
    return sorted(rng.sample(list(candidates), k=min(n, len(candidates))))


def pick_prop_assets(
    asset_db: AssetDBLike,
    *,
    tags: Optional[Set[str]] = None,
) -> List[Any]:
    """Public query used by decorate — same filter as generator M5 path."""
    if asset_db is None:
        return []
    lister = getattr(asset_db, "list_assets", None)
    if not callable(lister):
        return []
    # Prefer the typed helper when we have a real AssetDB.
    try:
        from pae.assets.db import AssetDB

        if isinstance(asset_db, AssetDB):
            return list_decorative_for_generator(asset_db, tags=tags)
    except Exception:
        pass

    required = set(tags) if tags is not None else set(DEFAULT_DECOR_TAGS)
    rows = lister(tags=required)
    return sorted(rows, key=lambda a: getattr(a, "id", ""))


def decorate(
    assembly: Assembly,
    asset_db: AssetDBLike | None = None,
    *,
    seed: int = 0,
    tags: Optional[Set[str]] = None,
    density: float = DEFAULT_DENSITY,
    max_props: int = DEFAULT_MAX_PROPS,
) -> Tuple[Assembly, Report]:
    """Optionally place decorative props from AssetDB onto interior cells.

    With ``asset_db=None`` or no matching tagged assets, returns the assembly
    unchanged (pass-through). Placement is sparse and seed-stable.
    """
    if asset_db is None:
        return assembly, Report.from_failures([])

    props = pick_prop_assets(asset_db, tags=tags)
    if not props:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="decorate_no_props",
                    message="AssetDB has no confirmed decorative assets for given tags",
                    critical=False,
                )
            ]
        )

    if not assembly.floor_plan:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="decorate_no_plan",
                    message="assembly has no floor_plan layers — cannot place props",
                    critical=False,
                )
            ]
        )

    candidates = _interior_cells(assembly.floor_plan)
    chosen = _select_cells(
        candidates, seed=seed, density=density, max_props=max_props
    )
    if not chosen:
        return assembly, Report.from_failures(
            [
                Failure(
                    check="decorate_no_cells",
                    message="no interior cells available for prop placement",
                    critical=False,
                )
            ]
        )

    new_placements: List[SolidPlacement] = list(assembly.placements)
    existing_ids = {p.piece_id for p in new_placements}

    for i, (level, cell) in enumerate(chosen):
        asset = props[i % len(props)]
        size = tuple(float(v) for v in asset.size_cm)
        pid = f"prop_{level}_{cell[0]}_{cell[1]}"
        if pid in existing_ids:
            pid = f"{pid}_{i}"
        existing_ids.add(pid)
        asset_tags = frozenset(getattr(asset, "tags", ()) or ())
        new_placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id=asset.id,
                kind="prop",
                cell=cell,
                level=level,
                yaw=0,
                offset_cm=_prop_offset_cm(size),  # type: ignore[arg-type]
                size_cm=size,  # type: ignore[arg-type]
                rotates_about_center=bool(
                    getattr(asset, "rotates_about_center", False)
                ),
                tags=asset_tags | frozenset({"decorative", "prop"}),
            )
        )

    out = replace(assembly, placements=new_placements)
    return out, Report.from_failures([])


__all__ = [
    "DEFAULT_DENSITY",
    "DEFAULT_MAX_PROPS",
    "decorate",
    "pick_prop_assets",
]

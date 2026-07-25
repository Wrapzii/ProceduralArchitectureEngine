"""Random BuildingSpec factories for property tests (WP-9 scaffolding)."""

from __future__ import annotations

import random
from typing import List, Tuple

from pae.spec import (
    SUPPORTED_STAIR_KINDS,
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    TowerSpec,
)


def _exterior_tower_cell(
    rng: random.Random,
    *,
    bays_x: int,
    bays_y: int,
    attached_to: str,
) -> Tuple[int, int]:
    """Pick a cell *outside* the [0,bays) bbox that abuts a wall or corner.

    Interior cells overlap the massing and used to fail ``volumes_no_overlap``
    before solver local-repair learned to push them out (M3 uses wall abut).
    """
    if attached_to == "corner":
        return rng.choice(
            [
                (-1, -1),
                (bays_x, -1),
                (-1, bays_y),
                (bays_x, bays_y),
            ]
        )
    # Wall mid-edge (edge abut, not diagonal) — preferred for circulation.
    face = rng.choice(["west", "east", "south", "north"])
    if face == "west":
        return (-1, rng.randint(0, bays_y - 1))
    if face == "east":
        return (bays_x, rng.randint(0, bays_y - 1))
    if face == "south":
        return (rng.randint(0, bays_x - 1), -1)
    return (rng.randint(0, bays_x - 1), bays_y)


def _stair_cell_on_main(
    *,
    kind: str,
    bays_x: int,
    bays_y: int,
    wing_depth: int,
) -> Tuple[int, int]:
    """South-bar interior cell so multi-storey stairs land in enclosed volume."""
    depth = max(1, min(wing_depth, bays_y // 2 or 1))
    if kind in ("L", "U", "courtyard"):
        sy = 0
        # Need room for a 2-module +Y straight run inside the south bar.
        if depth < 2:
            sy = 0
        sx = max(0, min(bays_x - 1, bays_x // 2))
        return (sx, sy)
    return (bays_x // 2, max(0, min(bays_y - 2, 0)))


def random_building_spec(rng: random.Random | None = None) -> BuildingSpec:
    """Draw a BuildingSpec within sane M1–M3 bounds (bays only, no world coords).

    Footprints: rect / L / U / courtyard (supported by greedy massing).
    Towers: exterior wall/corner attach only (no interior overlap cells).
    """
    rng = rng or random.Random()
    bays_x = rng.randint(2, 8)
    bays_y = rng.randint(2, 8)
    storeys = rng.randint(1, 4)
    kind = rng.choice(["rect", "L", "U", "courtyard"])
    wing_depth = rng.randint(1, max(1, min(3, bays_x // 2, bays_y // 2)))

    towers: List[TowerSpec] = []
    if rng.random() < 0.3 and storeys >= 2:
        attached_to = rng.choice(["wall", "corner"])
        # Prefer wall attach (corner still allowed; solver repair can nudge).
        if rng.random() < 0.7:
            attached_to = "wall"
        towers.append(
            TowerSpec(
                cell=_exterior_tower_cell(
                    rng, bays_x=bays_x, bays_y=bays_y, attached_to=attached_to
                ),
                storeys=rng.randint(storeys, storeys + 2),
                attached_to=attached_to,
            )
        )

    stair_cells: List[Tuple[int, int]] = []
    if storeys > 1:
        stair_cells = [
            _stair_cell_on_main(
                kind=kind, bays_x=bays_x, bays_y=bays_y, wing_depth=wing_depth
            )
        ]

    return BuildingSpec(
        name=f"prop_{rng.randint(0, 1_000_000)}",
        style=rng.choice(["gothic_academy", "default"]),
        footprint=FootprintSpec(
            kind=kind,
            bays_x=bays_x,
            bays_y=bays_y,
            wing_depth=wing_depth,
            courtyard=(kind == "courtyard"),
        ),
        storeys=storeys,
        storey_use=["residence"] * storeys,
        towers=towers,
        roof=RoofSpec(kind=rng.choice(["flat", "pitched"]), pitch=1.0),
        circulation=CirculationSpec(
            stair_kind=rng.choice(sorted(SUPPORTED_STAIR_KINDS)),
            stair_cells=stair_cells,
        ),
        openings=OpeningPolicy(
            windows_per_bay=rng.randint(0, 2),
            doors_ground=rng.randint(1, 2),
            skip_ground_windows=rng.choice([True, False]),
        ),
        seed=rng.randint(0, 2**31 - 1),
    )

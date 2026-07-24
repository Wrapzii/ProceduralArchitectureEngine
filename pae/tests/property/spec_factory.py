"""Random BuildingSpec factories for property tests (WP-9 scaffolding)."""

from __future__ import annotations

import random
from typing import List

from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    TowerSpec,
)


def random_building_spec(rng: random.Random | None = None) -> BuildingSpec:
    """Draw a BuildingSpec within sane M1–M3 bounds (bays only, no world coords)."""
    rng = rng or random.Random()
    bays_x = rng.randint(2, 8)
    bays_y = rng.randint(2, 8)
    storeys = rng.randint(1, 4)
    kind = rng.choice(["rect", "L", "U", "courtyard"])
    wing_depth = rng.randint(1, max(1, min(3, bays_x // 2, bays_y // 2)))

    towers: List[TowerSpec] = []
    if rng.random() < 0.3 and storeys >= 2:
        towers.append(
            TowerSpec(
                cell=(rng.randint(0, bays_x - 1), rng.randint(0, bays_y - 1)),
                storeys=rng.randint(storeys, storeys + 2),
                attached_to=rng.choice(["wall", "corner"]),
            )
        )

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
            stair_kind=rng.choice(["straight", "spiral"]),
            stair_cells=[(bays_x // 2, bays_y // 2)] if storeys > 1 else [],
        ),
        openings=OpeningPolicy(
            windows_per_bay=rng.randint(0, 2),
            doors_ground=rng.randint(1, 2),
            skip_ground_windows=rng.choice([True, False]),
        ),
        seed=rng.randint(0, 2**31 - 1),
    )

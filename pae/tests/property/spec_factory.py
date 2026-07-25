"""Random BuildingSpec factories for property tests (WP-9 scaffolding)."""

from __future__ import annotations

import random
from typing import List, Tuple

from pae.solver import (
    WING_ROLES,
    _default_stair_cells,
    _place_footprint,
    exterior_tower_attach_cells,
)
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
    wing_depth: int,
    footprint_kind: str,
    courtyard: bool,
    storeys: int,
    attached_to: str,
) -> Tuple[int, int]:
    """Pick a cell outside the massing that abuts a ``WING_ROLES`` body.

    Uses the same perimeter walk as solver local-repair so random towers never
    land on the footprint bbox when L/U/courtyard wings leave that edge open.
    """
    fp = FootprintSpec(
        kind=footprint_kind,
        bays_x=bays_x,
        bays_y=bays_y,
        wing_depth=wing_depth,
        courtyard=courtyard,
    )
    bodies = [v for v in _place_footprint(fp, storeys) if v.role in WING_ROLES]
    cells = exterior_tower_attach_cells(
        bodies,
        prefer_wall=(attached_to == "wall"),
    )
    if cells:
        return rng.choice(cells)

    # Degenerate footprint — fall back to rect bbox exterior (solver repair will snap).
    if attached_to == "corner":
        return rng.choice(
            [
                (-1, -1),
                (bays_x, -1),
                (-1, bays_y),
                (bays_x, bays_y),
            ]
        )
    face = rng.choice(["west", "east", "south", "north"])
    if face == "west":
        return (-1, rng.randint(0, bays_y - 1))
    if face == "east":
        return (bays_x, rng.randint(0, bays_y - 1))
    if face == "south":
        return (rng.randint(0, bays_x - 1), -1)
    return (rng.randint(0, bays_x - 1), bays_y)


def _draw_footprint(rng: random.Random, storeys: int) -> FootprintSpec:
    """Draw a footprint; multi-storey draws must fit at least a straight stair run."""
    for _ in range(12):
        bays_x = rng.randint(2, 8)
        bays_y = rng.randint(2, 8)
        kind = rng.choice(["rect", "L", "U", "courtyard"])
        wing_depth = rng.randint(1, max(1, min(3, bays_x // 2, bays_y // 2)))
        footprint = FootprintSpec(
            kind=kind,
            bays_x=bays_x,
            bays_y=bays_y,
            wing_depth=wing_depth,
            courtyard=(kind == "courtyard"),
        )
        if storeys <= 1:
            return footprint
        volumes = _place_footprint(footprint, storeys)
        if _default_stair_cells(volumes, "straight"):
            return footprint
    # Guaranteed stair-capable fallback (rect 4×4 fits a 2-module straight run).
    return FootprintSpec(kind="rect", bays_x=4, bays_y=4, wing_depth=1, courtyard=False)


def _circulation_for_footprint(
    footprint: FootprintSpec,
    storeys: int,
    rng: random.Random,
) -> CirculationSpec:
    """Emit a full stair footprint for multi-storey specs (solver parity)."""
    if storeys <= 1:
        return CirculationSpec(stair_kind="straight", stair_cells=[])
    kinds = sorted(SUPPORTED_STAIR_KINDS - {"spiral"})
    preferred = rng.choice(kinds)
    volumes = _place_footprint(footprint, storeys)
    stair_cells = _default_stair_cells(volumes, preferred)
    stair_kind = preferred
    if not stair_cells:
        stair_kind = "straight"
        stair_cells = _default_stair_cells(volumes, stair_kind)
    return CirculationSpec(stair_kind=stair_kind, stair_cells=stair_cells)


def random_building_spec(rng: random.Random | None = None) -> BuildingSpec:
    """Draw a BuildingSpec within sane M1–M3 bounds (bays only, no world coords).

    Footprints: rect / L / U / courtyard (supported by greedy massing).
    Towers: exterior wall/corner attach only (no interior overlap cells).
    """
    rng = rng or random.Random()
    storeys = rng.randint(1, 4)
    footprint = _draw_footprint(rng, storeys)
    bays_x = footprint.bays_x
    bays_y = footprint.bays_y
    kind = footprint.kind
    wing_depth = footprint.wing_depth

    towers: List[TowerSpec] = []
    if rng.random() < 0.3 and storeys >= 2:
        attached_to = rng.choice(["wall", "corner"])
        # Prefer wall attach (corner still allowed; solver repair can nudge).
        if rng.random() < 0.7:
            attached_to = "wall"
        towers.append(
            TowerSpec(
                cell=_exterior_tower_cell(
                    rng,
                    bays_x=bays_x,
                    bays_y=bays_y,
                    wing_depth=wing_depth,
                    footprint_kind=kind,
                    courtyard=(kind == "courtyard"),
                    storeys=storeys,
                    attached_to=attached_to,
                ),
                storeys=rng.randint(storeys, storeys + 2),
                attached_to=attached_to,
            )
        )

    circulation = _circulation_for_footprint(footprint, storeys, rng)

    return BuildingSpec(
        name=f"prop_{rng.randint(0, 1_000_000)}",
        style=rng.choice(["gothic_academy", "default"]),
        footprint=footprint,
        storeys=storeys,
        storey_use=["residence"] * storeys,
        towers=towers,
        roof=RoofSpec(kind=rng.choice(["flat", "pitched"]), pitch=1.0),
        circulation=circulation,
        openings=OpeningPolicy(
            # Multi-storey draws always glaze (>=1): windows_per_bay=0 plus
            # skip_ground_windows used to leave upper VOLUME critical until
            # assemble's south-face fallback; keep the factory honest too.
            windows_per_bay=(
                rng.randint(1, 2) if storeys >= 2 else rng.randint(0, 2)
            ),
            doors_ground=rng.randint(1, 2),
            skip_ground_windows=rng.choice([True, False]),
        ),
        seed=rng.randint(0, 2**31 - 1),
    )

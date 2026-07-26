"""New reference-image composition built from the current architecture systems.

This is intentionally independent of ``build_fortress_compound``. Each roof zone
belongs to one validated building assembly, so adjacent ranges can meet without
one giant roof crossing the whole campus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    TowerSpec,
)


@dataclass(frozen=True)
class ReferenceComponent:
    name: str
    factory: Callable[[], BuildingSpec]
    offset_m: Tuple[float, float, float]
    arcade: bool = False


def reference_courtyard_spec() -> BuildingSpec:
    """Two-storey open court with a real covered arcade and side stair towers."""
    return BuildingSpec(
        name="reference_courtyard",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="courtyard",
            bays_x=12,
            bays_y=10,
            wing_depth=2,
            courtyard=True,
        ),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[
            TowerSpec(
                cell=(0, 4),
                storeys=3,
                attached_to="wall",
                stair_kind="spiral",
                radius_bays=0.75,
                shape="square",
                cap_style="square_spire",
                spire_height_storeys=1.5,
            ),
            TowerSpec(
                cell=(11, 4),
                storeys=3,
                attached_to="wall",
                stair_kind="spiral",
                radius_bays=0.75,
                shape="round",
                cap_style="cone",
                spire_height_storeys=1.5,
            ),
        ],
        roof=RoofSpec(kind="flat", pitch=1.0),
        # The attached stair towers own vertical circulation; do not invent a
        # second unsupported hall stair inside the courtyard wing.
        circulation=CirculationSpec(stair_kind="spiral", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=2,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        entrances=[
            EntranceSpec(role="main", facade="south", bay=7),
            EntranceSpec(role="main", facade="north", bay=8),
        ],
        seed=101,
        ground_slab=True,
        building_class="academy",
    )


def reference_great_hall_spec() -> BuildingSpec:
    """Tall rear hall with separate pitched roof and two unequal stair towers."""
    return BuildingSpec(
        name="reference_great_hall",
        style="gothic_academy",
        footprint=FootprintSpec(kind="rect", bays_x=10, bays_y=5),
        storeys=3,
        storey_use=["hall", "hall", "hall"],
        towers=[
            TowerSpec(
                cell=(0, 2),
                storeys=5,
                attached_to="wall",
                stair_kind="spiral",
                radius_bays=1.5,
                shape="round",
                cap_style="cone",
                spire_height_storeys=2.0,
            ),
            TowerSpec(
                cell=(9, 2),
                storeys=4,
                attached_to="wall",
                stair_kind="spiral",
                radius_bays=1.5,
                shape="square",
                cap_style="square_spire",
                spire_height_storeys=1.5,
            ),
        ],
        roof=RoofSpec(kind="pitched", pitch=1.2),
        circulation=CirculationSpec(stair_kind="spiral", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        entrances=[EntranceSpec(role="main", facade="south", bay=4)],
        seed=102,
        ground_slab=True,
        building_class="academy",
        # Ground hall is two storeys clear. Level 2 is the first internal
        # crossing floor above the ceremonial volume.
        level_void_cells=(
            (),
            tuple((x, y) for x in range(10) for y in range(5)),
            (),
        ),
        interior_arch_rib_every_bays=2,
    )


def reference_gatehouse_spec() -> BuildingSpec:
    """Ground-level through gate: paired grand arches, no exterior stair obstruction."""
    return BuildingSpec(
        name="reference_gatehouse",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=6, bays_y=4),
        # The arches consume levels 0–1. Level 2 is the first continuous floor
        # that may cross above the carriage lanes.
        storeys=3,
        storey_use=["hall", "hall", "hall"],
        towers=[
            TowerSpec(
                cell=(0, 0),
                storeys=4,
                attached_to="corner",
                stair_kind="spiral",
                radius_bays=0.75,
                shape="round",
                cap_style="cone",
                spire_height_storeys=1.5,
            ),
            TowerSpec(
                cell=(5, 0),
                storeys=4,
                attached_to="corner",
                stair_kind="spiral",
                radius_bays=0.75,
                shape="round",
                cap_style="cone",
                spire_height_storeys=1.5,
            ),
        ],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="spiral", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=0,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="gate", facade="south", bay=2),
            EntranceSpec(role="gate", facade="south", bay=3),
        ],
        seed=103,
        ground_slab=True,
        building_class="castle",
        wall_height_storeys=2.0,
        # Only the two front-to-rear carriage lanes remain open through level 1.
        # The flanking and central strips are real upper guard rooms, so tower
        # doors have supported landings without bridging across either arch.
        level_void_cells=(
            (),
            (
                (0, 0),
                (0, 1),
                (0, 2),
                (0, 3),
                (1, 0),
                (1, 1),
                (1, 2),
                (1, 3),
                (2, 0),
                (2, 1),
                (2, 2),
                (2, 3),
                (3, 0),
                (3, 1),
                (3, 2),
                (3, 3),
                (4, 0),
                (4, 1),
                (4, 2),
                (4, 3),
                (5, 0),
                (5, 1),
                (5, 2),
                (5, 3),
            ),
            (),
        ),
    )


def reference_connector_spec(
    name: str = "reference_connector", *, seed: int = 104
) -> BuildingSpec:
    """Full-width, double-height covered link with open north/south ends."""
    return BuildingSpec(
        name=name,
        style="gothic_academy",
        # Three bays continue both gate lanes plus their central guard strip.
        # North/south ends remain fully open; only the west/east sides enclose
        # the connection.
        footprint=FootprintSpec(kind="rect", bays_x=3, bays_y=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=0,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[],
        seed=seed,
        ground_slab=True,
        building_class="connector",
        # A one-level volume with a two-storey height: no intermediate slab, and
        # the roof clears the adjoining monumental arches.
        level_height_units=(2,),
    )


def reference_citadel_components() -> Tuple[ReferenceComponent, ...]:
    """Front gate → open court → tall rear hall, with disjoint roof zones."""
    return (
        ReferenceComponent(
            "gatehouse", reference_gatehouse_spec, (12.0, 0.0, 0.0)
        ),
        ReferenceComponent(
            "gate_to_court",
            lambda: reference_connector_spec(
                "reference_gate_to_court", seed=104
            ),
            (16.0, 16.0, 0.0),
        ),
        ReferenceComponent(
            "courtyard",
            reference_courtyard_spec,
            (0.0, 24.0, 0.0),
            arcade=True,
        ),
        ReferenceComponent(
            "court_to_hall",
            lambda: reference_connector_spec(
                "reference_court_to_hall", seed=105
            ),
            (16.0, 64.0, 0.0),
        ),
        ReferenceComponent(
            "great_hall", reference_great_hall_spec, (4.0, 72.0, 0.0)
        ),
    )


__all__ = [
    "ReferenceComponent",
    "reference_citadel_components",
    "reference_courtyard_spec",
    "reference_connector_spec",
    "reference_gatehouse_spec",
    "reference_great_hall_spec",
]

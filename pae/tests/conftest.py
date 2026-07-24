"""Shared pytest fixtures and helpers for PAE tests (WP-9)."""

from __future__ import annotations

import pytest

from pae.assemble import Placement
from pae.contract import FLOOR_T_CM, WALL_T_CM
from pae.tests.property.determinism import hash_assembly, normalize_placements

__all__ = [
    "hash_assembly",
    "normalize_placements",
    "sample_placements",
]


@pytest.fixture
def sample_placements() -> list[Placement]:
    """Tiny deterministic placement set for hash / golden scaffolding."""
    return [
        Placement(
            asset_id="wall_plain",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, 0.0),
        ),
        Placement(
            asset_id="floor_slab",
            cell=(0, 0),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
        ),
        Placement(
            asset_id="wall_plain",
            cell=(1, 0),
            level=0,
            yaw=90,
            offset_cm=(WALL_T_CM, 0.0, 0.0),
        ),
    ]


@pytest.fixture
def box_house_spec_dict() -> dict:
    """M1 box-house declarative spec (bays only — no world coords)."""
    return {
        "name": "box_house_m1",
        "style": "gothic_academy",
        "footprint": {
            "kind": "rect",
            "bays_x": 4,
            "bays_y": 3,
            "wing_depth": 2,
            "courtyard": False,
        },
        "storeys": 1,
        "storey_use": ["residence"],
        "towers": [],
        "roof": {"kind": "flat", "pitch": 1.0},
        "circulation": {"stair_kind": "straight", "stair_cells": []},
        "openings": {
            "windows_per_bay": 1,
            "doors_ground": 1,
            "skip_ground_windows": False,
        },
        "seed": 42,
    }

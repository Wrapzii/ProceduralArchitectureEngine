"""Primitive catalog — single registry for assemble / tests / docs."""

from __future__ import annotations

from typing import Dict, List, Optional

from pae.primitives.battlements import all_battlements
from pae.primitives.columns import all_columns
from pae.primitives.floors import all_floors
from pae.primitives.plinth import all_plinths
from pae.primitives.railings import all_railings
from pae.primitives.roofs import all_roofs
from pae.primitives.spires import all_spires
from pae.primitives.stairs import all_stairs
from pae.primitives.surfaces import all_surfaces
from pae.primitives.towers import all_towers
from pae.primitives.types import PrimitiveDescriptor
from pae.primitives.walls import all_walls


def all_descriptors() -> List[PrimitiveDescriptor]:
    pieces: List[PrimitiveDescriptor] = []
    pieces.extend(all_walls())
    pieces.extend(all_floors())
    pieces.extend(all_stairs())
    pieces.extend(all_towers())
    pieces.extend(all_battlements())
    pieces.extend(all_roofs())
    pieces.extend(all_plinths())
    pieces.extend(all_columns())
    pieces.extend(all_railings())
    pieces.extend(all_spires())
    pieces.extend(all_surfaces())
    return pieces


def catalog_by_id() -> Dict[str, PrimitiveDescriptor]:
    return {d.id: d for d in all_descriptors()}


def get(piece_id: str) -> PrimitiveDescriptor:
    cat = catalog_by_id()
    if piece_id not in cat:
        known = ", ".join(sorted(cat))
        raise KeyError(f"unknown primitive {piece_id!r}; known: {known}")
    return cat[piece_id]


def piece_ids() -> List[str]:
    return [d.id for d in all_descriptors()]


def build_mesh(piece_id: str, *, name: Optional[str] = None):
    """Dispatch optional bpy builder by piece id."""
    from pae.primitives import (
        battlements,
        columns,
        floors,
        plinth,
        railings,
        roofs,
        spires,
        stairs,
        surfaces,
        towers,
        walls,
    )

    desc = get(piece_id)
    builders = {
        "wall": walls.build_wall_mesh,
        "floor": floors.build_floor_mesh,
        "stair": stairs.build_stair_mesh,
        "tower_arc": towers.build_tower_mesh,
        "tower_crown": towers.build_tower_mesh,
        "tower_cap": towers.build_tower_mesh,
        "battlement": battlements.build_battlement_mesh,
        "roof": roofs.build_roof_mesh,
        "plinth": plinth.build_plinth_mesh,
        "column": columns.build_column_mesh,
        "barrier": railings.build_railing_mesh,
        "roofline": spires.build_spire_mesh,
        "surface": surfaces.build_surface_mesh,
    }
    builder = builders.get(desc.kind)
    if builder is None:
        raise KeyError(f"no bpy builder for kind {desc.kind!r}")
    return builder(desc, name=name)

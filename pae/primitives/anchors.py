"""Light-anchor markers — position-only kit for UE light spawn (S-068)."""

from __future__ import annotations

from typing import List, Optional

from pae.contract import STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc

_MARKER_SIZE_CM = (8.0, 8.0, 8.0)


def _marker(piece_id: str, *, tags: frozenset[str], notes: str) -> PrimitiveDescriptor:
    sx, sy, sz = _MARKER_SIZE_CM
    return PrimitiveDescriptor(
        id=piece_id,
        kind="light_anchor",
        footprint_modules=(1, 1),
        height_storeys=sz / STOREY_CM,
        size_cm=_MARKER_SIZE_CM,
        sockets=(
            SocketDesc(
                name="emit",
                pos_cm=(sx * 0.5, sy * 0.5, sz * 0.5),
                normal=(0.0, 0.0, 1.0),
                type="light_emit",
                tags=frozenset({"anchor"}),
            ),
        ),
        tags=tags | frozenset({"light_anchor", "marker"}),
        rotates_about_center=True,
        aabb_min_cm=(-sx * 0.5, -sy * 0.5, -sz * 0.5),
        notes=notes,
    )


def light_anchor_sconce() -> PrimitiveDescriptor:
    return _marker(
        "light_anchor_sconce",
        tags=frozenset({"sconce"}),
        notes="Wall sconce anchor — UE spawns point/spot on wall normal.",
    )


def light_anchor_chandelier() -> PrimitiveDescriptor:
    return _marker(
        "light_anchor_chandelier",
        tags=frozenset({"chandelier"}),
        notes="Hall chandelier anchor — centred below ceiling with headroom clearance.",
    )


def light_anchor_pendant() -> PrimitiveDescriptor:
    return _marker(
        "light_anchor_pendant",
        tags=frozenset({"pendant"}),
        notes="Pendant / lantern anchor — stairs and landings.",
    )


def all_anchors() -> List[PrimitiveDescriptor]:
    return [
        light_anchor_sconce(),
        light_anchor_chandelier(),
        light_anchor_pendant(),
    ]


def build_anchor_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Tiny centred marker cube for editor viz (UE uses position only)."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    sx, sy, sz = desc.size_cm
    if desc.rotates_about_center:
        x0, y0, z0 = -sx * 0.5, -sy * 0.5, -sz * 0.5
    else:
        x0, y0, z0 = 0.0, 0.0, 0.0
    # Axis-aligned box from min corner (x0,y0,z0).
    x1, y1, z1 = x0 + sx, y0 + sy, z0 + sz
    verts = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return bpy_util.mesh_from_verts_faces(name or desc.id, verts, faces)

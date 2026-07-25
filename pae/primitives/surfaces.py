"""Ground surfaces — paving, sidewalks, kerbs, lawn, steps.

WHY THIS EXISTS: everything in the kit up to now was *building*.  A school is not a
building, it is a site: ranges around a courtyard, a paved walk connecting them, a kerbed
sidewalk along the boundary, lawn in between.  Without surfaces the engine can only produce
objects floating on nothing, which is the void bug at campus scale.

Surfaces are thin, horizontal, non-structural and never enclose anything.  They get their
own kind so the validator neither demands support beneath them nor counts them toward
enclosure — a paving slab is not a floor and a lawn is not a roof.

Convention: one module square, ``FLOOR_T``-family thickness, min-corner origin, laid with
their **top** at the given level so you never step up onto a path.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

_PAVING_T_FRAC = 0.55  # of FLOOR_T — paving is thinner than a structural slab
_PATH_T_FRAC = 0.45
_LAWN_T_FRAC = 0.30
_KERB_T_FRAC = 1.10  # kerb stands proud of the path it edges
_KERB_W_FRAC = 0.10  # of MODULE
_STEP_RISERS = 3
_STEP_GRAND_RISERS = 5
_STEP_H_FRAC = 0.06  # of STOREY, per riser
_STEP_GRAND_H_FRAC = 0.10  # of STOREY, per riser — monumental approach
_JOINT_FRAC = 0.012  # of MODULE — visible joint between flags
_FLAGS_PER_BAY = 2


def _surface_sockets(thickness_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "surface"})
    half = MODULE_CM * 0.5
    return (
        SocketDesc(
            name="top",
            pos_cm=(half, half, thickness_cm),
            normal=(0.0, 0.0, 1.0),
            type="surface_top",
            tags=tag,
        ),
        SocketDesc(
            name="edge_a",
            pos_cm=(half, 0.0, thickness_cm * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="surface_edge",
            tags=tag,
        ),
        SocketDesc(
            name="edge_b",
            pos_cm=(half, MODULE_CM, thickness_cm * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="surface_edge",
            tags=tag,
        ),
    )


def _surface(
    piece_id: str,
    *,
    thickness_frac: float,
    tags: frozenset,
    notes: str,
    size_cm: Optional[Tuple[float, float, float]] = None,
) -> PrimitiveDescriptor:
    t = FLOOR_T_CM * thickness_frac
    size = size_cm or (MODULE_CM, MODULE_CM, t)
    return PrimitiveDescriptor(
        id=piece_id,
        kind="surface",
        footprint_modules=(1, 1),
        height_storeys=size[2] / STOREY_CM,
        size_cm=size,
        sockets=_surface_sockets(size[2], piece_id),
        tags=frozenset({"surface", "exterior", module_tag()}) | tags,
        origin="min_corner",
        notes=notes,
    )


def paving_flagstone() -> PrimitiveDescriptor:
    return _surface(
        "paving_flagstone",
        thickness_frac=_PAVING_T_FRAC,
        tags=frozenset({"paving", "courtyard", "flagstone"}),
        notes="Courtyard flagstone paving — jointed flags, one bay square.",
    )


def paving_cobble() -> PrimitiveDescriptor:
    return _surface(
        "paving_cobble",
        thickness_frac=_PAVING_T_FRAC,
        tags=frozenset({"paving", "cobble", "carriage"}),
        notes="Cobbled surface for carriage yards and gate approaches.",
    )


def sidewalk_slab() -> PrimitiveDescriptor:
    return _surface(
        "sidewalk_slab",
        thickness_frac=_PATH_T_FRAC,
        tags=frozenset({"path", "sidewalk", "circulation"}),
        notes="Sidewalk / walk bay — the unit of a path between buildings.",
    )


def kerb_edge() -> PrimitiveDescriptor:
    """Raised edge between a walk and what is beside it."""
    return _surface(
        "kerb_edge",
        thickness_frac=_KERB_T_FRAC,
        tags=frozenset({"kerb", "path", "edge"}),
        notes="Kerb strip; stands proud of the walk it edges.",
        size_cm=(
            MODULE_CM * _KERB_W_FRAC,
            MODULE_CM,
            FLOOR_T_CM * _KERB_T_FRAC,
        ),
    )


def lawn_patch() -> PrimitiveDescriptor:
    return _surface(
        "lawn_patch",
        thickness_frac=_LAWN_T_FRAC,
        tags=frozenset({"lawn", "grounds", "soft"}),
        notes="Soft ground infill between walks and buildings.",
    )


def steps_external() -> PrimitiveDescriptor:
    """Short external flight — takes a walk up onto a plinth or terrace."""
    h = STOREY_CM * _STEP_H_FRAC * _STEP_RISERS
    return _surface(
        "steps_external",
        thickness_frac=1.0,
        tags=frozenset({"steps", "path", "circulation"}),
        notes="Three-riser external step run across one bay.",
        size_cm=(MODULE_CM, MODULE_CM, h),
    )


def steps_grand() -> PrimitiveDescriptor:
    """Monumental fortress entrance flight — five wide risers (S-052)."""
    h = STOREY_CM * _STEP_GRAND_H_FRAC * _STEP_GRAND_RISERS
    return _surface(
        "steps_grand",
        thickness_frac=1.0,
        tags=frozenset({"steps", "path", "circulation", "grand", "fortress"}),
        notes="Five-riser grand exterior steps for gatehouse / hall entrances.",
        size_cm=(MODULE_CM, MODULE_CM, h),
    )


def all_surfaces() -> tuple:
    return (
        paving_flagstone(),
        paving_cobble(),
        sidewalk_slab(),
        kerb_edge(),
        lawn_patch(),
        steps_external(),
        steps_grand(),
    )


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def _flagged_parts(size_cm: Tuple[float, float, float], per_bay: int) -> List[BoxPart]:
    """Slab split into flags with a recessed joint, so paving reads as paving."""
    sx, sy, sz = size_cm
    joint = MODULE_CM * _JOINT_FRAC
    parts: List[BoxPart] = [((0.0, 0.0, 0.0), (sx, sy, sz * 0.55))]  # bedding course
    fx = (sx - joint * (per_bay - 1)) / per_bay
    fy = (sy - joint * (per_bay - 1)) / per_bay
    for i in range(per_bay):
        for j in range(per_bay):
            x = i * (fx + joint)
            y = j * (fy + joint)
            parts.append(((x, y, sz * 0.55), (fx, fy, sz * 0.45)))
    return parts


def _step_parts(
    size_cm: Tuple[float, float, float],
    risers: int,
) -> List[BoxPart]:
    sx, sy, sz = size_cm
    riser = sz / risers
    tread = sy / risers
    parts: List[BoxPart] = []
    for i in range(risers):
        # Each step spans the full width and the remaining depth behind it.
        parts.append(((0.0, i * tread, 0.0), (sx, sy - i * tread, riser * (i + 1))))
    return parts


def build_surface_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id

    if desc.id in ("paving_flagstone", "paving_cobble"):
        per_bay = _FLAGS_PER_BAY if desc.id == "paving_flagstone" else _FLAGS_PER_BAY * 3
        parts = _flagged_parts(desc.size_cm, per_bay)
    elif desc.id == "sidewalk_slab":
        parts = _flagged_parts(desc.size_cm, _FLAGS_PER_BAY)
    elif desc.id == "steps_external":
        parts = _step_parts(desc.size_cm, _STEP_RISERS)
    elif desc.id == "steps_grand":
        parts = _step_parts(desc.size_cm, _STEP_GRAND_RISERS)
    else:  # kerb, lawn — plain slabs
        parts = [((0.0, 0.0, 0.0), desc.size_cm)]

    return bpy_util.build_mesh_from_box_parts(
        obj_name, parts, origin_at_min_corner=True
    )

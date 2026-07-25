"""Roofline pieces — spires, finials, dormers, chimneys, cupolas, gablets.

WHY THIS EXISTS: the only cone in the kit was ``tower_cap``, welded to a tower drum.  A
school silhouette is made almost entirely of the things in this module: a spire over the
chapel, dormers lighting the attic storey, chimney stacks over every hall, a cupola on the
crossing.  Without them every building reads as a shed with a pitched lid, which is exactly
how the M3 gallery reads today.

These are **roofline** pieces.  They sit on top of a deck or a ridge and carry nothing, so
the validator treats them like roofs for the support check (a spire's base rests on the
roof, not on a wall below it).
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

_SPIRE_H_STOREYS = 2.4  # a spire is the tallest thing on the building
_SPIRE_CONICAL_H_STOREYS = 2.0  # fortress round-tower cone (S-017)
_SPIRE_BASE_FRAC = 0.62  # of MODULE, at the springing
_SPIRE_CONICAL_BASE_FRAC = 0.50  # mates tower_cap drum diameter (2×MODULE)
_SPIRE_SEGMENTS = 32
_BROACH_H_FRAC = 0.18  # of spire height — square-to-octagon transition
_FINIAL_H_FRAC = 0.30  # of STOREY
_FINIAL_W_FRAC = 0.10  # of MODULE
_CUPOLA_H_STOREYS = 1.1
_CUPOLA_R_FRAC = 0.34  # of MODULE
_CUPOLA_POSTS = 8
_CHIMNEY_W_FRAC = 0.26  # of MODULE
_CHIMNEY_H_STOREYS = 1.35
_CHIMNEY_POTS = 2
_DORMER_W_FRAC = 0.55  # of MODULE
_DORMER_H_FRAC = 0.72  # of STOREY
_DORMER_STEEP_H_FRAC = 0.90  # of STOREY — reads on steep pitched roofs
_DORMER_D_FRAC = 0.55  # of MODULE
_GABLET_H_FRAC = 0.55
_ROOF_SEGMENTS = 16


def _top_socket(height_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "roofline"})
    half = MODULE_CM * 0.5
    return (
        SocketDesc(
            name="bottom",
            pos_cm=(half, half, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="roofline_base",
            tags=tag,
        ),
        SocketDesc(
            name="apex",
            pos_cm=(half, half, height_cm),
            normal=(0.0, 0.0, 1.0),
            type="finial_seat",
            tags=tag,
        ),
    )


def _roofline(
    piece_id: str,
    *,
    height_storeys: float,
    size_cm: Tuple[float, float, float],
    tags: frozenset,
    notes: str,
    rotates_about_center: bool = False,
) -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id=piece_id,
        kind="roofline",
        footprint_modules=(1, 1),
        height_storeys=height_storeys,
        size_cm=size_cm,
        sockets=_top_socket(size_cm[2], piece_id),
        tags=frozenset({"roofline", module_tag()}) | tags,
        origin="min_corner",
        rotates_about_center=rotates_about_center,
        notes=notes,
    )


def spire_octagonal() -> PrimitiveDescriptor:
    h = STOREY_CM * _SPIRE_H_STOREYS
    return _roofline(
        "spire_octagonal",
        height_storeys=_SPIRE_H_STOREYS,
        size_cm=(MODULE_CM, MODULE_CM, h),
        tags=frozenset({"spire", "gothic", "chapel"}),
        notes="Broached octagonal spire — square base, octagonal shaft, sharp apex.",
        rotates_about_center=True,
    )


def spire_needle() -> PrimitiveDescriptor:
    h = STOREY_CM * _SPIRE_H_STOREYS * 0.75
    return _roofline(
        "spire_needle",
        height_storeys=_SPIRE_H_STOREYS * 0.75,
        size_cm=(MODULE_CM, MODULE_CM, h),
        tags=frozenset({"spire", "needle", "turret"}),
        notes="Slim conical needle for corner turrets.",
        rotates_about_center=True,
    )


def spire_conical() -> PrimitiveDescriptor:
    """Round-tower conical cap — fortress / keep silhouette (S-017)."""
    h = STOREY_CM * _SPIRE_CONICAL_H_STOREYS
    return _roofline(
        "spire_conical",
        height_storeys=_SPIRE_CONICAL_H_STOREYS,
        size_cm=(MODULE_CM, MODULE_CM, h),
        tags=frozenset({"spire", "conical", "fortress", "tower"}),
        notes="Smooth conical spire over a round tower drum; mates tower_cap.",
        rotates_about_center=True,
    )


def finial() -> PrimitiveDescriptor:
    h = STOREY_CM * _FINIAL_H_FRAC
    w = MODULE_CM * _FINIAL_W_FRAC
    return _roofline(
        "finial",
        height_storeys=_FINIAL_H_FRAC,
        size_cm=(w, w, h),
        tags=frozenset({"finial", "ornament"}),
        notes="Apex ornament; seats on a spire, cupola or gable apex.",
        rotates_about_center=True,
    )


def cupola() -> PrimitiveDescriptor:
    h = STOREY_CM * _CUPOLA_H_STOREYS
    return _roofline(
        "cupola",
        height_storeys=_CUPOLA_H_STOREYS,
        size_cm=(MODULE_CM, MODULE_CM, h),
        tags=frozenset({"cupola", "lantern", "crossing"}),
        notes="Open lantern: posts carrying a small dome — bell / clock stage.",
        rotates_about_center=True,
    )


def chimney_stack() -> PrimitiveDescriptor:
    h = STOREY_CM * _CHIMNEY_H_STOREYS
    w = MODULE_CM * _CHIMNEY_W_FRAC
    return _roofline(
        "chimney_stack",
        height_storeys=_CHIMNEY_H_STOREYS,
        size_cm=(w, w, h),
        tags=frozenset({"chimney", "stack"}),
        notes="Masonry stack with a corbelled cap and pots.",
    )


def dormer_gabled() -> PrimitiveDescriptor:
    return _roofline(
        "dormer_gabled",
        height_storeys=_DORMER_H_FRAC,
        size_cm=(
            MODULE_CM * _DORMER_D_FRAC,
            MODULE_CM * _DORMER_W_FRAC,
            STOREY_CM * _DORMER_H_FRAC,
        ),
        tags=frozenset({"dormer", "attic", "window"}),
        notes="Gabled dormer with a light — breaks the roof plane, lights the attic.",
    )


def dormer_steep() -> PrimitiveDescriptor:
    """Taller dormer for steep-pitch hall roofs (wizard academy / fortress ranges)."""
    return _roofline(
        "dormer_steep",
        height_storeys=_DORMER_STEEP_H_FRAC,
        size_cm=(
            MODULE_CM * _DORMER_D_FRAC,
            MODULE_CM * _DORMER_W_FRAC,
            STOREY_CM * _DORMER_STEEP_H_FRAC,
        ),
        tags=frozenset({"dormer", "attic", "window", "steep"}),
        notes="Steep gabled dormer — taller peak for high-pitch roof silhouettes.",
    )


def gablet() -> PrimitiveDescriptor:
    return _roofline(
        "gablet",
        height_storeys=_GABLET_H_FRAC,
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM * _GABLET_H_FRAC),
        tags=frozenset({"gablet", "wall_head", "ornament"}),
        notes="Decorative gable over a bay or an entrance.",
    )


def all_spires() -> tuple:
    return (
        spire_octagonal(),
        spire_needle(),
        spire_conical(),
        finial(),
        cupola(),
        chimney_stack(),
        dormer_gabled(),
        dormer_steep(),
        gablet(),
    )


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def _tapered_prism_verts(
    centre: Tuple[float, float],
    z0: float,
    z1: float,
    r0: float,
    r1: float,
    segments: int,
    *,
    apex: bool = False,
):
    """Verts/faces for a tapered prism (or a pyramid when ``apex``)."""
    cx, cy = centre
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    for i in range(segments):
        a = 2.0 * math.pi * (i + 0.5) / segments
        verts.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a), z0))
    if apex:
        tip = len(verts)
        verts.append((cx, cy, z1))
        for i in range(segments):
            faces.append([i, (i + 1) % segments, tip])
    else:
        for i in range(segments):
            a = 2.0 * math.pi * (i + 0.5) / segments
            verts.append((cx + r1 * math.cos(a), cy + r1 * math.sin(a), z1))
        for i in range(segments):
            a0, a1 = i, (i + 1) % segments
            faces.append([a0, a1, a1 + segments, a0 + segments])
    # Close the bottom.
    base = len(verts)
    verts.append((cx, cy, z0))
    for i in range(segments):
        faces.append([base, (i + 1) % segments, i])
    return verts, faces


def _conical_spire_mesh(name: str, desc: PrimitiveDescriptor):
    """Smooth cone over a round tower — no broach, wide springing ring."""
    from pae.primitives import bpy_util

    cx = cy = MODULE_CM * 0.5
    h = desc.size_cm[2]
    r = MODULE_CM * _SPIRE_CONICAL_BASE_FRAC
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []

    def add(vs, fs):
        off = len(verts)
        verts.extend(vs)
        faces.extend([[i + off for i in f] for f in fs])

    collar_h = h * 0.08
    add(*_tapered_prism_verts((cx, cy), 0.0, collar_h, r * 1.04, r, _SPIRE_SEGMENTS, apex=False))
    add(*_tapered_prism_verts((cx, cy), collar_h, h, r, 0.0, _SPIRE_SEGMENTS, apex=True))
    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    bpy_util.smooth_shade_curved_faces(obj)
    return obj


def _spire_mesh(name: str, desc: PrimitiveDescriptor, *, segments: int, broach: bool):
    from pae.primitives import bpy_util

    cx = cy = MODULE_CM * 0.5
    h = desc.size_cm[2]
    r = MODULE_CM * _SPIRE_BASE_FRAC * 0.5
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []

    def add(vs, fs):
        off = len(verts)
        verts.extend(vs)
        faces.extend([[i + off for i in f] for f in fs])

    z = 0.0
    if broach:
        # Square broach base transitioning to the octagonal shaft.
        bh = h * _BROACH_H_FRAC
        add(*_tapered_prism_verts((cx, cy), 0.0, bh, r * 1.30, r, 4, apex=False))
        z = bh
    add(*_tapered_prism_verts((cx, cy), z, h, r, 0.0, segments, apex=True))

    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    bpy_util.smooth_shade_curved_faces(obj)
    return obj


def _cupola_mesh(name: str, desc: PrimitiveDescriptor):
    from pae.primitives import bpy_util

    cx = cy = MODULE_CM * 0.5
    h = desc.size_cm[2]
    r = MODULE_CM * _CUPOLA_R_FRAC
    post_w = MODULE_CM * 0.05
    deck_h = h * 0.10
    dome_h = h * 0.34
    post_h = h - deck_h - dome_h

    parts: List[BoxPart] = [
        ((cx - r, cy - r, 0.0), (r * 2.0, r * 2.0, deck_h)),
    ]
    for i in range(_CUPOLA_POSTS):
        a = 2.0 * math.pi * i / _CUPOLA_POSTS
        px, py = cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a)
        parts.append(((px - post_w * 0.5, py - post_w * 0.5, deck_h), (post_w, post_w, post_h)))
    obj = bpy_util.build_mesh_from_box_parts(name, parts, origin_at_min_corner=True)

    # Dome on top, welded in as a second mesh part.
    verts, faces = _tapered_prism_verts(
        (cx, cy), deck_h + post_h, h, r, 0.0, _ROOF_SEGMENTS, apex=True
    )
    dome = bpy_util.mesh_from_verts_faces(f"{name}_dome", verts, faces)
    bpy_util.smooth_shade_curved_faces(dome)
    return bpy_util._merge_mesh_parts(name, [obj, dome])


def _chimney_parts(desc: PrimitiveDescriptor) -> List[BoxPart]:
    w, _d, h = desc.size_cm
    shaft_h = h * 0.78
    cap_h = h * 0.08
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (w, w, shaft_h)),
        ((-w * 0.09, -w * 0.09, shaft_h), (w * 1.18, w * 1.18, cap_h)),
    ]
    pot_w = w * 0.26
    pot_h = h - shaft_h - cap_h
    for i in range(_CHIMNEY_POTS):
        cx = w * (i + 0.5) / _CHIMNEY_POTS
        parts.append(((cx - pot_w * 0.5, w * 0.5 - pot_w * 0.5, shaft_h + cap_h), (pot_w, pot_w, pot_h)))
    return parts


def _dormer_parts(desc: PrimitiveDescriptor, *, steep: bool = False) -> List[BoxPart]:
    """Cheeks, front wall with a light, and a stepped gable roof."""
    d, w, h = desc.size_cm
    cheek_t = WALL_T_CM * 0.4
    body_h = h * (0.58 if steep else 0.62)
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (d, cheek_t, body_h)),
        ((0.0, w - cheek_t, 0.0), (d, cheek_t, body_h)),
    ]
    # Front wall with a window opening punched through the depth axis.
    front_t = WALL_T_CM * 0.4
    op_w, op_h = w * 0.52, body_h * 0.62
    op0 = (w - op_w) * 0.5
    sill = body_h * 0.22
    parts.append(((0.0, cheek_t, 0.0), (front_t, op0 - cheek_t, body_h)))
    parts.append(((0.0, op0 + op_w, 0.0), (front_t, w - cheek_t - op0 - op_w, body_h)))
    parts.append(((0.0, op0, 0.0), (front_t, op_w, sill)))
    parts.append(((0.0, op0, sill + op_h), (front_t, op_w, body_h - sill - op_h)))
    # Stepped gable roof — more steps + sharper peak on steep variant.
    steps = 8 if steep else 6
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        half = (w * 0.5) * (1.0 - t1)
        parts.append(
            (
                (0.0, w * 0.5 - half, body_h + (h - body_h) * t0),
                (d, half * 2.0, (h - body_h) / steps),
            )
        )
    return parts


def _gablet_parts(desc: PrimitiveDescriptor) -> List[BoxPart]:
    t, w, h = desc.size_cm
    steps = 8
    parts: List[BoxPart] = []
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        half = (w * 0.5) * (1.0 - t1)
        parts.append(((0.0, w * 0.5 - half, h * t0), (t, half * 2.0, h / steps)))
    return parts


def build_spire_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id

    if desc.id == "spire_octagonal":
        return _spire_mesh(obj_name, desc, segments=8, broach=True)
    if desc.id == "spire_needle":
        return _spire_mesh(obj_name, desc, segments=_SPIRE_SEGMENTS, broach=False)
    if desc.id == "spire_conical":
        return _conical_spire_mesh(obj_name, desc)
    if desc.id == "finial":
        w = desc.size_cm[0]
        verts, faces = _tapered_prism_verts(
            (w * 0.5, w * 0.5), 0.0, desc.size_cm[2], w * 0.5, 0.0, 8, apex=True
        )
        return bpy_util.mesh_from_verts_faces(obj_name, verts, faces)
    if desc.id == "cupola":
        return _cupola_mesh(obj_name, desc)

    if desc.id == "chimney_stack":
        parts = _chimney_parts(desc)
    elif desc.id in ("dormer_gabled", "dormer_steep"):
        parts = _dormer_parts(desc, steep="steep" in desc.tags)
    else:  # gablet
        parts = _gablet_parts(desc)

    return bpy_util.build_mesh_from_box_parts(
        obj_name, parts, origin_at_min_corner=True
    )

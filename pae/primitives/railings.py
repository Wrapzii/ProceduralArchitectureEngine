"""Barriers — fences, railings, balustrades, parapets, gates.

WHY THIS EXISTS: a school has grounds.  Grounds have a boundary, courtyards have edges,
terraces and galleries and stair landings need something stopping you walking off them.
None of that is a *wall* — a wall is opaque, storey-height and load-bearing.  These are
waist-height, see-through and carry nothing, so they need their own kind: the validator
must not demand vertical support *above* them, and must not count them as enclosure.

All barriers share a run of one module along Y so they tile on the same boundary lines as
walls (§2.3) and inherit the same yaw-offset table.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

_RAIL_H_FRAC = 0.30  # of STOREY — waist height
_PARAPET_H_FRAC = 0.34
_FENCE_H_FRAC = 0.42  # boundary fences stand taller than an internal rail
_BARRIER_T_FRAC = 0.30  # of WALL_T — barriers are thinner than walls
_PARAPET_T_FRAC = 0.65

_POST_W_FRAC = 0.09  # of MODULE
_BALUSTER_W_FRAC = 0.045
_BALUSTERS_PER_BAY = 7
_PICKETS_PER_BAY = 9
_RAIL_BAR_H_FRAC = 0.10  # of barrier height
_GATE_LEAF_GAP_FRAC = 0.04  # of MODULE — visible centre joint


def _barrier_sockets(height_cm: float, thick_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "barrier"})
    return (
        SocketDesc(
            name="end_a",
            pos_cm=(thick_cm * 0.5, 0.0, height_cm * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="barrier_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(thick_cm * 0.5, MODULE_CM, height_cm * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="barrier_end",
            tags=tag,
        ),
        SocketDesc(
            name="bottom",
            pos_cm=(thick_cm * 0.5, MODULE_CM * 0.5, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="barrier_base",
            tags=tag,
        ),
    )


def _barrier(
    piece_id: str,
    *,
    height_frac: float,
    thick_frac: float,
    tags: frozenset,
    notes: str,
) -> PrimitiveDescriptor:
    h = STOREY_CM * height_frac
    t = WALL_T_CM * thick_frac
    return PrimitiveDescriptor(
        id=piece_id,
        kind="barrier",
        footprint_modules=(1, 1),
        height_storeys=height_frac,
        size_cm=(t, MODULE_CM, h),
        sockets=_barrier_sockets(h, t, piece_id),
        tags=frozenset({"barrier", module_tag()}) | tags,
        origin="min_corner",
        notes=notes,
    )


def fence_picket() -> PrimitiveDescriptor:
    return _barrier(
        "fence_picket",
        height_frac=_FENCE_H_FRAC,
        thick_frac=_BARRIER_T_FRAC,
        tags=frozenset({"fence", "exterior", "grounds"}),
        notes="Boundary fence: posts with vertical pickets and two rails.",
    )


def railing_metal() -> PrimitiveDescriptor:
    return _barrier(
        "railing_metal",
        height_frac=_RAIL_H_FRAC,
        thick_frac=_BARRIER_T_FRAC * 0.6,
        tags=frozenset({"railing", "interior", "gallery", "stair"}),
        notes="Slim rail for galleries, landings and stair edges.",
    )


def balustrade_stone() -> PrimitiveDescriptor:
    return _barrier(
        "balustrade_stone",
        height_frac=_RAIL_H_FRAC,
        thick_frac=_BARRIER_T_FRAC,
        tags=frozenset({"balustrade", "exterior", "terrace"}),
        notes="Turned balusters between a plinth and a coping rail.",
    )


def parapet_solid() -> PrimitiveDescriptor:
    return _barrier(
        "parapet_solid",
        height_frac=_PARAPET_H_FRAC,
        thick_frac=_PARAPET_T_FRAC,
        tags=frozenset({"parapet", "exterior", "roof_edge"}),
        notes="Solid low wall for roof edges and terrace perimeters.",
    )


def gate_iron() -> PrimitiveDescriptor:
    return _barrier(
        "gate_iron",
        height_frac=_FENCE_H_FRAC,
        thick_frac=_BARRIER_T_FRAC * 0.6,
        tags=frozenset({"gate", "fence", "exterior", "grounds", "opening"}),
        notes="Two-leaf gate matching fence height; centre joint left open.",
    )


def all_railings() -> tuple:
    return (
        fence_picket(),
        railing_metal(),
        balustrade_stone(),
        parapet_solid(),
        gate_iron(),
    )


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def _posts_and_rails(
    size_cm: Tuple[float, float, float],
    *,
    infill_count: int,
    infill_w_frac: float,
    rails: Tuple[float, ...],
    infill_z: Tuple[float, float],
    centre_gap_frac: float = 0.0,
) -> List[BoxPart]:
    """Generic barrier: end posts, horizontal rails, evenly spaced vertical infill."""
    tx, ty, tz = size_cm
    post_w = MODULE_CM * _POST_W_FRAC
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (tx, post_w, tz)),
        ((0.0, ty - post_w, 0.0), (tx, post_w, tz)),
    ]

    bar_h = tz * _RAIL_BAR_H_FRAC
    inner0, inner1 = post_w, ty - post_w
    span = inner1 - inner0
    for frac in rails:
        z = min(max(0.0, tz * frac - bar_h * 0.5), tz - bar_h)
        parts.append(((0.0, inner0, z), (tx, span, bar_h)))

    gap = MODULE_CM * centre_gap_frac
    iw = MODULE_CM * infill_w_frac
    z0 = tz * infill_z[0]
    z1 = tz * infill_z[1]
    for i in range(infill_count):
        centre = inner0 + span * (i + 0.5) / infill_count
        if gap > 0.0 and abs(centre - ty * 0.5) < gap * 0.5:
            continue  # gate centre joint
        parts.append(((0.0, centre - iw * 0.5, z0), (tx, iw, z1 - z0)))
    return parts


def _balustrade_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    """Plinth, coping and turned balusters between them."""
    tx, ty, tz = size_cm
    plinth_h = tz * 0.14
    coping_h = tz * 0.12
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (tx, ty, plinth_h)),
        ((-tx * 0.1, 0.0, tz - coping_h), (tx * 1.2, ty, coping_h)),
    ]
    bw = MODULE_CM * _BALUSTER_W_FRAC
    z0, z1 = plinth_h, tz - coping_h
    # Waisted profile: three stacked boxes read as a turned baluster at kit scale.
    for i in range(_BALUSTERS_PER_BAY):
        c = ty * (i + 0.5) / _BALUSTERS_PER_BAY
        h = z1 - z0
        parts.append(((tx * 0.15, c - bw * 0.5, z0), (tx * 0.7, bw, h * 0.22)))
        parts.append(((tx * 0.25, c - bw * 0.35, z0 + h * 0.22), (tx * 0.5, bw * 0.7, h * 0.56)))
        parts.append(((tx * 0.15, c - bw * 0.5, z0 + h * 0.78), (tx * 0.7, bw, h * 0.22)))
    return parts


def build_railing_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id

    if desc.id == "parapet_solid":
        parts: List[BoxPart] = [((0.0, 0.0, 0.0), desc.size_cm)]
    elif desc.id == "balustrade_stone":
        parts = _balustrade_parts(desc.size_cm)
    elif desc.id == "fence_picket":
        parts = _posts_and_rails(
            desc.size_cm,
            infill_count=_PICKETS_PER_BAY,
            infill_w_frac=_BALUSTER_W_FRAC * 1.4,
            rails=(0.30, 0.82),
            infill_z=(0.05, 1.0),
        )
    elif desc.id == "gate_iron":
        parts = _posts_and_rails(
            desc.size_cm,
            infill_count=_PICKETS_PER_BAY,
            infill_w_frac=_BALUSTER_W_FRAC,
            rails=(0.20, 0.92),
            infill_z=(0.05, 1.0),
            centre_gap_frac=_GATE_LEAF_GAP_FRAC,
        )
    else:  # railing_metal
        parts = _posts_and_rails(
            desc.size_cm,
            infill_count=_BALUSTERS_PER_BAY,
            infill_w_frac=_BALUSTER_W_FRAC * 0.8,
            rails=(0.55, 0.95),
            infill_z=(0.0, 0.95),
        )

    return bpy_util.build_mesh_from_box_parts(
        obj_name, parts, origin_at_min_corner=True
    )

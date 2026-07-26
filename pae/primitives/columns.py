"""Free-standing vertical supports and openings — pillars, columns, arches, buttresses.

WHY THIS EXISTS: the kit could build a *box with holes in it*.  A school is not a box.  It
has cloister walks where a colonnade carries the upper storey, undercrofts where piers take
the load instead of walls, gatehouses that are an arch with no wall around them, and
buttresses that keep a tall hall standing up.  None of that was expressible.

Everything here is a **structural** piece — it carries load and it participates in the
validator's support and connectivity checks.  Decorative mouldings belong in the Comfy
pipeline, not in this module.

Convention: square pieces are centred in their bay on XY but keep a ``min_corner`` origin so
the assembler's yaw-offset table (§2.2) applies unchanged.  Round columns set
``rotates_about_center`` so they are not scattered across four cells (the tower bug).
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

# Proportions as fractions of the contract — never raw dimensions.
_PIER_W_FRAC = 0.28  # square pier side, of MODULE
_COLUMN_R_FRAC = 0.11  # round shaft radius, of MODULE
_CAPITAL_H_FRAC = 0.07  # of STOREY
_CAPITAL_FLARE = 1.55  # capital width / shaft width
_BASE_H_FRAC = 0.05  # of STOREY
_BASE_FLARE = 1.35
_PILASTER_D_FRAC = 0.5  # projection from wall face, of WALL_T
_PILASTER_W_FRAC = 0.22  # of MODULE
# Projection, of MODULE. Was 0.85 — a 3.4 m lump sticking out of the wall, nearly as
# deep as it was tall, which read as an unidentifiable block rather than as masonry.
# User: "the buttresses or whatever ... I don't even know what they are."
_BUTTRESS_D_FRAC = 0.16  # projection, of MODULE  (64 cm — about its own width)
_BUTTRESS_W_FRAC = 0.17  # of MODULE               (68 cm)
_BUTTRESS_BATTER = 0.62  # top depth / bottom depth — sloped weathering
# Two set-offs, not four. Four coarse steps over one storey made a zigzag stack of
# blocks rather than a batter; stacked up three storeys that read as twelve blocks.
_BUTTRESS_STEPS = 2
_ARCH_PIER_FRAC = 0.11  # of MODULE — slim pier, wide clear opening
_ARCH_SPRING_FRAC = 0.10  # of STOREY — low spring = monumental headroom
_ARCH_BANDS = 24  # smooth semicircle, not stepped blocks
_COLUMN_SEGMENTS = 24
# Spiral tower newel — thicker than a colonnade shaft; greybox cylinder/box.
_NEWEL_D_FRAC = 0.22  # of MODULE (diameter)


def _shaft_sockets(width_cm: float, height_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece})
    half = MODULE_CM * 0.5
    return (
        SocketDesc(
            name="bottom",
            pos_cm=(half, half, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="column_base",
            tags=tag,
        ),
        SocketDesc(
            name="top",
            pos_cm=(half, half, height_cm),
            normal=(0.0, 0.0, 1.0),
            type="column_head",
            tags=tag,
        ),
    )


def _centred_square_parts(
    width_cm: float,
    height_cm: float,
    *,
    base_h: float,
    base_flare: float,
    cap_h: float,
    cap_flare: float,
) -> List[BoxPart]:
    """Base block, shaft and capital, centred on the bay."""
    cx = MODULE_CM * 0.5
    parts: List[BoxPart] = []

    def block(w: float, z0: float, h: float) -> BoxPart:
        return ((cx - w * 0.5, cx - w * 0.5, z0), (w, w, h))

    z = 0.0
    if base_h > 0.0:
        parts.append(block(width_cm * base_flare, z, base_h))
        z += base_h
    shaft_h = height_cm - base_h - cap_h
    if shaft_h > 0.0:
        parts.append(block(width_cm, z, shaft_h))
        z += shaft_h
    if cap_h > 0.0:
        parts.append(block(width_cm * cap_flare, z, cap_h))
    return parts


def pier_square() -> PrimitiveDescriptor:
    """Square masonry pier — the workhorse support of an undercroft or arcade."""
    w = MODULE_CM * _PIER_W_FRAC
    return PrimitiveDescriptor(
        id="pier_square",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
        sockets=_shaft_sockets(w, STOREY_CM, "pier"),
        tags=frozenset({"column", "pier", "structural", "interior", module_tag()}),
        origin="min_corner",
        notes="Square pier with base and capital, centred in its bay.",
    )


def column_round() -> PrimitiveDescriptor:
    """Round column with base and capital — cloister and hall colonnades."""
    return PrimitiveDescriptor(
        id="column_round",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
        sockets=_shaft_sockets(MODULE_CM * _COLUMN_R_FRAC * 2.0, STOREY_CM, "column"),
        tags=frozenset({"column", "round", "structural", "interior", module_tag()}),
        origin="min_corner",
        rotates_about_center=True,
        notes="Round shaft, flared base and capital; centred so yaw does not scatter it.",
    )


def pilaster() -> PrimitiveDescriptor:
    """Shallow engaged pier standing proud of a wall face — articulates long ranges."""
    depth = WALL_T_CM * _PILASTER_D_FRAC
    w = MODULE_CM * _PILASTER_W_FRAC
    tag = frozenset({module_tag(), "pilaster"})
    return PrimitiveDescriptor(
        id="pilaster",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(depth, w, STOREY_CM),
        sockets=(
            SocketDesc(
                name="back",
                pos_cm=(depth, w * 0.5, STOREY_CM * 0.5),
                normal=(1.0, 0.0, 0.0),
                type="wall_face",
                tags=tag,
            ),
        ),
        tags=frozenset({"column", "pilaster", "decorative", "exterior", module_tag()}),
        origin="min_corner",
        notes="Engaged pier; back face mates to a wall's outer face.",
    )


def buttress() -> PrimitiveDescriptor:
    """Stepped buttress with a battered face — takes thrust off a tall wall."""
    depth = MODULE_CM * _BUTTRESS_D_FRAC
    w = MODULE_CM * _BUTTRESS_W_FRAC
    tag = frozenset({module_tag(), "buttress"})
    return PrimitiveDescriptor(
        id="buttress",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(depth, w, STOREY_CM),
        sockets=(
            SocketDesc(
                name="back",
                pos_cm=(depth, w * 0.5, STOREY_CM * 0.5),
                normal=(1.0, 0.0, 0.0),
                type="wall_face",
                tags=tag,
            ),
            SocketDesc(
                name="bottom",
                pos_cm=(depth * 0.5, w * 0.5, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="column_base",
                tags=tag,
            ),
        ),
        tags=frozenset({"column", "buttress", "structural", "exterior", module_tag()}),
        origin="min_corner",
        notes="Projects from the wall face; batters back in steps toward the top.",
    )


def arch_freestanding() -> PrimitiveDescriptor:
    """Two piers carrying an arch, with no wall around it — cloister bay, gateway.

    Distinct from ``wall_arcade``: that is a *wall* with an arch cut into it and reads as
    solid at the ends.  This is open on both faces — you can see through it sideways.
    """
    tag = frozenset({module_tag(), "arch"})
    return PrimitiveDescriptor(
        id="arch_freestanding",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        sockets=(
            SocketDesc(
                name="end_a",
                pos_cm=(WALL_T_CM * 0.5, 0.0, STOREY_CM * 0.5),
                normal=(0.0, -1.0, 0.0),
                type="wall_end",
                tags=tag,
            ),
            SocketDesc(
                name="end_b",
                pos_cm=(WALL_T_CM * 0.5, MODULE_CM, STOREY_CM * 0.5),
                normal=(0.0, 1.0, 0.0),
                type="wall_end",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {"column", "arch", "arcade", "structural", "cloister", module_tag()}
        ),
        origin="min_corner",
        notes="Open arch on two piers; ends butt to neighbours so runs stay connected.",
    )


def arch_rib_freestanding() -> PrimitiveDescriptor:
    """Thin transverse structural rib: two piers joined by a curved band."""
    tag = frozenset({module_tag(), "arch", "arch_rib", "structural"})
    return PrimitiveDescriptor(
        id="arch_rib_freestanding",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        sockets=(
            SocketDesc(
                name="base_a",
                pos_cm=(WALL_T_CM * 0.5, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="column_base",
                tags=tag,
            ),
            SocketDesc(
                name="base_b",
                pos_cm=(WALL_T_CM * 0.5, MODULE_CM, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="column_base",
                tags=tag,
            ),
            SocketDesc(
                name="apex",
                pos_cm=(WALL_T_CM * 0.5, MODULE_CM * 0.5, STOREY_CM),
                normal=(0.0, 0.0, 1.0),
                type="column_head",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {
                "column",
                "arch",
                "arch_rib",
                "structural",
                "interior",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Two bearing piers and a smooth extruded arch band; no spandrel or plate.",
    )


def spiral_newel() -> PrimitiveDescriptor:
    """Central newel pillar for a spiral / helical tower stair (Phase 4.7 shell).

    Greybox cylinder (or box fallback) on the drum axis. Sub-bay footprint so the
    AABB does not swallow the whole bay; ``rotates_about_center`` keeps it on axis
    under yaw. Registered as ``kind=column`` for support / island rules.
    """
    d = MODULE_CM * _NEWEL_D_FRAC
    tag = frozenset({module_tag(), "newel", "spiral_shell", "column", "structural"})
    half = d * 0.5
    return PrimitiveDescriptor(
        id="spiral_newel",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(d, d, STOREY_CM),
        sockets=(
            SocketDesc(
                name="bottom",
                pos_cm=(half, half, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="column_base",
                tags=tag,
            ),
            SocketDesc(
                name="top",
                pos_cm=(half, half, STOREY_CM),
                normal=(0.0, 0.0, 1.0),
                type="column_head",
                tags=tag,
            ),
        ),
        tags=tag,
        origin="center",
        rotates_about_center=True,
        aabb_min_cm=(-half, -half, 0.0),
        notes=(
            f"Spiral newel diameter {_NEWEL_D_FRAC:.2f}×MODULE "
            f"({d:.1f} cm); greybox cylinder on tower axis."
        ),
    )


def all_columns() -> tuple:
    return (
        pier_square(),
        column_round(),
        pilaster(),
        buttress(),
        arch_freestanding(),
        arch_rib_freestanding(),
        spiral_newel(),
    )


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def _buttress_parts() -> List[BoxPart]:
    """Stepped, battered mass: deep at the base, shallow at the head."""
    depth = MODULE_CM * _BUTTRESS_D_FRAC
    w = MODULE_CM * _BUTTRESS_W_FRAC
    parts: List[BoxPart] = []
    step_h = STOREY_CM / _BUTTRESS_STEPS
    for i in range(_BUTTRESS_STEPS):
        t = i / max(1, _BUTTRESS_STEPS - 1)
        d = depth * (1.0 - t * (1.0 - _BUTTRESS_BATTER))
        parts.append(((depth - d, 0.0, i * step_h), (d, w, step_h)))
    return parts


def _freestanding_arch_parts() -> List[BoxPart]:
    """Piers plus a banded arch ring spanning between them."""
    pier_w = MODULE_CM * _ARCH_PIER_FRAC
    spring = STOREY_CM * _ARCH_SPRING_FRAC
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (WALL_T_CM, pier_w, spring)),
        ((0.0, MODULE_CM - pier_w, 0.0), (WALL_T_CM, pier_w, spring)),
    ]
    # Semicircular head from the pier faces to the apex.
    half = (MODULE_CM - 2.0 * pier_w) * 0.5
    centre = MODULE_CM * 0.5
    rise = half
    for i in range(_ARCH_BANDS):
        t0 = i / _ARCH_BANDS
        t1 = (i + 1) / _ARCH_BANDS
        # Solid outside the opening: band width shrinks as the arc closes.
        inner = half * math.sqrt(max(0.0, 1.0 - t1 * t1))
        z0 = spring + rise * t0
        h = rise * (t1 - t0)
        parts.append(((0.0, centre - half, z0), (WALL_T_CM, half - inner, h)))
        parts.append(((0.0, centre + inner, z0), (WALL_T_CM, half - inner, h)))
    # Spandrel block above the apex ties the two halves together.
    top = spring + rise
    if top < STOREY_CM:
        parts.append(((0.0, 0.0, top), (WALL_T_CM, MODULE_CM, STOREY_CM - top)))
    return parts


def _round_column_mesh(name: str):
    from pae.primitives import bpy_util

    r = MODULE_CM * _COLUMN_R_FRAC
    cx = cy = MODULE_CM * 0.5
    base_h = STOREY_CM * _BASE_H_FRAC
    cap_h = STOREY_CM * _CAPITAL_H_FRAC
    shaft_h = STOREY_CM - base_h - cap_h

    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []

    def drum(radius: float, z0: float, z1: float) -> None:
        start = len(verts)
        for i in range(_COLUMN_SEGMENTS):
            a = 2.0 * math.pi * i / _COLUMN_SEGMENTS
            x, y = cx + radius * math.cos(a), cy + radius * math.sin(a)
            verts.append((x, y, z0))
            verts.append((x, y, z1))
        for i in range(_COLUMN_SEGMENTS):
            a0 = start + 2 * i
            a1 = start + 2 * ((i + 1) % _COLUMN_SEGMENTS)
            faces.append([a0, a1, a1 + 1, a0 + 1])
        cap_lo = len(verts)
        verts.append((cx, cy, z0))
        cap_hi = len(verts)
        verts.append((cx, cy, z1))
        for i in range(_COLUMN_SEGMENTS):
            a0 = start + 2 * i
            a1 = start + 2 * ((i + 1) % _COLUMN_SEGMENTS)
            faces.append([cap_lo, a1, a0])
            faces.append([cap_hi, a0 + 1, a1 + 1])

    drum(r * _BASE_FLARE, 0.0, base_h)
    drum(r, base_h, base_h + shaft_h)
    drum(r * _CAPITAL_FLARE, base_h + shaft_h, STOREY_CM)

    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    bpy_util.smooth_shade_curved_faces(obj)
    return obj


def _spiral_newel_mesh(name: str):
    """Greybox cylinder on local origin (piece uses ``origin=center``)."""
    from pae.primitives import bpy_util

    d = MODULE_CM * _NEWEL_D_FRAC
    r = d * 0.5
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    start = 0
    for i in range(_COLUMN_SEGMENTS):
        a = 2.0 * math.pi * i / _COLUMN_SEGMENTS
        x, y = r * math.cos(a), r * math.sin(a)
        verts.append((x, y, 0.0))
        verts.append((x, y, STOREY_CM))
    for i in range(_COLUMN_SEGMENTS):
        a0 = start + 2 * i
        a1 = start + 2 * ((i + 1) % _COLUMN_SEGMENTS)
        faces.append([a0, a1, a1 + 1, a0 + 1])
    cap_lo = len(verts)
    verts.append((0.0, 0.0, 0.0))
    cap_hi = len(verts)
    verts.append((0.0, 0.0, STOREY_CM))
    for i in range(_COLUMN_SEGMENTS):
        a0 = start + 2 * i
        a1 = start + 2 * ((i + 1) % _COLUMN_SEGMENTS)
        faces.append([cap_lo, a1, a0])
        faces.append([cap_hi, a0 + 1, a1 + 1])
    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    bpy_util.smooth_shade_curved_faces(obj)
    return obj


def _arch_rib_mesh(name: str):
    """Extrude one smooth YZ arch-band polygon through the rib thickness."""
    from pae.primitives import bpy_util

    segments = 48
    band = MODULE_CM * 0.075
    outer_r = MODULE_CM * 0.5
    inner_r = outer_r - band
    centre_y = MODULE_CM * 0.5
    spring_z = STOREY_CM - outer_r

    outline: List[Tuple[float, float]] = []
    # Outer curve: right spring → apex → left spring.
    for i in range(segments + 1):
        theta = math.pi * i / segments
        outline.append(
            (
                centre_y + outer_r * math.cos(theta),
                spring_z + outer_r * math.sin(theta),
            )
        )
    # Left pier down and back to the inner spring.
    outline.extend(((0.0, 0.0), (band, 0.0), (band, spring_z)))
    # Inner curve: left spring → apex → right spring.
    for i in range(segments, -1, -1):
        theta = math.pi * i / segments
        outline.append(
            (
                centre_y + inner_r * math.cos(theta),
                spring_z + inner_r * math.sin(theta),
            )
        )
    # Right pier back to the outer spring.
    outline.extend(
        (
            (MODULE_CM - band, 0.0),
            (MODULE_CM, 0.0),
        )
    )

    verts: List[Tuple[float, float, float]] = []
    for x in (0.0, WALL_T_CM):
        verts.extend((x, y, z) for y, z in outline)
    count = len(outline)
    faces: List[Tuple[int, ...]] = [
        tuple(range(count)),
        tuple(range(count, count * 2))[::-1],
    ]
    for i in range(count):
        nxt = (i + 1) % count
        faces.append((i, nxt, count + nxt, count + i))
    obj = bpy_util.mesh_from_verts_faces(name, verts, faces)
    bpy_util.smooth_shade_curved_faces(obj, angle_deg=12.0)
    return obj


def build_column_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id

    if desc.id == "column_round":
        return _round_column_mesh(obj_name)
    if desc.id == "spiral_newel":
        return _spiral_newel_mesh(obj_name)
    if desc.id == "arch_rib_freestanding":
        return _arch_rib_mesh(obj_name)
    if desc.id == "buttress":
        parts = _buttress_parts()
    elif desc.id == "arch_freestanding":
        parts = _freestanding_arch_parts()
    elif desc.id == "pier_square":
        parts = _centred_square_parts(
            MODULE_CM * _PIER_W_FRAC,
            STOREY_CM,
            base_h=STOREY_CM * _BASE_H_FRAC,
            base_flare=_BASE_FLARE,
            cap_h=STOREY_CM * _CAPITAL_H_FRAC,
            cap_flare=_CAPITAL_FLARE,
        )
    else:  # pilaster — a plain slab against the wall
        parts = [((0.0, 0.0, 0.0), desc.size_cm)]

    return bpy_util.build_mesh_from_box_parts(
        obj_name, parts, origin_at_min_corner=True
    )

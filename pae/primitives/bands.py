"""Banding and coping — façade articulation, placeable anywhere.

Reference: the Wealden hall house. Its elevations are divided by a plinth course at the
base, a jettied bressummer with exposed joist ends at first floor, a wall plate under the
eaves, and vertical studs with diagonal braces between them. The frame IS the articulation.

Coping in PAE is therefore not "the cap on a parapet". It is edging, horizontal or vertical,
placed at any height or bay position on any wall face, dividing an elevation into panels.

Geometry convention: a band is thin on local X (its projection past the wall face), runs a
module on local Y, and is short on Z (a course) or a full storey (a vertical member). Its
BACK face sits at local x = 0 so it can be placed flush to a wall face and project outward
by exactly ``size_cm[0]`` — see ``pae/banding.py`` for the attachment contract.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

# Projections and sizes as fractions of the contract — never raw dimensions.
BAND_PROJ_FRAC = 0.25       # of WALL_T — how far a band stands proud of the face
COURSE_H_FRAC = 0.07        # of STOREY — height of a horizontal course
PILASTER_W_FRAC = 0.10      # of MODULE — width of a vertical member
BRACE_W_FRAC = 0.075        # of MODULE — width of a diagonal brace
COPING_OVERHANG_FRAC = 0.15  # of WALL_T, each side — coping is wider than the wall
COPING_H_FRAC = 0.045       # of STOREY
_BRACE_STEPS = 14           # stepped boxes approximating the diagonal
_JOIST_COUNT = 6            # exposed joist ends under a jettied course
_JOIST_W_FRAC = 0.05        # of MODULE


def _band_sockets(size_cm: Tuple[float, float, float], piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "band"})
    sx, sy, sz = size_cm
    return (
        SocketDesc(
            name="back",
            pos_cm=(0.0, sy * 0.5, sz * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_face",
            tags=tag,
        ),
        SocketDesc(
            name="end_a",
            pos_cm=(sx * 0.5, 0.0, sz * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="band_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(sx * 0.5, sy, sz * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="band_end",
            tags=tag,
        ),
    )


def _band(
    piece_id: str,
    size_cm: Tuple[float, float, float],
    tags: frozenset,
    notes: str,
) -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id=piece_id,
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=size_cm[2] / STOREY_CM,
        size_cm=size_cm,
        sockets=_band_sockets(size_cm, piece_id),
        tags=frozenset({"band", "trim", "decorative", module_tag()}) | tags,
        origin="min_corner",
        notes=notes,
    )


def band_course() -> PrimitiveDescriptor:
    """Horizontal course: plinth, stringcourse, sill band, bressummer, wall plate."""
    return _band(
        "band_course",
        (WALL_T_CM * BAND_PROJ_FRAC, MODULE_CM, STOREY_CM * COURSE_H_FRAC),
        frozenset({"course", "horizontal"}),
        "Horizontal band across one bay; placeable at any height.",
    )


def band_course_jettied() -> PrimitiveDescriptor:
    """Bressummer with exposed joist ends — the jetty of a Wealden front."""
    return _band(
        "band_course_jettied",
        (WALL_T_CM * BAND_PROJ_FRAC * 2.0, MODULE_CM, STOREY_CM * COURSE_H_FRAC * 1.6),
        frozenset({"course", "horizontal", "jetty", "timber"}),
        "Deep course with exposed joist ends beneath it.",
    )


def band_pilaster() -> PrimitiveDescriptor:
    """Vertical member: stud, corner post, pilaster strip, quoin run."""
    return _band(
        "band_pilaster",
        (WALL_T_CM * BAND_PROJ_FRAC, MODULE_CM * PILASTER_W_FRAC, STOREY_CM),
        frozenset({"vertical", "stud", "post"}),
        "Full-storey vertical member; placeable at any bay position.",
    )


def band_brace() -> PrimitiveDescriptor:
    """Diagonal brace across a panel — the timber-frame X/V members."""
    return _band(
        "band_brace",
        (WALL_T_CM * BAND_PROJ_FRAC, MODULE_CM, STOREY_CM),
        frozenset({"vertical", "brace", "diagonal", "timber"}),
        "Diagonal brace spanning one panel corner to corner.",
    )


def coping_cap() -> PrimitiveDescriptor:
    """Capping course sitting ON a wall or parapet top, oversailing both faces."""
    return _band(
        "coping_cap",
        (
            WALL_T_CM * (1.0 + 2.0 * COPING_OVERHANG_FRAC),
            MODULE_CM,
            STOREY_CM * COPING_H_FRAC,
        ),
        frozenset({"coping", "cap", "horizontal"}),
        "Weathering cap over a wall head; wider than the wall it caps.",
    )


def all_bands() -> tuple:
    return (
        band_course(),
        band_course_jettied(),
        band_pilaster(),
        band_brace(),
        coping_cap(),
    )


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------


def _chamfered_course(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    """A course reads better with a weathered top: two stacked boxes, upper set back."""
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.65)),
        ((0.0, 0.0, sz * 0.65), (sx * 0.6, sy, sz * 0.35)),
    ]


def _jettied_course(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    parts: List[BoxPart] = [((0.0, 0.0, sz * 0.45), (sx, sy, sz * 0.55))]
    jw = MODULE_CM * _JOIST_W_FRAC
    for i in range(_JOIST_COUNT):
        c = sy * (i + 0.5) / _JOIST_COUNT
        parts.append(((0.0, c - jw * 0.5, 0.0), (sx * 0.8, jw, sz * 0.45)))
    return parts


def _brace_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    """Stepped boxes along the diagonal of the panel."""
    sx, sy, sz = size_cm
    w = MODULE_CM * BRACE_W_FRAC
    parts: List[BoxPart] = []
    for i in range(_BRACE_STEPS):
        t0 = i / _BRACE_STEPS
        t1 = (i + 1) / _BRACE_STEPS
        y = sy * t0
        z = sz * t0
        parts.append(((0.0, y, z), (sx, max(w, sy * (t1 - t0) + w * 0.5), sz * (t1 - t0))))
    return parts


def _coping_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.55)),
        ((sx * 0.08, 0.0, sz * 0.55), (sx * 0.84, sy, sz * 0.45)),
    ]


def build_band_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id

    if desc.id == "band_course":
        parts = _chamfered_course(desc.size_cm)
    elif desc.id == "band_course_jettied":
        parts = _jettied_course(desc.size_cm)
    elif desc.id == "band_brace":
        parts = _brace_parts(desc.size_cm)
    elif desc.id == "coping_cap":
        parts = _coping_parts(desc.size_cm)
    else:  # band_pilaster — a plain strip
        parts = [((0.0, 0.0, 0.0), desc.size_cm)]

    return bpy_util.build_mesh_from_box_parts(obj_name, parts, origin_at_min_corner=True)

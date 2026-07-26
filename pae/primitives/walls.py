"""Wall kit pieces — plain / window / arrowslit / door / arcade.

Wall occupies the low-X strip of its cell: size ``(WALL_T, MODULE, STOREY)``.
Arcade arch is cut **into** the module so the outer footprint still fills one bay.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.primitives.apertures import ApertureProfile, PROFILES, get_profile
from pae.primitives.types import (
    ApertureDesc,
    PrimitiveDescriptor,
    SocketDesc,
    module_tag,
)

# Relative aperture layout (fractions of MODULE / STOREY — no raw contract literals).
_WINDOW_W = 0.35
_WINDOW_H = 0.40
_WINDOW_SILL = 0.28
_DOOR_W = 0.40
_DOOR_H = 0.72
_SLIT_W = 0.05
_SLIT_H = 0.45
_SLIT_SILL = 0.30
_ARCH_JAMB = 0.15  # fraction of MODULE each side
_ARCH_SPRING = 0.18  # fraction of STOREY — arch starts above plinth band

# Boolean cutter overrun (mesh build prefers bmesh frame; these pad descriptor X/Y/Z).
_CUTTER_PAD_X_FRAC = 0.25  # each face — pierces both wall skins
_CUTTER_PAD_YZ_CM = 0.5  # coplanar guard for boolean fallback

# Wall kit: thin in local X (``WALL_T``), run along Y (``MODULE``), vertical Z.
WALL_THIN_AXIS_INDEX = 0
WALL_RUN_AXIS_INDEX = 1
WALL_VERTICAL_AXIS_INDEX = 2


def aperture_opening_run_vertical(
    ap: ApertureDesc,
    wall_size_cm: Tuple[float, float, float],
) -> Tuple[float, float, float, float]:
    """Opening span on run (Y) and vertical (Z); thin axis (X) is always through-punched.

    Descriptor layout: ``min_cm = (-pad_x, run0, z0)``, ``max_cm = (WALL_T+pad_x, run1, z1)``.
    Run width must live on axis 1 — if it were stored on axis 0 the mesh would cut a
    side notch along the module run instead of punching the exterior thin face.
    """
    wx, wy, _wz = wall_size_cm
    run0, run1 = ap.min_cm[WALL_RUN_AXIS_INDEX], ap.max_cm[WALL_RUN_AXIS_INDEX]
    z0, z1 = ap.min_cm[WALL_VERTICAL_AXIS_INDEX], ap.max_cm[WALL_VERTICAL_AXIS_INDEX]
    run_w = run1 - run0
    thick_w = ap.max_cm[WALL_THIN_AXIS_INDEX] - ap.min_cm[WALL_THIN_AXIS_INDEX]
    if run_w < wy * 0.05 and thick_w > wx + TOL_CM:
        raise ValueError(
            "wall aperture run/thickness axes appear swapped on descriptor "
            f"(run_w={run_w:.1f} cm on Y, thick_w={thick_w:.1f} cm on X)"
        )
    return (run0, run1, z0, z1)


def aperture_opening_yz(ap: ApertureDesc) -> Tuple[float, float, float, float]:
    """Logical Y/Z opening inside the bay (ignores X cutter pad on the descriptor)."""
    return aperture_opening_run_vertical(ap, (WALL_T_CM, MODULE_CM, STOREY_CM))


def aperture_cutter_bounds(
    ap: ApertureDesc,
    wall_size_cm: Tuple[float, float, float],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Axis-aligned boolean cutter — oversized through wall thickness on X."""
    wx, _wy, wz = wall_size_cm
    pad_x = WALL_T_CM * _CUTTER_PAD_X_FRAC
    pad_yz = _CUTTER_PAD_YZ_CM
    run0, run1, z0, z1 = aperture_opening_run_vertical(ap, wall_size_cm)
    return (
        (-pad_x, run0 - pad_yz, z0 - pad_yz),
        (wx + pad_x, run1 + pad_yz, min(wz, z1 + pad_yz)),
    )


def _wall_aperture_desc(
    kind: str,
    run0: float,
    run1: float,
    z0: float,
    z1: float,
) -> ApertureDesc:
    """Aperture in wall-local cm: through thin X, opening rectangle in YZ."""
    pad_x = WALL_T_CM * _CUTTER_PAD_X_FRAC
    return ApertureDesc(
        kind=kind,
        min_cm=(-pad_x, run0, z0),
        max_cm=(WALL_T_CM + pad_x, run1, z1),
    )


def wall_aperture_frame_parts_cm(
    size_cm: Tuple[float, float, float],
    run0: float,
    run1: float,
    z0: float,
    z1: float,
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Frame boxes leaving a through-opening along thin X (exterior/interior faces).

    Each part spans the full wall thickness ``[0, wx]`` on X.  The void is
    ``run ∈ [run0, run1]``, ``z ∈ [z0, z1]`` — never a partial-X side notch.
    """
    wx, wy, wz = size_cm
    run0 = max(0.0, min(wy, run0))
    run1 = max(run0, min(wy, run1))
    z0 = max(0.0, min(wz, z0))
    z1 = max(z0, min(wz, z1))

    eps = 1e-5
    parts: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    run_span = run1 - run0

    # Full-height side pillars (thin axis X always spans [0, wx]).
    if run0 > eps:
        parts.append(((0.0, 0.0, 0.0), (wx, run0, wz)))
    if run1 < wy - eps:
        parts.append(((0.0, run1, 0.0), (wx, wy - run1, wz)))

    # Sill / lintel only between jambs (avoids boolean-style corner ears at floor).
    if z0 > eps and run_span > eps:
        parts.append(((0.0, run0, 0.0), (wx, run_span, z0)))
    if z1 < wz - eps and run_span > eps:
        parts.append(((0.0, run0, z1), (wx, run_span, wz - z1)))

    return parts


def wall_aperture_is_solid_at(
    parts: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]],
    lx: float,
    ly: float,
    lz: float,
) -> bool:
    """True when ``(lx, ly, lz)`` lies inside any frame part (import-safe probe)."""
    for origin, size in parts:
        ox, oy, oz = origin
        sx, sy, sz = size
        if (
            ox - 1e-9 <= lx <= ox + sx + 1e-9
            and oy - 1e-9 <= ly <= oy + sy + 1e-9
            and oz - 1e-9 <= lz <= oz + sz + 1e-9
        ):
            return True
    return False


def _wall_sockets() -> tuple:
    tag = frozenset({module_tag(), "wall"})
    # Long axis = Y. Ends face −Y / +Y.
    return (
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
        SocketDesc(
            name="face_out",
            pos_cm=(0.0, MODULE_CM * 0.5, STOREY_CM * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_face",
            tags=tag,
        ),
    )


def _base_wall(
    piece_id: str,
    *,
    tags: frozenset,
    aperture: Optional[ApertureDesc] = None,
    profile: Optional[str] = None,
    notes: str = "",
) -> PrimitiveDescriptor:
    return PrimitiveDescriptor(
        id=piece_id,
        kind="wall",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        sockets=_wall_sockets(),
        tags=tags,
        origin="min_corner",
        rotates_about_center=False,
        aabb_min_cm=(0.0, 0.0, 0.0),
        aperture=aperture,
        profile=profile,
        notes=notes,
    )


def wall_from_profile(
    profile: ApertureProfile,
    *,
    piece_id: Optional[str] = None,
    extra_tags: frozenset = frozenset(),
) -> PrimitiveDescriptor:
    """Build a wall bay whose opening is described by an aperture profile.

    The descriptor's ``aperture`` is the opening's bounding box (what the validator and
    the fitter reason about); ``profile`` carries the actual shape so the mesh builder can
    cut a pointed head or a three-light mullioned window rather than a rectangle.
    """
    run0, run1 = profile.opening_run_cm(MODULE_CM)
    z0, z1 = profile.opening_z_cm(STOREY_CM)
    return _base_wall(
        piece_id or f"wall_{profile.name}",
        tags=frozenset({"wall", "exterior", module_tag()}) | profile.tags | extra_tags,
        aperture=_wall_aperture_desc(profile.kind, run0, run1, z0, z1),
        profile=profile.name,
        notes=profile.notes,
    )


def wall_plain() -> PrimitiveDescriptor:
    return _base_wall(
        "wall_plain",
        tags=frozenset({"wall", "plain", "exterior", module_tag()}),
        notes="Solid bay wall, low-X strip.",
    )


# Legacy piece ids kept stable — they are referenced by assemble, golden hashes and the
# UE manifest. Each now delegates to a named profile instead of private constants.
LEGACY_PROFILE_IDS = {
    "wall_window": "window_plain",
    "wall_arrowslit": "arrowslit",
    "wall_door": "door_plain",
    "wall_arcade": "arcade_round",
    "wall_gate_arch": "gate_arch",
}


def wall_window() -> PrimitiveDescriptor:
    return wall_from_profile(get_profile("window_plain"), piece_id="wall_window")


def wall_arrowslit() -> PrimitiveDescriptor:
    return wall_from_profile(get_profile("arrowslit"), piece_id="wall_arrowslit")


def wall_door() -> PrimitiveDescriptor:
    return wall_from_profile(get_profile("door_plain"), piece_id="wall_door")


def wall_arcade() -> PrimitiveDescriptor:
    """Arcade bay: arch cut **into** the module — outer size still one bay."""
    return wall_from_profile(get_profile("arcade_round"), piece_id="wall_arcade")


def wall_gate_arch() -> PrimitiveDescriptor:
    """Monumental gate leaf — round-headed near full-bay opening."""
    return wall_from_profile(get_profile("gate_arch"), piece_id="wall_gate_arch")


def wall_gate_arch_grand() -> PrimitiveDescriptor:
    """Fortress gatehouse leaf — maximum clear carriage opening in one bay."""
    return wall_from_profile(
        get_profile("gate_arch_grand"), piece_id="wall_gate_arch_grand"
    )


def wall_arch_rib_interior() -> PrimitiveDescriptor:
    """Transverse great-hall arch rib; assemble scales its run to hall width."""
    return wall_from_profile(
        get_profile("arcade_monumental"),
        piece_id="wall_arch_rib_interior",
        extra_tags=frozenset(
            {"interior", "arch_rib", "structural", "great_hall"}
        ),
    )


def wall_arcade_monumental() -> PrimitiveDescriptor:
    """Tall cloister arcade — low spring, wide round head under a gallery roof."""
    return wall_from_profile(
        get_profile("arcade_monumental"), piece_id="wall_arcade_monumental"
    )


def all_walls() -> tuple:
    """Solid wall, the four legacy ids, and one bay per registered aperture profile."""
    pieces = [
        wall_plain(),
        wall_window(),
        wall_arrowslit(),
        wall_door(),
        wall_arcade(),
        wall_gate_arch(),
        wall_gate_arch_grand(),
        wall_arch_rib_interior(),
        wall_arcade_monumental(),
    ]
    taken = {p.id for p in pieces}
    for name in sorted(PROFILES):
        desc = wall_from_profile(PROFILES[name])
        if desc.id not in taken:
            pieces.append(desc)
            taken.add(desc.id)
    return tuple(pieces)


def build_wall_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    """Optional bpy builder: frame mesh around aperture (no boolean corner voids)."""
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    if desc.aperture is None:
        return bpy_util.box_mesh(obj_name, desc.size_cm, origin_at_min_corner=True)

    if desc.profile is not None:
        # Profile-driven: real head curvature, mullions and transoms.
        from pae.primitives import apertures

        parts = apertures.frame_parts(get_profile(desc.profile), desc.size_cm)
    else:
        ap = desc.aperture
        run0, run1, z0, z1 = aperture_opening_run_vertical(ap, desc.size_cm)
        parts = wall_aperture_frame_parts_cm(desc.size_cm, run0, run1, z0, z1)
    return bpy_util.build_mesh_from_box_parts(
        obj_name,
        parts,
        origin_at_min_corner=True,
    )

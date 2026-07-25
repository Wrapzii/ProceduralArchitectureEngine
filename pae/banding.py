"""Banding stage — places coping and façade articulation anywhere you ask for it.

Reference: the Wealden hall house. Plinth course at the base, jettied bressummer at first
floor, wall plate under the eaves, vertical studs and diagonal braces dividing each
elevation into panels.

THE ATTACHMENT CONTRACT — "attached" is not "not freestanding"
--------------------------------------------------------------
A band that merely *intersects something somewhere* is not attached. Four conditions, each
checked separately in ``validate.py`` so a failure says which one broke:

  1. HOST      it must contact a WALL, not a floor, roof, railing or another band.
  2. COVERAGE  contact must run along at least ``MIN_CONTACT_FRAC`` of the band's own
               length. A course clipping a wall at one corner is not a course.
  3. FLUSH     its back face must be coplanar with the host wall's outer face, within TOL.
               A band hovering 5 cm off the wall is a defect you would never see in an
               overhead render and always see at eye level.
  4. PROUD     it must project OUTWARD from that face by its full declared projection.
               A band sunk into the wall is invisible and pointless.

Bands are deliberately EXEMPT from ``vertical_support``: a stringcourse at mid-storey has
nothing beneath it and never will. Condition 1–4 replace that check for this kind. This
exemption is written in code, with this reason, per Handbook §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    WALL_T_CM,
    placement_world_aabb,
)
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report

Cell = Tuple[int, int]
Face = str

# A band must be in contact along at least this fraction of its own run.
MIN_CONTACT_FRAC = 0.80

_FACE_NORMAL = {"south": (0, -1), "north": (0, 1), "west": (-1, 0), "east": (1, 0)}
_OPPOSITE_FACE = {"south": "north", "north": "south", "west": "east", "east": "west"}


@dataclass(frozen=True)
class CourseSpec:
    """One horizontal band at a height, given as a fraction of the storey."""

    name: str
    height_frac: float
    piece: str = "band_course"

    def __post_init__(self) -> None:
        if not 0.0 <= self.height_frac <= 1.0:
            raise ValueError(
                f"course {self.name!r}: height_frac must be 0..1 of a storey, "
                f"got {self.height_frac}"
            )


# The Wealden default: plinth, jettied bressummer, wall plate.
DEFAULT_COURSES: Tuple[CourseSpec, ...] = (
    CourseSpec("plinth", 0.02),
    CourseSpec("bressummer", 0.62, piece="band_course_jettied"),
    CourseSpec("plate", 0.93),
)


@dataclass(frozen=True)
class BandingSpec:
    """Where banding goes. Everything is in fractions or bays — never centimetres."""

    courses: Tuple[CourseSpec, ...] = DEFAULT_COURSES
    verticals_every_bays: int = 1
    vertical_piece: str = "band_pilaster"
    braces: bool = True
    brace_piece: str = "band_brace"
    coping: bool = False
    coping_piece: str = "coping_cap"
    faces: Tuple[Face, ...] = ()      # empty = every outward face
    levels: Tuple[int, ...] = ()      # empty = every storey
    corners_only: bool = False        # verticals at bay ends only

    def wants_face(self, face: Face) -> bool:
        return not self.faces or face in self.faces


def _crosses_opening(opening, z0: float, z1: float) -> bool:
    """True when a band at z0..z1 would run across a wall's door or window."""
    if opening is None:
        return False
    a0, a1 = opening.min_cm[2], opening.max_cm[2]
    return z1 > a0 + TOL_CM and z0 < a1 - TOL_CM


def _aabb(p: SolidPlacement):
    return placement_world_aabb(
        p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def band_faces_of(assembly: Assembly) -> Dict[str, Face]:
    """Which way each exterior wall faces, derived from its OWN position in its cell.

    Not from cell neighbours — that says nothing about where the wall actually sits, and is
    the mistake that braced buttresses against thin air (Ledger A-7).
    """
    # Interior cells must come from covered_cells, not from rounding an AABB: a spanning
    # floor slab rounded outward claimed a ring of cells it does not occupy, so half the
    # perimeter walls were classified as inward-facing and got no banding and no windows.
    from pae.trim import covered_cells

    interior: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind == "floor" and "hole" not in p.asset_id:
            interior |= covered_cells(p)

    faces: Dict[str, Face] = {}
    for p in assembly.placements:
        if p.kind != "wall":
            continue
        # Drum window overlays are aperture shells on the tower annulus — not
        # façade runs to dress with plinth/jetty courses.
        if "drum_window" in p.tags or p.piece_id.startswith("tower_win_"):
            continue
        mn, mx = _aabb(p)
        cx0, cy0 = p.cell[0] * MODULE_CM, p.cell[1] * MODULE_CM
        near = MODULE_CM * 0.5
        if (mx[0] - mn[0]) < (mx[1] - mn[1]):
            face = "west" if (mn[0] - cx0) < near else "east"
        else:
            face = "south" if (mn[1] - cy0) < near else "north"
        # A north wall is stored on the boundary cell BEYOND the last interior cell, so it
        # sits at the LOW edge of its own cell and classifies as "south". Its outward
        # direction is still north. So when the neighbour in the face direction is
        # interior, flip the face rather than discarding the wall — discarding it left
        # half of every perimeter with no banding and no windows.
        dx, dy = _FACE_NORMAL[face]
        if (p.cell[0] + dx, p.cell[1] + dy) in interior:
            face = _OPPOSITE_FACE[face]
            dx, dy = _FACE_NORMAL[face]
            if (p.cell[0] + dx, p.cell[1] + dy) in interior:
                continue  # interior on both sides — a genuine partition
        faces[p.piece_id] = face
    return faces


def _place_on_face(
    piece_id: str,
    host: SolidPlacement,
    face: Face,
    *,
    z_cm: float,
    run0_frac: float = 0.0,
    run_len_frac: float = 1.0,
    suffix: str,
    extra_tags: frozenset = frozenset(),
) -> SolidPlacement:
    """Place a band flush against ``face`` of ``host``, projecting outward.

    Yaw and offset are derived from the host wall's measured AABB, so the band cannot drift
    from the wall it decorates even if the wall moves.
    """
    desc = catalog_by_id()[piece_id]
    hmn, hmx = _aabb(host)
    proj = desc.size_cm[0]

    if face in ("south", "north"):
        yaw = 90
        run_start = hmn[0] + (hmx[0] - hmn[0]) * run0_frac
        # yaw 90: local (x,y) -> world (-y, x); origin offset by +size_y puts it back.
        ox = run_start + desc.size_cm[1]
        oy = (hmn[1] - proj) if face == "south" else hmx[1]
    else:
        yaw = 0
        run_start = hmn[1] + (hmx[1] - hmn[1]) * run0_frac
        ox = (hmn[0] - proj) if face == "west" else hmx[0]
        oy = run_start

    cx0, cy0 = host.cell[0] * MODULE_CM, host.cell[1] * MODULE_CM
    return SolidPlacement(
        piece_id=f"band_{piece_id}_{host.piece_id}_{suffix}",
        asset_id=piece_id,
        kind=desc.kind,
        cell=host.cell,
        level=host.level,
        yaw=yaw,
        offset_cm=(ox - cx0, oy - cy0, z_cm),
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"band", f"face:{face}"}) | extra_tags,
    )


def band(
    assembly: Assembly,
    spec: Optional[BandingSpec] = None,
) -> Tuple[Assembly, Report]:
    """Additive banding pass. Returns a new assembly; the input is not mutated."""
    opts = spec or BandingSpec()
    catalog = catalog_by_id()

    wanted = {c.piece for c in opts.courses}
    if opts.verticals_every_bays > 0:
        wanted.add(opts.vertical_piece)
    if opts.braces:
        wanted.add(opts.brace_piece)
    if opts.coping:
        wanted.add(opts.coping_piece)
    missing = sorted(w for w in wanted if w not in catalog)
    if missing:
        return assembly, Report.from_failures([
            Failure(
                check="band_piece_missing",
                message=f"banding wants unknown pieces {missing}",
                world_xyz=None,
            )
        ])

    faces = band_faces_of(assembly)
    if not faces:
        return assembly, Report.from_failures([])

    hosts = {p.piece_id: p for p in assembly.placements if p.piece_id in faces}
    extra: List[SolidPlacement] = []

    # ------------------------------------------------------------------
    # Group walls into ELEVATIONS, not bays.
    #
    # Courses land at the requested storey fraction on every bay that can take them.
    # Bays with door/window openings are skipped until we can split a run into segments
    # (roadmap). Verticals and coping still group by elevation so corners line up.
    # ------------------------------------------------------------------
    elevations: Dict[Tuple[int, int, int, Face], List[SolidPlacement]] = {}
    for pid, face in faces.items():
        host = hosts[pid]
        if not opts.wants_face(face):
            continue
        if opts.levels and host.level not in opts.levels:
            continue
        axis = 1 if host.yaw in (0, 180) else 0
        plane = host.cell[1 - axis]
        elevations.setdefault((host.level, axis, plane, face), []).append(host)

    for key, members in sorted(elevations.items(), key=lambda kv: str(kv[0])):
        level, axis, _plane, face = key
        members.sort(key=lambda m: m.cell[axis])

        for course in opts.courses:
            z = STOREY_CM * course.height_frac
            band_h = catalog[course.piece].size_cm[2]
            for m in members:
                opening = getattr(catalog.get(m.asset_id), "aperture", None)
                if _crosses_opening(opening, z, z + band_h):
                    continue
                extra.append(
                    _place_on_face(
                        course.piece, m, face,
                        z_cm=z,
                        suffix="course_" + course.name,
                        extra_tags=frozenset(
                            {"course:" + course.name, "horizontal", "run"}
                        ),
                    )
                )

        # Vertical members belong at CORNERS and junctions - the ends of the run - not on
        # an arbitrary every-N-bays rhythm that lands mid-wall next to nothing.
        if opts.verticals_every_bays > 0 and members:
            picked = [members[0], members[-1]]
            if not opts.corners_only:
                for idx in range(
                    opts.verticals_every_bays,
                    max(1, len(members) - 1),
                    opts.verticals_every_bays,
                ):
                    m = members[idx]
                    if getattr(catalog.get(m.asset_id), "aperture", None) is None:
                        picked.append(m)
            seen_ids: Set[str] = set()
            for m in picked:
                if m.piece_id in seen_ids:
                    continue
                seen_ids.add(m.piece_id)
                extra.append(
                    _place_on_face(
                        opts.vertical_piece, m, face,
                        z_cm=0.0,
                        suffix="stud",
                        extra_tags=frozenset({"vertical", "corner"}),
                    )
                )

        if opts.braces:
            # A brace lives INSIDE a panel — between two courses — not across the whole
            # storey. Emitted at z=0 with the piece's full storey height it ran straight
            # through every horizontal course, which is the "sideways banding with the
            # flat banding" the render kept showing: bars crossing the bands at right
            # angles instead of bracing the panel between them.
            edges = sorted(
                {0.0, STOREY_CM}
                | {
                    STOREY_CM * c.height_frac + catalog[c.piece].size_cm[2]
                    for c in opts.courses
                }
                | {STOREY_CM * c.height_frac for c in opts.courses}
            )
            panels = [
                (lo, hi)
                for lo, hi in zip(edges, edges[1:])
                if hi - lo > STOREY_CM * 0.25
            ]
            if panels:
                # The tallest clear panel is the one a brace belongs in.
                lo, hi = max(panels, key=lambda ab: ab[1] - ab[0])
                brace_size = catalog[opts.brace_piece].size_cm
                for m in members:
                    if getattr(catalog.get(m.asset_id), "aperture", None) is not None:
                        continue  # a brace crosses the panel; it cannot share a bay
                    b = _place_on_face(
                        opts.brace_piece, m, face,
                        z_cm=lo,
                        suffix="brace",
                        extra_tags=frozenset({"diagonal"}),
                    )
                    extra.append(
                        SolidPlacement(
                            piece_id=b.piece_id, asset_id=b.asset_id, kind=b.kind,
                            cell=b.cell, level=b.level, yaw=b.yaw,
                            offset_cm=b.offset_cm,
                            size_cm=(brace_size[0], brace_size[1], hi - lo),
                            rotates_about_center=b.rotates_about_center,
                            tags=b.tags,
                        )
                    )

        if opts.coping:
            over = WALL_T_CM * 0.15
            for m in members:
                cap = _place_on_face(
                    opts.coping_piece, m, face,
                    z_cm=_aabb(m)[1][2] - _aabb(m)[0][2],
                    suffix="coping",
                    extra_tags=frozenset({"coping"}),
                )
                ox, oy, oz = cap.offset_cm
                if face in ("south", "north"):
                    oy = oy + (over if face == "south" else -over)
                else:
                    ox = ox + (over if face == "west" else -over)
                extra.append(
                    SolidPlacement(
                        piece_id=cap.piece_id, asset_id=cap.asset_id, kind=cap.kind,
                        cell=cap.cell, level=cap.level, yaw=cap.yaw,
                        offset_cm=(ox, oy, oz), size_cm=cap.size_cm,
                        rotates_about_center=cap.rotates_about_center, tags=cap.tags,
                    )
                )

    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    out = Assembly(
        placements=list(assembly.placements) + extra,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    return out, Report.from_failures([])

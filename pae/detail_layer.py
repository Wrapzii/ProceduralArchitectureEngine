"""Stage K detail layer — seeded façade / opening / roofline articulation.

High visual return, low geometry: reuses kit ``band_*`` / ``coping_cap`` pieces via
the existing banding attachment contract, plus deterministic metadata tags for
opening accents and weathering that the material pipeline does not yet consume.

Determinism: every choice derives from ``(style_id, seed)`` via keyed RNGs.
Same seed → identical detail signature; different seed → bounded legal variation.

Generic structures only — not school / fortress / citadel polish.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.banding import BandingSpec, CourseSpec, band, band_faces_of
from pae.contract import STOREY_CM
from pae.report import Failure, Report

# ---------------------------------------------------------------------------
# Budget — piece count must stay bounded on small/medium buildings
# ---------------------------------------------------------------------------

MAX_DETAIL_ABS = 40  # optional verticals / coping only (not continuous courses)
MAX_DETAIL_RATIO = 0.55  # vs exterior wall host count (optional pieces)
# Continuous plinth/string/cornice runs are kept in full — they may exceed the
# optional budget. Hard ceiling prevents runaway on huge façades.
MAX_COURSE_ABS = 120
DETAIL_TAG = "detail_layer"
DETAIL_META_TAG = "detail_meta"

# Honest material gaps (Stage K does not invent mesh noise or texture maps).
MATERIAL_CONSUMPTION_GAPS: Tuple[str, ...] = (
    "materials.wall / roof / trim authored on StylePack — export maps kind/tags "
    "to material_slot (MI_*) via pae.export.materials (@MP-WS-UEMAT); UE assigns "
    "real MIs in-engine (no baked textures from PAE).",
    "weather:*/wear:*/dampness:* tags export as placement masks "
    "(vertex-color / PerInstanceCustomData contract) — still metadata floats, "
    "not baked texture maps.",
    "opening sill/lintel/hood accents are tags on host aperture walls, not "
    "separate carved mesh pieces (avoids blocking clear openings).",
    "roofline eave/ridge accents are tags on existing roof pieces — Stage C "
    "roof generation is not modified.",
)


@dataclass(frozen=True)
class DetailPolicy:
    """Per-structure coherent detail recipe (not per-piece chaos)."""

    style_family: str
    #: Horizontal courses (names map to height strategy).
    course_names: Tuple[str, ...] = ("plinth", "cornice")
    mid_string: bool = False
    jettied_mid: bool = False
    braces: bool = False
    corners_only: bool = True
    verticals_every_bays: int = 1
    coping: bool = False
    #: Opening accent family — one choice for the whole structure.
    opening_accent: str = "sill_lintel"  # sill_lintel | hood | frame | none
    roof_eave_trim: bool = True
    ridge_accent: bool = False
    weathering: bool = True
    #: 0..1 scales the piece budget and sparse seeding.
    density: float = 0.65

    def __post_init__(self) -> None:
        if not 0.0 <= self.density <= 1.0:
            raise ValueError("density must be in [0, 1]")


@dataclass(frozen=True)
class DetailBudget:
    """Report added detail count / ratio for acceptance gates."""

    wall_hosts: int
    added_pieces: int
    meta_tagged: int
    cap: int
    ratio: float
    style_family: str
    seed: int

    def as_message(self) -> str:
        return (
            f"detail_layer style={self.style_family} seed={self.seed} "
            f"added={self.added_pieces}/{self.cap} "
            f"ratio={self.ratio:.3f} meta={self.meta_tagged}"
        )


# Distinct policies for all eight acceptance styles (+ modest default).
_STYLE_POLICIES: Dict[str, DetailPolicy] = {
    "rustic": DetailPolicy(
        style_family="rustic",
        course_names=("plinth", "cornice"),
        mid_string=False,
        jettied_mid=True,
        braces=False,
        corners_only=True,
        verticals_every_bays=2,
        coping=False,
        opening_accent="sill_lintel",
        roof_eave_trim=True,
        ridge_accent=False,
        weathering=True,
        density=0.50,
    ),
    "medieval": DetailPolicy(
        style_family="medieval",
        course_names=("plinth", "cornice"),
        mid_string=True,
        jettied_mid=False,
        braces=False,
        corners_only=False,
        verticals_every_bays=2,
        coping=False,
        opening_accent="hood",
        roof_eave_trim=True,
        ridge_accent=True,
        weathering=True,
        density=0.78,
    ),
    "manor": DetailPolicy(
        style_family="manor",
        course_names=("plinth", "cornice"),
        mid_string=True,
        jettied_mid=False,
        braces=False,
        corners_only=False,
        verticals_every_bays=1,
        coping=False,
        opening_accent="frame",
        roof_eave_trim=True,
        ridge_accent=True,
        weathering=False,
        density=0.88,
    ),
    "civic": DetailPolicy(
        style_family="civic",
        course_names=("plinth", "cornice"),
        mid_string=False,
        jettied_mid=False,
        braces=False,
        corners_only=False,
        verticals_every_bays=1,
        coping=True,
        opening_accent="frame",
        roof_eave_trim=True,
        ridge_accent=False,
        weathering=False,
        density=0.92,
    ),
    "townhouse": DetailPolicy(
        style_family="townhouse",
        course_names=("plinth", "cornice"),
        mid_string=True,
        jettied_mid=False,
        braces=False,
        corners_only=True,
        verticals_every_bays=1,
        coping=True,
        opening_accent="sill_lintel",
        roof_eave_trim=False,
        ridge_accent=False,
        weathering=False,
        density=0.58,
    ),
    "keep": DetailPolicy(
        style_family="keep",
        course_names=("plinth", "cornice"),
        mid_string=False,
        jettied_mid=False,
        braces=False,
        corners_only=True,
        verticals_every_bays=3,
        coping=False,
        opening_accent="none",
        roof_eave_trim=False,
        ridge_accent=False,
        weathering=True,
        density=0.40,
    ),
    "gothic_academy": DetailPolicy(
        style_family="gothic_academy",
        course_names=("plinth", "cornice"),
        mid_string=True,
        jettied_mid=False,
        braces=False,
        corners_only=False,
        verticals_every_bays=1,
        coping=False,
        opening_accent="hood",
        roof_eave_trim=True,
        ridge_accent=True,
        weathering=True,
        density=0.80,
    ),
    "wizard_academy": DetailPolicy(
        style_family="wizard_academy",
        course_names=("plinth", "cornice"),
        mid_string=False,
        jettied_mid=False,
        braces=False,
        corners_only=True,
        verticals_every_bays=1,
        coping=False,
        opening_accent="hood",
        roof_eave_trim=True,
        ridge_accent=True,
        weathering=True,
        density=0.70,
    ),
}

_DEFAULT_POLICY = DetailPolicy(
    style_family="generic",
    course_names=("plinth", "cornice"),
    corners_only=True,
    verticals_every_bays=1,
    opening_accent="sill_lintel",
    density=0.50,
)


def _rng(seed: int, key: str) -> random.Random:
    return random.Random(f"detail:{seed}:{key}")


def detail_policy_for_style(style_id: Optional[str]) -> DetailPolicy:
    """Resolve a coherent detail policy for a style pack id.

    Pack ``detail`` / ``shell`` sections override the built-in family recipe when present.
    """
    if not style_id:
        return _DEFAULT_POLICY
    sid = str(style_id).strip().lower()
    base = _STYLE_POLICIES.get(sid)
    if base is None:
        base = replace(_DEFAULT_POLICY, style_family=sid)

    try:
        from pae.style_pack import load_style_pack

        pack, report = load_style_pack(sid)
    except Exception:
        pack, report = None, None
    if pack is None or report is None or not report.ok:
        return base

    d = pack.detail
    s = pack.shell
    changes: Dict[str, object] = {"style_family": sid}
    if d.opening_accent is not None:
        changes["opening_accent"] = d.opening_accent
    if d.density is not None:
        changes["density"] = float(d.density)
    if d.mid_string is not None:
        changes["mid_string"] = bool(d.mid_string)
    if d.jettied_mid is not None:
        changes["jettied_mid"] = bool(d.jettied_mid)
    elif s.jetty:
        changes["jettied_mid"] = True
    if d.verticals_every_bays is not None:
        changes["verticals_every_bays"] = int(d.verticals_every_bays)
    if d.corners_only is not None:
        changes["corners_only"] = bool(d.corners_only)
    if d.coping is not None:
        changes["coping"] = bool(d.coping)
    elif s.coping:
        changes["coping"] = True
    if d.ridge_accent is not None:
        changes["ridge_accent"] = bool(d.ridge_accent)
    if d.weathering is not None:
        changes["weathering"] = bool(d.weathering)
    if d.roof_eave_trim is not None:
        changes["roof_eave_trim"] = bool(d.roof_eave_trim)
    if d.braces is not None:
        changes["braces"] = bool(d.braces)
    if s.pilasters and d.verticals_every_bays is None:
        changes["verticals_every_bays"] = 1
        changes["corners_only"] = False
    return replace(base, **changes)  # type: ignore[arg-type]


def _wall_bands_cm(style_id: Optional[str]) -> Tuple[float, float, float]:
    """Return (plinth_cm, cornice_cm, storey_cm) from the style pack when available."""
    plinth_cm = 30.0
    cornice_cm = 20.0
    storey_cm = STOREY_CM
    if not style_id:
        return plinth_cm, cornice_cm, storey_cm
    try:
        from pae.style_pack import load_style_pack, resolve_storey_height_cm

        pack, report = load_style_pack(str(style_id))
        if pack is not None and report.ok:
            plinth_cm = float(pack.wall_bands.plinth_cm)
            cornice_cm = float(pack.wall_bands.cornice_cm)
            storey_cm = float(resolve_storey_height_cm(pack))
    except Exception:
        pass
    return plinth_cm, cornice_cm, storey_cm


def _course_specs(policy: DetailPolicy, style_id: Optional[str]) -> Tuple[CourseSpec, ...]:
    """Build BandingSpec courses from pack wall_bands + policy family.

    ``band()`` places at ``STOREY_CM * height_frac``. Pack storeys may be shorter
    (e.g. rustic 320), so fracs are chosen so absolute Z stays on the host wall.
    """
    plinth_cm, cornice_cm, storey_cm = _wall_bands_cm(style_id)
    # Approximate course height (bands.COURSE_H_FRAC * STOREY_CM).
    course_h = STOREY_CM * 0.07
    # band() Z = STOREY_CM * frac, so usable host height is min(pack, STOREY_CM).
    host_h = min(float(storey_cm), float(STOREY_CM))
    # Plinth near base; cornice under eaves of the usable host height.
    plinth_z = max(4.0, min(host_h * 0.06, max(8.0, plinth_cm * 0.4)))
    cornice_z = min(
        host_h - course_h - 4.0,
        max(host_h * 0.82, host_h - max(course_h, cornice_cm * 0.5) - 6.0),
    )
    cornice_z = max(plinth_z + course_h * 2.0, cornice_z)
    plinth_frac = min(0.99, plinth_z / STOREY_CM)
    cornice_frac = min(0.99, cornice_z / STOREY_CM)
    # Mid features also clamp into the usable host height.
    mid_frac = min(0.62, (host_h * 0.55) / STOREY_CM)
    string_frac = min(0.52, (host_h * 0.48) / STOREY_CM)

    courses: List[CourseSpec] = []
    if "plinth" in policy.course_names:
        courses.append(CourseSpec("plinth", plinth_frac, piece="band_course"))
    if policy.jettied_mid:
        courses.append(
            CourseSpec("bressummer", mid_frac, piece="band_course_jettied")
        )
    elif policy.mid_string:
        courses.append(CourseSpec("string", string_frac, piece="band_course"))
    if "cornice" in policy.course_names:
        courses.append(CourseSpec("cornice", cornice_frac, piece="band_course"))
    return tuple(courses)


def banding_spec_for_policy(
    policy: DetailPolicy,
    *,
    style_id: Optional[str] = None,
) -> BandingSpec:
    """Public: BandingSpec derived from a DetailPolicy (+ pack wall_bands)."""
    return BandingSpec(
        courses=_course_specs(policy, style_id),
        verticals_every_bays=policy.verticals_every_bays,
        vertical_piece="band_pilaster",
        braces=policy.braces,
        brace_piece="band_brace",
        coping=policy.coping,
        coping_piece="coping_cap",
        corners_only=policy.corners_only,
    )


def _detail_cap(wall_hosts: int, density: float) -> int:
    if wall_hosts <= 0:
        return 0
    raw = int(round(wall_hosts * MAX_DETAIL_RATIO * max(0.0, min(1.0, density))))
    return max(0, min(MAX_DETAIL_ABS, max(4, raw) if density > 0 else 0))


def _piece_rank(p: SolidPlacement) -> Tuple[int, str]:
    tags = p.tags
    if "horizontal" in tags or "course:plinth" in tags or "course:cornice" in tags:
        return (0, p.piece_id)
    if "course:string" in tags or "course:bressummer" in tags:
        return (1, p.piece_id)
    if "corner" in tags or "vertical" in tags:
        return (2, p.piece_id)
    if "coping" in tags:
        return (3, p.piece_id)
    return (4, p.piece_id)


def _subsample_pieces(
    pieces: Sequence[SolidPlacement],
    *,
    cap: int,
    seed: int,
) -> List[SolidPlacement]:
    """Keep a coherent subset when over budget — courses before verticals before other."""
    if cap <= 0:
        return []
    if len(pieces) <= cap:
        return list(pieces)

    rng = _rng(seed, "budget_pick")
    by_rank: Dict[int, List[SolidPlacement]] = {}
    for p in pieces:
        by_rank.setdefault(_piece_rank(p)[0], []).append(p)
    for rank in by_rank:
        by_rank[rank].sort(key=lambda p: p.piece_id)

    keep: List[SolidPlacement] = []
    # Prefer filling with courses, but seed-sample within each rank so seeds differ.
    for rank in sorted(by_rank):
        bucket = by_rank[rank]
        remaining = cap - len(keep)
        if remaining <= 0:
            break
        if len(bucket) <= remaining:
            keep.extend(bucket)
            continue
        # Seeded sample without replacement, stable order after.
        picked = rng.sample(bucket, k=remaining)
        picked.sort(key=lambda p: p.piece_id)
        keep.extend(picked)
        break

    keep.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    return keep


def _seed_vary_optional(
    pieces: Sequence[SolidPlacement],
    *,
    seed: int,
    density: float,
) -> List[SolidPlacement]:
    """Drop a seed-stable subset of optional verticals/coping (never strip all courses)."""
    if not pieces:
        return []
    courses = [p for p in pieces if _piece_rank(p)[0] <= 1]
    optional = [p for p in pieces if _piece_rank(p)[0] >= 2]
    if not optional:
        # No verticals/coping — seed-thin a minority of non-plinth courses.
        rng = _rng(seed, "course_thin")
        plinth = [p for p in courses if "course:plinth" in p.tags]
        other = [p for p in courses if "course:plinth" not in p.tags]
        keep_other = [
            p
            for p in other
            if rng.random() < (0.62 + 0.30 * density)
        ]
        # Guarantee at least one non-plinth course when any exist, else seed picks one.
        if other and not keep_other:
            keep_other = [sorted(other, key=lambda p: p.piece_id)[seed % len(other)]]
        out = plinth + keep_other
        out.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
        return out

    rng = _rng(seed, "optional_thin")
    keep_opt = [p for p in optional if rng.random() < (0.45 + 0.45 * density)]
    if optional and not keep_opt:
        # Keep one seeded optional so the family still reads.
        keep_opt = [sorted(optional, key=lambda p: p.piece_id)[seed % len(optional)]]
    out = list(courses) + keep_opt
    out.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    return out


def _retag_detail(p: SolidPlacement, *, extra: frozenset[str]) -> SolidPlacement:
    return replace(p, tags=frozenset(p.tags) | frozenset({DETAIL_TAG}) | extra)


def _opening_accent_tags(policy: DetailPolicy) -> frozenset[str]:
    accent = policy.opening_accent
    if accent == "none":
        return frozenset()
    if accent == "hood":
        return frozenset(
            {DETAIL_META_TAG, "detail:hood", "detail:lintel", "aperture_accent"}
        )
    if accent == "frame":
        return frozenset(
            {
                DETAIL_META_TAG,
                "detail:frame",
                "detail:sill",
                "detail:lintel",
                "aperture_accent",
            }
        )
    return frozenset(
        {DETAIL_META_TAG, "detail:sill", "detail:lintel", "aperture_accent"}
    )


def _apply_opening_accents(
    placements: List[SolidPlacement],
    policy: DetailPolicy,
    *,
    seed: int,
) -> Tuple[List[SolidPlacement], int]:
    """Tag aperture host walls — never swap aperture families."""
    tags = _opening_accent_tags(policy)
    if not tags:
        return placements, 0
    rng = _rng(seed, "opening_accent")
    apertures = [
        p
        for p in placements
        if p.kind == "wall"
        and ("window" in p.asset_id or "door" in p.asset_id or "gate" in p.asset_id)
    ]
    if not apertures:
        return placements, 0
    # Coherent: seed picks how many apertures get accents (majority bias), not a tag mix.
    n_apply = max(1, int(round(len(apertures) * (0.55 + 0.40 * policy.density))))
    n_apply = min(len(apertures), n_apply)
    # Slight seed jitter ±1 when room allows.
    if len(apertures) > 2 and rng.random() < 0.45:
        n_apply = max(1, min(len(apertures), n_apply + rng.choice((-1, 0, 1))))
    chosen_ids = {
        p.piece_id for p in rng.sample(sorted(apertures, key=lambda x: x.piece_id), k=n_apply)
    }
    out: List[SolidPlacement] = []
    n = 0
    for p in placements:
        if p.piece_id in chosen_ids:
            out.append(replace(p, tags=frozenset(p.tags) | tags))
            n += 1
        else:
            out.append(p)
    return out, n


def _apply_roof_accents(
    placements: List[SolidPlacement],
    policy: DetailPolicy,
    *,
    seed: int,
) -> Tuple[List[SolidPlacement], int]:
    """Metadata on existing roof pieces — does not call Stage C roof logic."""
    if not policy.roof_eave_trim and not policy.ridge_accent:
        return placements, 0
    rng = _rng(seed, "roof_accent")
    out: List[SolidPlacement] = []
    n = 0
    for p in placements:
        if p.kind != "roof" and not str(p.asset_id).startswith("roof_"):
            out.append(p)
            continue
        extra: set[str] = {DETAIL_META_TAG}
        aid = p.asset_id
        if policy.roof_eave_trim and (
            "slope" in aid or "flat" in aid or "hip" in aid or "gable" in aid
        ):
            if rng.random() < (0.5 + 0.4 * policy.density):
                extra.add("detail:eave_trim")
        if policy.ridge_accent and (
            "slope" in aid or "hip" in aid or "gable_infill" in aid
        ):
            if rng.random() < (0.35 + 0.4 * policy.density):
                extra.add("detail:ridge_accent")
        if len(extra) > 1:
            out.append(replace(p, tags=frozenset(p.tags) | frozenset(extra)))
            n += 1
        else:
            out.append(p)
    return out, n


def _apply_weathering(
    assembly: Assembly,
    placements: List[SolidPlacement],
    policy: DetailPolicy,
    *,
    seed: int,
) -> Tuple[List[SolidPlacement], int]:
    """Height / orientation wear tags — metadata only."""
    if not policy.weathering:
        return placements, 0
    faces = band_faces_of(assembly)
    rng = _rng(seed, "weather")
    damp_faces = {"south", "west"}
    out: List[SolidPlacement] = []
    n = 0
    for p in placements:
        if p.kind != "wall" or p.piece_id not in faces:
            out.append(p)
            continue
        face = faces[p.piece_id]
        tags: set[str] = {DETAIL_META_TAG}
        if p.level == 0 and face in damp_faces and rng.random() < 0.7:
            tags.add("weather:damp")
            tags.add("wear:high")
            tags.add("dampness:base")
        elif p.level == 0:
            tags.add("wear:medium")
        else:
            tags.add("wear:low")
            if face in damp_faces and rng.random() < 0.25:
                tags.add("weather:streak")
        # Material variation hint by height band (consumer TBD).
        tags.add(f"mat_var:L{p.level}")
        tags.add(f"orient:{face}")
        out.append(replace(p, tags=frozenset(p.tags) | frozenset(tags)))
        n += 1
    return out, n


def detail_signature(assembly: Assembly) -> Tuple[Tuple[str, str, Tuple[str, ...]], ...]:
    """Stable signature of detail pieces + meta tags for determinism asserts."""
    rows: List[Tuple[str, str, Tuple[str, ...]]] = []
    for p in assembly.placements:
        detail_tags = sorted(
            t
            for t in p.tags
            if t == DETAIL_TAG
            or t == DETAIL_META_TAG
            or t.startswith("detail:")
            or t.startswith("weather:")
            or t.startswith("wear:")
            or t.startswith("dampness:")
            or t.startswith("mat_var:")
            or t.startswith("orient:")
            or t.startswith("course:")
            or t in ("band", "aperture_accent", "horizontal", "vertical", "corner", "coping")
        )
        if DETAIL_TAG in p.tags or DETAIL_META_TAG in p.tags or detail_tags:
            rows.append((p.piece_id, p.asset_id, tuple(detail_tags)))
    return tuple(sorted(rows))


def count_detail_pieces(assembly: Assembly) -> int:
    return sum(1 for p in assembly.placements if DETAIL_TAG in p.tags)


def _host_wall_for_band(
    band: SolidPlacement,
    hosts: Dict[str, SolidPlacement],
) -> Optional[SolidPlacement]:
    """Recover host wall id from banding piece_id ``band_{asset}_{host}_{suffix}``."""
    pid = band.piece_id
    if not pid.startswith("band_"):
        return None
    # Longest host id match wins (hosts contain underscores).
    best: Optional[SolidPlacement] = None
    best_len = 0
    for hid, host in hosts.items():
        token = f"_{hid}_"
        if token in f"_{pid}_" and len(hid) > best_len:
            best = host
            best_len = len(hid)
    return best


def _band_kisses_host(band: SolidPlacement, host: SolidPlacement) -> bool:
    """True when band AABB vertically overlaps and kisses the host wall face."""
    from pae.contract import TOL_CM, placement_world_aabb

    bmin, bmax = placement_world_aabb(
        band.cell[0],
        band.cell[1],
        band.level,
        band.yaw,
        band.size_cm,
        band.offset_cm,
        rotates_about_center=band.rotates_about_center,
    )
    hmin, hmax = placement_world_aabb(
        host.cell[0],
        host.cell[1],
        host.level,
        host.yaw,
        host.size_cm,
        host.offset_cm,
        rotates_about_center=host.rotates_about_center,
    )
    # Vertical overlap required (floating cornice / coping above short pack walls).
    z_overlap = min(bmax[2], hmax[2]) - max(bmin[2], hmin[2])
    if z_overlap <= TOL_CM:
        return False
    # Horizontal: band must share a face slab with the host (kiss or slight embed).
    xy_overlap = (
        min(bmax[0], hmax[0]) - max(bmin[0], hmin[0]),
        min(bmax[1], hmax[1]) - max(bmin[1], hmin[1]),
    )
    # One axis nearly flush (projection), the other overlaps the run.
    flush = abs(xy_overlap[0]) <= WALL_T_LIKE or abs(xy_overlap[1]) <= WALL_T_LIKE
    run = xy_overlap[0] > TOL_CM or xy_overlap[1] > TOL_CM
    # Also accept true AABB overlap on both XY (embedded proud check elsewhere).
    both = xy_overlap[0] > -TOL_CM and xy_overlap[1] > -TOL_CM
    return (flush and run) or (
        both and xy_overlap[0] > TOL_CM and xy_overlap[1] > TOL_CM
    )


# Contact slack ~ wall thickness (bands project by a fraction of WALL_T).
WALL_T_LIKE = 60.0


def _filter_legible_bands(
    assembly: Assembly,
    pieces: Sequence[SolidPlacement],
) -> List[SolidPlacement]:
    """Drop orphan bands that do not touch a host wall (unreadable floaters)."""
    hosts = {p.piece_id: p for p in assembly.placements if p.kind == "wall"}
    kept: List[SolidPlacement] = []
    for p in pieces:
        host = _host_wall_for_band(p, hosts)
        if host is None:
            # Non-banding detail — keep.
            kept.append(p)
            continue
        if _band_kisses_host(p, host):
            kept.append(p)
    return kept


def apply_detail_layer(
    assembly: Assembly,
    *,
    style_id: Optional[str] = None,
    seed: int = 0,
    policy: Optional[DetailPolicy] = None,
    enabled: bool = True,
) -> Tuple[Assembly, Report]:
    """Additive Stage K pass. Deterministic; bounded; does not mutate *assembly*."""
    if not enabled:
        return assembly, Report.from_failures([])
    from pae.facade_shell import is_facade_shell_assembly

    if is_facade_shell_assembly(assembly):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="detail_layer_shell_skip",
                    message=(
                        "facade_shell assembly — jettied_mid / band dress skipped"
                    ),
                    critical=False,
                )
            ]
        )

    # Idempotent — do not stack detail on an already-detailed assembly.
    if any(DETAIL_TAG in p.tags or DETAIL_META_TAG in p.tags for p in assembly.placements):
        return assembly, Report.from_failures(
            [
                Failure(
                    check="detail_layer_skip",
                    message="detail_layer already applied — skipped",
                    critical=False,
                )
            ]
        )

    pol = policy or detail_policy_for_style(style_id)
    # Full-height bay posts are OK (timber grid); random course thinning is not.
    pol = replace(pol, verticals_every_bays=max(1, pol.verticals_every_bays))
    faces = band_faces_of(assembly)
    wall_hosts = len(faces)
    cap = _detail_cap(wall_hosts, pol.density)

    # 1) Façade articulation via existing banding contract.
    bspec = banding_spec_for_policy(pol, style_id=style_id)
    banded, breport = band(assembly, bspec)
    if not breport.ok:
        return assembly, breport

    base_ids = {p.piece_id for p in assembly.placements}
    raw_extra = [p for p in banded.placements if p.piece_id not in base_ids]

    # NEVER shatter horizontal courses — orphan mid-wall rectangles are unreadable.
    # Keep every plinth / string / cornice / bressummer bay; budget only verticals/coping.
    course_ids = {
        p.piece_id
        for p in raw_extra
        if "horizontal" in p.tags or any(t.startswith("course:") for t in p.tags)
    }
    courses = [p for p in raw_extra if p.piece_id in course_ids]
    optional = [p for p in raw_extra if p.piece_id not in course_ids]
    # Seed-thin optional verticals/coping only.
    optional = _seed_vary_optional(optional, seed=seed, density=pol.density)
    opt_cap = max(0, cap)  # courses do not consume the spot-budget
    if len(optional) > opt_cap:
        optional = _subsample_pieces(optional, cap=opt_cap, seed=seed)
    # Soft ceiling on courses for huge elevations (still contiguous per face).
    if len(courses) > MAX_COURSE_ABS:
        courses = _subsample_pieces(courses, cap=MAX_COURSE_ABS, seed=seed)
    chosen = list(courses) + list(optional)
    # Drop floaters from pack-storey vs STOREY_CM mismatch (L1 cornice/coping).
    chosen = _filter_legible_bands(assembly, chosen)
    chosen.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    family_tag = frozenset({f"detail_style:{pol.style_family}"})
    detail_pieces = [
        _retag_detail(p, extra=family_tag | frozenset({"articulation"}))
        for p in chosen
    ]
    # Visually scale course thickness from pack wall_bands (height only —
    # growing projection without re-offsetting trips band_proud).
    plinth_cm, cornice_cm, _storey = _wall_bands_cm(style_id)
    scaled: List[SolidPlacement] = []
    for p in detail_pieces:
        sx, sy, sz = p.size_cm
        if "course:plinth" in p.tags:
            scale = max(1.0, float(plinth_cm) / 30.0)
            scaled.append(replace(p, size_cm=(sx, sy, sz * min(2.8, scale))))
        elif "course:cornice" in p.tags:
            scale = max(1.0, float(cornice_cm) / 20.0)
            scaled.append(replace(p, size_cm=(sx, sy, sz * min(2.5, scale))))
        elif "course:string" in p.tags or "course:bressummer" in p.tags:
            scaled.append(replace(p, size_cm=(sx, sy, sz * 1.35)))
        else:
            scaled.append(p)
    detail_pieces = scaled

    # 2) Metadata accents on hosts / roofs (no new blocking geometry).
    working = list(assembly.placements)
    working, n_open = _apply_opening_accents(working, pol, seed=seed)
    working, n_roof = _apply_roof_accents(working, pol, seed=seed)
    # Weathering needs original face map from pre-detail assembly.
    weather_asm = Assembly(
        placements=working,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        entrance_specs=list(getattr(assembly, "entrance_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )
    working, n_weather = _apply_weathering(
        weather_asm, working, pol, seed=seed
    )

    out_placements = working + detail_pieces
    out_placements.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))

    budget = DetailBudget(
        wall_hosts=wall_hosts,
        added_pieces=len(detail_pieces),
        meta_tagged=n_open + n_roof + n_weather,
        cap=cap,
        ratio=(len(detail_pieces) / wall_hosts) if wall_hosts else 0.0,
        style_family=pol.style_family,
        seed=int(seed),
    )

    out = Assembly(
        placements=out_placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=list(getattr(assembly, "room_specs", []) or []),
        entrance_specs=list(getattr(assembly, "entrance_specs", []) or []),
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )

    return out, Report.from_failures(
        [
            Failure(
                check="detail_layer_budget",
                message=budget.as_message(),
                critical=False,
            )
        ]
    )


__all__ = [
    "DETAIL_META_TAG",
    "DETAIL_TAG",
    "DetailBudget",
    "DetailPolicy",
    "MATERIAL_CONSUMPTION_GAPS",
    "MAX_COURSE_ABS",
    "MAX_DETAIL_ABS",
    "MAX_DETAIL_RATIO",
    "apply_detail_layer",
    "banding_spec_for_policy",
    "count_detail_pieces",
    "detail_policy_for_style",
    "detail_signature",
]

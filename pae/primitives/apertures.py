"""Aperture profiles — data-driven window / door / arch types.

WHY THIS EXISTS: window geometry used to be three private constants in ``walls.py``
(``_WINDOW_W``, ``_WINDOW_H``, ``_WINDOW_SILL``).  One window shape, unreachable from a
spec, unreachable from a slider, unadjustable without editing source.  A school needs
lancets in the chapel, mullioned lights in the hall, oculi in a gable and a shopfront-wide
opening in a refectory — so the shape has to be *data*, not code.

An ``ApertureProfile`` is a declarative description in fractions of MODULE / STOREY.  It
never contains a contract dimension.  ``opening_slices`` turns a profile into horizontal
bands, which is what lets a head be round, pointed or flat with the same code path, and
what lets mullions divide one opening into several lights.

Frame parts are derived from the slices by subtraction, so an arched head is genuinely cut
out of the wall solid rather than approximated by a rectangle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple

from pae.contract import MODULE_CM, STOREY_CM

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]
Slice = Tuple[float, float, float, float]  # (z0, z1, run0, run1)

# Head shapes.
HEAD_FLAT = "flat"
HEAD_ROUND = "round"  # semicircular — rise = half the opening width
HEAD_POINTED = "pointed"  # gothic lancet — two arcs meeting at an apex
HEAD_SEGMENTAL = "segmental"  # shallow arc, rise = a fraction of half-width
HEAD_SHOULDERED = "shouldered"  # flat head on corbelled corners
HEAD_SHAPES = (
    HEAD_FLAT,
    HEAD_ROUND,
    HEAD_POINTED,
    HEAD_SEGMENTAL,
    HEAD_SHOULDERED,
)

# Vertical resolution of a curved head. Enough bands that a 1.4 m opening reads as a
# curve, not a staircase, without exploding the vertex budget on a 600-window school.
HEAD_BANDS = 12
# Monumental gate / cloister arches span most of a bay — 12 bands reads as stepped blocks.
MONUMENTAL_HEAD_BANDS = 36

_SEGMENTAL_RISE_FRAC = 0.35  # of half-width
_SHOULDER_FRAC = 0.18  # corbel inset as fraction of opening width


@dataclass(frozen=True)
class ApertureProfile:
    """A window / door / arch type, in fractions of the grid contract.

    ``width_frac`` and ``sill_frac`` / ``height_frac`` are fractions of MODULE and STOREY
    respectively.  ``height_frac`` measures the *total* opening including any curved head.
    ``lights`` > 1 divides the opening with mullions; ``transom_frac`` (of opening height)
    inserts a horizontal bar.  All values are validated on construction — a profile that
    would punch through the floor or the ceiling plate is a bug caught here, not a defect
    found in a render.
    """

    name: str
    kind: str  # window | door | arrowslit | arch
    width_frac: float
    height_frac: float
    sill_frac: float = 0.0
    head: str = HEAD_FLAT
    head_bands: int = HEAD_BANDS
    lights: int = 1
    mullion_frac: float = 0.06  # of MODULE, per mullion
    transom_frac: float = 0.0  # of opening height; 0 = none
    tags: FrozenSet[str] = field(default_factory=frozenset)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.head not in HEAD_SHAPES:
            raise ValueError(
                f"aperture profile {self.name!r}: unknown head {self.head!r}; "
                f"known: {', '.join(HEAD_SHAPES)}"
            )
        if not 0.0 < self.width_frac < 1.0:
            raise ValueError(
                f"aperture profile {self.name!r}: width_frac must be in (0, 1), "
                f"got {self.width_frac}"
            )
        if self.lights < 1:
            raise ValueError(f"aperture profile {self.name!r}: lights must be >= 1")
        top = self.sill_frac + self.height_frac
        if self.sill_frac < 0.0 or top > 1.0:
            raise ValueError(
                f"aperture profile {self.name!r}: opening spans "
                f"{self.sill_frac:.2f}..{top:.2f} of STOREY — must stay within 0..1"
            )
        if not 0.0 <= self.transom_frac < 1.0:
            raise ValueError(
                f"aperture profile {self.name!r}: transom_frac must be in [0, 1)"
            )
        if self.head_bands < 4:
            raise ValueError(
                f"aperture profile {self.name!r}: head_bands must be >= 4, "
                f"got {self.head_bands}"
            )

    # -- derived cm geometry -------------------------------------------------

    def opening_run_cm(self, module_cm: float = MODULE_CM) -> Tuple[float, float]:
        """Opening span on the wall run axis, centred in the bay."""
        half = module_cm * self.width_frac * 0.5
        return (module_cm * 0.5 - half, module_cm * 0.5 + half)

    def opening_z_cm(self, storey_cm: float = STOREY_CM) -> Tuple[float, float]:
        z0 = storey_cm * self.sill_frac
        return (z0, z0 + storey_cm * self.height_frac)

    def head_rise_cm(self, module_cm: float = MODULE_CM) -> float:
        """Vertical extent of the curved head (0 for a flat head)."""
        run0, run1 = self.opening_run_cm(module_cm)
        half = (run1 - run0) * 0.5
        if self.head == HEAD_ROUND:
            return half
        if self.head == HEAD_POINTED:
            # Equilateral lancet: centres at the opposite springing point.
            return half * math.sqrt(3.0)
        if self.head == HEAD_SEGMENTAL:
            return half * _SEGMENTAL_RISE_FRAC
        return 0.0


def _head_half_width_at(profile: ApertureProfile, half: float, t: float) -> float:
    """Half-width of a curved head at height fraction ``t`` (0 = springing, 1 = apex)."""
    if profile.head == HEAD_ROUND:
        # x = half * cos(asin(t)) — circle of radius `half`.
        return half * math.sqrt(max(0.0, 1.0 - t * t))
    if profile.head == HEAD_SEGMENTAL:
        rise = half * _SEGMENTAL_RISE_FRAC
        # Circle through the springing points with the given rise.
        radius = (half * half + rise * rise) / (2.0 * rise)
        y = t * rise
        dx = radius - rise + y
        return math.sqrt(max(0.0, radius * radius - dx * dx))
    if profile.head == HEAD_POINTED:
        # Two arcs of radius = full width, centred on the opposite springing point.
        radius = half * 2.0
        y = t * profile_pointed_rise(half)
        inner = radius * radius - y * y
        if inner <= 0.0:
            return 0.0
        return max(0.0, math.sqrt(inner) - half)
    return half


def profile_pointed_rise(half: float) -> float:
    return half * math.sqrt(3.0)


def opening_slices(
    profile: ApertureProfile,
    *,
    module_cm: float = MODULE_CM,
    storey_cm: float = STOREY_CM,
) -> List[Slice]:
    """Decompose an opening into horizontal bands ``(z0, z1, run0, run1)``.

    A flat head is one band.  A curved head is ``profile.head_bands`` bands whose width
    follows the curve.  Mullions and transoms are applied by subtracting bars from these
    bands in :func:`frame_parts`.
    """
    run0, run1 = profile.opening_run_cm(module_cm)
    z0, z1 = profile.opening_z_cm(storey_cm)
    rise = profile.head_rise_cm(module_cm)
    half = (run1 - run0) * 0.5
    centre = (run0 + run1) * 0.5

    if rise <= 0.0 or profile.head in (HEAD_FLAT, HEAD_SHOULDERED):
        slices: List[Slice] = [(z0, z1, run0, run1)]
        if profile.head == HEAD_SHOULDERED:
            # Corbel the top corners: a narrower band under the lintel.
            inset = (run1 - run0) * _SHOULDER_FRAC
            shoulder_z = z1 - inset
            if shoulder_z > z0:
                slices = [
                    (z0, shoulder_z, run0, run1),
                    (shoulder_z, z1, run0 + inset, run1 - inset),
                ]
        return slices

    # Curved head: straight jambs up to the springing, then banded arc.
    spring_z = max(z0, z1 - rise)
    slices = []
    if spring_z > z0:
        slices.append((z0, spring_z, run0, run1))
    bands = profile.head_bands
    for i in range(bands):
        t0 = i / bands
        t1 = (i + 1) / bands
        # Use the *upper* edge width so the band never pokes outside the curve.
        w = _head_half_width_at(profile, half, t1)
        if w <= 1e-6:
            continue
        slices.append(
            (
                spring_z + rise * t0,
                spring_z + rise * t1,
                centre - w,
                centre + w,
            )
        )
    return slices


def _subtract_bars(
    profile: ApertureProfile,
    slices: List[Slice],
    module_cm: float,
    storey_cm: float,
) -> List[BoxPart]:
    """Mullion / transom bars that re-fill part of the opening."""
    bars: List[BoxPart] = []
    run0, run1 = profile.opening_run_cm(module_cm)
    z0, z1 = profile.opening_z_cm(storey_cm)
    span = run1 - run0

    if profile.lights > 1:
        bar_w = module_cm * profile.mullion_frac
        for i in range(1, profile.lights):
            centre = run0 + span * i / profile.lights
            bars.append(
                (
                    (0.0, centre - bar_w * 0.5, z0),
                    (0.0, bar_w, z1 - z0),  # x size filled in by caller
                )
            )
    if profile.transom_frac > 0.0:
        bar_h = storey_cm * profile.height_frac * profile.mullion_frac
        ty = z0 + (z1 - z0) * profile.transom_frac
        bars.append(((0.0, run0, ty - bar_h * 0.5), (0.0, span, bar_h)))
    return bars


def frame_parts(
    profile: ApertureProfile,
    size_cm: Tuple[float, float, float],
    *,
    module_cm: float = MODULE_CM,
    storey_cm: float = STOREY_CM,
) -> List[BoxPart]:
    """Solid boxes of a wall bay with this profile's opening removed.

    Every part spans the full wall thickness on X — the opening is a genuine through-hole,
    never a side notch (the ``P``-shaped-silhouette bug from @APERTURE_FACE).
    """
    wx, wy, wz = size_cm
    slices = opening_slices(profile, module_cm=module_cm, storey_cm=storey_cm)
    slices = [s for s in slices if s[1] > s[0]]
    if not slices:
        return [((0.0, 0.0, 0.0), (wx, wy, wz))]

    eps = 1e-5
    parts: List[BoxPart] = []
    lowest = min(s[0] for s in slices)
    highest = max(s[1] for s in slices)

    # Full-width bands below the sill and above the head.
    if lowest > eps:
        parts.append(((0.0, 0.0, 0.0), (wx, wy, lowest)))
    if highest < wz - eps:
        parts.append(((0.0, 0.0, highest), (wx, wy, wz - highest)))

    # Jambs either side of each band.
    for z0, z1, run0, run1 in slices:
        h = z1 - z0
        if h <= eps:
            continue
        if run0 > eps:
            parts.append(((0.0, 0.0, z0), (wx, run0, h)))
        if run1 < wy - eps:
            parts.append(((0.0, run1, z0), (wx, wy - run1, h)))

    # Mullions / transoms fill back in, full wall thickness.
    for (_ox, oy, oz), (_sx, sy, sz) in _subtract_bars(
        profile, slices, module_cm, storey_cm
    ):
        parts.append(((0.0, oy, oz), (wx, sy, sz)))

    return parts


# --------------------------------------------------------------------------
# Registry — the shapes a spec or a slider can ask for by name.
# --------------------------------------------------------------------------

_W = "window"
_D = "door"

PROFILES: Dict[str, ApertureProfile] = {}


def _register(p: ApertureProfile) -> ApertureProfile:
    if p.name in PROFILES:
        raise ValueError(f"duplicate aperture profile {p.name!r}")
    PROFILES[p.name] = p
    return p


# Windows ------------------------------------------------------------------
_register(
    ApertureProfile(
        name="window_plain",
        kind=_W,
        width_frac=0.35,
        height_frac=0.40,
        sill_frac=0.28,
        head=HEAD_FLAT,
        tags=frozenset({"window", "plain"}),
        notes="Square-headed single light — the original PAE window.",
    )
)
_register(
    ApertureProfile(
        name="window_round",
        kind=_W,
        width_frac=0.35,
        height_frac=0.46,
        sill_frac=0.26,
        head=HEAD_ROUND,
        tags=frozenset({"window", "romanesque"}),
        notes="Semicircular head — cloister / romanesque range.",
    )
)
_register(
    ApertureProfile(
        name="window_lancet",
        kind=_W,
        width_frac=0.20,
        height_frac=0.58,
        sill_frac=0.22,
        head=HEAD_POINTED,
        tags=frozenset({"window", "gothic", "window_gothic"}),
        notes="Tall pointed light — chapel and gothic academy ranges.",
    )
)
_register(
    ApertureProfile(
        name="window_mullioned",
        kind=_W,
        width_frac=0.62,
        height_frac=0.48,
        sill_frac=0.26,
        head=HEAD_FLAT,
        lights=3,
        transom_frac=0.62,
        tags=frozenset({"window", "hall", "mullioned"}),
        notes="Three-light transomed window — great hall / refectory.",
    )
)
_register(
    ApertureProfile(
        name="window_gothic_traceried",
        kind=_W,
        width_frac=0.58,
        height_frac=0.62,
        sill_frac=0.20,
        head=HEAD_POINTED,
        lights=2,
        tags=frozenset({"window", "gothic", "window_gothic", "traceried"}),
        notes="Two-light pointed window with a central mullion.",
    )
)
_register(
    ApertureProfile(
        name="window_oculus",
        kind=_W,
        width_frac=0.30,
        height_frac=0.30,
        sill_frac=0.52,
        head=HEAD_ROUND,
        tags=frozenset({"window", "oculus", "gable"}),
        notes="Round window for gable ends and stair towers.",
    )
)
_register(
    ApertureProfile(
        name="window_clerestory",
        kind=_W,
        width_frac=0.55,
        height_frac=0.22,
        sill_frac=0.62,
        head=HEAD_SEGMENTAL,
        lights=2,
        tags=frozenset({"window", "clerestory"}),
        notes="Wide shallow high-level light — corridors and halls.",
    )
)
_register(
    ApertureProfile(
        name="window_bay_wide",
        kind=_W,
        width_frac=0.70,
        height_frac=0.52,
        sill_frac=0.20,
        head=HEAD_SEGMENTAL,
        lights=4,
        transom_frac=0.70,
        tags=frozenset({"window", "wide", "library"}),
        notes="Near-full-bay glazing — library / refectory ranges.",
    )
)
_register(
    ApertureProfile(
        name="arrowslit",
        kind="arrowslit",
        width_frac=0.05,
        height_frac=0.45,
        sill_frac=0.30,
        head=HEAD_FLAT,
        tags=frozenset({"arrowslit", "defensive"}),
        notes="Narrow vertical slit.",
    )
)

# Doors --------------------------------------------------------------------
_register(
    ApertureProfile(
        name="door_plain",
        kind=_D,
        width_frac=0.40,
        height_frac=0.72,
        sill_frac=0.0,
        head=HEAD_FLAT,
        tags=frozenset({"door", "plain"}),
        notes="Square-headed door reaching the floor.",
    )
)
_register(
    ApertureProfile(
        name="door_arched",
        kind=_D,
        width_frac=0.42,
        height_frac=0.78,
        sill_frac=0.0,
        head=HEAD_ROUND,
        tags=frozenset({"door", "arched"}),
        notes="Round-headed doorway.",
    )
)
_register(
    ApertureProfile(
        name="door_gothic",
        kind=_D,
        width_frac=0.40,
        height_frac=0.84,
        sill_frac=0.0,
        head=HEAD_POINTED,
        tags=frozenset({"door", "gothic"}),
        notes="Pointed-arch doorway — chapel and main entrances.",
    )
)
_register(
    ApertureProfile(
        name="door_double",
        kind=_D,
        width_frac=0.62,
        height_frac=0.80,
        sill_frac=0.0,
        head=HEAD_SHOULDERED,
        lights=2,
        tags=frozenset({"door", "double", "grand"}),
        notes="Wide double doorway with a central mullion — great hall.",
    )
)
_register(
    ApertureProfile(
        name="gate_arch",
        kind=_D,
        width_frac=0.88,
        height_frac=0.90,
        sill_frac=0.0,
        head=HEAD_ROUND,
        head_bands=MONUMENTAL_HEAD_BANDS,
        tags=frozenset({"door", "gate", "grand", "monumental"}),
        notes="Monumental round gate — near full-bay carriage opening (BUILDING_HEIGHT_FLEX Z).",
    )
)
_register(
    ApertureProfile(
        name="gate_arch_grand",
        kind=_D,
        width_frac=0.92,
        height_frac=0.94,
        sill_frac=0.0,
        head=HEAD_ROUND,
        head_bands=MONUMENTAL_HEAD_BANDS,
        tags=frozenset({"door", "gate", "grand", "monumental", "fortress"}),
        notes=(
            "Fortress gatehouse leaf — max clear width/height in one bay "
            "(@GATEHOUSE_MONUMENTAL; arcade gallery owns cloister arches)."
        ),
    )
)
_register(
    ApertureProfile(
        name="gate_arch_pointed",
        kind=_D,
        width_frac=0.82,
        height_frac=0.88,
        sill_frac=0.0,
        head=HEAD_POINTED,
        tags=frozenset({"door", "gate", "grand", "gothic"}),
        notes="Pointed gate variant — gothic gatehouses.",
    )
)

# Arcades ------------------------------------------------------------------
_register(
    ApertureProfile(
        name="arcade_round",
        kind="arch",
        width_frac=0.78,
        height_frac=0.82,
        sill_frac=0.10,
        head=HEAD_ROUND,
        head_bands=MONUMENTAL_HEAD_BANDS,
        tags=frozenset({"arch", "arcade", "cloister"}),
        notes="Round-arched arcade bay — cut into the module, one piece.",
    )
)
_register(
    ApertureProfile(
        name="arcade_monumental",
        kind="arch",
        width_frac=0.84,
        height_frac=0.88,
        sill_frac=0.06,
        head=HEAD_ROUND,
        tags=frozenset({"arch", "arcade", "cloister", "monumental"}),
        notes="Tall cloister arch — low spring, wide round head under a gallery roof.",
    )
)
_register(
    ApertureProfile(
        name="arcade_gothic",
        kind="arch",
        width_frac=0.70,
        height_frac=0.80,
        sill_frac=0.12,
        head=HEAD_POINTED,
        tags=frozenset({"arch", "arcade", "gothic", "cloister"}),
        notes="Pointed arcade bay for cloister walks.",
    )
)


def get_profile(name: str) -> ApertureProfile:
    if name not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise KeyError(f"unknown aperture profile {name!r}; known: {known}")
    return PROFILES[name]


def profile_names(kind: str = "") -> List[str]:
    if not kind:
        return sorted(PROFILES)
    return sorted(n for n, p in PROFILES.items() if p.kind == kind)


def profiles_with_tag(tag: str) -> List[ApertureProfile]:
    return [PROFILES[n] for n in sorted(PROFILES) if tag in PROFILES[n].tags]

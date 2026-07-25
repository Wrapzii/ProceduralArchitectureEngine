"""BuildingSpec loader (§3) — WP-4.

Specs are declarative and in bays/modules. The loader rejects any LLM JSON that
contains world coordinates or centimetre placement fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pae.report import Failure, Report

# Keys / patterns that imply world placement or centimetre coordinates.
# Style JSON may use *_cm for band heights; BuildingSpec JSON must not.
_FORBIDDEN_KEY_RE = re.compile(
    r"(?i)^("
    r"x|y|z|pos|position|location|origin|placement|coordinate|coordinates|"
    r"translation|offset|world_.*|.*_world|"
    r".*_cm|.*_m|metres?|meters?|centimetres?|centimeters?"
    r")$"
)

_STYLES_DIR = Path(__file__).resolve().parent / "styles"

# Auto-placed circulation kinds. Spiral uses same-cell stacking (tower well).
SUPPORTED_STAIR_KINDS = frozenset({"straight", "switchback", "wide", "spiral"})
# ``auto`` → style RoofHints.kind_default via ``resolve_roof_kind`` (variation hook).
SUPPORTED_ROOF_KINDS = frozenset({"flat", "pitched", "hip", "auto"})
ROOF_PITCH_MIN = 0.5
ROOF_PITCH_MAX = 2.5
STEEP_PITCH_MIN = 1.6  # S-011 anime-fantasy silhouette

# Building typology — drives default / allowed stair kinds (VAL_STAIR_TYPOLOGY).
# Buttresses are structural trim, NEVER stairs (see STAIR_TYPOLOGY_FORBIDDEN_ASSETS).
BUILDING_CLASSES = frozenset(
    {"house", "cottage", "industrial", "academy", "castle", "tower", "generic"}
)
# Compact dwelling stairs (1×1 / 2×1). ``stair_half`` is an asset, not a stair_kind.
COMPACT_STAIR_ASSETS = frozenset({"stair_straight", "stair_half", "stair_landing"})
# Monumental / institutional wells (2×2).
MONUMENTAL_STAIR_ASSETS = frozenset({"stair_wide", "stair_switchback"})
SPIRAL_STAIR_ASSETS = frozenset({"stair_spiral_quarter"})
# Never treat these as circulation stairs.
STAIR_TYPOLOGY_FORBIDDEN_ASSETS = frozenset(
    {"buttress", "buttress_flying", "flying_buttress"}
)
STAIR_ASSET_TO_KIND = {
    "stair_straight": "straight",
    "stair_half": "straight",  # compact half-rise → same typology as straight
    "stair_landing": "straight",
    "stair_wide": "wide",
    "stair_switchback": "switchback",
    "stair_spiral_quarter": "spiral",
}
# Policy table: class → default kind + allowed kinds (continuity-safe subset applied later).
STAIR_TYPOLOGY_POLICY: Dict[str, Dict[str, Any]] = {
    "house": {
        "default": "straight",
        "allowed": frozenset({"straight"}),
        "notes": "Houses / small dwellings → compact stair_straight / stair_half only",
    },
    "cottage": {
        "default": "straight",
        "allowed": frozenset({"straight"}),
        "notes": "Cottages share house compact stairs",
    },
    "industrial": {
        "default": "wide",
        "allowed": frozenset({"wide", "switchback"}),
        "notes": "Workshops / mills → monumental wells when footprint allows",
    },
    "academy": {
        "default": "switchback",
        "allowed": frozenset({"wide", "switchback"}),
        "notes": "Schools / large academies → switchback or wide",
    },
    "castle": {
        "default": "switchback",
        "allowed": frozenset({"wide", "switchback", "spiral"}),
        "notes": "Castle ranges → wide/switchback; towers may use spiral",
    },
    "tower": {
        "default": "spiral",
        "allowed": frozenset({"spiral"}),
        "notes": "Standalone / keep towers → spiral with newel (shell owned elsewhere)",
    },
    "generic": {
        "default": "straight",
        "allowed": frozenset({"straight", "switchback", "wide", "spiral"}),
        "notes": "Unclassified — any continuity-safe supported kind",
    },
}

ROOM_KINDS = frozenset(
    {"classroom", "hall", "chapel", "library", "dormitory", "kitchen", "store"}
)

ENTRANCE_ROLES = frozenset(
    {
        "grand",
        "main",
        "side",
        "service",
        "postern",
        "gate",
        "balcony",
        "internal",
        "upper_exterior",  # Phase 9.2 — door on storey N opening to outside air
    }
)
ENTRANCE_FACADES = frozenset({"south", "north", "east", "west"})


@dataclass
class FootprintSpec:
    kind: str  # rect | L | U | courtyard | compound | school
    bays_x: int
    bays_y: int
    wing_depth: int = 2
    courtyard: bool = False


@dataclass
class TowerSpec:
    """Tower attachment in *cell* space (never world cm)."""

    cell: Tuple[int, int]
    storeys: int
    attached_to: str = "corner"  # wall | corner


@dataclass
class RoofSpec:
    kind: str = "flat"  # flat | pitched | hip | auto (→ style kind_default)
    pitch: float = 1.0


@dataclass
class CirculationSpec:
    stair_kind: str = "straight"  # straight | switchback | wide | spiral (tower / 1-cell)
    stair_cells: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class OpeningPolicy:
    windows_per_bay: int = 1
    doors_ground: int = 1
    windows_ground: Optional[int] = None  # exact count override (e.g. M1 = 2)
    skip_ground_windows: bool = False


EntranceRole = str  # grand | main | side | service | postern | gate | balcony | internal | upper_exterior


@dataclass
class EntranceSpec:
    """Declarative entrance — role drives piece choice; facade/bay place it.

    Every declared entrance is a *passage breach*: assemble must place a door or
    gate leaf (never a bare hole). Enforced by ``no_bare_aperture`` (roadmap §1.5).

    When ``ensemble`` is True (Phase 1.3), assemble expands the entrance into a
    greybox composition: arch leaf + exterior steps + flanking columns, and twin
    interior stairs when the building has ≥2 storeys and free interior cells.

    Phase 9.2: ``role="upper_exterior"`` with ``storey >= 1`` declares a door that
    opens to outside air. It must pair with an exterior landing
    (``upper_entrance_landing`` / ``aperture_reachability``).
    """

    role: EntranceRole
    facade: Optional[str] = None  # south | north | east | west
    bay: Optional[int] = None  # 0-based index along the facade run
    ensemble: bool = False
    storey: int = 0  # 0 = ground; upper_exterior requires >= 1


@dataclass
class RoomSpec:
    """Programmed room intent — geometry resolved in plan/assemble."""

    name: str
    kind: str  # classroom | hall | chapel | library | dormitory | kitchen | store
    area_bays: Optional[int] = None
    double_height: bool = False


@dataclass
class BuildingSpec:
    name: str
    style: str
    footprint: FootprintSpec
    storeys: int
    storey_use: List[str]
    towers: List[TowerSpec] = field(default_factory=list)
    roof: RoofSpec = field(default_factory=RoofSpec)
    circulation: CirculationSpec = field(default_factory=CirculationSpec)
    openings: OpeningPolicy = field(default_factory=OpeningPolicy)
    entrances: List[EntranceSpec] = field(default_factory=list)
    seed: int = 0
    # Intent only — geometry emitted by assemble (WP-5).
    ground_slab: bool = True
    rooms: List[RoomSpec] = field(default_factory=list)
    #: Typology hint for stair policy. None → derived from massing/program.
    building_class: Optional[str] = None


def footprint_allows_wide_stair_well(footprint: FootprintSpec) -> bool:
    """True when primary body can host a 2×2 switchback/wide stairwell."""
    return min(int(footprint.bays_x), int(footprint.bays_y)) >= 4


def derive_building_class(spec: BuildingSpec) -> str:
    """Resolve building_class from explicit field or massing/program hints.

    Order: explicit → footprint.kind school → tower-only keep → style/name cues
    → footprint size + storeys (industrial vs house) → generic.
    """
    raw = (spec.building_class or "").strip().lower()
    if raw in BUILDING_CLASSES:
        return raw

    if spec.footprint.kind == "school":
        return "academy"

    name = (spec.name or "").lower()
    style = (spec.style or "").lower()
    if "industrial" in name or "workshop" in name or "mill" in name:
        return "industrial"
    if "academy" in name or "school" in name or "gothic_academy" in style:
        return "academy"
    if "cottage" in name or "wealden" in name:
        return "cottage"
    if "house" in name or style in ("townhouse",):
        # Small dwellings only — large townhouse ranges stay generic below.
        if max(spec.footprint.bays_x, spec.footprint.bays_y) <= 6 and spec.storeys <= 3:
            return "house"
    if "castle" in name or "curtain" in name or "gatehouse" in name or style == "keep":
        if spec.towers and spec.footprint.bays_x <= 4 and spec.footprint.bays_y <= 4:
            return "tower"
        return "castle"
    if "tower" in name or (spec.towers and max(spec.footprint.bays_x, spec.footprint.bays_y) <= 3):
        return "tower"

    area = spec.footprint.bays_x * spec.footprint.bays_y
    if area >= 48 and spec.storeys >= 2:
        return "industrial"
    if area <= 20 and spec.storeys <= 3 and not spec.towers:
        return "house"
    return "generic"


def continuity_safe_stair_kinds(
    building_class: str,
    *,
    has_tower: bool = False,
    wide_well: bool = False,
    storeys: int = 1,
) -> frozenset:
    """Allowed stair_kinds for a class that the solver can actually place.

    Spiral requires a tower. Wide/switchback require a 2×2 well and ≥2 storeys.
    Never returns empty — falls back to ``straight`` so continuity checks stay green.
    """
    policy = STAIR_TYPOLOGY_POLICY.get(
        building_class, STAIR_TYPOLOGY_POLICY["generic"]
    )
    allowed = set(policy["allowed"])
    if storeys <= 1:
        # Single-storey buildings need no climb; keep straight as a no-op default.
        return frozenset({"straight"}) & allowed or frozenset({"straight"})
    if "spiral" in allowed and not has_tower:
        allowed.discard("spiral")
    if not wide_well:
        allowed.discard("wide")
        allowed.discard("switchback")
    # House/cottage must stay compact even if a large footprint accidentally
    # satisfies wide_well — policy already excludes monumental kinds.
    if not allowed:
        allowed = {"straight"}
    return frozenset(allowed)


def default_stair_kind_for_class(
    building_class: str,
    *,
    has_tower: bool = False,
    wide_well: bool = False,
    storeys: int = 1,
) -> str:
    """Default stair_kind for a building class (continuity-safe)."""
    policy = STAIR_TYPOLOGY_POLICY.get(
        building_class, STAIR_TYPOLOGY_POLICY["generic"]
    )
    safe = continuity_safe_stair_kinds(
        building_class,
        has_tower=has_tower,
        wide_well=wide_well,
        storeys=storeys,
    )
    preferred = str(policy["default"])
    if preferred in safe:
        return preferred
    # Prefer monumental when both available, else any stable order.
    for kind in ("switchback", "wide", "spiral", "straight"):
        if kind in safe:
            return kind
    return "straight"


def pick_stair_kind_for_class(
    building_class: str,
    seed: int,
    *,
    has_tower: bool = False,
    wide_well: bool = False,
    storeys: int = 1,
    name: str = "",
) -> str:
    """Seeded pick among continuity-safe kinds for ``building_class``."""
    import random

    safe = sorted(
        continuity_safe_stair_kinds(
            building_class,
            has_tower=has_tower,
            wide_well=wide_well,
            storeys=storeys,
        )
    )
    if len(safe) == 1:
        return safe[0]
    rng = random.Random(f"{seed}:stair_kind:{name or building_class}")
    return rng.choice(safe)


def stair_kind_from_asset(asset_id: str) -> Optional[str]:
    """Map a placed stair asset to a typology kind; None if unknown/non-stair."""
    aid = (asset_id or "").lower()
    if aid in STAIR_TYPOLOGY_FORBIDDEN_ASSETS or aid.startswith("buttress"):
        return None  # caller treats as forbidden-as-stair
    return STAIR_ASSET_TO_KIND.get(aid)


def _scan_forbidden_keys(node: Any, path: str = "") -> List[str]:
    """Return human-readable paths of forbidden world/cm keys."""
    hits: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if _FORBIDDEN_KEY_RE.match(str(key)):
                hits.append(child)
            hits.extend(_scan_forbidden_keys(value, child))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            hits.extend(_scan_forbidden_keys(value, f"{path}[{i}]"))
    return hits


def _as_int_pair(value: Any, label: str) -> Tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be a [x, y] cell pair")
    return (int(value[0]), int(value[1]))


def _school_footprint_min_depth(fp_bays_x: int, fp_bays_y: int, wing_depth: int) -> int:
    """Effective wing depth for school program (matches solver ``_place_school_academy``)."""
    return max(
        4,
        min(wing_depth if wing_depth else 5, min(fp_bays_x, fp_bays_y) // 2 or 4),
    )


def _validate_school_footprint(
    bays_x: int, bays_y: int, wing_depth: int
) -> Optional[str]:
    """Return error message when school cannot emit classroom_wing volumes."""
    depth = _school_footprint_min_depth(bays_x, bays_y, wing_depth)
    min_span = 2 * depth + 1
    if bays_x < min_span or bays_y < min_span:
        return (
            f"school footprint too small for wing_depth={depth}: "
            f"need bays_x and bays_y >= {min_span}, got {bays_x}x{bays_y}"
        )
    mid_h = bays_y - 2 * depth
    if mid_h < 2:
        return (
            f"school footprint cannot fit classroom wings: "
            f"mid_h={mid_h} < 2 (bays_y={bays_y}, depth={depth})"
        )
    return None


def _parse_footprint(raw: dict) -> FootprintSpec:
    kind = str(raw.get("kind", "rect"))
    if kind not in ("rect", "L", "U", "courtyard", "compound", "school"):
        raise ValueError(f"unknown footprint kind: {kind}")
    bays_x = int(raw["bays_x"])
    bays_y = int(raw["bays_y"])
    if bays_x < 1 or bays_y < 1:
        raise ValueError("bays_x and bays_y must be >= 1")
    wing_depth = int(raw.get("wing_depth", 2))
    courtyard = bool(raw.get("courtyard", kind == "courtyard"))
    if kind == "school":
        err = _validate_school_footprint(bays_x, bays_y, wing_depth)
        if err:
            raise ValueError(err)
    return FootprintSpec(
        kind=kind,
        bays_x=bays_x,
        bays_y=bays_y,
        wing_depth=wing_depth,
        courtyard=courtyard,
    )


def _parse_towers(raw: Any) -> List[TowerSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("towers must be a list")
    out: List[TowerSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("tower entries must be objects")
        attached = str(item.get("attached_to", "corner"))
        if attached not in ("wall", "corner"):
            raise ValueError(f"tower.attached_to must be wall|corner, got {attached}")
        out.append(
            TowerSpec(
                cell=_as_int_pair(item["cell"], "tower.cell"),
                storeys=int(item["storeys"]),
                attached_to=attached,
            )
        )
    return out


def _parse_roof(raw: Any) -> RoofSpec:
    if raw is None:
        return RoofSpec()
    if not isinstance(raw, dict):
        raise ValueError("roof must be an object")
    kind = str(raw.get("kind", "flat"))
    pitch = float(raw.get("pitch", 1.0))
    if kind not in SUPPORTED_ROOF_KINDS:
        supported = ", ".join(sorted(SUPPORTED_ROOF_KINDS))
        raise ValueError(f"unsupported roof kind '{kind}' — supported: {supported}")
    if not (ROOF_PITCH_MIN <= pitch <= ROOF_PITCH_MAX):
        raise ValueError(
            f"roof pitch {pitch} out of range [{ROOF_PITCH_MIN}, {ROOF_PITCH_MAX}]"
        )
    return RoofSpec(kind=kind, pitch=pitch)


def _parse_circulation(raw: Any) -> CirculationSpec:
    if raw is None:
        return CirculationSpec()
    if not isinstance(raw, dict):
        raise ValueError("circulation must be an object")
    cells_raw = raw.get("stair_cells") or []
    cells = [_as_int_pair(c, "stair_cells") for c in cells_raw]
    stair_kind = str(raw.get("stair_kind", "straight")).lower()
    if stair_kind not in SUPPORTED_STAIR_KINDS:
        supported = ", ".join(sorted(SUPPORTED_STAIR_KINDS))
        raise ValueError(
            f"unsupported stair_kind '{stair_kind}' — supported: {supported}"
        )
    return CirculationSpec(
        stair_kind=stair_kind,
        stair_cells=cells,
    )


def _parse_rooms(raw: Any) -> List[RoomSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("rooms must be a list")
    out: List[RoomSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("room entries must be objects")
        kind = str(item.get("kind", "")).lower()
        if kind not in ROOM_KINDS:
            kinds = ", ".join(sorted(ROOM_KINDS))
            raise ValueError(f"room.kind must be one of {kinds}, got {kind!r}")
        area_raw = item.get("area_bays")
        area_bays = None if area_raw is None else int(area_raw)
        out.append(
            RoomSpec(
                name=str(item.get("name", kind)),
                kind=kind,
                area_bays=area_bays,
                double_height=bool(item.get("double_height", False)),
            )
        )
    return out


def _parse_openings(raw: Any) -> OpeningPolicy:
    if raw is None:
        return OpeningPolicy()
    if not isinstance(raw, dict):
        raise ValueError("openings must be an object")
    windows_ground = raw.get("windows_ground")
    return OpeningPolicy(
        windows_per_bay=int(raw.get("windows_per_bay", 1)),
        doors_ground=int(raw.get("doors_ground", 1)),
        windows_ground=None if windows_ground is None else int(windows_ground),
        skip_ground_windows=bool(raw.get("skip_ground_windows", False)),
    )


def _parse_entrances(raw: Any) -> List[EntranceSpec]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("entrances must be a list")
    out: List[EntranceSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"entrances[{i}] must be an object")
        role = str(item.get("role", "")).lower()
        if role not in ENTRANCE_ROLES:
            known = ", ".join(sorted(ENTRANCE_ROLES))
            raise ValueError(f"entrances[{i}].role must be one of {known}, got {role!r}")
        facade_raw = item.get("facade")
        facade = None if facade_raw is None else str(facade_raw).lower()
        if facade is not None and facade not in ENTRANCE_FACADES:
            known = ", ".join(sorted(ENTRANCE_FACADES))
            raise ValueError(
                f"entrances[{i}].facade must be one of {known}, got {facade!r}"
            )
        bay_raw = item.get("bay")
        bay = None if bay_raw is None else int(bay_raw)
        if bay is not None and bay < 0:
            raise ValueError(f"entrances[{i}].bay must be >= 0")
        ensemble = bool(item.get("ensemble", False))
        storey_raw = item.get("storey", 0)
        storey = int(storey_raw)
        if storey < 0:
            raise ValueError(f"entrances[{i}].storey must be >= 0")
        if role == "upper_exterior":
            if "storey" not in item:
                storey = 1
            elif storey < 1:
                raise ValueError(
                    f"entrances[{i}].storey must be >= 1 for role upper_exterior"
                )
        out.append(
            EntranceSpec(
                role=role,
                facade=facade,
                bay=bay,
                ensemble=ensemble,
                storey=storey,
            )
        )
    return out


def load_spec(data: dict) -> Tuple[Optional[BuildingSpec], Report]:
    """Load BuildingSpec from LLM/UI JSON.

    Rejects any world-coordinate or centimetre placement fields (hard failure).
    """
    failures: List[Failure] = []
    if not isinstance(data, dict):
        failures.append(
            Failure(
                check="spec_type",
                message="BuildingSpec JSON must be an object",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    forbidden = _scan_forbidden_keys(data)
    if forbidden:
        for path in forbidden:
            failures.append(
                Failure(
                    check="spec_no_world_coords",
                    message=(
                        f"forbidden world/cm placement field at '{path}' — "
                        "specs use bays/cells only"
                    ),
                    world_xyz=None,
                )
            )
        return None, Report.from_failures(failures)

    try:
        footprint = _parse_footprint(data.get("footprint") or {})
        storeys = int(data["storeys"])
        if storeys < 1:
            raise ValueError("storeys must be >= 1")
        storey_use = list(data.get("storey_use") or [])
        if not storey_use:
            storey_use = ["hall"] * storeys
        while len(storey_use) < storeys:
            storey_use.append(storey_use[-1] if storey_use else "hall")
        building_class_raw = data.get("building_class")
        building_class: Optional[str] = None
        if building_class_raw is not None and str(building_class_raw).strip():
            building_class = str(building_class_raw).strip().lower()
            if building_class not in BUILDING_CLASSES:
                known = ", ".join(sorted(BUILDING_CLASSES))
                raise ValueError(
                    f"building_class must be one of {known}, got {building_class!r}"
                )
        spec = BuildingSpec(
            name=str(data.get("name", "unnamed")),
            style=str(data.get("style", "townhouse")),
            footprint=footprint,
            storeys=storeys,
            storey_use=storey_use[:storeys],
            towers=_parse_towers(data.get("towers")),
            roof=_parse_roof(data.get("roof")),
            circulation=_parse_circulation(data.get("circulation")),
            openings=_parse_openings(data.get("openings")),
            entrances=_parse_entrances(data.get("entrances")),
            seed=int(data.get("seed", 0)),
            ground_slab=bool(data.get("ground_slab", True)),
            rooms=_parse_rooms(data.get("rooms")),
            building_class=building_class,
        )
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(
            Failure(
                check="spec_parse",
                message=f"failed to parse BuildingSpec: {exc}",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    return spec, Report.from_failures([])


def load_spec_json(text: str) -> Tuple[Optional[BuildingSpec], Report]:
    """Parse a JSON string then load_spec."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="spec_json",
                    message=f"invalid JSON: {exc}",
                    world_xyz=None,
                )
            ]
        )
    return load_spec(data)


def load_style(style_id: str) -> Tuple[Optional[Dict[str, Any]], Report]:
    """Load a style preset from pae/styles/<id>.json via StylePack bridge."""
    from pae.style_pack import load_style_pack

    pack, report = load_style_pack(style_id)
    if pack is None:
        return None, report
    return pack.to_legacy_dict(), report


def m1_box_house_spec(*, seed: int = 1) -> BuildingSpec:
    """Factory for Milestone 1 — one-storey 4×3 box house.

    Intent only: 1 door, 2 windows, flat roof, ground slab.
    Assembly geometry is WP-5.
    """
    return BuildingSpec(
        name="m1_box_house",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=2,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        building_class="house",
    )


def m2_two_storey_stair_spec(*, seed: int = 2) -> BuildingSpec:
    """Factory for Milestone 2 — two-storey 4×3 box with straight stair.

    Solver auto-places a 2-module straight run; plan marks VOID above the
    stair top; assembly emits ``stair_straight`` + ``floor_hole``.
    Compact house typology — never wide/switchback.
    """
    return BuildingSpec(
        name="m2_two_storey_stair",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=2,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        building_class="house",
    )


def m2_two_storey_stair_dict(*, seed: int = 2) -> dict:
    """JSON-serialisable form of the M2 factory (for loader round-trips)."""
    spec = m2_two_storey_stair_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m1_box_house_dict(*, seed: int = 1) -> dict:
    """JSON-serialisable form of the M1 factory (for loader round-trips)."""
    spec = m1_box_house_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m3_keep_tower_spec(*, seed: int = 3) -> BuildingSpec:
    """Factory for Milestone 3 — keep with pitched roof + wall-attached round tower.

    Does not alter M1/M2 factories. Tower sits on the west wall (edge abut, not
    diagonal corner) so plan circulation stays 4-connected; arcs still share one
    cell (§2.2 centred exception).
    """
    return BuildingSpec(
        name="m3_keep_tower",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[TowerSpec(cell=(-1, 0), storeys=3, attached_to="wall")],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        seed=seed,
        ground_slab=True,
    )


def m3_keep_tower_dict(*, seed: int = 3) -> dict:
    """JSON-serialisable form of the M3 factory."""
    spec = m3_keep_tower_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [
            {
                "cell": list(t.cell),
                "storeys": t.storeys,
                "attached_to": t.attached_to,
            }
            for t in spec.towers
        ],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m11_hip_roof_spec(*, seed: int = 11) -> BuildingSpec:
    """Factory for Milestone 11 — 4×4 rect with four-slope hip roof (S-012)."""
    return BuildingSpec(
        name="m11_hip_roof",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=4),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="hip", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=2,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m11_hip_roof_dict(*, seed: int = 11) -> dict:
    """JSON-serialisable form of the M11 hip-roof factory."""
    spec = m11_hip_roof_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m_spiral_tower_spec(*, seed: int = 31) -> BuildingSpec:
    """Milestone 3.1 — keep + wall tower with helical spiral in the drum.

    Solver auto-places a single tower cell; assemble emits 4×
    ``stair_spiral_quarter`` per storey climb (yaw 0/90/180/270).
    """
    spec = m3_keep_tower_spec(seed=seed)
    return BuildingSpec(
        name="m_spiral_tower",
        style=spec.style,
        footprint=spec.footprint,
        storeys=spec.storeys,
        storey_use=list(spec.storey_use),
        towers=list(spec.towers),
        roof=spec.roof,
        circulation=CirculationSpec(stair_kind="spiral", stair_cells=[]),
        openings=spec.openings,
        seed=spec.seed,
        ground_slab=spec.ground_slab,
        building_class="tower",
    )


def m_spiral_tower_dict(*, seed: int = 31) -> dict:
    """JSON-serialisable form of the spiral tower factory."""
    spec = m_spiral_tower_spec(seed=seed)
    data = m3_keep_tower_dict(seed=seed)
    data["name"] = spec.name
    data["circulation"]["stair_kind"] = "spiral"
    return data


def m4_l_plan_spec(*, seed: int = 4) -> BuildingSpec:
    """Factory for Milestone 4 — L-shaped cloister wing (8×8, wing_depth=2).

    South bar + west leg; re-entrant inner face gets inhabited walls in assemble.
    """
    return BuildingSpec(
        name="m4_l_plan",
        style="townhouse",
        footprint=FootprintSpec(kind="L", bays_x=8, bays_y=8, wing_depth=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_u_plan_spec(*, seed: int = 5) -> BuildingSpec:
    """Factory for Milestone 4 — U-shaped plan (8×8, wing_depth=2).

    South bar + west/east legs; open court to the north (exterior, not courtyard role).
    """
    return BuildingSpec(
        name="m4_u_plan",
        style="townhouse",
        footprint=FootprintSpec(kind="U", bays_x=8, bays_y=8, wing_depth=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_courtyard_spec(*, seed: int = 6) -> BuildingSpec:
    """Factory for Milestone 4 — ring plan with open courtyard (8×8, wing_depth=2).

    Courtyard cells are outside the enclosed envelope; no roof/floor over the hole.
    """
    return BuildingSpec(
        name="m4_courtyard",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="courtyard", bays_x=8, bays_y=8, wing_depth=2, courtyard=True
        ),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
    )


def m4_l_plan_dict(*, seed: int = 4) -> dict:
    """JSON-serialisable form of the M4 L factory."""
    spec = m4_l_plan_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m4_u_plan_dict(*, seed: int = 5) -> dict:
    """JSON-serialisable form of the M4 U factory."""
    spec = m4_u_plan_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def m4_courtyard_dict(*, seed: int = 6) -> dict:
    """JSON-serialisable form of the M4 courtyard factory."""
    spec = m4_courtyard_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
    }


def school_academy_spec(*, seed: int = 70) -> BuildingSpec:
    """Giant academy massing — named hall / classroom wings / admin + courtyard.

    Uses footprint kind ``school`` (solver emits program roles). Default circulation
    is a switchback stairwell (2×2). Storey use biases classroom partitioning.
    """
    classroom_count = 8
    return BuildingSpec(
        name="school_academy",
        style="gothic_academy",
        footprint=FootprintSpec(
            kind="school",
            bays_x=16,
            bays_y=14,
            wing_depth=5,
            courtyard=True,
        ),
        storeys=3,
        storey_use=["classroom", "classroom", "classroom"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.05),
        circulation=CirculationSpec(stair_kind="switchback", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=2,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        rooms=[
            RoomSpec(name="great_hall", kind="hall", double_height=True),
            RoomSpec(
                name="classrooms",
                kind="classroom",
                area_bays=classroom_count,
            ),
        ],
        building_class="academy",
    )


def industrial_workshop_spec(*, seed: int = 80) -> BuildingSpec:
    """Multi-storey industrial hall — monumental stair well (wide default).

    Large footprint (≥4×4) so continuity-safe typology can place ``wide`` /
    ``switchback``. Compact ``straight`` is a typology mismatch when a 2×2 well
    fits.
    """
    return BuildingSpec(
        name="industrial_workshop",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=10, bays_y=8),
        storeys=3,
        storey_use=["hall", "hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="wide", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=2,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        building_class="industrial",
    )


def castle_curtain_wall_spec(
    name: str,
    length_bays: int,
    *,
    storeys: int = 2,
    depth_bays: int = 3,
    seed: int = 40,
) -> BuildingSpec:
    """Thin curtain-wall run — shallow bar, ``wall_plain`` envelope, no towers.

    Default ``depth_bays=3`` is the minimum depth the solver can stairserve for two
    storeys on a straight run. Trimmed with ``parapet_solid`` and ``battlement`` when
    built via :func:`pae.compound.build_castle_curtain_compound`.
    """
    return BuildingSpec(
        name=name,
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=length_bays, bays_y=depth_bays),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        seed=seed,
        ground_slab=True,
        building_class="castle",
    )


def castle_gatehouse_spec(*, seed: int = 41) -> BuildingSpec:
    """Twin-tower gate block with a south ``gate`` entrance (``wall_gate_arch``)."""
    return BuildingSpec(
        name="castle_gatehouse",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[
            TowerSpec(cell=(0, 0), storeys=3, attached_to="corner"),
            TowerSpec(cell=(3, 0), storeys=3, attached_to="corner"),
        ],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=0,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[EntranceSpec(role="gate", facade="south")],
        seed=seed,
        ground_slab=True,
    )


@dataclass(frozen=True)
class CastleBaileySpec:
    """Layout knobs for :func:`pae.compound.build_castle_curtain_compound`."""

    curtain_length_bays: int = 8
    curtain_storeys: int = 2
    gatehouse_seed: int = 41
    west_curtain_seed: int = 42
    east_curtain_seed: int = 43


def castle_bailey_spec() -> CastleBaileySpec:
    """Default inner-ward curtain + gatehouse preset (Phase 4.1–4.2 greybox)."""
    return CastleBaileySpec()


# ---------------------------------------------------------------------------
# Fortress / bailey campus (flat-ground compound massing)
# ---------------------------------------------------------------------------


def fortress_keep_spec(
    *,
    bays_x: int = 8,
    bays_y: int = 5,
    storeys: int = 3,
    seed: int = 50,
) -> BuildingSpec:
    """Central multi-storey hall/manor — steep gable, corner + wall towers.

    Composed for :func:`pae.compound.build_fortress_compound`. Towers at several
    heights; conical/needle spires come from keep trim (``spire_needle``).
    """
    bx = max(4, int(bays_x))
    by = max(3, int(bays_y))
    mid_y = by // 2
    return BuildingSpec(
        name="fortress_keep",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=bx, bays_y=by),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=[
            # Several heights; SW/SE on the court front, NW corner, west wall drum.
            TowerSpec(cell=(0, 0), storeys=3, attached_to="corner"),
            TowerSpec(cell=(bx - 1, 0), storeys=4, attached_to="corner"),
            TowerSpec(cell=(0, by - 1), storeys=3, attached_to="corner"),
            # Wall-attached on the west flank — keep the south court facade clear
            # for the main entrance (door existence fails if a drum owns that bay).
            TowerSpec(cell=(-1, mid_y), storeys=3, attached_to="wall"),
        ],
        roof=RoofSpec(kind="pitched", pitch=1.7),
        circulation=CirculationSpec(stair_kind="switchback", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        entrances=[EntranceSpec(role="main", facade="south", bay=2)],
        seed=seed,
        ground_slab=True,
        building_class="castle",
    )


def fortress_gatehouse_spec(*, seed: int = 51) -> BuildingSpec:
    """Twin-arch gatehouse — two south gate leaves + corner drum towers.

    Footprint matches :func:`castle_gatehouse_spec` (4×3, storeys=3 drums) so
    ``tower_hall_kiss`` stays green; twin ``gate`` bays give the double entrance.
    """
    return BuildingSpec(
        name="fortress_gatehouse",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[
            TowerSpec(cell=(0, 0), storeys=3, attached_to="corner"),
            TowerSpec(cell=(3, 0), storeys=3, attached_to="corner"),
        ],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=0,
            doors_ground=0,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="gate", facade="south", bay=1),
            EntranceSpec(role="gate", facade="south", bay=2),
        ],
        seed=seed,
        ground_slab=True,
        building_class="castle",
    )


def fortress_cloister_range_spec(
    name: str,
    bays_x: int,
    bays_y: int,
    *,
    storeys: int = 2,
    seed: int = 52,
) -> BuildingSpec:
    """Cloister / lodging range — arcade colonnade via compound cloister trim."""
    return BuildingSpec(
        name=name,
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=bays_x, bays_y=bays_y),
        storeys=storeys,
        storey_use=["hall"] * storeys,
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=1.25),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=seed,
        ground_slab=True,
        building_class="castle",
    )


def fortress_north_curtain_spec(
    length_bays: int,
    *,
    storeys: int = 2,
    depth_bays: int = 3,
    seed: int = 53,
) -> BuildingSpec:
    """North curtain closing the outer bailey — plain envelope, battlement trim."""
    return castle_curtain_wall_spec(
        "north_curtain",
        length_bays,
        storeys=storeys,
        depth_bays=depth_bays,
        seed=seed,
    )


@dataclass(frozen=True)
class FortressBaileySpec:
    """Layout knobs for :func:`pae.compound.build_fortress_compound`.

    Flat-ground nested bailey: south curtain+gate, west/east cloisters around an
    open court, north keep/manor, and a stepped approach causeway south of the gate.
    """

    court_bays_x: int = 8
    court_bays_y: int = 5
    range_depth: int = 3
    curtain_length_bays: int = 5
    curtain_storeys: int = 2
    approach_rows: int = 3
    approach_width_bays: int = 5
    keep_seed: int = 50
    gatehouse_seed: int = 51
    west_cloister_seed: int = 52
    east_cloister_seed: int = 54
    west_curtain_seed: int = 55
    east_curtain_seed: int = 56
    north_curtain_seed: int = 53


def fortress_bailey_compound_spec() -> FortressBaileySpec:
    """Default fortress / bailey campus preset (flat Z=0 compound massing)."""
    return FortressBaileySpec()


def m8_entrances_spec(*, seed: int = 8) -> BuildingSpec:
    """Factory for Milestone 8 — declarative entrance roles on south/north facades.

    Grand carriage arch on the south front; service postern on the north rear.
    When ``entrances`` is non-empty, legacy ``openings.doors_ground`` is ignored.
    """
    return BuildingSpec(
        name="m8_entrances",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=6, bays_y=5),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="grand", facade="south"),
            EntranceSpec(role="service", facade="north"),
        ],
        seed=seed,
        ground_slab=True,
    )


def m9_grand_ensemble_spec(*, seed: int = 9) -> BuildingSpec:
    """Milestone 9 — grand entrance ensemble (Phase 1.3 greybox stub).

    South ``grand`` entrance with ``ensemble=True`` expands to arch + steps +
    flanking columns (and twin interior stairs when feasible). Service door
    remains a plain leaf without ensemble expansion.
    """
    return BuildingSpec(
        name="m9_grand_ensemble",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=8, bays_y=6),
        storeys=2,
        storey_use=["hall", "hall"],
        towers=[],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(
            stair_kind="straight",
            # Keep the hall stair off the south grand bay so twin ensemble
            # flights can occupy the inward flanks (Phase 1.3).
            stair_cells=[(6, 3), (6, 4)],
        ),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=True,
        ),
        entrances=[
            EntranceSpec(role="grand", facade="south", ensemble=True),
            EntranceSpec(role="service", facade="north", ensemble=False),
        ],
        seed=seed,
        ground_slab=True,
    )


def school_academy_dict(*, seed: int = 70) -> dict:
    """JSON-serialisable form of the school academy factory."""
    spec = school_academy_spec(seed=seed)
    return {
        "name": spec.name,
        "style": spec.style,
        "footprint": {
            "kind": spec.footprint.kind,
            "bays_x": spec.footprint.bays_x,
            "bays_y": spec.footprint.bays_y,
            "wing_depth": spec.footprint.wing_depth,
            "courtyard": spec.footprint.courtyard,
        },
        "storeys": spec.storeys,
        "storey_use": list(spec.storey_use),
        "towers": [],
        "roof": {"kind": spec.roof.kind, "pitch": spec.roof.pitch},
        "circulation": {
            "stair_kind": spec.circulation.stair_kind,
            "stair_cells": [],
        },
        "openings": {
            "windows_per_bay": spec.openings.windows_per_bay,
            "doors_ground": spec.openings.doors_ground,
            "windows_ground": spec.openings.windows_ground,
            "skip_ground_windows": spec.openings.skip_ground_windows,
        },
        "seed": spec.seed,
        "ground_slab": spec.ground_slab,
        "rooms": [
            {
                "name": r.name,
                "kind": r.kind,
                "area_bays": r.area_bays,
                "double_height": r.double_height,
            }
            for r in spec.rooms
        ],
    }

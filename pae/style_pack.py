"""StylePack loader and resolution (S-001..S-011+ hooks).

Resolution order (deterministic): engine defaults → style pack (with optional
``extends`` chain) → per-call overrides.

S-007 piece substitution and S-011 steep-pitch roof hints live here; assembly
consumes ``resolve_roof_pitch`` / ``resolve_roof_kind`` / ``resolve_piece_id``
without re-parsing JSON.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

from pae.contract import FLOOR_T_CM
from pae.report import Failure, Report
from pae.spec import ROOF_PITCH_MAX, ROOF_PITCH_MIN, STEEP_PITCH_MIN

_STYLES_DIR = Path(__file__).resolve().parent / "styles"


class StylePackError(ValueError):
    """Fail-closed style schema / inheritance error.

    ``check`` mirrors Report failure codes: ``style_schema`` | ``style_extends`` |
    ``style_missing`` | ``style_load``.
    """

    def __init__(self, message: str, *, check: str = "style_schema") -> None:
        super().__init__(message)
        self.check = check


def styles_dir(override: Optional[Path] = None) -> Path:
    """Resolved styles directory (tests pass *override* instead of monkeypatch)."""
    return Path(override) if override is not None else _STYLES_DIR

_TOP_LEVEL_KEYS: FrozenSet[str] = frozenset(
    {
        "id",
        "extends",
        "geometry",
        "window",
        "door",
        "materials",
        "wall_bands",
        "tower",
        "roof",
        "substitutions",
        # legacy flat alias accepted during load
        "roof_pitch",
    }
)
_GEOMETRY_KEYS: FrozenSet[str] = frozenset(
    {"roof_pitch", "storey_height_cm", "wall_thickness_cm"}
)
_WINDOW_KEYS: FrozenSet[str] = frozenset({"tag", "per_bay", "skip_ground"})
_DOOR_KEYS: FrozenSet[str] = frozenset({"tag"})
_MATERIALS_KEYS: FrozenSet[str] = frozenset({"wall", "roof", "trim"})
_WALL_BANDS_KEYS: FrozenSet[str] = frozenset({"plinth_cm", "cornice_cm"})
_TOWER_KEYS: FrozenSet[str] = frozenset({"cap", "crown", "finial"})
_ROOF_KEYS: FrozenSet[str] = frozenset(
    {"pitch_min", "pitch_max", "steep_silhouette", "kind_default"}
)

_SUPPORTED_ROOF_KIND_DEFAULTS: Dict[str, str] = {
    "flat": "roof_flat",
    "pitched": "roof_pitched_slope",
    "hip": "roof_hip",
}


def _reject_unknown_keys(
    data: Mapping[str, Any],
    allowed: FrozenSet[str],
    *,
    section: str,
) -> Optional[str]:
    unknown = sorted(k for k in data if k not in allowed)
    if unknown:
        return f"{section}: unknown key(s): {', '.join(unknown)}"
    return None


def _raise_schema(message: str) -> None:
    raise StylePackError(message, check="style_schema")


@dataclass(frozen=True)
class GeometryHints:
    roof_pitch: float = 1.0
    storey_height_cm: Optional[float] = None
    wall_thickness_cm: Optional[float] = None


@dataclass(frozen=True)
class WindowPolicy:
    tag: str = "window_plain"
    per_bay: int = 1
    skip_ground: bool = False


@dataclass(frozen=True)
class DoorPolicy:
    tag: str = "door_plain"


@dataclass(frozen=True)
class MaterialsHints:
    wall: str = "brick_red"
    roof: str = "tile_terracotta"
    trim: str = "stone_light"


@dataclass(frozen=True)
class WallBands:
    plinth_cm: float = FLOOR_T_CM
    cornice_cm: float = 20.0


@dataclass(frozen=True)
class TowerHints:
    cap: str = "flat"
    crown: bool = False
    finial: bool = False


@dataclass(frozen=True)
class RoofHints:
    """S-011 steep silhouette and roof-kind defaults (style-level, not spec)."""

    pitch_min: Optional[float] = None
    pitch_max: Optional[float] = None
    steep_silhouette: bool = False
    kind_default: Optional[str] = None


@dataclass(frozen=True)
class StylePack:
    """Declarative style preset — geometry, openings, materials, substitutions."""

    id: str
    geometry: GeometryHints = field(default_factory=GeometryHints)
    window: WindowPolicy = field(default_factory=WindowPolicy)
    door: DoorPolicy = field(default_factory=DoorPolicy)
    materials: MaterialsHints = field(default_factory=MaterialsHints)
    wall_bands: WallBands = field(default_factory=WallBands)
    tower: TowerHints = field(default_factory=TowerHints)
    roof: RoofHints = field(default_factory=RoofHints)
    substitutions: Dict[str, str] = field(default_factory=dict)
    extends: Optional[str] = None

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Shape expected by assemble / pipeline (backward-compatible dict)."""
        return {
            "id": self.id,
            "roof_pitch": self.geometry.roof_pitch,
            "window": {
                "tag": self.window.tag,
                "per_bay": self.window.per_bay,
                "skip_ground": self.window.skip_ground,
            },
            "door": {"tag": self.door.tag},
            "wall_bands": {
                "plinth_cm": self.wall_bands.plinth_cm,
                "cornice_cm": self.wall_bands.cornice_cm,
            },
            "tower": {
                "cap": self.tower.cap,
                "crown": self.tower.crown,
                "finial": self.tower.finial,
            },
            "materials": {
                "wall": self.materials.wall,
                "roof": self.materials.roof,
                "trim": self.materials.trim,
            },
            "roof": asdict(self.roof),
            "substitutions": dict(self.substitutions),
            "geometry": asdict(self.geometry),
        }

    def resolve(self, overrides: Optional[Mapping[str, Any]] = None) -> "StylePack":
        """Re-resolve this pack id then apply optional per-call overrides."""
        try:
            resolved = resolve_style_pack(self.id)
        except StylePackError:
            resolved = None
        except ValueError:
            resolved = None
        if resolved is None:
            resolved = ENGINE_DEFAULTS
        if not overrides:
            return resolved
        return _apply_overrides(resolved, overrides)


ENGINE_DEFAULTS = StylePack(id="__engine__")


def _rebuild_pack(pack: StylePack, *, style_id: Optional[str] = None, **changes: Any) -> StylePack:
    return StylePack(
        id=style_id if style_id is not None else pack.id,
        geometry=changes.get("geometry", pack.geometry),
        window=changes.get("window", pack.window),
        door=changes.get("door", pack.door),
        materials=changes.get("materials", pack.materials),
        wall_bands=changes.get("wall_bands", pack.wall_bands),
        tower=changes.get("tower", pack.tower),
        roof=changes.get("roof", pack.roof),
        substitutions=changes.get("substitutions", pack.substitutions),
        extends=changes.get("extends", pack.extends),
    )


def _overlay_from_raw(base: StylePack, raw: Mapping[str, Any], *, style_id: str) -> StylePack:
    """Apply only keys present in *raw* JSON onto *base* (inheritance-friendly)."""
    pack = base
    if "geometry" in raw or "roof_pitch" in raw:
        geom_raw: Dict[str, Any] = {}
        if isinstance(raw.get("geometry"), dict):
            geom_raw.update(raw["geometry"])
        if "roof_pitch" in raw:
            geom_raw["roof_pitch"] = raw["roof_pitch"]
        geometry, err = _parse_section(
            geom_raw,
            GeometryHints,
            _GEOMETRY_KEYS,
            section="geometry",
            defaults=pack.geometry,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, geometry=geometry)

    if "window" in raw:
        window, err = _parse_section(
            raw.get("window"),
            WindowPolicy,
            _WINDOW_KEYS,
            section="window",
            defaults=pack.window,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, window=window)

    if "door" in raw:
        door, err = _parse_section(
            raw.get("door"),
            DoorPolicy,
            _DOOR_KEYS,
            section="door",
            defaults=pack.door,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, door=door)

    if "materials" in raw:
        materials, err = _parse_section(
            raw.get("materials"),
            MaterialsHints,
            _MATERIALS_KEYS,
            section="materials",
            defaults=pack.materials,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, materials=materials)

    if "wall_bands" in raw:
        wall_bands, err = _parse_section(
            raw.get("wall_bands"),
            WallBands,
            _WALL_BANDS_KEYS,
            section="wall_bands",
            defaults=pack.wall_bands,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, wall_bands=wall_bands)

    if "tower" in raw:
        tower, err = _parse_section(
            raw.get("tower"),
            TowerHints,
            _TOWER_KEYS,
            section="tower",
            defaults=pack.tower,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, tower=tower)

    if "roof" in raw:
        roof, err = _parse_section(
            raw.get("roof"),
            RoofHints,
            _ROOF_KEYS,
            section="roof",
            defaults=pack.roof,
        )
        if err:
            _raise_schema(err)
        pack = _rebuild_pack(pack, style_id=style_id, roof=roof)

    if "substitutions" in raw:
        raw_subs = raw.get("substitutions")
        if not isinstance(raw_subs, dict):
            _raise_schema("substitutions: expected object")
        subs = dict(pack.substitutions)
        for key, value in raw_subs.items():
            if not isinstance(key, str) or not isinstance(value, str):
                _raise_schema("substitutions: keys and values must be strings")
            subs[key] = value
        pack = _rebuild_pack(pack, style_id=style_id, substitutions=subs)

    if pack.id != style_id:
        pack = _rebuild_pack(pack, style_id=style_id)
    return pack


def _apply_overrides(pack: StylePack, overrides: Mapping[str, Any]) -> StylePack:
    err = _reject_unknown_keys(overrides, _TOP_LEVEL_KEYS - {"extends"}, section="overrides")
    if err:
        _raise_schema(err)
    return _overlay_from_raw(pack, overrides, style_id=pack.id)


def _parse_section(
    data: Optional[Mapping[str, Any]],
    cls: type,
    allowed: FrozenSet[str],
    *,
    section: str,
    defaults: Any,
) -> Tuple[Any, Optional[str]]:
    if data is None:
        return defaults, None
    if not isinstance(data, dict):
        return defaults, f"{section}: expected object"
    err = _reject_unknown_keys(data, allowed, section=section)
    if err:
        return defaults, err
    merged = {**asdict(defaults), **data}
    return cls(**merged), None


def _roof_hints_from_mapping(style: Mapping[str, Any]) -> RoofHints:
    roof_raw = style.get("roof")
    if not isinstance(roof_raw, dict):
        return RoofHints()
    merged = {**asdict(RoofHints()), **roof_raw}
    return RoofHints(**{k: merged[k] for k in asdict(RoofHints())})


def _geometry_pitch_from_mapping(style: Mapping[str, Any]) -> float:
    geom = style.get("geometry")
    if isinstance(geom, dict) and "roof_pitch" in geom:
        return float(geom["roof_pitch"])
    if "roof_pitch" in style:
        return float(style["roof_pitch"])
    return ENGINE_DEFAULTS.geometry.roof_pitch


def resolve_roof_pitch(
    style: StylePack | Mapping[str, Any],
    *,
    spec_pitch: Optional[float] = None,
) -> float:
    """S-011 hook — merge spec pitch with style geometry and roof hint clamps."""
    if isinstance(style, StylePack):
        geom_pitch = style.geometry.roof_pitch
        roof = style.roof
    elif isinstance(style, dict):
        geom_pitch = _geometry_pitch_from_mapping(style)
        roof = _roof_hints_from_mapping(style)
    else:
        geom_pitch = ENGINE_DEFAULTS.geometry.roof_pitch
        roof = RoofHints()

    pitch = geom_pitch if spec_pitch is None else float(spec_pitch)
    pitch_min = roof.pitch_min
    if roof.steep_silhouette and pitch_min is None:
        pitch_min = STEEP_PITCH_MIN
    if pitch_min is not None:
        pitch = max(pitch, pitch_min)
    if roof.pitch_max is not None:
        pitch = min(pitch, roof.pitch_max)
    return max(ROOF_PITCH_MIN, min(ROOF_PITCH_MAX, pitch))


# Concrete roof kinds assemblers place (excludes ``auto``).
_CONCRETE_ROOF_KINDS: Tuple[str, ...] = ("flat", "pitched", "hip")


def resolve_roof_kind(
    style: StylePack | Mapping[str, Any],
    *,
    spec_kind: Optional[str] = None,
) -> str:
    """S-011…S-021 hook — style ``kind_default`` fills in when spec is open.

    Explicit ``flat`` / ``pitched`` / ``hip`` always win. ``None`` or ``\"auto\"``
    selects style ``RoofHints.kind_default``, else ``flat``.
    """
    if isinstance(style, StylePack):
        roof = style.roof
    elif isinstance(style, dict):
        roof = _roof_hints_from_mapping(style)
    else:
        roof = RoofHints()

    if spec_kind is not None and spec_kind not in ("", "auto"):
        kind = str(spec_kind).lower()
        if kind not in _CONCRETE_ROOF_KINDS:
            supported = ", ".join(_CONCRETE_ROOF_KINDS)
            raise ValueError(
                f"unsupported roof kind '{kind}' — supported: {supported}, auto"
            )
        return kind

    default = roof.kind_default
    if isinstance(default, str) and default.lower() in _CONCRETE_ROOF_KINDS:
        return default.lower()
    return "flat"


def choose_roof_kind(
    style: StylePack | Mapping[str, Any],
    *,
    seed: int = 0,
    spec_kind: Optional[str] = None,
    choices: Optional[Sequence[str]] = None,
    key: str = "roof_kind",
) -> str:
    """Seed-stable roof kind for variation (flat / pitched / hip).

    Explicit spec kinds win. With ``auto`` / ``None``, uses style ``kind_default``
    when set; otherwise picks from *choices* (default all concrete kinds) by seed.
    """
    if spec_kind is not None and spec_kind not in ("", "auto"):
        return resolve_roof_kind(style, spec_kind=spec_kind)

    if isinstance(style, StylePack):
        roof = style.roof
    elif isinstance(style, dict):
        roof = _roof_hints_from_mapping(style)
    else:
        roof = RoofHints()
    if isinstance(roof.kind_default, str) and roof.kind_default.lower() in _CONCRETE_ROOF_KINDS:
        return roof.kind_default.lower()

    pool = tuple(
        c.lower()
        for c in (choices if choices is not None else _CONCRETE_ROOF_KINDS)
        if str(c).lower() in _CONCRETE_ROOF_KINDS
    )
    if not pool:
        pool = _CONCRETE_ROOF_KINDS
    rng = random.Random(f"{seed}:{key}")
    return rng.choice(pool)


def is_steep_silhouette_style(style: StylePack | Mapping[str, Any]) -> bool:
    """True when the style pack targets S-011 steep anime-fantasy read."""
    if isinstance(style, StylePack):
        roof = style.roof
        pitch = style.geometry.roof_pitch
    elif isinstance(style, dict):
        roof = _roof_hints_from_mapping(style)
        pitch = _geometry_pitch_from_mapping(style)
    else:
        return False
    if roof.steep_silhouette:
        return True
    floor = roof.pitch_min if roof.pitch_min is not None else STEEP_PITCH_MIN
    return pitch >= floor


def _parse_style_dict(
    data: Mapping[str, Any],
    *,
    style_id: str,
) -> Tuple[Optional[StylePack], Optional[str]]:
    err = _reject_unknown_keys(data, _TOP_LEVEL_KEYS, section="style")
    if err:
        return None, err

    pack_id = str(data.get("id", style_id))
    if pack_id != style_id:
        return None, f"style id mismatch: expected {style_id!r}, got {pack_id!r}"

    geom_raw: Dict[str, Any] = {}
    if isinstance(data.get("geometry"), dict):
        geom_raw.update(data["geometry"])
    if "roof_pitch" in data:
        geom_raw["roof_pitch"] = data["roof_pitch"]

    geometry, err = _parse_section(
        geom_raw or None,
        GeometryHints,
        _GEOMETRY_KEYS,
        section="geometry",
        defaults=ENGINE_DEFAULTS.geometry,
    )
    if err:
        return None, err

    window, err = _parse_section(
        data.get("window"),
        WindowPolicy,
        _WINDOW_KEYS,
        section="window",
        defaults=ENGINE_DEFAULTS.window,
    )
    if err:
        return None, err

    door, err = _parse_section(
        data.get("door"),
        DoorPolicy,
        _DOOR_KEYS,
        section="door",
        defaults=ENGINE_DEFAULTS.door,
    )
    if err:
        return None, err

    materials, err = _parse_section(
        data.get("materials"),
        MaterialsHints,
        _MATERIALS_KEYS,
        section="materials",
        defaults=ENGINE_DEFAULTS.materials,
    )
    if err:
        return None, err

    wall_bands, err = _parse_section(
        data.get("wall_bands"),
        WallBands,
        _WALL_BANDS_KEYS,
        section="wall_bands",
        defaults=ENGINE_DEFAULTS.wall_bands,
    )
    if err:
        return None, err

    tower, err = _parse_section(
        data.get("tower"),
        TowerHints,
        _TOWER_KEYS,
        section="tower",
        defaults=ENGINE_DEFAULTS.tower,
    )
    if err:
        return None, err

    roof, err = _parse_section(
        data.get("roof"),
        RoofHints,
        _ROOF_KEYS,
        section="roof",
        defaults=ENGINE_DEFAULTS.roof,
    )
    if err:
        return None, err

    substitutions: Dict[str, str] = {}
    raw_subs = data.get("substitutions")
    if raw_subs is not None:
        if not isinstance(raw_subs, dict):
            return None, "substitutions: expected object"
        for key, value in raw_subs.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return None, "substitutions: keys and values must be strings"
            substitutions[key] = value

    extends = data.get("extends")
    if extends is not None and not isinstance(extends, str):
        return None, "extends: expected string"

    return (
        StylePack(
            id=pack_id,
            geometry=geometry,
            window=window,
            door=door,
            materials=materials,
            wall_bands=wall_bands,
            tower=tower,
            roof=roof,
            substitutions=substitutions,
            extends=extends,
        ),
        None,
    )


def _load_raw_json(
    style_id: str,
    *,
    styles_dir_path: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Report]:
    path = styles_dir(styles_dir_path) / f"{style_id}.json"
    if not path.is_file():
        return None, Report.from_failures(
            [
                Failure(
                    check="style_missing",
                    message=f"style preset not found: {style_id}",
                    world_xyz=None,
                )
            ]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="style_load",
                    message=f"failed to load style {style_id}: {exc}",
                    world_xyz=None,
                )
            ]
        )
    if not isinstance(data, dict):
        return None, Report.from_failures(
            [
                Failure(
                    check="style_load",
                    message=f"style {style_id}: root must be an object",
                    world_xyz=None,
                )
            ]
        )
    return data, Report.from_failures([])


def _resolve_with_extends(
    raw: Mapping[str, Any],
    pack: StylePack,
    *,
    chain: Tuple[str, ...] = (),
    styles_dir_path: Optional[Path] = None,
) -> StylePack:
    if not pack.extends:
        return _overlay_from_raw(ENGINE_DEFAULTS, raw, style_id=pack.id)
    parent_id = pack.extends
    if parent_id in chain:
        cycle = " → ".join((*chain, parent_id))
        raise StylePackError(f"style inheritance cycle: {cycle}", check="style_extends")
    parent = resolve_style_pack(
        parent_id,
        _chain=(*chain, pack.id),
        styles_dir_path=styles_dir_path,
    )
    if parent is None:
        raise StylePackError(
            f"style extends unknown parent: {parent_id!r}",
            check="style_extends",
        )
    return _overlay_from_raw(parent, raw, style_id=pack.id)


def resolve_style_pack(
    style_id: str,
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    _chain: Tuple[str, ...] = (),
    styles_dir_path: Optional[Path] = None,
) -> Optional[StylePack]:
    """Load and fully resolve a style pack (engine → extends chain → pack).

    Inheritance cycles raise ``StylePackError`` (caught by ``load_style_pack`` as
    ``style_extends``). Schema errors on a parent raise ``StylePackError``.
    Missing presets return ``None``.
    """
    if style_id in _chain:
        cycle = " → ".join((*_chain, style_id))
        raise StylePackError(f"style inheritance cycle: {cycle}", check="style_extends")
    data, report = _load_raw_json(style_id, styles_dir_path=styles_dir_path)
    if data is None or not report.ok:
        return None
    pack, err = _parse_style_dict(data, style_id=style_id)
    if err or pack is None:
        raise StylePackError(err or "style parse failed", check="style_schema")
    resolved = _resolve_with_extends(
        data, pack, chain=_chain, styles_dir_path=styles_dir_path
    )
    if overrides:
        resolved = _apply_overrides(resolved, overrides)
    return resolved


def load_style_pack(
    style_id: str,
    *,
    styles_dir_path: Optional[Path] = None,
) -> Tuple[Optional[StylePack], Report]:
    """Load a style preset from ``pae/styles/<id>.json`` with schema validation.

    Unknown top-level / nested keys → ``style_schema`` (fail-closed).
    Broken ``extends`` chains / cycles → ``style_extends`` (fail-closed).

    Pass ``styles_dir_path`` from tests instead of monkeypatching ``_STYLES_DIR``.
    """
    data, report = _load_raw_json(style_id, styles_dir_path=styles_dir_path)
    if data is None:
        return None, report
    pack, err = _parse_style_dict(data, style_id=style_id)
    if err:
        return None, Report.from_failures(
            [
                Failure(
                    check="style_schema",
                    message=err,
                    world_xyz=None,
                    critical=True,
                )
            ]
        )
    assert pack is not None
    try:
        resolved = _resolve_with_extends(
            data, pack, styles_dir_path=styles_dir_path
        )
    except StylePackError as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check=exc.check,
                    message=str(exc),
                    world_xyz=None,
                    critical=True,
                )
            ]
        )
    except ValueError as exc:
        # Legacy callers / nested ValueError — still fail-closed as extends.
        return None, Report.from_failures(
            [
                Failure(
                    check="style_extends",
                    message=str(exc),
                    world_xyz=None,
                    critical=True,
                )
            ]
        )
    return resolved, Report.from_failures([])


# Built-in piece tag → asset id fallbacks (engine default substitution layer).
_BUILTIN_SUBSTITUTIONS: Dict[str, str] = {
    "window_plain": "wall_window",
    "window_simple": "wall_window",
    "window_gothic": "wall_window_lancet",
    "window_lancet": "wall_window_lancet",
    "window_gothic_traceried": "wall_window_gothic_traceried",
    "window_mullioned": "wall_window_mullioned",
    "window_round": "wall_window_round",
    "window_oculus": "wall_window_oculus",
    "window_clerestory": "wall_window_clerestory",
    "window_bay_wide": "wall_window_bay_wide",
    "window_arrowslit": "wall_arrowslit",
    "arrowslit": "wall_arrowslit",
    "door_plain": "wall_door",
    "door_gothic": "wall_door_gothic",
    "roof_flat": "roof_flat",
    "roof_pitched_slope": "roof_pitched_slope",
    "roof_gable_infill": "roof_gable_infill",
    "roof_hip": "roof_hip",
    "band_course": "band_course",
    "band_pilaster": "band_pilaster",
}


def _default_tag_for_role(style: Optional[Mapping[str, Any]], role: str) -> str:
    role = role.lower()
    if role == "window":
        if style and isinstance(style.get("window"), dict):
            return str(style["window"].get("tag") or "window_plain")
        return "window_plain"
    if role == "door":
        if style and isinstance(style.get("door"), dict) and style["door"].get("tag"):
            return str(style["door"]["tag"])
        win = style.get("window") if style else None
        win_tag = str(win.get("tag") or "") if isinstance(win, dict) else ""
        if "gothic" in win_tag.lower() or "lancet" in win_tag.lower():
            return "door_gothic"
        return "door_plain"
    if role == "roof":
        roof_raw = style.get("roof") if style else None
        kind = None
        if isinstance(roof_raw, dict):
            kind = roof_raw.get("kind_default")
        if isinstance(kind, str) and kind in _SUPPORTED_ROOF_KIND_DEFAULTS:
            return _SUPPORTED_ROOF_KIND_DEFAULTS[kind]
        return "roof_pitched_slope"
    if role == "band":
        return "band_course"
    return "door_plain"


def resolve_piece_id(
    style: Optional[Mapping[str, Any]],
    *,
    role: str,
    tag: Optional[str] = None,
) -> str:
    """Resolve a style tag to a catalog piece id (deterministic).

    Supports aperture roles (window/door) and structural roles (roof/band).
    Style ``substitutions`` map style tags to catalog ids for any role.
    """
    role = role.lower()
    if tag is None:
        tag = _default_tag_for_role(style if isinstance(style, dict) else None, role)
    tag_key = tag.lower()

    if isinstance(style, dict):
        subs = style.get("substitutions")
        if isinstance(subs, dict):
            hit = subs.get(tag_key) or subs.get(tag)
            if isinstance(hit, str):
                return hit

    builtin = _BUILTIN_SUBSTITUTIONS.get(tag_key)
    if builtin:
        return builtin
    if role == "roof":
        return tag_key if tag_key.startswith("roof_") else "roof_pitched_slope"
    if role == "band":
        return tag_key if tag_key.startswith("band_") else "band_course"
    if role == "window":
        return "wall_window"
    return "wall_door"

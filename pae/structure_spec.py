"""Structure + LevelSpec authoring — Master Plan Stage A/B + YAML §3.1.

Replaces the old ``footprint + storeys:int`` surface with:

    Structure = foundation mask + ordered levels + style + seed
    LevelSpec = sketch + height_units + program + wall_style?

Foundation is identity: two touching masses on one foundation are one structure
(one stair core). Upper levels may omit cells. Level Z = sum of ``height_units``
below — routed through ``storey_datum_z_cm(..., height_units=..., storey_cm=...)``.
Per-pack ``geometry.storey_height_cm`` (Stage I) supplies ``storey_cm``; default is
contract ``STOREY_CM`` when the pack omits it.

Compatibility: ``structure_to_building_spec`` flattens into the existing
``BuildingSpec`` path so m1–m4 / fortress factories keep working.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from pae.contract import MODULE_CM
from pae.report import Failure, Report
from pae.sketch import (
    BUILT_ROLES,
    SketchError,
    built_cells,
    parse_sketch,
    rect_cover,
)

Cell = Tuple[int, int]
ProgramRegion = Tuple[int, int, int, int]  # x0, y0, x1, y1 inclusive


def _connected_components(cells: Set[Cell]) -> List[Set[Cell]]:
    """4-connected components — used to turn sketch program paint into rectangles."""
    remaining = set(cells)
    out: List[Set[Cell]] = []
    while remaining:
        start = min(remaining)
        remaining.discard(start)
        comp: Set[Cell] = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in remaining:
                    remaining.discard(n)
                    comp.add(n)
                    stack.append(n)
        out.append(comp)
    return out


@dataclass
class LevelSpec:
    """One level in a structure stack (Master Plan §3.1)."""

    sketch: str
    height_units: int = 1
    program: Dict[str, List[ProgramRegion]] = field(default_factory=dict)
    wall_style: Optional[str] = None
    #: Optional per-level window shape override (Stage H) — lancet, round, oculus, …
    window_tag: Optional[str] = None
    #: Parsed once; rebuilt from sketch when empty.
    marks: Dict[str, Set[Cell]] = field(default_factory=dict)

    def ensure_marks(self) -> Dict[str, Set[Cell]]:
        if not self.marks:
            self.marks = parse_sketch(self.sketch)
        return self.marks

    def built(self) -> Set[Cell]:
        return built_cells(self.ensure_marks())

    def void_cells(self) -> Set[Cell]:
        """Open-to-below / courtyard marks (``.`` in the sketch legend)."""
        return set(self.ensure_marks().get("open", set()))

    def stair_cells(self) -> List[Cell]:
        return sorted(self.ensure_marks().get("stair", set()))

    def entrance_cells(self) -> List[Cell]:
        return sorted(self.ensure_marks().get("entrance", set()))

    def tower_cells(self) -> List[Cell]:
        return sorted(self.ensure_marks().get("tower", set()))

    def arcade_cells(self) -> Set[Cell]:
        """Cells marked ``A`` — walkable arcade gallery bays (Stage G)."""
        return set(self.ensure_marks().get("arcade", set()))

    def program_from_sketch(self) -> Dict[str, List[ProgramRegion]]:
        """Derive program rectangles from sketch letters H/C/V/R/A (Stage G).

        Each contiguous 4-connected component of a program mark becomes one
        inclusive bbox rectangle. Explicit ``program:`` YAML entries still win
        on merge (caller decides).
        """
        from pae.sketch import PROGRAM_SKETCH_ROLES

        marks = self.ensure_marks()
        out: Dict[str, List[ProgramRegion]] = {}
        for role in sorted(PROGRAM_SKETCH_ROLES):
            cells = set(marks.get(role, set()))
            if not cells:
                continue
            for component in _connected_components(cells):
                xs = [c[0] for c in component]
                ys = [c[1] for c in component]
                out.setdefault(role, []).append(
                    (min(xs), min(ys), max(xs), max(ys))
                )
        return out

    def to_dict(self) -> dict:
        out: Dict[str, Any] = {
            "height_units": int(self.height_units),
            "sketch": self.sketch if self.sketch.endswith("\n") else self.sketch + "\n",
        }
        if self.program:
            out["program"] = {
                k: [[[r[0], r[1]], [r[2], r[3]]] for r in v]
                for k, v in self.program.items()
            }
        if self.wall_style:
            out["wall_style"] = self.wall_style
        if self.window_tag:
            out["window_tag"] = self.window_tag
        return out


@dataclass
class StructureSpec:
    """One building — foundation identity + level stack (Master Plan Stage A/B)."""

    name: str
    style: str
    levels: List[LevelSpec]
    seed: int = 0
    unit_cm: Optional[float] = None
    foundation_sketch: Optional[str] = None
    foundation_cells: Tuple[Cell, ...] = ()
    structure_id: Optional[str] = None
    roof_kind: str = "pitched"
    roof_pitch: float = 1.0
    stair_kind: str = "straight"
    ground_slab: bool = True
    building_class: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("StructureSpec requires at least one level")
        for i, lv in enumerate(self.levels):
            if int(lv.height_units) < 1:
                raise ValueError(f"levels[{i}].height_units must be >= 1")
        if not self.structure_id:
            self.structure_id = self.name

    def resolved_foundation_cells(self) -> Set[Cell]:
        """Declared foundation, or union of all level built cells."""
        if self.foundation_cells:
            return set(self.foundation_cells)
        if self.foundation_sketch and self.foundation_sketch.strip():
            marks = parse_sketch(self.foundation_sketch)
            return built_cells(marks)
        cells: Set[Cell] = set()
        for lv in self.levels:
            cells |= lv.built()
        return cells

    def level_height_units(self) -> Tuple[int, ...]:
        return tuple(int(lv.height_units) for lv in self.levels)

    def level_built_cells(self) -> Tuple[Tuple[Cell, ...], ...]:
        return tuple(tuple(sorted(lv.built())) for lv in self.levels)

    def level_void_cells(self) -> Tuple[Tuple[Cell, ...], ...]:
        return tuple(tuple(sorted(lv.void_cells())) for lv in self.levels)

    def to_dict(self) -> dict:
        out: Dict[str, Any] = {
            "name": self.name,
            "style": self.style,
            "seed": int(self.seed),
            "levels": [lv.to_dict() for lv in self.levels],
        }
        if self.unit_cm is not None:
            out["unit_cm"] = float(self.unit_cm)
        if self.foundation_sketch and self.foundation_sketch.strip():
            sk = self.foundation_sketch
            out["foundation"] = sk if sk.endswith("\n") else sk + "\n"
        elif self.foundation_cells:
            # Emit a compact sketch when only cells were provided.
            out["foundation"] = _cells_to_sketch(set(self.foundation_cells))
            x0 = min(c[0] for c in self.foundation_cells)
            y0 = min(c[1] for c in self.foundation_cells)
            if (x0, y0) != (0, 0):
                out["foundation_origin"] = [x0, y0]
        if self.structure_id and self.structure_id != self.name:
            out["structure_id"] = self.structure_id
        if self.roof_kind != "pitched" or self.roof_pitch != 1.0:
            out["roof"] = {"kind": self.roof_kind, "pitch": self.roof_pitch}
        if self.stair_kind != "straight":
            out["circulation"] = {"stair_kind": self.stair_kind}
        if not self.ground_slab:
            out["ground_slab"] = False
        if self.building_class:
            out["building_class"] = self.building_class
        return out

    def to_yaml(self) -> str:
        return dict_to_structure_yaml(self.to_dict())


def _cells_to_sketch(cells: Set[Cell]) -> str:
    if not cells:
        return ""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    lines: List[str] = []
    for y in range(y1, y0 - 1, -1):
        row = []
        for x in range(x0, x1 + 1):
            row.append("#" if (x, y) in cells else " ")
        lines.append("".join(row).rstrip())
    return "\n".join(lines) + "\n"


def _parse_program(raw: Any) -> Dict[str, List[ProgramRegion]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("level.program must be an object")
    out: Dict[str, List[ProgramRegion]] = {}
    for key, regions in raw.items():
        if not isinstance(regions, list):
            raise ValueError(f"program.{key} must be a list of rectangles")
        parsed: List[ProgramRegion] = []
        for item in regions:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(
                    f"program.{key} entries must be [[x0,y0],[x1,y1]] rectangles"
                )
            a, b = item
            if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
                raise ValueError(f"program.{key} corners must be [x, y] pairs")
            if len(a) != 2 or len(b) != 2:
                raise ValueError(f"program.{key} corners must be [x, y] pairs")
            x0, y0 = int(a[0]), int(a[1])
            x1, y1 = int(b[0]), int(b[1])
            parsed.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        out[str(key)] = parsed
    return out


def _parse_level(raw: Any, index: int) -> LevelSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"levels[{index}] must be an object")
    unknown = sorted(set(raw) - {"sketch", "height_units", "program", "wall_style", "window_tag"})
    if unknown:
        raise ValueError(
            f"levels[{index}] contains unknown field(s): {', '.join(unknown)}"
        )
    sketch = raw.get("sketch")
    if sketch is None or not str(sketch).strip():
        raise ValueError(f"levels[{index}].sketch is required")
    height = int(raw.get("height_units", 1))
    if height < 1:
        raise ValueError(f"levels[{index}].height_units must be >= 1")
    wall_style = raw.get("wall_style")
    wall_style_s = None if wall_style is None else str(wall_style)
    window_tag = raw.get("window_tag")
    window_tag_s = None if window_tag is None else str(window_tag)
    level = LevelSpec(
        sketch=str(sketch),
        height_units=height,
        program=_parse_program(raw.get("program")),
        wall_style=wall_style_s,
        window_tag=window_tag_s,
    )
    try:
        level.ensure_marks()
    except SketchError as exc:
        raise ValueError(f"levels[{index}] sketch error: {exc}") from exc
    return level


def load_structure(data: Mapping[str, Any]) -> Tuple[Optional[StructureSpec], Report]:
    """Load StructureSpec from a §3.1 dict (YAML-decoded or hand-built)."""
    failures: List[Failure] = []
    if not isinstance(data, Mapping):
        failures.append(
            Failure(
                check="structure_type",
                message="StructureSpec must be an object",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    try:
        unknown = sorted(
            set(data)
            - {
                "name",
                "style",
                "levels",
                "seed",
                "unit_cm",
                "foundation",
                "foundation_origin",
                "structure_id",
                "roof",
                "circulation",
                "ground_slab",
                "building_class",
            }
        )
        if unknown:
            raise ValueError(
                f"StructureSpec contains unknown field(s): {', '.join(unknown)}"
            )
        levels_raw = data.get("levels")
        if not isinstance(levels_raw, list) or not levels_raw:
            raise ValueError("levels must be a non-empty list")
        levels = [_parse_level(item, i) for i, item in enumerate(levels_raw)]

        foundation_sketch = data.get("foundation")
        foundation_cells: Tuple[Cell, ...] = ()
        if foundation_sketch is not None and str(foundation_sketch).strip():
            try:
                marks = parse_sketch(str(foundation_sketch))
            except SketchError as exc:
                raise ValueError(f"foundation sketch error: {exc}") from exc
            foundation_cells = tuple(sorted(built_cells(marks)))
            origin_raw = data.get("foundation_origin", (0, 0))
            if not isinstance(origin_raw, (list, tuple)) or len(origin_raw) != 2:
                raise ValueError("foundation_origin must be a [x, y] cell pair")
            origin = (int(origin_raw[0]), int(origin_raw[1]))
            foundation_cells = tuple(
                sorted((x + origin[0], y + origin[1]) for x, y in foundation_cells)
            )
            foundation_sketch = str(foundation_sketch)
        else:
            foundation_sketch = None

        roof = data.get("roof") or {}
        if roof and not isinstance(roof, dict):
            raise ValueError("roof must be an object")
        roof_unknown = sorted(set(roof) - {"kind", "pitch"})
        if roof_unknown:
            raise ValueError(f"roof contains unknown field(s): {', '.join(roof_unknown)}")
        circ = data.get("circulation") or {}
        if circ and not isinstance(circ, dict):
            raise ValueError("circulation must be an object")
        circ_unknown = sorted(set(circ) - {"stair_kind"})
        if circ_unknown:
            raise ValueError(
                f"circulation contains unknown field(s): {', '.join(circ_unknown)}"
            )

        unit_raw = data.get("unit_cm")
        unit_cm = None if unit_raw is None else float(unit_raw)
        if unit_cm is not None and abs(unit_cm - MODULE_CM) > 1e-6:
            raise ValueError(
                f"unit_cm={unit_cm:g} is unsupported; this project uses "
                f"the fixed module size {MODULE_CM:g} cm"
            )

        structure_id = data.get("structure_id")
        name = str(data.get("name", "unnamed"))
        spec = StructureSpec(
            name=name,
            style=str(data.get("style", "townhouse")),
            levels=levels,
            seed=int(data.get("seed", 0)),
            unit_cm=unit_cm,
            foundation_sketch=foundation_sketch,
            foundation_cells=foundation_cells,
            structure_id=None if structure_id is None else str(structure_id),
            roof_kind=str(roof.get("kind", "pitched")),
            roof_pitch=float(roof.get("pitch", 1.0)),
            stair_kind=str(circ.get("stair_kind", "straight")),
            ground_slab=bool(data.get("ground_slab", True)),
            building_class=(
                None
                if data.get("building_class") is None
                else str(data.get("building_class"))
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(
            Failure(
                check="structure_parse",
                message=f"failed to parse StructureSpec: {exc}",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    return spec, Report.from_failures([])


def structure_to_building_spec(structure: StructureSpec):
    """Compatibility shim — StructureSpec → BuildingSpec for the existing pipeline.

    L0 (or foundation) becomes the ``cells`` footprint; per-level masks and
    ``height_units`` ride on BuildingSpec extension fields consumed by
    solver/plan/assemble.
    """
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        RoofSpec,
        TowerSpec,
    )

    levels = structure.levels
    storeys = len(levels)
    foundation = structure.resolved_foundation_cells()
    if not foundation:
        raise ValueError("structure has empty foundation / no built cells")

    # Primary footprint for volume decomposition: L0 built, else foundation.
    l0 = set(levels[0].built()) or set(foundation)
    xs = [c[0] for c in foundation]
    ys = [c[1] for c in foundation]
    footprint = FootprintSpec(
        kind="cells",
        bays_x=max(xs) - min(xs) + 1,
        bays_y=max(ys) - min(ys) + 1,
        cells=tuple(sorted(l0)),
    )

    # Towers / stairs: union marks across levels (solver places once).
    towers = [
        TowerSpec(cell=c, storeys=storeys)
        for c in sorted({c for lv in levels for c in lv.tower_cells()})
    ]
    stair_cells = sorted({c for lv in levels for c in lv.stair_cells()})
    storey_use: List[str] = []
    for lv in levels:
        if lv.program:
            storey_use.append(next(iter(lv.program.keys())))
        else:
            storey_use.append("hall")

    return BuildingSpec(
        name=structure.name,
        style=structure.style,
        footprint=footprint,
        storeys=storeys,
        storey_use=storey_use[:storeys],
        towers=towers,
        roof=RoofSpec(kind=structure.roof_kind, pitch=structure.roof_pitch),
        circulation=CirculationSpec(
            stair_kind=structure.stair_kind,
            stair_cells=stair_cells,
        ),
        seed=structure.seed,
        ground_slab=structure.ground_slab,
        building_class=structure.building_class,
        structure_id=structure.structure_id or structure.name,
        foundation_cells=tuple(sorted(foundation)),
        level_height_units=structure.level_height_units(),
        level_cells=structure.level_built_cells(),
        level_void_cells=structure.level_void_cells(),
        level_wall_styles=tuple(lv.wall_style for lv in levels),
        level_window_tags=tuple(lv.window_tag for lv in levels),
        level_programs=tuple(
            _merge_level_program(lv) for lv in levels
        ),
    )


def _merge_level_program(
    lv: LevelSpec,
) -> Dict[str, Tuple[Tuple[int, int, int, int], ...]]:
    """Explicit YAML program rectangles plus sketch H/C/V/R/A paint (Stage G).

    Explicit ``program:`` wins on name collision — sketch paint fills gaps only
    for names not already authored.
    """
    merged: Dict[str, List[Tuple[int, int, int, int]]] = {
        name: [tuple(region) for region in regions]  # type: ignore[misc]
        for name, regions in lv.program.items()
    }
    for name, regions in lv.program_from_sketch().items():
        if name in merged and merged[name]:
            continue
        merged[name] = [tuple(r) for r in regions]  # type: ignore[misc]
    return {
        name: tuple(tuple(r) for r in regions)  # type: ignore[misc]
        for name, regions in merged.items()
        if regions
    }


def building_spec_from_legacy(spec) -> "StructureSpec":
    """Wrap a classic BuildingSpec as a single-footprint StructureSpec (shim)."""
    from pae.spec import BuildingSpec

    if not isinstance(spec, BuildingSpec):
        raise TypeError("expected BuildingSpec")

    # Prefer cells mask; else synthesize a rect sketch.
    if spec.footprint.kind == "cells" and spec.footprint.cells:
        cells = set(spec.footprint.cells)
        sketch = _cells_to_sketch(cells)
    else:
        bx, by = spec.footprint.bays_x, spec.footprint.bays_y
        # Named shapes still go through solver; emit a filled rect sketch for
        # StructureSpec round-trip of the bounding box only.
        sketch = ("#" * bx + "\n") * by
        if spec.footprint.kind == "cells":
            sketch = _cells_to_sketch(set(spec.footprint.cells or ()))

    levels = [
        LevelSpec(sketch=sketch, height_units=1)
        for _ in range(max(1, int(spec.storeys)))
    ]
    return StructureSpec(
        name=spec.name,
        style=spec.style,
        levels=levels,
        seed=spec.seed,
        structure_id=getattr(spec, "structure_id", None) or spec.name,
        roof_kind=spec.roof.kind,
        roof_pitch=spec.roof.pitch,
        stair_kind=spec.circulation.stair_kind,
        ground_slab=spec.ground_slab,
        building_class=spec.building_class,
        foundation_cells=tuple(getattr(spec, "foundation_cells", ()) or ()),
    )


# ---------------------------------------------------------------------------
# Minimal YAML codec for §3.1 (no PyYAML dependency)
# ---------------------------------------------------------------------------

_BLOCK_KEY_RE = re.compile(r"^([A-Za-z_][\w]*)\s*:\s*(?:\|\s*)?$")
_SIMPLE_KEY_RE = re.compile(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$")


def dict_to_structure_yaml(data: Mapping[str, Any]) -> str:
    """Emit Master Plan §3.1 YAML from a structure dict."""
    lines: List[str] = []

    def emit_scalar(key: str, value: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, bool):
            lines.append(f"{pad}{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            lines.append(f"{pad}{key}: {value}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{pad}{key}: |")
            for row in value.splitlines():
                lines.append(f"{pad}  {row}")
        else:
            lines.append(f"{pad}{key}: {value}")

    for key in ("name", "style", "seed", "unit_cm", "structure_id", "building_class"):
        if key in data and data[key] is not None:
            emit_scalar(key, data[key])

    if "foundation" in data and data["foundation"]:
        emit_scalar("foundation", data["foundation"])
    if "foundation_origin" in data:
        emit_scalar("foundation_origin", data["foundation_origin"])

    if "roof" in data and isinstance(data["roof"], dict):
        lines.append("roof:")
        for rk, rv in data["roof"].items():
            emit_scalar(str(rk), rv, indent=1)

    if "circulation" in data and isinstance(data["circulation"], dict):
        lines.append("circulation:")
        for ck, cv in data["circulation"].items():
            emit_scalar(str(ck), cv, indent=1)

    if "ground_slab" in data:
        emit_scalar("ground_slab", data["ground_slab"])

    lines.append("levels:")
    for level in data.get("levels") or []:
        lines.append(f"  - height_units: {int(level.get('height_units', 1))}")
        sketch = level.get("sketch") or ""
        lines.append("    sketch: |")
        for row in str(sketch).splitlines():
            lines.append(f"      {row}")
        if level.get("wall_style"):
            emit_scalar("wall_style", level["wall_style"], indent=2)
        if level.get("window_tag"):
            emit_scalar("window_tag", level["window_tag"], indent=2)
        program = level.get("program") or {}
        if program:
            lines.append("    program:")
            for pname, regions in program.items():
                # Prefer rectangle form from to_dict: [[x0,y0],[x1,y1]]
                rendered: List[str] = []
                for r in regions:
                    if (
                        isinstance(r, (list, tuple))
                        and len(r) == 2
                        and isinstance(r[0], (list, tuple))
                    ):
                        rendered.append(
                            f"[[{int(r[0][0])},{int(r[0][1])}],"
                            f"[{int(r[1][0])},{int(r[1][1])}]]"
                        )
                    elif isinstance(r, (list, tuple)) and len(r) == 4:
                        rendered.append(
                            f"[[{int(r[0])},{int(r[1])}],[{int(r[2])},{int(r[3])}]]"
                        )
                lines.append(f"      {pname}: [{', '.join(rendered)}]")
    return "\n".join(lines) + "\n"


def _parse_yaml_scalar(text: str) -> Any:
    s = text.strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "None", "~", ""):
        return None
    try:
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d+", s):
            return float(s)
    except ValueError:
        pass
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    return s


def _parse_program_list(text: str) -> List[List[List[int]]]:
    """Parse ``[[x0,y0],[x1,y1]], ...`` from a single line."""
    # Use json by wrapping as an array.
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid program regions: {text!r}") from exc


def load_structure_yaml(text: str) -> Tuple[Optional[StructureSpec], Report]:
    """Parse a minimal §3.1 YAML document into StructureSpec."""
    try:
        data = parse_structure_yaml(text)
    except ValueError as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="structure_yaml",
                    message=str(exc),
                    world_xyz=None,
                )
            ]
        )
    return load_structure(data)


def parse_structure_yaml(text: str) -> dict:
    """Hand-rolled parser for the Master Plan §3.1 subset."""
    raw_lines = text.splitlines()
    data: Dict[str, Any] = {}
    i = 0
    n = len(raw_lines)

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    while i < n:
        line = raw_lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        ind = indent_of(line)
        stripped = line.strip()

        if stripped == "levels:":
            levels: List[dict] = []
            i += 1
            while i < n:
                ln = raw_lines[i]
                if not ln.strip() or ln.lstrip().startswith("#"):
                    i += 1
                    continue
                if indent_of(ln) <= ind and not ln.strip().startswith("-"):
                    break
                if ln.strip().startswith("-"):
                    level: Dict[str, Any] = {}
                    # "- height_units: N" or "- sketch: |"
                    rest = ln.strip()[1:].strip()
                    if rest:
                        m = _SIMPLE_KEY_RE.match(rest)
                        if m:
                            k, v = m.group(1), m.group(2).strip()
                            if v == "|":
                                block, i = _read_block(raw_lines, i + 1, indent_of(ln) + 2)
                                level[k] = block
                                # continue without increment (already advanced)
                                levels.append(level)
                                # read remaining keys for this level
                                while i < n:
                                    ln2 = raw_lines[i]
                                    if not ln2.strip() or ln2.lstrip().startswith("#"):
                                        i += 1
                                        continue
                                    if indent_of(ln2) <= indent_of(ln):
                                        break
                                    if ln2.strip().startswith("-") and indent_of(ln2) <= indent_of(ln) + 1:
                                        break
                                    i = _read_level_field(raw_lines, i, level, indent_of(ln) + 2)
                                continue
                            level[k] = _parse_yaml_scalar(v)
                    i += 1
                    while i < n:
                        ln2 = raw_lines[i]
                        if not ln2.strip() or ln2.lstrip().startswith("#"):
                            i += 1
                            continue
                        if indent_of(ln2) <= indent_of(ln):
                            break
                        if ln2.strip().startswith("-") and indent_of(ln2) <= indent_of(ln) + 1:
                            break
                        i = _read_level_field(raw_lines, i, level, indent_of(ln) + 2)
                    levels.append(level)
                    continue
                i += 1
            data["levels"] = levels
            continue

        if stripped.endswith(": |") or stripped.endswith(":|"):
            key = stripped.split(":")[0].strip()
            block, i = _read_block(raw_lines, i + 1, ind + 2)
            data[key] = block
            continue

        if stripped.endswith(":") and not stripped.startswith("-"):
            key = stripped[:-1].strip()
            # nested mapping (roof / circulation)
            nested: Dict[str, Any] = {}
            i += 1
            while i < n:
                ln = raw_lines[i]
                if not ln.strip() or ln.lstrip().startswith("#"):
                    i += 1
                    continue
                if indent_of(ln) <= ind:
                    break
                m = _SIMPLE_KEY_RE.match(ln.strip())
                if not m:
                    break
                nested[m.group(1)] = _parse_yaml_scalar(m.group(2))
                i += 1
            data[key] = nested
            continue

        m = _SIMPLE_KEY_RE.match(stripped)
        if m and ind == 0:
            data[m.group(1)] = _parse_yaml_scalar(m.group(2))
            i += 1
            continue

        raise ValueError(f"unrecognized YAML line {i + 1}: {line!r}")

    return data


def _read_block(lines: List[str], start: int, min_indent: int) -> Tuple[str, int]:
    rows: List[str] = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            # blank line inside block — keep if next content is still indented
            if i + 1 < len(lines) and indent_of(lines[i + 1]) >= min_indent:
                rows.append("")
                i += 1
                continue
            break
        if indent_of(ln) < min_indent:
            break
        rows.append(ln[min_indent:] if len(ln) >= min_indent else ln.lstrip())
        i += 1
    return "\n".join(rows) + ("\n" if rows else ""), i


def _read_level_field(
    lines: List[str], i: int, level: dict, base_indent: int
) -> int:
    ln = lines[i]
    stripped = ln.strip()
    if stripped.startswith("program:"):
        program: Dict[str, Any] = {}
        i += 1
        while i < len(lines):
            ln2 = lines[i]
            if not ln2.strip() or ln2.lstrip().startswith("#"):
                i += 1
                continue
            if indent_of(ln2) <= base_indent:
                break
            m = _SIMPLE_KEY_RE.match(ln2.strip())
            if not m:
                break
            program[m.group(1)] = _parse_program_list(m.group(2))
            i += 1
        level["program"] = program
        return i

    if stripped.endswith(": |") or stripped.endswith(":|"):
        key = stripped.split(":")[0].strip()
        block, i2 = _read_block(lines, i + 1, indent_of(ln) + 2)
        level[key] = block
        return i2

    m = _SIMPLE_KEY_RE.match(stripped)
    if not m:
        raise ValueError(f"bad level field: {ln!r}")
    key, val = m.group(1), m.group(2).strip()
    if val == "|":
        block, i2 = _read_block(lines, i + 1, indent_of(ln) + 2)
        level[key] = block
        return i2
    level[key] = _parse_yaml_scalar(val)
    return i + 1


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


__all__ = [
    "LevelSpec",
    "StructureSpec",
    "building_spec_from_legacy",
    "dict_to_structure_yaml",
    "load_structure",
    "load_structure_yaml",
    "parse_structure_yaml",
    "structure_to_building_spec",
]

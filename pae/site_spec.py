"""SiteSpec — Master Plan Stage J authoring skeleton (not M-G city gen).

WHY: Stage J needs an authoring model for *several* structures on one site
(offsets, style/seed, ``structure:<id>`` grouping) before streets/plots/city
generation. Product-shaped city presets stay deferred — this module is the
spec + tiny merge path only.

Public surface:

  SiteSpec / PlacedStructureSpec / RoadPlaceholder / PlotPlaceholder
  load_site / load_site_yaml / to_dict / to_yaml
  build_from_site_spec  — assemble each placement via pipeline, merge with
                         ``place_buildings`` + distinct ``structure:<id>`` tags

Road/plot fields are placeholders (serialized, not consumed by build).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from pae.assembly_types import Assembly
from pae.report import Failure, Report
from pae.site import BuildingInstance, place_buildings
from pae.structure_spec import LevelSpec, StructureSpec, load_structure

Cell = Tuple[int, int]
PipelineSpec = Union[StructureSpec, Any]  # StructureSpec or BuildingSpec

# Soft guard for the Stage J skeleton — M-G will raise this.
SKELETON_MAX_STRUCTURES = 3

_SIMPLE_KEY_RE = re.compile(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$")
_LIST_ITEM_RE = re.compile(r"^-\s+(.*)$")


@dataclass(frozen=True)
class RoadPlaceholder:
    """Deferred street network sketch (Stage J / M-G). Not consumed by build."""

    name: str = "road"
    path_cells: Tuple[Cell, ...] = ()

    def to_dict(self) -> dict:
        out: Dict[str, Any] = {"name": self.name}
        if self.path_cells:
            out["path_cells"] = [[c[0], c[1]] for c in self.path_cells]
        return out


@dataclass(frozen=True)
class PlotPlaceholder:
    """Deferred plot subdivision (Stage J / M-G). Not consumed by build."""

    name: str
    origin: Cell = (0, 0)
    bays_x: int = 1
    bays_y: int = 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "origin": [self.origin[0], self.origin[1]],
            "bays_x": int(self.bays_x),
            "bays_y": int(self.bays_y),
        }


@dataclass
class PlacedStructureSpec:
    """One structure on a site: id, cell offset, and authoring payload."""

    structure_id: str
    cell_offset: Cell = (0, 0)
    name: Optional[str] = None
    #: Full StructureSpec when authored explicitly.
    structure: Optional[StructureSpec] = None
    #: Optional BuildingSpec (pipeline public API). Mutually exclusive with sketch.
    building: Any = None
    #: Tiny one-level shorthand sketch (e.g. 3×2 ``###\\n###``).
    sketch: Optional[str] = None
    style: Optional[str] = None
    seed: Optional[int] = None

    def instance_name(self) -> str:
        return self.name or self.structure_id

    def resolve(self, site: "SiteSpec") -> PipelineSpec:
        """Resolve to a StructureSpec or BuildingSpec for ``run_through_assemble``."""
        if self.building is not None:
            if self.structure is not None or self.sketch:
                raise ValueError(
                    f"placed structure {self.structure_id!r}: "
                    "building and structure/sketch are mutually exclusive"
                )
            return self.building
        if self.structure is not None:
            return self.structure
        if not self.sketch or not str(self.sketch).strip():
            raise ValueError(
                f"placed structure {self.structure_id!r} needs structure, "
                "building, or sketch"
            )
        style = self.style if self.style is not None else site.style
        seed = int(self.seed if self.seed is not None else site.seed)
        return StructureSpec(
            name=self.instance_name(),
            style=style,
            seed=seed,
            structure_id=self.structure_id,
            levels=[LevelSpec(sketch=str(self.sketch), height_units=1)],
            roof_kind="flat",
        )

    def to_dict(self) -> dict:
        out: Dict[str, Any] = {
            "structure_id": self.structure_id,
            "cell_offset": [int(self.cell_offset[0]), int(self.cell_offset[1])],
        }
        if self.name and self.name != self.structure_id:
            out["name"] = self.name
        if self.style is not None:
            out["style"] = self.style
        if self.seed is not None:
            out["seed"] = int(self.seed)
        if self.structure is not None:
            out["structure"] = self.structure.to_dict()
        elif self.sketch:
            sk = self.sketch if self.sketch.endswith("\n") else self.sketch + "\n"
            out["sketch"] = sk
        elif self.building is not None:
            # BuildingSpec is in-memory only (no public dict loader yet).
            out["building_ref"] = getattr(self.building, "name", "building")
        return out


@dataclass
class SiteSpec:
    """Several structures with offsets — Stage J site authoring (city deferred)."""

    name: str
    style: str = "townhouse"
    seed: int = 0
    structures: List[PlacedStructureSpec] = field(default_factory=list)
    roads: List[RoadPlaceholder] = field(default_factory=list)
    plots: List[PlotPlaceholder] = field(default_factory=list)

    def to_dict(self) -> dict:
        out: Dict[str, Any] = {
            "name": self.name,
            "style": self.style,
            "seed": int(self.seed),
            "structures": [p.to_dict() for p in self.structures],
        }
        if self.roads:
            out["roads"] = [r.to_dict() for r in self.roads]
        if self.plots:
            out["plots"] = [p.to_dict() for p in self.plots]
        return out

    def to_yaml(self) -> str:
        return dict_to_site_yaml(self.to_dict())


def _parse_cell(raw: Any, *, field_name: str) -> Cell:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{field_name} must be a [x, y] cell pair")
    return (int(raw[0]), int(raw[1]))


def _parse_road(raw: Any, index: int) -> RoadPlaceholder:
    if not isinstance(raw, Mapping):
        raise ValueError(f"roads[{index}] must be an object")
    name = str(raw.get("name", f"road_{index}"))
    cells_raw = raw.get("path_cells") or []
    if not isinstance(cells_raw, list):
        raise ValueError(f"roads[{index}].path_cells must be a list")
    cells = tuple(_parse_cell(c, field_name=f"roads[{index}].path_cells") for c in cells_raw)
    return RoadPlaceholder(name=name, path_cells=cells)


def _parse_plot(raw: Any, index: int) -> PlotPlaceholder:
    if not isinstance(raw, Mapping):
        raise ValueError(f"plots[{index}] must be an object")
    name = raw.get("name")
    if not name:
        raise ValueError(f"plots[{index}].name is required")
    origin = _parse_cell(raw.get("origin", [0, 0]), field_name=f"plots[{index}].origin")
    return PlotPlaceholder(
        name=str(name),
        origin=origin,
        bays_x=int(raw.get("bays_x", 1)),
        bays_y=int(raw.get("bays_y", 1)),
    )


def _parse_placed(raw: Any, index: int) -> PlacedStructureSpec:
    if not isinstance(raw, Mapping):
        raise ValueError(f"structures[{index}] must be an object")
    unknown = sorted(
        set(raw)
        - {
            "structure_id",
            "id",
            "cell_offset",
            "offset",
            "name",
            "style",
            "seed",
            "structure",
            "sketch",
            "building_ref",  # serialize marker only — BuildingSpec is in-memory
        }
    )
    if unknown:
        raise ValueError(
            f"structures[{index}] unknown field(s): {', '.join(unknown)}"
        )
    sid = raw.get("structure_id", raw.get("id"))
    if not sid:
        raise ValueError(f"structures[{index}].structure_id is required")
    offset_raw = raw.get("cell_offset", raw.get("offset", [0, 0]))
    offset = _parse_cell(offset_raw, field_name=f"structures[{index}].cell_offset")

    structure: Optional[StructureSpec] = None
    sketch = raw.get("sketch")
    if "structure" in raw and raw["structure"] is not None:
        nested, report = load_structure(raw["structure"])
        if not report.ok or nested is None:
            msgs = "; ".join(f.message for f in report.failures)
            raise ValueError(f"structures[{index}].structure: {msgs}")
        structure = nested
        sketch = None

    if structure is None and (sketch is None or not str(sketch).strip()):
        raise ValueError(
            f"structures[{index}] needs structure or sketch "
            "(BuildingSpec is in-memory via PlacedStructureSpec.building only)"
        )

    seed = raw.get("seed")
    return PlacedStructureSpec(
        structure_id=str(sid),
        cell_offset=offset,
        name=None if raw.get("name") is None else str(raw["name"]),
        structure=structure,
        building=None,
        sketch=None if sketch is None else str(sketch),
        style=None if raw.get("style") is None else str(raw["style"]),
        seed=None if seed is None else int(seed),
    )


def load_site(data: Mapping[str, Any]) -> Tuple[Optional[SiteSpec], Report]:
    """Load SiteSpec from a dict (YAML-decoded or hand-built)."""
    failures: List[Failure] = []
    if not isinstance(data, Mapping):
        failures.append(
            Failure(
                check="site_type",
                message="SiteSpec must be an object",
                world_xyz=None,
            )
        )
        return None, Report.from_failures(failures)

    try:
        unknown = sorted(
            set(data) - {"name", "style", "seed", "structures", "roads", "plots"}
        )
        if unknown:
            raise ValueError(f"SiteSpec unknown field(s): {', '.join(unknown)}")
        name = data.get("name")
        if not name:
            raise ValueError("name is required")
        structures_raw = data.get("structures")
        if not isinstance(structures_raw, list) or not structures_raw:
            raise ValueError("structures must be a non-empty list")
        structures = [_parse_placed(item, i) for i, item in enumerate(structures_raw)]
        ids = [p.structure_id for p in structures]
        if len(set(ids)) != len(ids):
            raise ValueError(f"structure_id values must be unique, got {ids}")
        names = [p.instance_name() for p in structures]
        if len(set(names)) != len(names):
            raise ValueError(f"instance names must be unique, got {names}")

        roads_raw = data.get("roads") or []
        plots_raw = data.get("plots") or []
        if not isinstance(roads_raw, list):
            raise ValueError("roads must be a list")
        if not isinstance(plots_raw, list):
            raise ValueError("plots must be a list")
        roads = [_parse_road(item, i) for i, item in enumerate(roads_raw)]
        plots = [_parse_plot(item, i) for i, item in enumerate(plots_raw)]

        site = SiteSpec(
            name=str(name),
            style=str(data.get("style", "townhouse")),
            seed=int(data.get("seed", 0)),
            structures=structures,
            roads=roads,
            plots=plots,
        )
        return site, Report.from_failures([])
    except ValueError as exc:
        failures.append(
            Failure(check="site_load", message=str(exc), world_xyz=None)
        )
        return None, Report.from_failures(failures)


def build_from_site_spec(
    site: SiteSpec,
    *,
    asset_db=None,
    max_structures: int = SKELETON_MAX_STRUCTURES,
) -> Tuple[Assembly, Report]:
    """Assemble each placed structure and merge at cell offsets.

    Uses ``pipeline.run_through_assemble`` only (no assemble internals).
    Each placement is tagged ``structure:<structure_id>`` via ``place_buildings``.

    ``max_structures`` defaults to 3 for the Stage J skeleton (RAM). Pass a
    higher value later for M-G; do not use this for fortress / street_scene.
    """
    if not site.structures:
        return Assembly(placements=[]), Report.from_failures(
            [
                Failure(
                    check="site_empty",
                    message="SiteSpec has no structures",
                    world_xyz=None,
                )
            ]
        )
    if len(site.structures) > int(max_structures):
        return Assembly(placements=[]), Report.from_failures(
            [
                Failure(
                    check="site_too_many_structures",
                    message=(
                        f"SiteSpec has {len(site.structures)} structures; "
                        f"skeleton max is {max_structures} (M-G city deferred)"
                    ),
                    world_xyz=None,
                )
            ]
        )

    from pae.pipeline import run_through_assemble

    instances: List[BuildingInstance] = []
    for placed in site.structures:
        try:
            spec = placed.resolve(site)
        except ValueError as exc:
            return Assembly(placements=[]), Report.from_failures(
                [
                    Failure(
                        check="site_resolve",
                        message=str(exc),
                        world_xyz=None,
                    )
                ]
            )
        _, _, assembly, areport = run_through_assemble(spec, asset_db=asset_db)
        if not areport.ok:
            return Assembly(placements=[]), areport
        instances.append(
            BuildingInstance(
                assembly=assembly,
                cell_offset=placed.cell_offset,
                name=placed.instance_name(),
                structure=placed.structure_id,
            )
        )
    return place_buildings(instances)


# ---------------------------------------------------------------------------
# YAML (minimal subset — mirrors structure_spec style, no PyYAML dep)
# ---------------------------------------------------------------------------


def dict_to_site_yaml(data: Mapping[str, Any]) -> str:
    """Emit Stage J site YAML from a site dict."""
    lines: List[str] = []

    def emit_scalar(key: str, value: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, bool):
            lines.append(f"{pad}{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            lines.append(f"{pad}{key}: {value}")
        elif isinstance(value, list) and all(
            isinstance(x, (int, float)) for x in value
        ):
            lines.append(f"{pad}{key}: {json.dumps(value)}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{pad}{key}: |")
            for row in value.splitlines():
                lines.append(f"{pad}  {row}")
        else:
            lines.append(f"{pad}{key}: {value}")

    for key in ("name", "style", "seed"):
        if key in data and data[key] is not None:
            emit_scalar(key, data[key])

    lines.append("structures:")
    for item in data.get("structures") or []:
        if not isinstance(item, Mapping):
            continue
        sid = item.get("structure_id", item.get("id", "structure"))
        lines.append(f"  - structure_id: {sid}")
        offset = item.get("cell_offset", item.get("offset", [0, 0]))
        emit_scalar("cell_offset", list(offset), indent=2)
        if item.get("name") and item["name"] != sid:
            emit_scalar("name", item["name"], indent=2)
        if item.get("style") is not None:
            emit_scalar("style", item["style"], indent=2)
        if item.get("seed") is not None:
            emit_scalar("seed", item["seed"], indent=2)
        if item.get("sketch"):
            emit_scalar("sketch", item["sketch"], indent=2)
        elif item.get("structure"):
            # Nested StructureSpec as JSON blob — round-trip safe without full YAML nesting.
            blob = json.dumps(item["structure"], separators=(",", ":"))
            lines.append("    structure_json: |")
            lines.append(f"      {blob}")
        elif item.get("building_ref"):
            emit_scalar("building_ref", item["building_ref"], indent=2)

    roads = data.get("roads") or []
    if roads:
        lines.append("roads:")
        for road in roads:
            if not isinstance(road, Mapping):
                continue
            lines.append(f"  - name: {road.get('name', 'road')}")
            cells = road.get("path_cells") or []
            if cells:
                emit_scalar("path_cells", cells, indent=2)

    plots = data.get("plots") or []
    if plots:
        lines.append("plots:")
        for plot in plots:
            if not isinstance(plot, Mapping):
                continue
            lines.append(f"  - name: {plot.get('name', 'plot')}")
            emit_scalar("origin", list(plot.get("origin", [0, 0])), indent=2)
            emit_scalar("bays_x", int(plot.get("bays_x", 1)), indent=2)
            emit_scalar("bays_y", int(plot.get("bays_y", 1)), indent=2)

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


def parse_site_yaml(text: str) -> dict:
    """Hand-rolled parser for the Stage J site YAML subset."""
    raw_lines = text.splitlines()
    data: Dict[str, Any] = {}
    i = 0
    n = len(raw_lines)

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def read_block(start_indent: int) -> Tuple[str, int]:
        nonlocal i
        rows: List[str] = []
        while i < n:
            line = raw_lines[i]
            if not line.strip():
                rows.append("")
                i += 1
                continue
            if indent_of(line) <= start_indent and line.strip():
                break
            rows.append(line[start_indent + 2 :] if len(line) > start_indent + 2 else line.lstrip())
            i += 1
        # Drop trailing empties.
        while rows and rows[-1] == "":
            rows.pop()
        return "\n".join(rows) + ("\n" if rows else ""), i

    while i < n:
        line = raw_lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        ind = indent_of(line)
        stripped = line.strip()

        if ind == 0 and stripped in ("structures:", "roads:", "plots:"):
            key = stripped[:-1]
            i += 1
            items: List[dict] = []
            while i < n:
                line = raw_lines[i]
                if not line.strip() or line.lstrip().startswith("#"):
                    i += 1
                    continue
                if indent_of(line) == 0:
                    break
                m_item = _LIST_ITEM_RE.match(line.strip())
                if indent_of(line) == 2 and m_item:
                    item: Dict[str, Any] = {}
                    rest = m_item.group(1)
                    km = _SIMPLE_KEY_RE.match(rest)
                    if km:
                        k, v = km.group(1), km.group(2)
                        if v.strip() == "|":
                            i += 1
                            block, _ = read_block(2)
                            item[k] = block
                        else:
                            item[k] = _parse_yaml_scalar(v)
                            i += 1
                    else:
                        i += 1
                    # Nested fields at indent 4.
                    while i < n:
                        line = raw_lines[i]
                        if not line.strip() or line.lstrip().startswith("#"):
                            i += 1
                            continue
                        if indent_of(line) <= 2:
                            break
                        if indent_of(line) != 4:
                            i += 1
                            continue
                        km = _SIMPLE_KEY_RE.match(line.strip())
                        if not km:
                            i += 1
                            continue
                        k, v = km.group(1), km.group(2)
                        if v.strip() == "|":
                            i += 1
                            block, _ = read_block(4)
                            if k == "structure_json":
                                item["structure"] = json.loads(block.strip())
                            else:
                                item[k] = block
                        else:
                            item[k] = _parse_yaml_scalar(v)
                            i += 1
                    items.append(item)
                    continue
                i += 1
            data[key] = items
            continue

        if ind == 0:
            km = _SIMPLE_KEY_RE.match(stripped)
            if km:
                k, v = km.group(1), km.group(2)
                if v.strip() == "|":
                    i += 1
                    block, _ = read_block(0)
                    data[k] = block
                else:
                    data[k] = _parse_yaml_scalar(v)
                    i += 1
                continue
        i += 1

    return data


def load_site_yaml(text: str) -> Tuple[Optional[SiteSpec], Report]:
    """Parse Stage J site YAML into SiteSpec."""
    try:
        data = parse_site_yaml(text)
    except (ValueError, json.JSONDecodeError) as exc:
        return None, Report.from_failures(
            [
                Failure(
                    check="site_yaml",
                    message=str(exc),
                    world_xyz=None,
                )
            ]
        )
    return load_site(data)


__all__ = [
    "SKELETON_MAX_STRUCTURES",
    "RoadPlaceholder",
    "PlotPlaceholder",
    "PlacedStructureSpec",
    "SiteSpec",
    "load_site",
    "load_site_yaml",
    "parse_site_yaml",
    "dict_to_site_yaml",
    "build_from_site_spec",
]

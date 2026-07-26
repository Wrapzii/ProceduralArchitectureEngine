"""StructureSpec authoring helpers for the Blender add-on (bpy-free)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pae.report import Report
from pae.spec import SUPPORTED_ROOF_KINDS, SUPPORTED_STAIR_KINDS
from pae.structure_spec import (
    LevelSpec,
    StructureSpec,
    load_structure_yaml,
)

DEFAULT_LEVEL_SKETCH = "####\n####\n"

GATEHOUSE_PRESET_YAML = """
name: gatehouse
style: townhouse
seed: 7

foundation: |
  ##########
  ##########

levels:
  - height_units: 1
    sketch: |
      ########
      ########
  - height_units: 1
    sketch: |
      #####...
      #####...
  - height_units: 3
    sketch: |
      ....####
      ....####
    wall_style: arcade
"""


def default_level_sketch(*, rows: int = 2, cols: int = 4) -> str:
    rows = max(1, int(rows))
    cols = max(1, int(cols))
    return ("#" * cols + "\n") * rows


def _normalize_sketch(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return DEFAULT_LEVEL_SKETCH
    return raw if raw.endswith("\n") else raw + "\n"


def level_dict_from_ui(
    *,
    sketch: str,
    height_units: int,
    wall_style: str = "",
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "sketch": _normalize_sketch(sketch),
        "height_units": max(1, int(height_units)),
    }
    ws = (wall_style or "").strip()
    if ws:
        out["wall_style"] = ws
    return out


def build_structure_from_ui(
    *,
    name: str,
    style: str,
    seed: int,
    levels: Sequence[Mapping[str, Any]],
    foundation_sketch: str = "",
    use_foundation: bool = False,
    roof_kind: str = "pitched",
    roof_pitch: float = 1.0,
    stair_kind: str = "straight",
) -> StructureSpec:
    """Build ``StructureSpec`` from add-on property values (Master Plan §3.1 / §5)."""
    if not levels:
        raise ValueError("structure requires at least one level")

    rk = (roof_kind or "pitched").lower()
    if rk not in SUPPORTED_ROOF_KINDS:
        rk = "pitched"
    sk = (stair_kind or "straight").lower()
    if sk not in SUPPORTED_STAIR_KINDS:
        sk = "straight"

    level_specs: List[LevelSpec] = []
    for index, raw in enumerate(levels):
        sketch = _normalize_sketch(str(raw.get("sketch", "")))
        height = max(1, int(raw.get("height_units", 1)))
        wall_style = str(raw.get("wall_style", "") or "").strip() or None
        try:
            level_specs.append(
                LevelSpec(
                    sketch=sketch,
                    height_units=height,
                    wall_style=wall_style,
                )
            )
        except ValueError as exc:
            raise ValueError(f"levels[{index}]: {exc}") from exc

    foundation: Optional[str] = None
    if use_foundation:
        foundation = _normalize_sketch(foundation_sketch)

    return StructureSpec(
        name=name or "pae_structure",
        style=style or "townhouse",
        levels=level_specs,
        seed=int(seed),
        foundation_sketch=foundation,
        roof_kind=rk,
        roof_pitch=max(0.5, min(2.5, float(roof_pitch))),
        stair_kind=sk,
    )


def structure_ui_values_from_spec(structure: StructureSpec) -> Dict[str, Any]:
    """Map ``StructureSpec`` onto add-on property field values."""
    levels: List[Dict[str, Any]] = []
    for lv in structure.levels:
        levels.append(
            {
                "sketch": lv.sketch,
                "height_units": int(lv.height_units),
                "wall_style": lv.wall_style or "",
            }
        )
    foundation = structure.foundation_sketch or ""
    use_foundation = bool(foundation.strip())
    return {
        "building_name": structure.name,
        "style": structure.style,
        "seed": int(structure.seed),
        "roof_kind": structure.roof_kind,
        "roof_pitch": float(structure.roof_pitch),
        "stair_kind": structure.stair_kind,
        "structure_use_foundation": use_foundation,
        "structure_foundation_sketch": foundation,
        "structure_levels": levels,
    }


def structure_yaml_from_ui(
    *,
    name: str,
    style: str,
    seed: int,
    levels: Sequence[Mapping[str, Any]],
    foundation_sketch: str = "",
    use_foundation: bool = False,
    roof_kind: str = "pitched",
    roof_pitch: float = 1.0,
    stair_kind: str = "straight",
) -> str:
    structure = build_structure_from_ui(
        name=name,
        style=style,
        seed=seed,
        levels=levels,
        foundation_sketch=foundation_sketch,
        use_foundation=use_foundation,
        roof_kind=roof_kind,
        roof_pitch=roof_pitch,
        stair_kind=stair_kind,
    )
    return structure.to_yaml()


def parse_structure_yaml_to_ui_values(text: str) -> Tuple[Optional[Dict[str, Any]], Report]:
    """Parse §3.1 YAML into UI property values."""
    structure, report = load_structure_yaml(text)
    if not report.ok or structure is None:
        return None, report
    return structure_ui_values_from_spec(structure), report


def ensure_default_levels(
    levels: Sequence[Mapping[str, Any]],
    *,
    rows: int = 2,
    cols: int = 4,
) -> List[Dict[str, Any]]:
    if levels:
        return [dict(item) for item in levels]
    return [
        {
            "sketch": default_level_sketch(rows=rows, cols=cols),
            "height_units": 1,
            "wall_style": "",
        }
    ]


def coerce_pipeline_spec(spec):
    """Normalize addon input for ``run_through_assemble`` (reload-safe)."""
    from pae.spec import BuildingSpec

    if isinstance(spec, BuildingSpec):
        return spec
    if hasattr(spec, "levels") and hasattr(spec, "resolved_foundation_cells"):
        from pae.structure_spec import structure_to_building_spec

        return structure_to_building_spec(spec)
    return spec

"""Shared operator helpers (bpy-only)."""

from __future__ import annotations

from typing import Optional, Tuple, Union

from pae.addon.helpers import build_spec_from_ui, ui_values_from_spec
from pae.addon.properties import HAS_BPY
from pae.addon.session import report_to_json
from pae.addon.structure_helpers import (
    build_structure_from_ui,
    ensure_default_levels,
    structure_ui_values_from_spec,
)
from pae.report import Report
from pae.spec import BuildingSpec
from pae.structure_spec import StructureSpec

if HAS_BPY:

    def _level_items_from_props(props) -> list:
        return [
            {
                "sketch": item.sketch,
                "height_units": item.height_units,
                "wall_style": item.wall_style,
            }
            for item in props.structure_levels
        ]

    def structure_from_context(context) -> StructureSpec:
        props = scene_props(context)
        levels = _level_items_from_props(props)
        if not levels:
            levels = ensure_default_levels(
                [],
                rows=max(1, props.bays_y),
                cols=max(1, props.bays_x),
            )
        return build_structure_from_ui(
            name=props.building_name,
            style=props.style,
            seed=props.seed,
            levels=levels,
            foundation_sketch=props.structure_foundation_sketch,
            use_foundation=props.structure_use_foundation,
            roof_kind=props.roof_kind,
            roof_pitch=props.roof_pitch,
            stair_kind=props.stair_kind,
        )

    def pipeline_input_from_context(
        context,
    ) -> Union[StructureSpec, BuildingSpec]:
        """Prefer StructureSpec when the level stack has entries."""
        props = scene_props(context)
        if len(props.structure_levels) > 0:
            return structure_from_context(context)
        return spec_from_context(context)

    def apply_structure_values_to_props(props, values: dict) -> None:
        """Copy parsed structure UI values onto scene properties."""
        for key in (
            "building_name",
            "style",
            "seed",
            "roof_kind",
            "roof_pitch",
            "stair_kind",
            "structure_use_foundation",
            "structure_foundation_sketch",
        ):
            if key in values:
                setattr(props, key, values[key])
        props.structure_levels.clear()
        for item in values.get("structure_levels") or []:
            row = props.structure_levels.add()
            row.sketch = str(item.get("sketch", ""))
            row.height_units = max(1, int(item.get("height_units", 1)))
            row.wall_style = str(item.get("wall_style", "") or "")
        props.structure_active_level = 0

    def apply_structure_spec_to_props(props, structure: StructureSpec) -> None:
        apply_structure_values_to_props(props, structure_ui_values_from_spec(structure))

    def scene_props(context):
        return context.scene.pae

    def spec_from_context(context) -> BuildingSpec:
        props = scene_props(context)
        return build_spec_from_ui(
            name=props.building_name,
            style=props.style,
            storeys=props.storeys,
            bays_x=props.bays_x,
            bays_y=props.bays_y,
            footprint_kind=props.footprint_kind,
            seed=props.seed,
            wing_depth=props.wing_depth,
            courtyard=props.courtyard,
            roof_kind=props.roof_kind,
            roof_pitch=props.roof_pitch,
            stair_kind=props.stair_kind,
            wall_height_storeys=props.wall_height_storeys,
            doors_ground=props.doors_ground,
            windows_per_bay=props.windows_per_bay,
            entrance_enabled=props.entrance_enabled,
            entrance_role=props.entrance_role,
            entrance_facade=props.entrance_facade,
            entrance_ensemble=props.entrance_ensemble,
        )

    def apply_spec_to_props(props, spec: BuildingSpec) -> None:
        """Copy a ``BuildingSpec`` into scene UI properties."""
        for key, value in ui_values_from_spec(spec).items():
            setattr(props, key, value)

    def apply_facade_preset_to_props(props, preset: str) -> None:
        """Load a documented facade slider preset into the Procedural Building panel."""
        presets = {
            "quick": {
                "facade_seed": 1812,
                "facade_archetype": "georgian_merchant",
                "facade_frontage_m": 10.0,
                "facade_depth_m": 8.0,
                "facade_storeys": 2,
                "facade_wealth": 2,
                "facade_row_context": "freestanding",
            },
            "demo": {
                "facade_seed": 1812,
                "facade_archetype": "georgian_merchant",
                "facade_frontage_m": 22.0,
                "facade_depth_m": 12.0,
                "facade_storeys": 4,
                "facade_wealth": 4,
                "facade_row_context": "end_left",
            },
        }
        values = presets.get(preset)
        if values is None:
            raise ValueError(f"unknown facade preset {preset!r}")
        for key, value in values.items():
            setattr(props, key, value)

    def report_operator_exception(operator, props, exc: BaseException) -> None:
        """Surface RuntimeError / critical failures in the UI status line."""
        msg = str(exc).strip() or exc.__class__.__name__
        if len(msg) > 480:
            msg = msg[:477] + "..."
        props.last_error_message = msg
        props.last_pipeline_message = f"ERROR: {msg[:120]}"
        operator.report({"ERROR"}, msg[:240])

    def store_validation_report(props, report: Report) -> None:
        props.validation_report_json = report_to_json(report)

    def report_validation_result(
        operator,
        props,
        report: Report,
        *,
        prefix: str = "",
    ) -> Tuple[bool, str]:
        """Cache report JSON and return (ok, user-facing message)."""
        store_validation_report(props, report)
        if report.ok:
            msg = f"{prefix} OK" if prefix else "Validation OK"
            props.last_pipeline_message = msg
            props.last_error_message = ""
            operator.report({"INFO"}, msg)
            return True, msg
        crit = report.critical[:3]
        detail = "; ".join(f.message for f in crit) or "validation failed"
        msg = f"{prefix}: {detail}" if prefix else f"{len(report.critical)} critical defect(s)"
        props.last_pipeline_message = msg
        props.last_error_message = detail
        operator.report({"ERROR"}, msg[:240])
        return False, msg

    def maybe_clear_pae_scene(props) -> Optional[dict]:
        """Clear prior PAE builds when the user enabled the checkbox."""
        if not props.clear_scene_before_build:
            return None
        from pae.blender_build import clear_pae_scene

        return clear_pae_scene()

else:  # pragma: no cover

    def structure_from_context(context):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def pipeline_input_from_context(context):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def apply_structure_values_to_props(props, values):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def apply_structure_spec_to_props(props, structure):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def scene_props(context):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def spec_from_context(context):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def apply_spec_to_props(props, spec):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def report_operator_exception(operator, props, exc):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def store_validation_report(props, report):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def report_validation_result(operator, props, report, *, prefix=""):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

    def maybe_clear_pae_scene(props):  # type: ignore[misc]
        raise ImportError("operator_utils requires bpy")

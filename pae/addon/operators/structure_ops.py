"""StructureSpec authoring operators (Master Plan §5)."""

from __future__ import annotations

from pathlib import Path

from pae.addon.bpy_bridge import HAS_BPY, sync_assembly_preview
from pae.addon.operator_utils import (
    apply_structure_values_to_props,
    maybe_clear_pae_scene,
    report_operator_exception,
    report_validation_result,
    scene_props,
    structure_from_context,
)
from pae.addon.pipeline_ui import run_full_pipeline
from pae.addon.structure_helpers import (
    GATEHOUSE_PRESET_YAML,
    default_level_sketch,
    parse_structure_yaml_to_ui_values,
)

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_UL_structure_levels(bpy.types.UIList):
        bl_idname = "PAE_UL_structure_levels"

        def draw_item(
            self,
            context,
            layout,
            data,
            item,
            icon,
            active_data,
            active_propname,
            index,
        ):
            if self.layout_type in {"DEFAULT", "COMPACT"}:
                row = layout.row(align=True)
                row.prop(item, "height_units", text="")
                preview = (item.sketch or "").split("\n")[0].strip() or "(empty)"
                row.label(text=f"L{index}: {preview[:18]}")

    class PAE_OT_structure_add_level(bpy.types.Operator):
        bl_idname = "pae.structure_add_level"
        bl_label = "Add Level"
        bl_description = "Append a level to the structure stack"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            props = scene_props(context)
            row = props.structure_levels.add()
            row.sketch = default_level_sketch(
                rows=max(1, props.bays_y),
                cols=max(1, props.bays_x),
            )
            row.height_units = 1
            row.wall_style = ""
            props.structure_active_level = len(props.structure_levels) - 1
            self.report({"INFO"}, f"Level {props.structure_active_level} added")
            return {"FINISHED"}

    class PAE_OT_structure_remove_level(bpy.types.Operator):
        bl_idname = "pae.structure_remove_level"
        bl_label = "Remove Level"
        bl_description = "Remove the active level from the stack"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            props = scene_props(context)
            if len(props.structure_levels) <= 1:
                self.report({"ERROR"}, "Structure requires at least one level")
                return {"CANCELLED"}
            index = min(props.structure_active_level, len(props.structure_levels) - 1)
            props.structure_levels.remove(index)
            props.structure_active_level = max(0, index - 1)
            self.report({"INFO"}, "Level removed")
            return {"FINISHED"}

    class PAE_OT_generate_from_structure(bpy.types.Operator):
        bl_idname = "pae.generate_from_structure"
        bl_label = "Generate Structure"
        bl_description = (
            "Build from Structure panel: StructureSpec → solve → plan → assemble → validate"
        )
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                if len(props.structure_levels) == 0:
                    bpy.ops.pae.structure_add_level()
                maybe_clear_pae_scene(props)
                structure = structure_from_context(context)
                _, _, assembly, report = run_full_pipeline(structure)
                if assembly is not None and assembly.placements:
                    sync_assembly_preview(assembly)
                ok, _msg = report_validation_result(
                    self, props, report, prefix="Structure"
                )
                return {"FINISHED"} if ok else {"CANCELLED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_load_structure_yaml(bpy.types.Operator):
        bl_idname = "pae.load_structure_yaml"
        bl_label = "Load Structure YAML"
        bl_description = "Load a Master Plan §3.1 YAML file into the Structure / Levels panels"
        bl_options = {"REGISTER", "UNDO"}

        filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore
        filter_glob: bpy.props.StringProperty(default="*.yaml;*.yml", options={"HIDDEN"})  # type: ignore

        def invoke(self, context, event):
            props = scene_props(context)
            self.filepath = bpy.path.abspath(props.structure_yaml_path)
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

        def execute(self, context):
            props = scene_props(context)
            path = Path(bpy.path.abspath(self.filepath))
            if not path.is_file():
                self.report({"ERROR"}, f"File not found: {path}")
                return {"CANCELLED"}
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}
            values, report = parse_structure_yaml_to_ui_values(text)
            if not report.ok or values is None:
                msg = report.failures[0].message if report.failures else "YAML parse failed"
                report_operator_exception(self, props, ValueError(msg))
                return {"CANCELLED"}
            apply_structure_values_to_props(props, values)
            props.structure_yaml_path = self.filepath
            props.last_error_message = ""
            props.last_pipeline_message = f"Loaded structure from {path.name}"
            self.report({"INFO"}, props.last_pipeline_message)
            return {"FINISHED"}

    class PAE_OT_export_structure_yaml(bpy.types.Operator):
        bl_idname = "pae.export_structure_yaml"
        bl_label = "Export Structure YAML"
        bl_description = "Write the current structure stack to a §3.1 YAML file"
        bl_options = {"REGISTER"}

        filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore
        filter_glob: bpy.props.StringProperty(default="*.yaml;*.yml", options={"HIDDEN"})  # type: ignore

        def invoke(self, context, event):
            props = scene_props(context)
            self.filepath = bpy.path.abspath(props.structure_yaml_path)
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

        def execute(self, context):
            props = scene_props(context)
            if len(props.structure_levels) == 0:
                self.report({"ERROR"}, "No levels to export — add a level first")
                return {"CANCELLED"}
            try:
                structure = structure_from_context(context)
                yaml_text = structure.to_yaml()
                path = Path(bpy.path.abspath(self.filepath))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml_text, encoding="utf-8")
            except (RuntimeError, ValueError, OSError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}
            props.structure_yaml_path = self.filepath
            props.last_pipeline_message = f"Exported structure YAML → {path.name}"
            props.last_error_message = ""
            self.report({"INFO"}, props.last_pipeline_message)
            return {"FINISHED"}

    class PAE_OT_load_gatehouse_preset(bpy.types.Operator):
        bl_idname = "pae.load_gatehouse_preset"
        bl_label = "Load Gatehouse Preset"
        bl_description = "Fill Structure / Levels from the §3.1 gatehouse example"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            props = scene_props(context)
            values, report = parse_structure_yaml_to_ui_values(GATEHOUSE_PRESET_YAML)
            if not report.ok or values is None:
                msg = report.failures[0].message if report.failures else "preset parse failed"
                report_operator_exception(self, props, ValueError(msg))
                return {"CANCELLED"}
            apply_structure_values_to_props(props, values)
            props.last_error_message = ""
            props.last_pipeline_message = "Gatehouse preset loaded"
            self.report({"INFO"}, props.last_pipeline_message)
            return {"FINISHED"}

    classes = (
        PAE_UL_structure_levels,
        PAE_OT_structure_add_level,
        PAE_OT_structure_remove_level,
        PAE_OT_generate_from_structure,
        PAE_OT_load_structure_yaml,
        PAE_OT_export_structure_yaml,
        PAE_OT_load_gatehouse_preset,
    )
else:
    classes = tuple()

"""Export operators — validation gate visible (§10)."""

from __future__ import annotations

from pae.addon.helpers import export_gate_allows, export_gate_message
from pae.addon.operator_utils import scene_props, spec_from_context
from pae.addon.pipeline_ui import run_full_pipeline
from pae.addon.properties import HAS_BPY
from pae.addon.session import report_from_json

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_OT_export_blend(bpy.types.Operator):
        bl_idname = "pae.export_blend"
        bl_label = "Export Blend"
        bl_description = "Export .blend (blocked when validation fails)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            report = report_from_json(props.validation_report_json)
            if not export_gate_allows(report):
                self.report({"ERROR"}, export_gate_message(report))
                return {"CANCELLED"}
            spec = spec_from_context(context)
            _, _, assembly, _ = run_full_pipeline(spec)
            if assembly is None:
                self.report({"ERROR"}, "No assembly to export")
                return {"CANCELLED"}
            from pae.export.blender import export_blend

            try:
                export_blend(assembly, props.export_blend_path)
            except NotImplementedError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Blend export requested: {props.export_blend_path}")
            return {"FINISHED"}

    class PAE_OT_export_fbx(bpy.types.Operator):
        bl_idname = "pae.export_fbx"
        bl_label = "Export FBX"
        bl_description = "Export FBX (blocked when validation fails)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            report = report_from_json(props.validation_report_json)
            if not export_gate_allows(report):
                self.report({"ERROR"}, export_gate_message(report))
                return {"CANCELLED"}
            from pae.export.fbx import export_fbx

            try:
                export_fbx(props.export_fbx_path)
            except NotImplementedError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"FBX export requested: {props.export_fbx_path}")
            return {"FINISHED"}

    classes = (PAE_OT_export_blend, PAE_OT_export_fbx)
else:
    classes = tuple()

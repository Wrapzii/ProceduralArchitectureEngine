"""Generate panel operators."""

from __future__ import annotations

from pae.addon.bpy_bridge import HAS_BPY, sync_assembly_preview
from pae.addon.operator_utils import scene_props, spec_from_context
from pae.addon.pipeline_ui import run_full_pipeline, run_stage
from pae.addon.session import report_to_json

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_OT_run_pipeline_stage(bpy.types.Operator):
        bl_idname = "pae.run_pipeline_stage"
        bl_label = "Run Stage"
        bl_description = "Run the selected pipeline stage"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            spec = spec_from_context(context)
            stage = props.pipeline_stage
            _, _, assembly, report = run_stage(stage, spec)
            if assembly is not None and assembly.placements:
                sync_assembly_preview(assembly)
            if stage == "validate":
                props.validation_report_json = report_to_json(report)
            props.last_pipeline_message = (
                f"{stage}: OK" if report.ok else f"{stage}: {len(report.critical)} critical"
            )
            self.report(
                {"INFO" if report.ok else "ERROR"},
                props.last_pipeline_message,
            )
            return {"FINISHED"}

    class PAE_OT_run_full_generate(bpy.types.Operator):
        bl_idname = "pae.run_full_generate"
        bl_label = "Generate Full Pipeline"
        bl_description = "spec → solve → plan → assemble → validate"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            spec = spec_from_context(context)
            _, _, assembly, report = run_full_pipeline(spec)
            if assembly is not None and assembly.placements:
                sync_assembly_preview(assembly)
            props.validation_report_json = report_to_json(report)
            props.last_pipeline_message = (
                "Generate OK" if report.ok else f"Generate: {len(report.critical)} critical"
            )
            self.report(
                {"INFO" if report.ok else "ERROR"},
                props.last_pipeline_message,
            )
            return {"FINISHED"}

    class PAE_OT_load_m1_preset(bpy.types.Operator):
        bl_idname = "pae.load_m1_preset"
        bl_label = "Load M1 Box House"
        bl_description = "Fill spec fields with the M1 milestone preset"
        bl_options = {"REGISTER"}

        def execute(self, context):
            from pae.spec import m1_box_house_spec

            spec = m1_box_house_spec()
            props = scene_props(context)
            props.building_name = spec.name
            props.style = spec.style
            props.storeys = spec.storeys
            props.bays_x = spec.footprint.bays_x
            props.bays_y = spec.footprint.bays_y
            props.footprint_kind = spec.footprint.kind
            props.seed = spec.seed
            self.report({"INFO"}, "M1 box house preset loaded")
            return {"FINISHED"}

    classes = (PAE_OT_run_pipeline_stage, PAE_OT_run_full_generate, PAE_OT_load_m1_preset)
else:
    classes = tuple()

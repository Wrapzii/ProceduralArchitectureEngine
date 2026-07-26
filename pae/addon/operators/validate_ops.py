"""Validation operators — frame defect (§10 highest-value feature)."""

from __future__ import annotations

from pae.addon.bpy_bridge import HAS_BPY, select_and_frame_failure, sync_assembly_preview
from pae.addon.operator_utils import (
    pipeline_input_from_context,
    report_operator_exception,
    report_validation_result,
    scene_props,
)
from pae.addon.pipeline_ui import run_full_pipeline
from pae.addon.session import report_from_json

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_OT_run_validate(bpy.types.Operator):
        bl_idname = "pae.run_validate"
        bl_label = "Run Validation"
        bl_description = "Assemble (if needed) and run the §7 validator"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                spec = pipeline_input_from_context(context)
                _, _, assembly, report = run_full_pipeline(spec)
                if assembly is not None and assembly.placements:
                    sync_assembly_preview(assembly)
                ok, _msg = report_validation_result(
                    self, props, report, prefix="Validate"
                )
                return {"FINISHED"} if ok else {"CANCELLED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_frame_defect(bpy.types.Operator):
        bl_idname = "pae.frame_defect"
        bl_label = "Frame Defect"
        bl_description = "Select and frame the object for this validation defect"
        bl_options = {"REGISTER"}

        failure_index: bpy.props.IntProperty(name="Failure Index", default=0)  # type: ignore

        def execute(self, context):
            props = scene_props(context)
            report = report_from_json(props.validation_report_json)
            if report is None or not report.failures:
                self.report({"WARNING"}, "No validation report — run Validate first")
                return {"CANCELLED"}
            if self.failure_index < 0 or self.failure_index >= len(report.failures):
                self.report({"WARNING"}, "Defect index out of range")
                return {"CANCELLED"}
            failure = report.failures[self.failure_index]
            if not select_and_frame_failure(failure, failure_index=self.failure_index):
                self.report({"WARNING"}, "Could not find object for defect")
                return {"CANCELLED"}
            self.report({"INFO"}, failure.check)
            return {"FINISHED"}

    classes = (PAE_OT_run_validate, PAE_OT_frame_defect)
else:
    classes = tuple()

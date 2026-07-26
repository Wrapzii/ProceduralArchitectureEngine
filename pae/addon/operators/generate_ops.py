"""Generate panel operators."""

from __future__ import annotations

from pae.addon.bpy_bridge import HAS_BPY, sync_assembly_preview
from pae.addon.operator_utils import (
    apply_spec_to_props,
    maybe_clear_pae_scene,
    report_operator_exception,
    report_validation_result,
    scene_props,
    spec_from_context,
    store_validation_report,
)
from pae.addon.pipeline_ui import run_full_pipeline, run_stage

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_OT_run_pipeline_stage(bpy.types.Operator):
        bl_idname = "pae.run_pipeline_stage"
        bl_label = "Run Stage"
        bl_description = "Run the selected pipeline stage"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                spec = spec_from_context(context)
                stage = props.pipeline_stage
                _, _, assembly, report = run_stage(stage, spec)
                if assembly is not None and assembly.placements:
                    sync_assembly_preview(assembly)
                if stage == "validate":
                    store_validation_report(props, report)
                ok, msg = report_validation_result(
                    self, props, report, prefix=stage
                )
                return {"FINISHED"} if ok else {"CANCELLED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_generate_current_spec(bpy.types.Operator):
        bl_idname = "pae.generate_current_spec"
        bl_label = "Generate Current Spec"
        bl_description = "Build from Spec panel fields: spec → solve → plan → assemble → validate"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                spec = spec_from_context(context)
                _, _, assembly, report = run_full_pipeline(spec)
                if assembly is not None and assembly.placements:
                    sync_assembly_preview(assembly)
                ok, _msg = report_validation_result(
                    self, props, report, prefix="Generate"
                )
                return {"FINISHED"} if ok else {"CANCELLED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_run_full_generate(bpy.types.Operator):
        bl_idname = "pae.run_full_generate"
        bl_label = "Generate Full Pipeline"
        bl_description = "Alias for Generate Current Spec"
        bl_options = {"REGISTER"}

        def execute(self, context):
            return bpy.ops.pae.generate_current_spec()

    class PAE_OT_load_m1_preset(bpy.types.Operator):
        bl_idname = "pae.load_m1_preset"
        bl_label = "Load M1 Box House"
        bl_description = "Fill spec fields with the M1 milestone preset"
        bl_options = {"REGISTER"}

        def execute(self, context):
            from pae.spec import m1_box_house_spec

            apply_spec_to_props(scene_props(context), m1_box_house_spec())
            self.report({"INFO"}, "M1 box house preset loaded")
            return {"FINISHED"}

    class PAE_OT_load_school_preset(bpy.types.Operator):
        bl_idname = "pae.load_school_preset"
        bl_label = "Load School Preset"
        bl_description = "Fill spec fields from school_academy_spec (single-building path)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            from pae.spec import school_academy_spec

            apply_spec_to_props(scene_props(context), school_academy_spec())
            self.report({"INFO"}, "School academy preset loaded into Spec panel")
            return {"FINISHED"}

    class PAE_OT_build_fortress(bpy.types.Operator):
        bl_idname = "pae.build_fortress"
        bl_label = "Generate Fortress"
        bl_description = "Compound fortress campus via pae.compound (preset connections)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                cleared = maybe_clear_pae_scene(props)
                from pae.blender_build import build_fortress_live

                result = build_fortress_live(
                    write_png=False,
                    skip_scene_clear=cleared is not None,
                )
                report = result.get("validation_report")
                if report is not None:
                    store_validation_report(props, report)
                if not result.get("ok"):
                    msg = (
                        f"Fortress failed — {len(report.critical) if report else '?'} critical"
                    )
                    props.last_pipeline_message = msg
                    self.report({"ERROR"}, msg)
                    return {"CANCELLED"}
                props.last_pipeline_message = (
                    f"Fortress OK ({result.get('placements', 0)} placements, "
                    f"{result.get('collection', 'PAE_Fortress')})"
                )
                props.last_error_message = ""
                self.report({"INFO"}, props.last_pipeline_message)
                return {"FINISHED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_build_school(bpy.types.Operator):
        bl_idname = "pae.build_school"
        bl_label = "Generate School"
        bl_description = "School academy showcase into PAE_School (validate → trim → re-validate)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                cleared = maybe_clear_pae_scene(props)
                from pae.blender_build import build_school_showcase

                result = build_school_showcase(
                    write_png=False,
                    skip_scene_clear=cleared is not None,
                )
                report = result.get("validation_report")
                if report is None:
                    milestones = result.get("milestones") or []
                    if milestones:
                        report = milestones[0].get("validation_report")
                if report is not None:
                    store_validation_report(props, report)
                milestones = result.get("milestones") or []
                placements = milestones[0].get("placements", 0) if milestones else 0
                if report is not None and not report.ok:
                    ok, _ = report_validation_result(
                        self, props, report, prefix="School"
                    )
                    return {"CANCELLED"}
                props.last_pipeline_message = (
                    f"School OK ({placements} placements, PAE_School)"
                )
                props.last_error_message = ""
                self.report({"INFO"}, props.last_pipeline_message)
                return {"FINISHED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_build_gallery(bpy.types.Operator):
        bl_idname = "pae.build_gallery"
        bl_label = "Build Gallery"
        bl_description = "M1–M4 (+ fortress) side-by-side collections under PAE_Gallery"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                cleared = maybe_clear_pae_scene(props)
                from pae.blender_build import build_gallery

                result = build_gallery(
                    write_png=False,
                    skip_scene_clear=cleared is not None,
                )
                report = result.get("validation_report")
                if report is not None:
                    store_validation_report(props, report)
                milestones = result.get("milestones") or []
                labels = ", ".join(m.get("label", "?") for m in milestones[:6])
                if report is not None and not report.ok:
                    report_validation_result(self, props, report, prefix="Gallery")
                    return {"CANCELLED"}
                props.last_pipeline_message = (
                    f"Gallery OK ({len(milestones)} milestones: {labels})"
                )
                props.last_error_message = ""
                self.report({"INFO"}, props.last_pipeline_message)
                return {"FINISHED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_reload_pae(bpy.types.Operator):
        bl_idname = "pae.reload_pae"
        bl_label = "Reload PAE"
        bl_description = "Drop cached pae.* modules so code edits take effect without restart"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                from pae.blender_build import reload_pae

                dropped = reload_pae()
                props.last_pipeline_message = f"Reloaded {len(dropped)} pae module(s)"
                props.last_error_message = ""
                self.report({"INFO"}, props.last_pipeline_message)
                return {"FINISHED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    classes = (
        PAE_OT_run_pipeline_stage,
        PAE_OT_generate_current_spec,
        PAE_OT_run_full_generate,
        PAE_OT_load_m1_preset,
        PAE_OT_load_school_preset,
        PAE_OT_build_fortress,
        PAE_OT_build_school,
        PAE_OT_build_gallery,
        PAE_OT_reload_pae,
    )
else:
    classes = tuple()

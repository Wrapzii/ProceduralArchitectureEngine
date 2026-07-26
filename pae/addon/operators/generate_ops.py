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
        bl_description = "Reload pae modules and re-register UI so new panels/props appear"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                from pae.blender_build import reload_pae

                dropped = reload_pae()
                import importlib

                import pae.addon as addon_pkg

                importlib.reload(addon_pkg)
                try:
                    addon_pkg.unregister()
                except Exception:
                    pass
                addon_pkg.register()
                props = scene_props(context)
                props.last_pipeline_message = (
                    f"Reloaded {len(dropped)} module(s); UI re-registered"
                )
                props.last_error_message = ""
                self.report({"INFO"}, props.last_pipeline_message)
                return {"FINISHED"}
            except (RuntimeError, ValueError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_copy_facade_params_json(bpy.types.Operator):
        bl_idname = "pae.copy_facade_params_json"
        bl_label = "Copy Parameters JSON"
        bl_description = "Copy Procedural Building slider params to the clipboard"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                from pae.facade_grammar import FacadeParams, export_params_json

                params = FacadeParams(
                    seed=int(props.facade_seed),
                    archetype=str(props.facade_archetype),
                    palette_family=str(props.facade_palette_family),
                    frontage_m=float(props.facade_frontage_m),
                    depth_m=float(props.facade_depth_m),
                    storeys=int(props.facade_storeys),
                    wealth=int(props.facade_wealth),
                    weathering=float(props.facade_weathering),
                    lit_windows=float(props.facade_lit_windows),
                    row_context=str(props.facade_row_context),
                )
                text = export_params_json(params)
                props.facade_params_json = text
                context.window_manager.clipboard = text
                props.last_pipeline_message = "Copied facade params JSON"
                self.report({"INFO"}, "Parameters JSON copied")
                return {"FINISHED"}
            except (RuntimeError, ValueError, AttributeError) as exc:
                report_operator_exception(self, props, exc)
                return {"CANCELLED"}

    class PAE_OT_generate_facade(bpy.types.Operator):
        bl_idname = "pae.generate_facade"
        bl_label = "Generate Building"
        bl_description = (
            "Build from Procedural Building sliders "
            "(facade grammar + shared door/stair ids)"
        )
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            try:
                maybe_clear_pae_scene(props)
                from pae.blender_build import (
                    CM_TO_M,
                    assembly_bounds_cm,
                    clear_pae_scene,
                    instance_facade_shell,
                )
                from pae.facade_grammar import (
                    FacadeParams,
                    build_from_params,
                    export_params_json,
                )

                params = FacadeParams(
                    seed=int(props.facade_seed),
                    archetype=str(props.facade_archetype or "georgian_merchant"),
                    palette_family=str(props.facade_palette_family or "cream_render"),
                    frontage_m=float(props.facade_frontage_m),
                    depth_m=float(props.facade_depth_m),
                    storeys=int(props.facade_storeys),
                    wealth=int(props.facade_wealth),
                    weathering=float(props.facade_weathering),
                    lit_windows=float(props.facade_lit_windows),
                    row_context=str(props.facade_row_context),
                )
                props.facade_params_json = export_params_json(params)
                _massing, _plan, assembly, report, _out = build_from_params(
                    params, validate_assembly=False
                )
                if assembly is not None and assembly.placements:
                    import bpy

                    coll_name = "PAE_GeorgianTownhouse"
                    clear_pae_scene()
                    coll = bpy.data.collections.get(coll_name)
                    if coll is None:
                        coll = bpy.data.collections.new(coll_name)
                        bpy.context.scene.collection.children.link(coll)
                    bb_min, _bb_max = assembly_bounds_cm(assembly)
                    offset_m = (
                        -bb_min[0] * CM_TO_M,
                        -bb_min[1] * CM_TO_M,
                        -bb_min[2] * CM_TO_M,
                    )
                    instance_facade_shell(
                        assembly,
                        label="facade",
                        target_coll=coll,
                        offset_m=offset_m,
                    )
                    sync_assembly_preview(assembly)
                store_validation_report(props, report)
                n = len(assembly.placements) if assembly else 0
                ok, _msg = report_validation_result(
                    self, props, report, prefix="Facade"
                )
                props.last_pipeline_message = (
                    f"Procedural Building OK ({n} placements)"
                    if ok
                    else f"Procedural Building — {len(report.critical)} critical"
                )
                return {"FINISHED"} if ok else {"CANCELLED"}
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
        PAE_OT_copy_facade_params_json,
        PAE_OT_generate_facade,
    )
else:
    classes = tuple()

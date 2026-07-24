"""Export operators — validation gate visible (§10). Wired to WP-6 APIs."""

from __future__ import annotations

from pae.addon.helpers import export_gate_allows, export_gate_message
from pae.addon.operator_utils import scene_props, spec_from_context
from pae.addon.pipeline_ui import run_full_pipeline
from pae.addon.properties import HAS_BPY
from pae.addon.session import report_from_json
from pae.export.gate import ExportRefused
from pae.validate import validate

if HAS_BPY:
    import bpy  # type: ignore

    def _assembly_and_report(context):
        props = scene_props(context)
        report = report_from_json(props.validation_report_json)
        if not export_gate_allows(report):
            return None, None, export_gate_message(report)
        spec = spec_from_context(context)
        _, _, assembly, _ = run_full_pipeline(spec)
        if assembly is None:
            return None, None, "No assembly to export"
        assembly, vreport = validate(assembly)
        return assembly, vreport, None

    class PAE_OT_export_blend(bpy.types.Operator):
        bl_idname = "pae.export_blend"
        bl_label = "Export Blend"
        bl_description = "Export .blend / linked-dupe plan (blocked when validation fails)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            assembly, vreport, err = _assembly_and_report(context)
            if err:
                self.report({"ERROR"}, err)
                return {"CANCELLED"}
            from pae.export.blender import export_blend

            try:
                plan, _rep, meta = export_blend(
                    assembly, props.export_blend_path, report=vreport
                )
            except ExportRefused as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            msg = meta.get("plan") or meta.get("blend") or f"{len(plan.instances)} instances"
            self.report({"INFO"}, f"Blend/plan export: {msg}")
            return {"FINISHED"}

    class PAE_OT_export_fbx(bpy.types.Operator):
        bl_idname = "pae.export_fbx"
        bl_label = "Export FBX"
        bl_description = "Export FBX / placement list (blocked when validation fails)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            assembly, vreport, err = _assembly_and_report(context)
            if err:
                self.report({"ERROR"}, err)
                return {"CANCELLED"}
            from pae.export.fbx import export_fbx

            try:
                _fbx, _rep, meta = export_fbx(
                    assembly, props.export_fbx_path, report=vreport
                )
            except ExportRefused as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            msg = meta.get("placement_list") or meta.get("fbx") or meta.get("note", "ok")
            self.report({"INFO"}, f"FBX/placements export: {msg}")
            return {"FINISHED"}

    class PAE_OT_export_manifest(bpy.types.Operator):
        bl_idname = "pae.export_manifest"
        bl_label = "Export UE Manifest"
        bl_description = "Write pae.manifest/1 JSON (blocked when validation fails)"
        bl_options = {"REGISTER"}

        def execute(self, context):
            props = scene_props(context)
            assembly, vreport, err = _assembly_and_report(context)
            if err:
                self.report({"ERROR"}, err)
                return {"CANCELLED"}
            from pae.export.manifest import export_manifest

            try:
                data, _rep = export_manifest(
                    assembly, props.export_manifest_path, report=vreport
                )
            except ExportRefused as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report(
                {"INFO"},
                f"Manifest export: {props.export_manifest_path} "
                f"({len(data.get('placements', []))} placements)",
            )
            return {"FINISHED"}

    classes = (PAE_OT_export_blend, PAE_OT_export_fbx, PAE_OT_export_manifest)
else:
    classes = tuple()

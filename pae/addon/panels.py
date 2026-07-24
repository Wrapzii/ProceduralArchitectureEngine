"""PAE sidebar panels (§10)."""

from __future__ import annotations

from pae.addon.helpers import build_validate_draw_groups, export_gate_allows, export_gate_message
from pae.addon.properties import HAS_BPY
from pae.addon.session import report_from_json

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_PT_spec(bpy.types.Panel):
        bl_label = "Spec"
        bl_idname = "PAE_PT_spec"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            layout.prop(props, "building_name")
            layout.prop(props, "style")
            layout.prop(props, "storeys")
            row = layout.row(align=True)
            row.prop(props, "bays_x")
            row.prop(props, "bays_y")
            layout.prop(props, "footprint_kind")
            layout.prop(props, "seed")
            layout.operator("pae.load_m1_preset", icon="PRESET")

    class PAE_PT_assets(bpy.types.Panel):
        bl_label = "Assets"
        bl_idname = "PAE_PT_assets"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            layout.label(text="Browse by tag (stub)")
            layout.prop(props, "asset_tag_filter")
            layout.operator("pae.browse_assets_stub", icon="ASSET_MANAGER")
            layout.label(text="Import / sockets: pae/assets/", icon="INFO")

    class PAE_PT_generate(bpy.types.Panel):
        bl_label = "Generate"
        bl_idname = "PAE_PT_generate"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            layout.prop(props, "pipeline_stage")
            layout.operator("pae.run_pipeline_stage", icon="PLAY")
            layout.operator("pae.run_full_generate", icon="MOD_BUILD")
            if props.last_pipeline_message:
                layout.label(text=props.last_pipeline_message, icon="TIME")

    class PAE_PT_validate(bpy.types.Panel):
        bl_label = "Validate"
        bl_idname = "PAE_PT_validate"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_options = {"DEFAULT_CLOSED"}

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            report = report_from_json(props.validation_report_json)

            row = layout.row()
            row.operator("pae.run_validate", icon="CHECKMARK")
            if report is None:
                layout.label(text="No report — Generate or Validate", icon="INFO")
                return

            icon = "CHECKMARK" if report.ok else "ERROR"
            layout.label(
                text=f"{'PASS' if report.ok else 'FAIL'} — {len(report.failures)} issue(s)",
                icon=icon,
            )

            groups = build_validate_draw_groups(report)
            if not groups:
                layout.label(text="No defects", icon="CHECKMARK")
                return

            for group in groups:
                box = layout.box()
                box.label(text=group.label, icon="ERROR" if group.severity == "critical" else "INFO")
                for item in group.items:
                    col = box.column(align=True)
                    op = col.operator(
                        "pae.frame_defect",
                        text=item.message[:72] + ("…" if len(item.message) > 72 else ""),
                        icon="ZOOM_SELECTED",
                    )
                    op.failure_index = item.index
                    sub = col.row()
                    sub.scale_y = 0.7
                    sub.label(text=f"{item.check}" + (f" → {item.select_id}" if item.select_id else ""))

    class PAE_PT_export(bpy.types.Panel):
        bl_label = "Export"
        bl_idname = "PAE_PT_export"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_options = {"DEFAULT_CLOSED"}

        def draw(self, context):
            props = context.scene.pae
            report = report_from_json(props.validation_report_json)
            layout = self.layout

            gate_ok = export_gate_allows(report)
            box = layout.box()
            box.label(text="Validation gate", icon="CHECKMARK" if gate_ok else "CANCEL")
            box.label(text=export_gate_message(report))

            col = layout.column()
            col.enabled = gate_ok
            col.prop(props, "export_blend_path")
            col.operator("pae.export_blend", icon="EXPORT")
            col.prop(props, "export_fbx_path")
            col.operator("pae.export_fbx", icon="EXPORT")
            col.prop(props, "export_manifest_path")
            col.operator("pae.export_manifest", icon="FILE_TEXT")

    classes = (
        PAE_PT_spec,
        PAE_PT_assets,
        PAE_PT_generate,
        PAE_PT_validate,
        PAE_PT_export,
    )
else:
    classes = tuple()

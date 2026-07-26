"""PAE sidebar panels (§10)."""

from __future__ import annotations

from pae.addon.helpers import build_validate_draw_groups, export_gate_allows, export_gate_message
from pae.addon.properties import HAS_BPY
from pae.addon.session import report_from_json

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_PT_structure(bpy.types.Panel):
        bl_label = "Structure"
        bl_idname = "PAE_PT_structure"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_options = {"DEFAULT_CLOSED"}
        bl_order = 1

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            layout.prop(props, "building_name", text="Name")
            layout.prop(props, "style")
            layout.prop(props, "seed")
            layout.separator()
            layout.prop(props, "structure_use_foundation")
            if props.structure_use_foundation:
                layout.prop(props, "structure_foundation_sketch", text="Foundation")
            layout.separator()
            row = layout.row(align=True)
            row.prop(props, "roof_kind")
            row.prop(props, "stair_kind")
            layout.prop(props, "roof_pitch")
            layout.separator()
            layout.prop(props, "structure_yaml_path", text="YAML")
            row = layout.row(align=True)
            row.operator("pae.load_structure_yaml", icon="IMPORT")
            row.operator("pae.export_structure_yaml", icon="EXPORT")
            row = layout.row(align=True)
            row.operator("pae.load_gatehouse_preset", icon="PRESET")
            row.operator("pae.generate_from_structure", icon="MOD_BUILD")
            layout.operator("pae.run_validate", icon="CHECKMARK")

    class PAE_PT_levels(bpy.types.Panel):
        bl_label = "Levels"
        bl_idname = "PAE_PT_levels"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_options = {"DEFAULT_CLOSED"}
        bl_order = 2

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout
            row = layout.row()
            row.template_list(
                "PAE_UL_structure_levels",
                "",
                props,
                "structure_levels",
                props,
                "structure_active_level",
                rows=4,
            )
            col = row.column(align=True)
            col.operator("pae.structure_add_level", icon="ADD", text="")
            col.operator("pae.structure_remove_level", icon="REMOVE", text="")

            if len(props.structure_levels) == 0:
                layout.label(text="No levels — click + to add", icon="INFO")
                return

            index = min(props.structure_active_level, len(props.structure_levels) - 1)
            level = props.structure_levels[index]
            box = layout.box()
            box.label(text=f"Level {index}", icon="LINENUMBERS_ON")
            box.prop(level, "height_units")
            box.prop(level, "wall_style")
            box.prop(level, "sketch", text="")

    class PAE_PT_procedural_building(bpy.types.Panel):
        """CITY&BEYOND-style Procedural Building parameters (primary generate path)."""

        bl_label = "Procedural Building"
        bl_idname = "PAE_PT_procedural_building"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_order = 0

        def draw(self, context):
            props = context.scene.pae
            layout = self.layout

            box = layout.box()
            box.label(text="Lot-driven facade grammar", icon="HOME")
            box.label(text="Shell + openings + shared interior IDs")

            col = layout.column(align=True)
            col.prop(props, "facade_seed", text="Seed")
            col.prop(props, "facade_archetype", text="Archetype")
            col.prop(props, "facade_palette_family", text="Palette Family")
            col.separator()
            col.prop(props, "facade_frontage_m")
            col.prop(props, "facade_depth_m")
            col.prop(props, "facade_storeys")
            col.prop(props, "facade_wealth")
            col.prop(props, "facade_weathering")
            col.prop(props, "facade_lit_windows")
            col.prop(props, "facade_row_context")
            col.prop(props, "facade_grit_district")

            layout.separator()
            row = layout.row(align=True)
            row.scale_y = 1.4
            row.operator("pae.generate_facade", text="Generate Building", icon="MOD_BUILD")
            layout.operator("pae.copy_facade_params_json", text="Copy Parameters JSON", icon="COPYDOWN")
            if props.facade_params_json:
                layout.label(text="JSON copied to clipboard / property", icon="INFO")

    class PAE_PT_spec(bpy.types.Panel):
        bl_label = "Spec (Legacy)"
        bl_idname = "PAE_PT_spec"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "PAE"
        bl_options = {"DEFAULT_CLOSED"}
        bl_order = 3

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
            row = layout.row(align=True)
            row.prop(props, "wing_depth")
            row.prop(props, "courtyard")
            layout.prop(props, "seed")

            box = layout.box()
            box.label(text="Roof / Height", icon="MOD_BUILD")
            box.prop(props, "roof_kind")
            box.prop(props, "roof_pitch")
            box.prop(props, "wall_height_storeys")

            box = layout.box()
            box.label(text="Circulation / Openings", icon="MOD_STAIR")
            box.prop(props, "stair_kind")
            row = box.row(align=True)
            row.prop(props, "doors_ground")
            row.prop(props, "windows_per_bay")

            box = layout.box()
            box.label(text="Entrance", icon="OUTLINER_OB_EMPTY")
            box.prop(props, "entrance_enabled")
            if props.entrance_enabled:
                box.prop(props, "entrance_role")
                box.prop(props, "entrance_facade")
                box.prop(props, "entrance_ensemble")

            row = layout.row(align=True)
            row.operator("pae.load_m1_preset", icon="PRESET")
            row.operator("pae.load_school_preset", icon="PRESET")

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
            layout.prop(props, "clear_scene_before_build")
            layout.separator()
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator("pae.generate_facade", text="Generate Procedural Building", icon="HOME")
            layout.operator("pae.generate_current_spec", icon="MOD_BUILD")
            row = layout.row(align=True)
            row.operator("pae.build_fortress", icon="HOME")
            row.operator("pae.build_school", icon="COMMUNITY")
            layout.operator("pae.build_gallery", icon="IMAGE")
            layout.operator("pae.reload_pae", text="Reload PAE (pick up UI)", icon="FILE_REFRESH")
            layout.separator()
            layout.label(text="Stage stepping (debug)", icon="SETTINGS")
            layout.prop(props, "pipeline_stage")
            layout.operator("pae.run_pipeline_stage", icon="PLAY")
            if props.last_pipeline_message:
                layout.label(text=props.last_pipeline_message, icon="TIME")
            if props.last_error_message:
                box = layout.box()
                box.label(text="Last error", icon="ERROR")
                box.label(text=props.last_error_message[:240])

            box = layout.box()
            box.label(text="Compound presets (CLI wiring)", icon="INFO")
            box.label(text="ConnectionPolicy / arcades / fitout")
            box.label(text="live in pae/compound.py — not")
            box.label(text="single-spec UI fields yet.")

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
        PAE_PT_procedural_building,
        PAE_PT_structure,
        PAE_PT_levels,
        PAE_PT_spec,
        PAE_PT_assets,
        PAE_PT_generate,
        PAE_PT_validate,
        PAE_PT_export,
    )
else:
    classes = tuple()

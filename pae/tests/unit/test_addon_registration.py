"""Add-on registration metadata (no bpy)."""

from __future__ import annotations

from pae.addon import bl_info
from pae.addon.helpers import bl_info_metadata
from pae.addon.panels import classes as panel_classes
from pae.addon.properties import PAESceneProperties


def test_bl_info_present():
    meta = bl_info_metadata()
    assert meta["name"] == "Procedural Architecture Engine"
    assert meta["blender"] >= (4, 0, 0)
    assert bl_info["version"] == (0, 2, 0)


def test_addon_modules_import_without_bpy():
    from pae.addon import helpers, pipeline_ui, session
    from pae.addon.bpy_bridge import HAS_BPY

    assert HAS_BPY is False
    assert helpers.list_style_ids()
    assert helpers.PIPELINE_STAGES
    assert session.report_from_json("") is None


def test_expected_operator_ids_registered_in_source():
    """Operator bl_idnames that Blender smoke test expects."""
    from pathlib import Path

    expected = {
        "pae.generate_current_spec",
        "pae.generate_from_structure",
        "pae.structure_add_level",
        "pae.structure_remove_level",
        "pae.load_structure_yaml",
        "pae.export_structure_yaml",
        "pae.load_gatehouse_preset",
        "pae.build_fortress",
        "pae.build_school",
        "pae.build_gallery",
        "pae.reload_pae",
        "pae.run_validate",
        "pae.frame_defect",
        "pae.run_pipeline_stage",
        "pae.load_m1_preset",
        "pae.load_school_preset",
        "pae.generate_facade",
        "pae.copy_facade_params_json",
    }
    src_root = Path(__file__).resolve().parents[2] / "addon" / "operators"
    text = "\n".join(p.read_text(encoding="utf-8") for p in src_root.glob("*.py"))
    missing = {op for op in expected if op.replace("pae.", "") not in text}
    assert not missing, f"missing operator bl_idname in source: {missing}"


def test_panel_ids():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "addon" / "panels.py"
    text = src.read_text(encoding="utf-8")
    for panel_id in (
        "PAE_PT_procedural_building",
        "PAE_PT_structure",
        "PAE_PT_levels",
        "PAE_PT_spec",
        "PAE_PT_generate",
        "PAE_PT_validate",
    ):
        assert panel_id in text
    if panel_classes:
        ids = {cls.bl_idname for cls in panel_classes}
        assert "PAE_PT_procedural_building" in ids
        assert "PAE_PT_structure" in ids
        assert "PAE_PT_levels" in ids


def test_scene_property_fields_declared_in_source():
    """Property names the UI/operators rely on (checked in source — no bpy in CI)."""
    from pathlib import Path

    text = Path(__file__).resolve().parents[2] / "addon" / "properties.py"
    src = text.read_text(encoding="utf-8")
    for field in (
        "roof_kind",
        "stair_kind",
        "wall_height_storeys",
        "clear_scene_before_build",
        "entrance_enabled",
        "last_error_message",
        "structure_levels",
        "structure_use_foundation",
        "structure_foundation_sketch",
        "structure_yaml_path",
        "facade_archetype",
        "facade_seed",
        "facade_palette_family",
        "facade_frontage_m",
        "facade_depth_m",
        "facade_storeys",
        "facade_wealth",
        "facade_weathering",
        "facade_lit_windows",
        "facade_row_context",
        "facade_grit_district",
        "facade_params_json",
    ):
        assert f"{field}:" in src, f"missing PAESceneProperties.{field}"
    assert PAESceneProperties is None or hasattr(PAESceneProperties, "roof_kind")

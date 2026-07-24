"""Add-on registration metadata (no bpy)."""

from __future__ import annotations

from pae.addon import bl_info
from pae.addon.helpers import bl_info_metadata


def test_bl_info_present():
    meta = bl_info_metadata()
    assert meta["name"] == "Procedural Architecture Engine"
    assert meta["blender"] >= (4, 0, 0)
    assert bl_info["version"] == (0, 1, 0)


def test_addon_modules_import_without_bpy():
    from pae.addon import helpers, pipeline_ui, session
    from pae.addon.bpy_bridge import HAS_BPY

    assert HAS_BPY is False
    assert helpers.list_style_ids()
    assert helpers.PIPELINE_STAGES
    assert session.report_from_json("") is None

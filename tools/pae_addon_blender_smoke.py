"""Blender 5.2 background smoke test for the installed PAE extension.

Runs without the GUI — exercises ``bl_ext.user_default.pae`` registration and
core operators the same way a user would from the N-panel.

Usage::

    blender --background --python tools/pae_addon_blender_smoke.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

MODULE = "bl_ext.user_default.pae"
EXPECTED_OPERATORS = (
    "pae.generate_current_spec",
    "pae.generate_from_structure",
    "pae.load_structure_yaml",
    "pae.export_structure_yaml",
    "pae.load_gatehouse_preset",
    "pae.structure_add_level",
    "pae.build_fortress",
    "pae.build_school",
    "pae.build_gallery",
    "pae.reload_pae",
    "pae.run_validate",
    "pae.frame_defect",
)


def _fail(msg: str) -> None:
    print("PAE_ADDON_SMOKE_FAIL", msg)
    raise SystemExit(1)


def main() -> None:
    try:
        import bpy  # type: ignore
    except ImportError:
        _fail("bpy not available — run inside Blender")

    import addon_utils

    loaded_mod = addon_utils.enable(MODULE, default_set=True, handle_error=None)
    if loaded_mod is None:
        _fail(f"could not enable extension {MODULE}")
    enabled = True

    # Force register (extension may lazy-load).
    mod = sys.modules.get(MODULE)
    if mod is None:
        _fail(f"module {MODULE} missing after enable")

    if hasattr(mod, "register"):
        try:
            mod.register()
        except ValueError:
            pass  # already registered

    missing = []
    # bpy.ops uses nested attributes — check via bpy.ops.pae
    pae_ops = getattr(bpy.ops, "pae", None)
    if pae_ops is None:
        _fail("bpy.ops.pae missing — operators not registered")
    for op_id in EXPECTED_OPERATORS:
        short = op_id.split(".", 1)[1]
        if not hasattr(pae_ops, short):
            missing.append(op_id)
    if missing:
        _fail(f"missing operators: {missing}")

    panels = [
        cls
        for cls in bpy.types.Panel.__subclasses__()
        if getattr(cls, "bl_category", "") == "PAE"
    ]
    if len(panels) < 6:
        _fail(f"expected >=6 PAE panels, got {len(panels)}")

    # Reload modules.
    result = bpy.ops.pae.reload_pae()
    if result != {"FINISHED"}:
        _fail(f"reload_pae returned {result}")

    # Lightweight generate from default spec (M1-sized defaults).
    bpy.context.scene.pae.building_name = "smoke_m1"
    bpy.context.scene.pae.bays_x = 4
    bpy.context.scene.pae.bays_y = 3
    bpy.context.scene.pae.storeys = 1
    bpy.context.scene.pae.clear_scene_before_build = True

    gen = bpy.ops.pae.generate_current_spec()
    if gen not in ({"FINISHED"}, {"CANCELLED"}):
        _fail(f"generate_current_spec returned {gen}")

    # StructureSpec path — gatehouse preset populates UI; simple box generates.
    bpy.ops.pae.load_gatehouse_preset()
    if len(bpy.context.scene.pae.structure_levels) < 3:
        _fail("load_gatehouse_preset did not populate structure_levels")

    bpy.context.scene.pae.structure_levels.clear()
    row = bpy.context.scene.pae.structure_levels.add()
    row.sketch = "####\n####\n"
    row.height_units = 1
    row.wall_style = ""
    bpy.context.scene.pae.structure_use_foundation = False
    bpy.context.scene.pae.building_name = "smoke_structure"
    bpy.context.scene.pae.clear_scene_before_build = True

    try:
        struct_gen = bpy.ops.pae.generate_from_structure()
    except RuntimeError:
        struct_gen = {"CANCELLED"}
    if struct_gen not in ({"FINISHED"}, {"CANCELLED"}):
        _fail(f"generate_from_structure returned {struct_gen}")

    report_raw = bpy.context.scene.pae.validation_report_json
    if not report_raw:
        _fail("generate_current_spec did not cache validation_report_json")

    val = bpy.ops.pae.run_validate()
    if val not in ({"FINISHED"}, {"CANCELLED"}):
        _fail(f"run_validate returned {val}")

    # Fortress compound — may take ~30s; fail-closed on critical.
    bpy.context.scene.pae.clear_scene_before_build = True
    try:
        fort = bpy.ops.pae.build_fortress()
    except RuntimeError:
        fort = {"CANCELLED"}
    if fort not in ({"FINISHED"}, {"CANCELLED"}):
        _fail(f"build_fortress returned {fort}")

    import bpy as _bpy

    collections = sorted(c.name for c in _bpy.data.collections if c.name.startswith("PAE_"))
    summary = {
        "module": MODULE,
        "enabled": enabled,
        "panels": [p.bl_idname for p in panels],
        "operators_ok": EXPECTED_OPERATORS,
        "generate_result": list(gen),
        "structure_generate_result": list(struct_gen),
        "structure_levels": len(bpy.context.scene.pae.structure_levels),
        "validate_result": list(val),
        "fortress_result": list(fort),
        "collections": collections,
        "last_message": bpy.context.scene.pae.last_pipeline_message,
        "report_ok": json.loads(report_raw).get("ok"),
    }
    out = REPO / "Saved" / "pae_addon_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PAE_ADDON_SMOKE_OK", json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        _fail("unhandled exception")

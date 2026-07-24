"""Asset browse stubs (§10 Assets panel)."""

from __future__ import annotations

from pae.addon.properties import HAS_BPY

if HAS_BPY:
    import bpy  # type: ignore

    class PAE_OT_browse_assets_stub(bpy.types.Operator):
        bl_idname = "pae.browse_assets_stub"
        bl_label = "Browse Asset DB"
        bl_description = "Stub — wire to pae.assets.db in a later pass"
        bl_options = {"REGISTER"}

        def execute(self, context):
            tag = context.scene.pae.asset_tag_filter
            self.report({"INFO"}, f"Asset browse stub (tag={tag!r}) — see pae/assets/db.py")
            return {"FINISHED"}

    classes = (PAE_OT_browse_assets_stub,)
else:
    classes = tuple()

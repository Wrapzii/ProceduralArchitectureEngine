"""Scene properties for the PAE add-on."""

from __future__ import annotations

from pae.addon.helpers import FOOTPRINT_KINDS, PIPELINE_STAGES, list_style_ids

try:
    import bpy  # type: ignore
    from bpy.props import (  # type: ignore
        BoolProperty,
        EnumProperty,
        IntProperty,
        PointerProperty,
        StringProperty,
    )
    from bpy.types import PropertyGroup  # type: ignore

    HAS_BPY = True
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    HAS_BPY = False


def _style_items(self, context):
    return [(sid, sid.replace("_", " ").title(), "") for sid in list_style_ids()] or [
        ("townhouse", "Townhouse", "")
    ]


def _footprint_items(self, context):
    return [(k, k.upper() if len(k) == 1 else k.title(), "") for k in FOOTPRINT_KINDS]


def _stage_items(self, context):
    return [(s, s.title(), "") for s in PIPELINE_STAGES]


if HAS_BPY:

    class PAESceneProperties(PropertyGroup):
        building_name: StringProperty(name="Name", default="pae_building")  # type: ignore
        style: EnumProperty(name="Style", items=_style_items, default="townhouse")  # type: ignore
        storeys: IntProperty(name="Storeys", default=1, min=1, max=12)  # type: ignore
        bays_x: IntProperty(name="Bays X", default=4, min=1, max=32)  # type: ignore
        bays_y: IntProperty(name="Bays Y", default=3, min=1, max=32)  # type: ignore
        footprint_kind: EnumProperty(name="Footprint", items=_footprint_items, default="rect")  # type: ignore
        seed: IntProperty(name="Seed", default=1, min=0)  # type: ignore
        pipeline_stage: EnumProperty(  # type: ignore
            name="Stage",
            items=_stage_items,
            default="solve",
        )
        validation_report_json: StringProperty(name="Validation JSON", default="")  # type: ignore
        last_pipeline_message: StringProperty(name="Pipeline", default="")  # type: ignore
        export_blend_path: StringProperty(  # type: ignore
            name="Blend Path",
            subtype="FILE_PATH",
            default="//pae_export.blend",
        )
        export_fbx_path: StringProperty(  # type: ignore
            name="FBX Path",
            subtype="FILE_PATH",
            default="//pae_export.fbx",
        )
        asset_tag_filter: StringProperty(name="Tag Filter", default="wall")  # type: ignore

    classes = (PAESceneProperties,)

else:
    PAESceneProperties = None  # type: ignore
    classes = tuple()

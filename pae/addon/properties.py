"""Scene properties for the PAE add-on."""

from __future__ import annotations

from pae.addon.helpers import (
    ENTRANCE_ROLES,
    FACADE_SIDES,
    FOOTPRINT_KINDS,
    PIPELINE_STAGES,
    ROOF_KINDS,
    STAIR_KINDS,
    list_style_ids,
)
from pae.addon.structure_helpers import DEFAULT_LEVEL_SKETCH

try:
    import bpy  # type: ignore
    from bpy.props import (  # type: ignore
        BoolProperty,
        EnumProperty,
        FloatProperty,
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


def _roof_items(self, context):
    return [(k, k.replace("_", " ").title(), "") for k in ROOF_KINDS]


def _stair_items(self, context):
    return [(k, k.replace("_", " ").title(), "") for k in STAIR_KINDS]


def _entrance_role_items(self, context):
    return [(r, r.replace("_", " ").title(), "") for r in ENTRANCE_ROLES]


def _facade_items(self, context):
    return [(f, f.title(), "") for f in FACADE_SIDES]


if HAS_BPY:

    class PAELevelSpecItem(PropertyGroup):
        height_units: IntProperty(name="Height Units", default=1, min=1, max=12)  # type: ignore
        sketch: StringProperty(  # type: ignore
            name="Sketch",
            description="ASCII sketch per Master Plan §3.1 (# built, . open, S stair, E entrance, T tower)",
            default=DEFAULT_LEVEL_SKETCH,
        )
        wall_style: StringProperty(  # type: ignore
            name="Wall Style",
            description="Optional per-level wall style (e.g. arcade)",
            default="",
        )

    class PAESceneProperties(PropertyGroup):
        building_name: StringProperty(name="Name", default="pae_building")  # type: ignore
        style: EnumProperty(name="Style", items=_style_items, default=0)  # type: ignore
        storeys: IntProperty(name="Storeys", default=1, min=1, max=12)  # type: ignore
        bays_x: IntProperty(name="Bays X", default=4, min=1, max=32)  # type: ignore
        bays_y: IntProperty(name="Bays Y", default=3, min=1, max=32)  # type: ignore
        footprint_kind: EnumProperty(name="Footprint", items=_footprint_items, default=0)  # type: ignore
        wing_depth: IntProperty(name="Wing Depth", default=2, min=1, max=12)  # type: ignore
        courtyard: BoolProperty(name="Courtyard", default=False)  # type: ignore
        seed: IntProperty(name="Seed", default=1, min=0)  # type: ignore
        roof_kind: EnumProperty(name="Roof Kind", items=_roof_items, default=0)  # type: ignore
        roof_pitch: FloatProperty(name="Roof Pitch", default=1.0, min=0.5, max=2.5)  # type: ignore
        stair_kind: EnumProperty(name="Stair Kind", items=_stair_items, default=0)  # type: ignore
        wall_height_storeys: FloatProperty(  # type: ignore
            name="Wall Height (storeys)",
            description="Envelope wall height in storeys; 0 = match building storeys",
            default=0.0,
            min=0.0,
            max=20.0,
        )
        doors_ground: IntProperty(name="Ground Doors", default=1, min=0, max=8)  # type: ignore
        windows_per_bay: IntProperty(name="Windows / Bay", default=1, min=0, max=4)  # type: ignore
        entrance_enabled: BoolProperty(name="Declare Entrance", default=False)  # type: ignore
        entrance_role: EnumProperty(  # type: ignore
            name="Entrance Role",
            items=_entrance_role_items,
            default=1,
        )
        entrance_facade: EnumProperty(name="Entrance Facade", items=_facade_items, default=0)  # type: ignore
        entrance_ensemble: BoolProperty(  # type: ignore
            name="Ensemble (arch + steps)",
            default=False,
        )
        clear_scene_before_build: BoolProperty(  # type: ignore
            name="Clear PAE Scene First",
            description="Remove prior PAE collections/objects before Gallery/Fortress/School builds",
            default=True,
        )
        pipeline_stage: EnumProperty(  # type: ignore
            name="Stage",
            items=_stage_items,
            default=0,
        )
        validation_report_json: StringProperty(name="Validation JSON", default="")  # type: ignore
        last_pipeline_message: StringProperty(name="Pipeline", default="")  # type: ignore
        last_error_message: StringProperty(name="Last Error", default="")  # type: ignore
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
        export_manifest_path: StringProperty(  # type: ignore
            name="Manifest Path",
            subtype="FILE_PATH",
            default="//pae_manifest.json",
        )
        asset_tag_filter: StringProperty(name="Tag Filter", default="wall")  # type: ignore
        structure_levels: bpy.props.CollectionProperty(type=PAELevelSpecItem)  # type: ignore
        structure_active_level: IntProperty(name="Active Level", default=0, min=0)  # type: ignore
        structure_use_foundation: BoolProperty(  # type: ignore
            name="Custom Foundation",
            description="When off, foundation defaults to the union of all level sketches",
            default=False,
        )
        structure_foundation_sketch: StringProperty(  # type: ignore
            name="Foundation Sketch",
            default="##########\n##########\n",
        )
        structure_yaml_path: StringProperty(  # type: ignore
            name="Structure YAML",
            subtype="FILE_PATH",
            default="//structure.yaml",
        )

    classes = (PAELevelSpecItem, PAESceneProperties,)

else:
    PAESceneProperties = None  # type: ignore
    classes = tuple()

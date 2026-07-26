"""Export package — Blender / FBX / UE manifest / terrain bind (§8)."""

from __future__ import annotations

from pae.export.blender import (
    BlenderRequired as BlendBlenderRequired,
    LinkedDuplicatePlan,
    LinkedInstance,
    export_blend,
    plan_linked_duplicates,
)
from pae.export.fbx import (
    BlenderRequired as FbxBlenderRequired,
    FbxPlacementRow,
    export_fbx,
    write_placement_list,
)
from pae.export.delivery import (
    DELIVERY_SCHEMA,
    check_artifact_consistency,
    run_delivery_batch,
    run_milestone_delivery,
)
from pae.export.gate import ExportRefused, ensure_exportable, validate_for_export
from pae.export.manifest import SCHEMA, build_manifest, export_manifest
from pae.export.materials import (
    MASK_CHANNEL_CONTRACT,
    MATERIAL_SLOT_BY_KIND,
    material_contract_block,
    material_slot_for,
    masks_from_tags,
    placement_material_fields,
)
from pae.export.spawn_groups import group_rows_by_asset_id
from pae.export.terrain import bind_to_terrain, sample_heightmap

__all__ = [
    "DELIVERY_SCHEMA",
    "MASK_CHANNEL_CONTRACT",
    "MATERIAL_SLOT_BY_KIND",
    "SCHEMA",
    "ExportRefused",
    "LinkedDuplicatePlan",
    "LinkedInstance",
    "FbxPlacementRow",
    "BlendBlenderRequired",
    "FbxBlenderRequired",
    "bind_to_terrain",
    "build_manifest",
    "check_artifact_consistency",
    "ensure_exportable",
    "group_rows_by_asset_id",
    "export_blend",
    "export_fbx",
    "export_manifest",
    "masks_from_tags",
    "material_contract_block",
    "material_slot_for",
    "placement_material_fields",
    "plan_linked_duplicates",
    "run_delivery_batch",
    "run_milestone_delivery",
    "sample_heightmap",
    "validate_for_export",
    "write_placement_list",
]

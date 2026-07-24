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
from pae.export.gate import ExportRefused, ensure_exportable, validate_for_export
from pae.export.manifest import SCHEMA, build_manifest, export_manifest
from pae.export.terrain import bind_to_terrain, sample_heightmap

__all__ = [
    "SCHEMA",
    "ExportRefused",
    "LinkedDuplicatePlan",
    "LinkedInstance",
    "FbxPlacementRow",
    "BlendBlenderRequired",
    "FbxBlenderRequired",
    "bind_to_terrain",
    "build_manifest",
    "ensure_exportable",
    "export_blend",
    "export_fbx",
    "export_manifest",
    "plan_linked_duplicates",
    "sample_heightmap",
    "validate_for_export",
    "write_placement_list",
]

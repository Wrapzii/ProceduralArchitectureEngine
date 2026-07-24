"""Blender bridge — select objects and frame defects (bpy behind try/import)."""

from __future__ import annotations

from typing import Tuple

from pae.addon.helpers import (
    cm_to_blender_location,
    frame_camera_from_bounds,
    frame_camera_from_world_point,
    piece_id_to_object_name,
)
from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import placement_world_aabb
from pae.report import Failure

try:
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore

    HAS_BPY = True
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore
    HAS_BPY = False

PAE_COLLECTION_NAME = "PAE_Building"
PAE_MARKER_PREFIX = "PAE_Marker_"


def require_bpy() -> None:
    if not HAS_BPY:
        raise RuntimeError("bpy is not available — enable the add-on inside Blender")


def _ensure_collection():
    require_bpy()
    coll = bpy.data.collections.get(PAE_COLLECTION_NAME)  # type: ignore[union-attr]
    if coll is None:
        coll = bpy.data.collections.new(PAE_COLLECTION_NAME)  # type: ignore[union-attr]
        bpy.context.scene.collection.children.link(coll)  # type: ignore[union-attr]
    return coll


def _placement_origin_m(placement: SolidPlacement) -> Tuple[float, float, float]:
    bb_min, _ = placement_world_aabb(
        placement.cell[0],
        placement.cell[1],
        placement.level,
        placement.yaw,
        placement.size_cm,
        placement.offset_cm,
        rotates_about_center=placement.rotates_about_center,
    )
    return cm_to_blender_location(bb_min)


def sync_assembly_preview(assembly: Assembly) -> int:
    """Create/update placeholder mesh cubes for each placement. Returns object count."""
    require_bpy()
    coll = _ensure_collection()
    count = 0
    for placement in assembly.placements:
        name = piece_id_to_object_name(placement.piece_id)
        sx, sy, sz = placement.size_cm
        size_m = (sx / 100.0, sy / 100.0, max(sz, 1.0) / 100.0)
        loc = _placement_origin_m(placement)
        obj = bpy.data.objects.get(name)  # type: ignore[union-attr]
        if obj is None:
            mesh = bpy.data.meshes.new(name)  # type: ignore[union-attr]
            obj = bpy.data.objects.new(name, mesh)  # type: ignore[union-attr]
            coll.objects.link(obj)
        obj.location = Vector(loc)  # type: ignore[union-attr]
        if obj.type != "MESH":
            continue
        mesh = obj.data
        if mesh is None:
            continue
        import bmesh  # type: ignore

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector(size_m), verts=bm.verts)  # type: ignore[union-attr]
        bmesh.ops.translate(
            bm,
            vec=Vector((size_m[0] * 0.5, size_m[1] * 0.5, size_m[2] * 0.5)),
            verts=bm.verts,
        )
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        obj["pae_piece_id"] = placement.piece_id
        count += 1
    return count


def _marker_name(failure_index: int) -> str:
    return f"{PAE_MARKER_PREFIX}{failure_index}"


def _ensure_marker_at(world_xyz_cm: Tuple[float, float, float], failure_index: int):
    require_bpy()
    name = _marker_name(failure_index)
    loc = cm_to_blender_location(world_xyz_cm)
    obj = bpy.data.objects.get(name)  # type: ignore[union-attr]
    if obj is None:
        obj = bpy.data.objects.new(name, None)  # type: ignore[union-attr]
        _ensure_collection().objects.link(obj)
        obj.empty_display_size = 0.5
        obj.empty_display_type = "SPHERE"
    obj.location = Vector(loc)  # type: ignore[union-attr]
    return obj


def select_and_frame_failure(
    failure: Failure,
    *,
    failure_index: int = 0,
) -> bool:
    """Select offending object (or marker at world_xyz) and frame the viewport."""
    require_bpy()
    target = None
    piece_id = failure.piece_id
    if piece_id:
        target = bpy.data.objects.get(piece_id_to_object_name(piece_id))  # type: ignore[union-attr]
    if target is None and failure.world_xyz is not None:
        target = _ensure_marker_at(failure.world_xyz, failure_index)
    if target is None:
        return False

    for obj in bpy.context.view_layer.objects:  # type: ignore[union-attr]
        obj.select_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target  # type: ignore[union-attr]

    region = bpy.context.region  # type: ignore[union-attr]
    if region and region.type == "WINDOW":
        with bpy.context.temp_override(  # type: ignore[union-attr]
            window=bpy.context.window,
            area=bpy.context.area,
            region=region,
        ):
            bpy.ops.view3d.view_selected(use_all_regions=False)  # type: ignore[union-attr]
    return True


def frame_world_point(world_xyz_cm: Tuple[float, float, float]) -> None:
    """Move the active 3D view to frame a world point (cm)."""
    require_bpy()
    frame = frame_camera_from_world_point(world_xyz_cm)
    _apply_view_frame(frame)


def frame_bounds(
    bb_min: Tuple[float, float, float],
    bb_max: Tuple[float, float, float],
) -> None:
    frame = frame_camera_from_bounds(bb_min, bb_max)
    _apply_view_frame(frame)


def _apply_view_frame(frame: dict) -> None:
    require_bpy()
    loc_cm = frame["location"]
    tgt_cm = frame["target"]
    loc = Vector(cm_to_blender_location(loc_cm))  # type: ignore[union-attr]
    tgt = Vector(cm_to_blender_location(tgt_cm))  # type: ignore[union-attr]
    for area in bpy.context.screen.areas:  # type: ignore[union-attr]
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type != "VIEW_3D":
                continue
            rv3d = space.region_3d
            if rv3d is None:
                continue
            direction = (loc - tgt).normalized()
            rv3d.view_location = tgt
            rv3d.view_distance = (loc - tgt).length
            rv3d.view_rotation = direction.to_track_quat("-Z", "Y")

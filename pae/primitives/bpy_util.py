"""Optional Blender mesh builders.

Import-safe outside Blender: ``HAS_BPY`` is False and ``build_*`` raises
``RuntimeError`` when bpy is missing. Geometry uses bmesh boxes / fans so
unit tests never need the editor.

Boolean gotchas (when cutters are used):
- Cut the **core** before joining decorative bands.
- ``modifier_apply`` requires the target active **and** selected.
- Blender 5.x solver enums are ``FLOAT`` / ``EXACT`` / ``MANIFOLD`` —
  never ``FAST`` (renamed to ``FLOAT`` in 5.0).

Agent re-runs: Blender caches modules — callers should
``importlib.reload`` this module (see ``pae.blender_build.reload_pae``).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

try:
    import bpy  # type: ignore
    import bmesh  # type: ignore
    from mathutils import Vector  # type: ignore

    HAS_BPY = True
except ImportError:  # pragma: no cover - exercised only inside Blender
    bpy = None  # type: ignore
    bmesh = None  # type: ignore
    Vector = None  # type: ignore
    HAS_BPY = False

Vec3 = Tuple[float, float, float]

# Arc tessellation: ≥ 96 segments per full circle (§ WP-3 / swarm prompt).
ARC_SEGMENTS_FULL = 96

# Blender 5.0+ BooleanModifier.solver enums (FAST was renamed to FLOAT).
BOOLEAN_SOLVERS = frozenset({"FLOAT", "EXACT", "MANIFOLD"})
DEFAULT_BOOLEAN_SOLVER = "EXACT"


def require_bpy() -> None:
    if not HAS_BPY:
        raise RuntimeError("bpy is not available — run inside Blender to build meshes")


def normalize_boolean_solver(solver: Optional[str] = None) -> str:
    """Map legacy / caller solver names onto Blender 5 enums.

    ``FAST`` is accepted as an alias for ``FLOAT`` but never written back as
    ``FAST`` (removed from the Blender 5 API).
    """
    raw = (solver or DEFAULT_BOOLEAN_SOLVER).strip().upper()
    if raw == "FAST":
        return "FLOAT"
    if raw not in BOOLEAN_SOLVERS:
        raise ValueError(
            f"boolean solver must be one of {sorted(BOOLEAN_SOLVERS)} "
            f"(or legacy FAST→FLOAT); got {solver!r}"
        )
    return raw


def safe_select_set(obj, value: bool) -> None:
    """Call ``obj.select_set`` only when *obj* is not None."""
    if obj is None:
        return
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(value)


def _deselect_all() -> None:
    require_bpy()
    view_layer = getattr(bpy.context, "view_layer", None)  # type: ignore[union-attr]
    objects = getattr(view_layer, "objects", None) if view_layer is not None else None
    if objects is None:
        return
    for obj in objects:
        safe_select_set(obj, False)


def set_active_selected(obj) -> None:
    """modifier_apply needs the target both active and selected; others deselected."""
    require_bpy()
    if obj is None:
        raise RuntimeError("set_active_selected: target object is None")
    _deselect_all()
    safe_select_set(obj, True)
    view_layer = bpy.context.view_layer  # type: ignore[union-attr]
    if view_layer is not None:
        view_layer.objects.active = obj


def default_link_collection(collection=None):
    """Collection to link new objects into.

    Prefer ``scene.collection`` — ``context.collection`` is flaky under MCP /
    background scripts / wrong area context.
    """
    require_bpy()
    if collection is not None:
        return collection
    scene = getattr(bpy.context, "scene", None)  # type: ignore[union-attr]
    if scene is not None:
        coll = getattr(scene, "collection", None)
        if coll is not None:
            return coll
    ctx_coll = getattr(bpy.context, "collection", None)  # type: ignore[union-attr]
    if ctx_coll is not None:
        return ctx_coll
    if scene is not None and scene.collection is not None:
        return scene.collection
    raise RuntimeError("no Blender collection available to link objects")


def new_empty_mesh_object(name: str, collection=None):
    require_bpy()
    mesh = bpy.data.meshes.new(name)  # type: ignore[union-attr]
    obj = bpy.data.objects.new(name, mesh)  # type: ignore[union-attr]
    coll = default_link_collection(collection)
    coll.objects.link(obj)
    return obj


def box_mesh(
    name: str,
    size_cm: Vec3,
    *,
    origin_at_min_corner: bool = True,
    location: Vec3 = (0.0, 0.0, 0.0),
    collection=None,
):
    """Create a rectangular solid. Default origin = min corner. Units = cm."""
    require_bpy()
    sx, sy, sz = size_cm
    obj = new_empty_mesh_object(name, collection=collection)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=bm.verts)
    if origin_at_min_corner:
        bmesh.ops.translate(bm, vec=Vector((sx * 0.5, sy * 0.5, sz * 0.5)), verts=bm.verts)
    bm.to_mesh(obj.data)
    bm.free()
    obj.location = Vector(location)
    return obj


def apply_boolean_difference(
    target,
    cutter,
    *,
    dissolve_cutter: bool = True,
    solver: str = DEFAULT_BOOLEAN_SOLVER,
) -> None:
    """Boolean DIFFERENCE on *target* using *cutter*. Cut core before joining bands."""
    require_bpy()
    if target is None or cutter is None:
        raise RuntimeError("apply_boolean_difference: target and cutter must be non-None")
    set_active_selected(target)
    mod = target.modifiers.new(name="PAE_Cut", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = normalize_boolean_solver(solver)
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)  # type: ignore[union-attr]
    if dissolve_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)  # type: ignore[union-attr]


def smooth_shade_curved_faces(obj, *, angle_deg: float = 30.0) -> None:
    """Smooth-shade only curved faces; leave flats sharp (arc kit pieces)."""
    require_bpy()
    set_active_selected(obj)
    bpy.ops.object.shade_smooth()  # type: ignore[union-attr]
    mesh = obj.data
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = angle_deg * 3.141592653589793 / 180.0


def _snap_axis_xy(x: float, y: float, *, eps: float = 1e-9) -> Tuple[float, float]:
    """Snap near-axis coordinates so quarter seams meet on cardinal axes."""
    if abs(x) < eps:
        x = 0.0
    if abs(y) < eps:
        y = 0.0
    return x, y


def mesh_aabb_from_verts(verts: Sequence[Vec3]) -> Tuple[Vec3, Vec3]:
    """Axis-aligned bounds of *verts* — import-safe (no bpy)."""
    if not verts:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def annulus_quarter_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, int, int, int]]]:
    """Author a 90° annular sector about the origin (centred piece).

    First quadrant: angles 0 → π/2. Origin at circle centre.
    """
    import math

    n = max(3, segments_full // 4)
    verts: List[Vec3] = []
    # bottom outer, bottom inner, top outer, top inner rings
    for z in (z0, z1):
        for r in (outer_r, inner_r):
            for i in range(n + 1):
                t = (i / n) * (math.pi * 0.5)
                x, y = _snap_axis_xy(r * math.cos(t), r * math.sin(t))
                verts.append((x, y, z))

    # indexing: 0:bot_outer, 1:bot_inner, 2:top_outer, 3:top_inner — each n+1 verts
    stride = n + 1

    def idx(ring: int, i: int) -> int:
        return ring * stride + i

    faces: List[Tuple[int, int, int, int]] = []
    for i in range(n):
        # outer wall
        faces.append((idx(0, i), idx(0, i + 1), idx(2, i + 1), idx(2, i)))
        # inner wall (reversed winding)
        faces.append((idx(1, i + 1), idx(1, i), idx(3, i), idx(3, i + 1)))
        # bottom
        faces.append((idx(0, i), idx(1, i), idx(1, i + 1), idx(0, i + 1)))
        # top
        faces.append((idx(2, i + 1), idx(3, i + 1), idx(3, i), idx(2, i)))
    # radial end caps at 0° and 90°
    faces.append((idx(0, 0), idx(2, 0), idx(3, 0), idx(1, 0)))
    faces.append((idx(0, n), idx(1, n), idx(3, n), idx(2, n)))
    return verts, faces


def annulus_ring_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, int, int, int]]]:
    """Full 360° annulus centred on the origin (tower crown parapet base)."""
    import math

    n = max(8, segments_full)
    verts: List[Vec3] = []
    for z in (z0, z1):
        for r in (outer_r, inner_r):
            for i in range(n):
                t = (i / n) * (2.0 * math.pi)
                x, y = _snap_axis_xy(r * math.cos(t), r * math.sin(t))
                verts.append((x, y, z))

    stride = n

    def idx(ring: int, i: int) -> int:
        return ring * stride + (i % n)

    faces: List[Tuple[int, int, int, int]] = []
    for i in range(n):
        i1 = (i + 1) % n
        faces.append((idx(0, i), idx(0, i1), idx(2, i1), idx(2, i)))
        faces.append((idx(1, i1), idx(1, i), idx(3, i), idx(3, i1)))
        faces.append((idx(0, i), idx(1, i), idx(1, i1), idx(0, i1)))
        faces.append((idx(2, i1), idx(3, i1), idx(3, i), idx(2, i)))
    return verts, faces


def annulus_battlement_ring_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    merlon_count: int = 12,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """Annular parapet with alternating merlons and gaps (centred tower crown)."""
    import math

    n = max(merlon_count * 4, segments_full)
    parapet_z = z0 + (z1 - z0) * 0.38
    verts: List[Vec3] = []
    # 0 bottom outer, 1 bottom inner, 2 parapet inner, 3 top outer (varying)
    for z in (z0, z0):
        for r in (outer_r, inner_r):
            for i in range(n):
                t = (i / n) * (2.0 * math.pi)
                x, y = _snap_axis_xy(r * math.cos(t), r * math.sin(t))
                verts.append((x, y, z))
    for i in range(n):
        t = (i / n) * (2.0 * math.pi)
        x, y = _snap_axis_xy(inner_r * math.cos(t), inner_r * math.sin(t))
        verts.append((x, y, parapet_z))
    for i in range(n):
        t = (i / n) * (2.0 * math.pi)
        x, y = _snap_axis_xy(outer_r * math.cos(t), outer_r * math.sin(t))
        is_merlon = (i * merlon_count) // n % 2 == 0
        z_top = z1 if is_merlon else parapet_z
        verts.append((x, y, z_top))

    stride = n

    def idx(ring: int, i: int) -> int:
        return ring * stride + (i % n)

    faces: List[Tuple[int, ...]] = []
    for i in range(n):
        i1 = (i + 1) % n
        faces.append((idx(0, i), idx(1, i), idx(1, i1), idx(0, i1)))
        faces.append((idx(1, i), idx(2, i), idx(2, i1), idx(1, i1)))
        faces.append((idx(0, i), idx(0, i1), idx(3, i1), idx(3, i)))
        faces.append((idx(3, i), idx(3, i1), idx(2, i1), idx(2, i)))
    return verts, faces


def cone_verts(
    base_r: float,
    z0: float,
    z1: float,
    *,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """Steep cone (or pyramid if segments_full is small) centred on the origin."""
    import math

    n = max(8, segments_full)
    verts: List[Vec3] = [(0.0, 0.0, z1)]
    apex = 0
    for i in range(n):
        t = (i / n) * (2.0 * math.pi)
        x, y = _snap_axis_xy(base_r * math.cos(t), base_r * math.sin(t))
        verts.append((x, y, z0))
    faces: List[Tuple[int, ...]] = []
    for i in range(n):
        i1 = (i + 1) % n
        faces.append((apex, i + 1, i1 + 1))
    return verts, faces


def mesh_from_verts_faces(
    name: str,
    verts: Sequence[Vec3],
    faces: Sequence[Sequence[int]],
    *,
    collection=None,
):
    require_bpy()
    obj = new_empty_mesh_object(name, collection=collection)
    bm = bmesh.new()
    bm_verts = [bm.verts.new(v) for v in verts]
    bm.verts.ensure_lookup_table()
    for f in faces:
        try:
            bm.faces.new([bm_verts[i] for i in f])
        except ValueError:
            continue
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    return obj

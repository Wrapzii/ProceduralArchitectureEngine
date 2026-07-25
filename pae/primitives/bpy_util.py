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
# Tower drum/crown/cap: denser cylinder so stacked storeys read straight, not puffy.
TOWER_ARC_SEGMENTS_FULL = 128

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


def _bmesh_add_axis_aligned_box(bm, origin: Vec3, size: Vec3) -> None:
    """Append a closed axis-aligned box (cm) to an existing *bm*."""
    ox, oy, oz = origin
    sx, sy, sz = size
    if sx <= 0.0 or sy <= 0.0 or sz <= 0.0:
        return
    v = [
        bm.verts.new((ox, oy, oz)),
        bm.verts.new((ox + sx, oy, oz)),
        bm.verts.new((ox + sx, oy + sy, oz)),
        bm.verts.new((ox, oy + sy, oz)),
        bm.verts.new((ox, oy, oz + sz)),
        bm.verts.new((ox + sx, oy, oz + sz)),
        bm.verts.new((ox + sx, oy + sy, oz + sz)),
        bm.verts.new((ox, oy + sy, oz + sz)),
    ]
    for face in (
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ):
        try:
            bm.faces.new([v[i] for i in face])
        except ValueError:
            continue


def build_box_with_rect_aperture_along_x(
    name: str,
    size_cm: Vec3,
    opening_min: Vec3,
    opening_max: Vec3,
    *,
    origin_at_min_corner: bool = True,
    location: Vec3 = (0.0, 0.0, 0.0),
    collection=None,
):
    """Solid box with a rectangular through-opening along +X (wall thickness).

    Builds sill / lintel / jambs as separate sub-boxes and welds them in bmesh —
    avoids boolean corner voids on door/window bases.  ``opening_*`` Y/Z are
    clamped to the wall interior; the opening spans the full wall thickness in X.
    """
    require_bpy()
    wx, wy, wz = size_cm
    _, oy0, oz0 = opening_min
    _, oy1, oz1 = opening_max
    oy0 = max(0.0, min(wy, oy0))
    oy1 = max(oy0, min(wy, oy1))
    oz0 = max(0.0, min(wz, oz0))
    oz1 = max(oz0, min(wz, oz1))

    eps = 1e-5
    parts: List[Tuple[Vec3, Vec3]] = []
    if oz0 > eps:
        parts.append(((0.0, 0.0, 0.0), (wx, wy, oz0)))
    if oz1 < wz - eps:
        parts.append(((0.0, 0.0, oz1), (wx, wy, wz - oz1)))
    if oy0 > eps:
        parts.append(((0.0, 0.0, oz0), (wx, oy0, oz1 - oz0)))
    if oy1 < wy - eps:
        parts.append(((0.0, oy1, oz0), (wx, wy - oy1, oz1 - oz0)))

    if not parts:
        return box_mesh(
            name,
            size_cm,
            origin_at_min_corner=origin_at_min_corner,
            location=location,
            collection=collection,
        )

    obj = new_empty_mesh_object(name, collection=collection)
    bm = bmesh.new()
    for part_origin, part_size in parts:
        _bmesh_add_axis_aligned_box(bm, part_origin, part_size)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.location = Vector(location)
    return obj


def apply_aperture_boolean_cut(
    target,
    cutter_min: Vec3,
    cutter_max: Vec3,
    *,
    solver: str = DEFAULT_BOOLEAN_SOLVER,
    dissolve_cutter: bool = True,
) -> None:
    """Boolean DIFFERENCE using an axis-aligned cutter box (EXACT/MANIFOLD only)."""
    require_bpy()
    size = (
        cutter_max[0] - cutter_min[0],
        cutter_max[1] - cutter_min[1],
        cutter_max[2] - cutter_min[2],
    )
    cutter = box_mesh(
        f"{target.name}_cut",
        size,
        origin_at_min_corner=True,
        location=cutter_min,
    )
    apply_boolean_difference(
        target,
        cutter,
        dissolve_cutter=dissolve_cutter,
        solver=solver,
    )


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


def _merge_mesh_parts(
    *parts: Tuple[List[Vec3], Sequence[Sequence[int]]],
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """Concatenate mesh parts with face index offsets."""
    verts: List[Vec3] = []
    faces: List[Tuple[int, ...]] = []
    offset = 0
    for part_verts, part_faces in parts:
        verts.extend(part_verts)
        for face in part_faces:
            faces.append(tuple(i + offset for i in face))
        offset += len(part_verts)
    return verts, faces


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
    cap_horizontal: bool = True,
    cap_radial: bool = True,
) -> Tuple[List[Vec3], List[Tuple[int, int, int, int]]]:
    """Author a 90° annular sector about the origin (centred piece).

    First quadrant: angles 0 → π/2. Origin at circle centre. Vertical walls
    share (x, y) columns from *z0* to *z1* so the outer surface is a true
    cylinder segment (not a torus-like ring stack). Set ``cap_horizontal``
    False for tower drums that stack storey-to-storey without doubled slabs.
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
        # outer wall — straight vertical quads
        faces.append((idx(0, i), idx(0, i + 1), idx(2, i + 1), idx(2, i)))
        # inner wall (reversed winding)
        faces.append((idx(1, i + 1), idx(1, i), idx(3, i), idx(3, i + 1)))
        if cap_horizontal:
            faces.append((idx(0, i), idx(1, i), idx(1, i + 1), idx(0, i + 1)))
            faces.append((idx(2, i + 1), idx(3, i + 1), idx(3, i), idx(2, i)))
    if cap_radial:
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
    cap_bottom: bool = True,
    cap_top: bool = True,
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
        if cap_bottom:
            faces.append((idx(0, i), idx(1, i), idx(1, i1), idx(0, i1)))
        if cap_top:
            faces.append((idx(2, i1), idx(3, i1), idx(3, i), idx(2, i)))
    return verts, faces


def _annular_wedge_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    t0: float,
    t1: float,
) -> Tuple[List[Vec3], List[Tuple[int, int, int, int]]]:
    """Small annular wedge (one merlon tooth) between angles *t0* and *t1*."""
    import math

    def corner(r: float, t: float, z: float) -> Vec3:
        x, y = _snap_axis_xy(r * math.cos(t), r * math.sin(t))
        return (x, y, z)

    verts = [
        corner(outer_r, t0, z0),
        corner(inner_r, t0, z0),
        corner(inner_r, t1, z0),
        corner(outer_r, t1, z0),
        corner(outer_r, t0, z1),
        corner(inner_r, t0, z1),
        corner(inner_r, t1, z1),
        corner(outer_r, t1, z1),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (3, 7, 6, 2),
        (0, 4, 7, 3),
        (1, 2, 6, 5),
    ]
    return verts, faces


def annulus_battlement_ring_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    merlon_count: int = 8,
    segments_full: int = TOWER_ARC_SEGMENTS_FULL,
    parapet_frac: float = 0.42,
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """Battlement crown: straight parapet drum + discrete merlon teeth on top.

    The lower ring is a true vertical annulus (drum continuation). Merlons are
    separate wedges above the parapet walk — not a wavy per-vertex outer ring.
    """
    import math

    parapet_z = z0 + (z1 - z0) * parapet_frac
    base_v, base_f = annulus_ring_verts(
        outer_r,
        inner_r,
        z0,
        parapet_z,
        segments_full=segments_full,
        cap_bottom=True,
        cap_top=False,
    )
    period = (2.0 * math.pi) / merlon_count
    tooth = period * 0.46
    merlon_parts: List[Tuple[List[Vec3], List[Tuple[int, int, int, int]]]] = []
    for m in range(merlon_count):
        if m % 2 == 1:
            continue
        t0 = m * period
        merlon_parts.append(
            _annular_wedge_verts(outer_r, inner_r, parapet_z, z1, t0, t0 + tooth)
        )
    return _merge_mesh_parts((base_v, base_f), *merlon_parts)


def cone_verts(
    base_r: float,
    z0: float,
    z1: float,
    *,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """Steep cone (or pyramid if segments_full is small) centred on the origin.

    Open base (no bottom cap) so the cap sits cleanly on the crown with a small
    intentional Z gap from assembly.
    """
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
        faces.append((apex, i1 + 1, i + 1))
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

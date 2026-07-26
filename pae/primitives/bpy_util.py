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


def build_mesh_from_box_parts(
    name: str,
    parts: Sequence[Tuple[Vec3, Vec3]],
    *,
    origin_at_min_corner: bool = True,
    location: Vec3 = (0.0, 0.0, 0.0),
    collection=None,
):
    """Weld axis-aligned box parts into one mesh object."""
    require_bpy()
    if not parts:
        return box_mesh(
            name,
            (0.0, 0.0, 0.0),
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
    from pae.primitives.walls import wall_aperture_frame_parts_cm

    require_bpy()
    wx, wy, wz = size_cm
    _, run0, z0 = opening_min
    _, run1, z1 = opening_max
    parts = wall_aperture_frame_parts_cm(size_cm, run0, run1, z0, z1)
    if not parts:
        return box_mesh(
            name,
            size_cm,
            origin_at_min_corner=origin_at_min_corner,
            location=location,
            collection=collection,
        )
    return build_mesh_from_box_parts(
        name,
        parts,
        origin_at_min_corner=origin_at_min_corner,
        location=location,
        collection=collection,
    )


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


def annulus_ring_door_cut_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    opening_width: float,
    opening_height: float,
    window_width: float = 0.0,
    window_sill: float = 0.0,
    window_height: float = 0.0,
    segments_full: int = ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, int, int, int]]]:
    """Full drum ring with a west door and optional windows on other faces.

    This is the stable mesh-authoring equivalent of subtracting a doorway
    cutter after the drum is placed.  It avoids Blender runtime booleans while
    preserving the continuous curved wall on both sides and above the opening.
    """
    import math

    n = max(24, int(segments_full))
    mid_r = max(1.0, (outer_r + inner_r) * 0.5)
    half_angle = math.asin(
        min(0.95, max(0.0, opening_width * 0.5 / mid_r))
    )
    window_half_angle = math.asin(
        min(0.95, max(0.0, window_width * 0.5 / mid_r))
    )
    door_top = min(z1, max(z0, z0 + opening_height))
    sill_top = min(z1, max(z0, z0 + window_sill))
    window_peak = min(z1, max(sill_top, sill_top + window_height))
    window_spring = sill_top + (window_peak - sill_top) * 0.58
    verts: List[Vec3] = []
    faces: List[Tuple[int, int, int, int]] = []

    def add_sector(
        a0: float,
        a1: float,
        low: float,
        high: float,
        *,
        cap_bottom: bool = False,
        cap_top: bool = False,
    ) -> None:
        base = len(verts)
        for z in (low, high):
            for radius in (outer_r, inner_r):
                for angle in (a0, a1):
                    verts.append(
                        (
                            radius * math.cos(angle),
                            radius * math.sin(angle),
                            z,
                        )
                    )
        # bottom outer 0,1; bottom inner 2,3; top outer 4,5; top inner 6,7
        faces.extend(
            [
                (base + 0, base + 1, base + 5, base + 4),
                (base + 3, base + 2, base + 6, base + 7),
            ]
        )
        if cap_bottom:
            faces.append((base + 0, base + 2, base + 3, base + 1))
        if cap_top:
            faces.append((base + 4, base + 5, base + 7, base + 6))

    def add_reveal(angle: float, low: float, high: float) -> None:
        """Close the masonry thickness only at a real opening jamb."""
        if high <= low:
            return
        base = len(verts)
        ca, sa = math.cos(angle), math.sin(angle)
        verts.extend(
            [
                (outer_r * ca, outer_r * sa, low),
                (inner_r * ca, inner_r * sa, low),
                (inner_r * ca, inner_r * sa, high),
                (outer_r * ca, outer_r * sa, high),
            ]
        )
        faces.append((base, base + 1, base + 2, base + 3))

    window_angles = (0.0, math.pi * 0.5, math.pi * 1.5)
    sector_classes: List[str] = []
    for index in range(n):
        a0 = (index / n) * math.tau
        a1 = ((index + 1) / n) * math.tau
        mid = (a0 + a1) * 0.5
        delta = abs((mid - math.pi + math.pi) % math.tau - math.pi)
        in_opening = delta <= half_angle
        if in_opening and door_top < z1:
            sector_classes.append("door")
            add_sector(a0, a1, door_top, z1, cap_bottom=True)
            continue
        in_window = any(
            abs((mid - angle + math.pi) % math.tau - math.pi)
            <= window_half_angle
            for angle in window_angles
        )
        if (
            in_window
            and window_width > 0.0
            and sill_top > z0
            and window_peak < z1
        ):
            sector_classes.append("window")
            nearest_delta = min(
                abs((mid - angle + math.pi) % math.tau - math.pi)
                for angle in window_angles
            )
            arch_t = max(
                0.0,
                1.0 - nearest_delta / max(window_half_angle, 1e-9),
            )
            shaped_top = window_spring + (
                window_peak - window_spring
            ) * arch_t
            add_sector(a0, a1, z0, sill_top, cap_top=True)
            add_sector(a0, a1, shaped_top, z1, cap_bottom=True)
        elif not in_opening:
            sector_classes.append("solid")
            add_sector(a0, a1, z0, z1)

    # Adjacent solid sectors share an edge and need no internal radial face.
    # Only opening transitions receive jamb/reveal geometry.
    for index, current in enumerate(sector_classes):
        previous = sector_classes[index - 1]
        if current == previous:
            continue
        angle = (index / n) * math.tau
        pair = {current, previous}
        if "door" in pair:
            add_reveal(angle, z0, door_top)
        elif "window" in pair:
            add_reveal(angle, sill_top, window_spring)
    return verts, faces


def annulus_quarter_window_cut_verts(
    outer_r: float,
    inner_r: float,
    z0: float,
    z1: float,
    *,
    opening_width: float,
    opening_sill: float,
    opening_height: float,
    segments_full: int = TOWER_ARC_SEGMENTS_FULL,
) -> Tuple[List[Vec3], List[Tuple[int, ...]]]:
    """First-quadrant drum sector with a pointed stair-light opening."""
    import math

    n = max(12, int(segments_full) // 4)
    mid_r = max(1.0, (outer_r + inner_r) * 0.5)
    half_angle = math.asin(
        min(0.95, max(0.0, opening_width * 0.5 / mid_r))
    )
    centre = math.pi * 0.25
    sill = min(z1, max(z0, z0 + opening_sill))
    peak = min(z1, max(sill, sill + opening_height))
    spring = sill + (peak - sill) * 0.58
    verts: List[Vec3] = []
    faces: List[Tuple[int, ...]] = []
    classes: List[str] = []

    def add_sector(
        a0: float,
        a1: float,
        low: float,
        high: float,
        *,
        cap_bottom: bool = False,
        cap_top: bool = False,
    ) -> None:
        base = len(verts)
        for z in (low, high):
            for radius in (outer_r, inner_r):
                for angle in (a0, a1):
                    verts.append(
                        (
                            radius * math.cos(angle),
                            radius * math.sin(angle),
                            z,
                        )
                    )
        faces.extend(
            [
                (base + 0, base + 1, base + 5, base + 4),
                (base + 3, base + 2, base + 6, base + 7),
            ]
        )
        if cap_bottom:
            faces.append((base + 0, base + 2, base + 3, base + 1))
        if cap_top:
            faces.append((base + 4, base + 5, base + 7, base + 6))

    def add_reveal(angle: float, low: float, high: float) -> None:
        base = len(verts)
        ca, sa = math.cos(angle), math.sin(angle)
        verts.extend(
            [
                (outer_r * ca, outer_r * sa, low),
                (inner_r * ca, inner_r * sa, low),
                (inner_r * ca, inner_r * sa, high),
                (outer_r * ca, outer_r * sa, high),
            ]
        )
        faces.append((base, base + 1, base + 2, base + 3))

    for index in range(n):
        a0 = (index / n) * (math.pi * 0.5)
        a1 = ((index + 1) / n) * (math.pi * 0.5)
        mid = (a0 + a1) * 0.5
        delta = abs(mid - centre)
        if delta <= half_angle and sill > z0 and peak < z1:
            classes.append("window")
            arch_t = max(0.0, 1.0 - delta / max(half_angle, 1e-9))
            shaped_top = spring + (peak - spring) * arch_t
            add_sector(a0, a1, z0, sill, cap_top=True)
            add_sector(a0, a1, shaped_top, z1, cap_bottom=True)
        else:
            classes.append("solid")
            add_sector(a0, a1, z0, z1)

    for index in range(1, n):
        if classes[index] == classes[index - 1]:
            continue
        add_reveal((index / n) * (math.pi * 0.5), sill, spring)
    # Close the two quarter seams; adjacent quarters meet these faces exactly.
    add_reveal(0.0, z0, z1)
    add_reveal(math.pi * 0.5, z0, z1)
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

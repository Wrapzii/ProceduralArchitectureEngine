"""Build an isolated multi-storey stair core in Blender for eyeball inspection.

Run inside Blender (BlenderMCP ``execute_blender_code`` or the Text Editor):

    exec(open(r"<repo>/tools/blender_stair_scene.py", encoding="utf-8").read())

Builds ONLY the stair core plus the decks it passes through, so nothing hides the
flights. Walls/roofs/apertures are dropped. Ground plane is kept for scale.
"""

import sys
from pathlib import Path

REPO = Path(r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import bpy  # noqa: E402


def _sketch(bx, by, sx, sy):
    return "\n".join(
        "".join("S" if (x == sx and y == sy) else "#" for x in range(bx))
        for y in range(by)
    )


CASES = [
    # label, style, bays_x, bays_y, storeys
    ("keep_4s", "keep", 9, 7, 4),
    ("townhouse_4s", "townhouse", 8, 5, 4),
]

# Only these kinds are instanced - everything else would hide the stair.
KEEP_KINDS = {"stair", "floor"}

# Keep deck only within this many bays of the stair core, otherwise a full-footprint
# deck roofs over the flights and you cannot see anything from outside.
CORE_PAD_BAYS = 2


def _core_window(assembly):
    from pae.trim import covered_cells

    core = set()
    for p in assembly.placements:
        if p.kind == "stair":
            core |= covered_cells(p)
    if not core:
        return None
    return (
        min(c[0] for c in core) - CORE_PAD_BAYS,
        max(c[0] for c in core) + CORE_PAD_BAYS,
        min(c[1] for c in core) - CORE_PAD_BAYS,
        max(c[1] for c in core) + CORE_PAD_BAYS,
    )


def _near_core(p, win):
    """Drop spanning decks whose cells all lie outside the stair-core window."""
    from pae.trim import covered_cells

    if win is None or p.kind == "stair":
        return True
    x0, x1, y0, y1 = win
    cells = covered_cells(p)
    return any(x0 <= cx <= x1 and y0 <= cy <= y1 for cx, cy in cells)


def build():
    from pae.blender_build import clear_pae_scene, instance_assembly, reload_pae
    from pae.pipeline import run_through_assemble
    from pae.sketch import sketch_to_spec

    reload_pae()
    clear_pae_scene()

    root = bpy.data.collections.get("PAE_StairProof")
    if root is None:
        root = bpy.data.collections.new("PAE_StairProof")
        bpy.context.scene.collection.children.link(root)

    out = []
    x_off = 0.0
    for label, style, bx, by, storeys in CASES:
        spec = sketch_to_spec(
            _sketch(bx, by, bx // 2, by // 2),
            name=label, style=style, storeys=storeys, seed=7,
        )
        _m, _fp, assembly, _rep = run_through_assemble(spec)
        if assembly is None:
            out.append(f"{label}: assemble failed")
            continue

        win = _core_window(assembly)
        trimmed = type(assembly)(
            **{
                **{
                    f: getattr(assembly, f)
                    for f in assembly.__dataclass_fields__
                },
                "placements": [
                    p
                    for p in assembly.placements
                    if p.kind in KEEP_KINDS and _near_core(p, win)
                ],
            }
        )

        sub = bpy.data.collections.new(f"PAE_Stair_{label}")
        root.children.link(sub)
        n = instance_assembly(
            trimmed, label=label, target_coll=sub, offset_m=(x_off, 0.0, 0.0)
        )
        stairs = [p for p in trimmed.placements if p.kind == "stair"]
        out.append(
            f"{label}: {n} instances, {len(stairs)} flights, "
            f"yaws={[p.yaw for p in sorted(stairs, key=lambda q: q.level)]}, "
            f"x_offset={x_off:.1f}m"
        )
        x_off += bx * 4.0 + 8.0

    return "\n".join(out)


print(build())

#!/usr/bin/env python3
"""Render the stair core of a multi-storey building without Blender.

Produces two proofs per case:
  * a per-storey plan strip - deck solid/open, the flight footprint and its climb
    arrow, so you can read straight off whether you can walk up
  * a 3D section of the stair core using the REAL deck meshes (holes punched by
    ``slab_with_rect_holes_verts_faces``) and the REAL stair meshes

    python tools/stair_core_proof.py [--storeys 4] [--out Saved/stair_proof]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

Cell = Tuple[int, int]

DECK_FACE = "#c9c4b6"
DECK_EDGE = "#6f6a5e"
STAIR_FACE = "#d98a4a"
STAIR_EDGE = "#8a4f22"
HOLE_FACE = "#2b3a4a"


def _sketch(bays_x: int, bays_y: int, stair_at: Cell) -> str:
    rows = []
    for y in range(bays_y):
        row = ["#"] * bays_x
        if y == stair_at[1]:
            row[stair_at[0]] = "S"
        rows.append("".join(row))
    return "\n".join(rows)


def _yaw_arrow(yaw: int) -> Tuple[float, float]:
    return {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}.get(int(yaw) % 360, (0, 0))


def plan_strip(name: str, assembly, out_png: Path) -> None:
    """Per-storey plan: solid deck, punched openings, flights and climb arrows."""
    from pae.contract import MODULE_CM
    from pae.stair_occupancy import landing_cells_for_stair
    from pae.trim import covered_cells

    solid: Dict[int, Set[Cell]] = {}
    hole: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "floor":
            continue
        bucket = hole if p.asset_id == "floor_hole" else solid
        bucket.setdefault(p.level, set()).update(covered_cells(p))

    stairs_by_level: Dict[int, list] = {}
    for p in assembly.placements:
        if p.kind == "stair" and "spiral" not in p.asset_id:
            stairs_by_level.setdefault(p.level, []).append(p)

    levels = sorted(set(solid) | set(hole) | set(stairs_by_level))
    if not levels:
        return
    all_cells = set()
    for s in solid.values():
        all_cells |= s
    for s in hole.values():
        all_cells |= s
    if not all_cells:
        return
    xs = [c[0] for c in all_cells]
    ys = [c[1] for c in all_cells]

    fig, axes = plt.subplots(1, len(levels), figsize=(3.2 * len(levels), 3.6))
    if len(levels) == 1:
        axes = [axes]
    for ax, level in zip(axes, levels):
        lvl_solid = solid.get(level, set()) - hole.get(level, set())
        for cx, cy in lvl_solid:
            ax.add_patch(Rectangle((cx, cy), 1, 1, facecolor=DECK_FACE, edgecolor=DECK_EDGE, lw=0.4))
        for cx, cy in hole.get(level, set()):
            ax.add_patch(Rectangle((cx, cy), 1, 1, facecolor=HOLE_FACE, edgecolor=DECK_EDGE, lw=0.4))
        # Flights standing on THIS deck.
        for st in stairs_by_level.get(level, []):
            cells = covered_cells(st)
            for cx, cy in cells:
                ax.add_patch(
                    Rectangle(
                        (cx, cy), 1, 1, facecolor=STAIR_FACE, edgecolor=STAIR_EDGE,
                        lw=1.0, alpha=0.85,
                    )
                )
            pads = {n: c for (n, c, _lv, _f, _t) in landing_cells_for_stair(st)}
            bot = pads.get("bottom")
            top = pads.get("top")
            if bot and top:
                dx, dy = _yaw_arrow(st.yaw)
                cxm = min(c[0] for c in cells) + 0.5
                cym = min(c[1] for c in cells) + 0.5
                ax.arrow(
                    cxm - dx * 0.4, cym - dy * 0.4, dx * 1.2, dy * 1.2,
                    head_width=0.28, head_length=0.28, fc=STAIR_EDGE, ec=STAIR_EDGE,
                    length_includes_head=True, zorder=5,
                )
                ax.plot(*[bot[0] + 0.5], *[bot[1] + 0.5], marker="o", ms=6,
                        color="#1c7c3f", zorder=6)
                ax.plot(*[top[0] + 0.5], *[top[1] + 0.5], marker="s", ms=6,
                        color="#b3261e", zorder=6)
        ax.set_xlim(min(xs) - 0.5, max(xs) + 1.5)
        ax.set_ylim(min(ys) - 0.5, max(ys) + 1.5)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"deck L{level}", fontsize=10)
    fig.suptitle(
        f"{name} — orange = flight on this deck, dark = opening, "
        "green dot = foot, red square = arrival",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def _placement_world_mesh(p, assembly):
    """Real verts/faces in world cm for decks (holes punched) and stairs."""
    from pae.blender_build import is_spanning_floor_deck, spanning_floor_hole_rects_cm
    from pae.contract import placement_origin_cm, rotate_local_xy
    from pae.primitives.floors import slab_with_rect_holes_verts_faces
    from pae.primitives.stairs import straight_stair_verts_faces

    # Build in LOCAL space then apply the engine's own yaw transform, exactly as
    # the Blender builder does - the stair mesh always ascends +X locally and the
    # placement yaw is what reverses a switchback flight.
    sx, sy, sz = p.size_cm

    if p.kind == "floor" and p.asset_id != "floor_hole":
        holes = []
        if is_spanning_floor_deck(p):
            hole_placements = [
                q for q in assembly.placements
                if q.asset_id == "floor_hole" and q.level == p.level
            ]
            holes = spanning_floor_hole_rects_cm(p, hole_placements)
        verts, faces = slab_with_rect_holes_verts_faces(sx, sy, sz, holes)
    elif p.kind == "stair":
        verts, faces = straight_stair_verts_faces(
            sx, sy, max(sz, 1.0), steps=12, along="x"
        )
    else:
        return None

    wx, wy, wz = placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)
    world = []
    for lx, ly, lz in verts:
        rx, ry = rotate_local_xy(lx, ly, p.yaw, sx, sy)
        world.append((wx + rx, wy + ry, wz + lz))
    return world, faces


def section_3d(name: str, assembly, out_png: Path, pad_bays: float = 1.5) -> None:
    """Isometric view of the stair core using real deck + stair meshes."""
    from pae.contract import MODULE_CM
    from pae.trim import covered_cells

    stairs = [p for p in assembly.placements if p.kind == "stair" and "spiral" not in p.asset_id]
    if not stairs:
        return
    core = set()
    for s in stairs:
        core |= covered_cells(s)
    cx0 = min(c[0] for c in core) - pad_bays
    cx1 = max(c[0] for c in core) + 1 + pad_bays
    cy0 = min(c[1] for c in core) - pad_bays
    cy1 = max(c[1] for c in core) + 1 + pad_bays
    xlim = (cx0 * MODULE_CM, cx1 * MODULE_CM)
    ylim = (cy0 * MODULE_CM, cy1 * MODULE_CM)

    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")

    def in_view(vs):
        return any(
            xlim[0] - 1 <= v[0] <= xlim[1] + 1 and ylim[0] - 1 <= v[1] <= ylim[1] + 1
            for v in vs
        )

    for p in assembly.placements:
        if p.kind not in ("floor", "stair") or p.asset_id == "floor_hole":
            continue
        mesh = _placement_world_mesh(p, assembly)
        if mesh is None:
            continue
        verts, faces = mesh
        if not in_view(verts):
            continue
        polys = [[verts[i] for i in f] for f in faces]
        # Clip to the core window so the rest of the building does not hide it.
        polys = [
            poly for poly in polys
            if all(xlim[0] - 1 <= v[0] <= xlim[1] + 1 for v in poly)
            and all(ylim[0] - 1 <= v[1] <= ylim[1] + 1 for v in poly)
        ]
        if not polys:
            continue
        is_stair = p.kind == "stair"
        ax.add_collection3d(
            Poly3DCollection(
                polys,
                facecolor=STAIR_FACE if is_stair else DECK_FACE,
                edgecolor=STAIR_EDGE if is_stair else DECK_EDGE,
                linewidths=0.25,
                alpha=1.0 if is_stair else 0.92,
            )
        )

    zs = [p.level for p in assembly.placements if p.kind in ("floor", "stair")]
    from pae.contract import STOREY_CM

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_zlim(-50, (max(zs) + 1.2) * STOREY_CM if zs else 1000)
    ax.set_box_aspect(
        (xlim[1] - xlim[0], ylim[1] - ylim[0], (max(zs) + 1.2) * STOREY_CM if zs else 1000)
    )
    ax.view_init(elev=18, azim=-58)
    ax.set_axis_off()
    ax.set_title(f"{name} — stair core section (real deck + stair meshes)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def main() -> int:
    from pae.pipeline import run_through_assemble
    from pae.sketch import sketch_to_spec

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="Saved/stair_proof")
    ap.add_argument("--storeys", type=int, nargs="*", default=[3, 4])
    args = ap.parse_args()
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for storeys in args.storeys:
        for style, (bx, by) in (("keep", (9, 7)), ("townhouse", (8, 5))):
            name = f"{style}_{bx}x{by}_{storeys}storey"
            spec = sketch_to_spec(
                _sketch(bx, by, (bx // 2, by // 2)),
                name=name, style=style, storeys=storeys, seed=7,
            )
            _m, _p, assembly, report = run_through_assemble(spec)
            if assembly is None:
                print(f"{name}: assembly failed")
                continue
            p1 = out_dir / f"{name}_plan.png"
            p2 = out_dir / f"{name}_section.png"
            plan_strip(name, assembly, p1)
            section_3d(name, assembly, p2)
            written += [str(p1), str(p2)]
            print(f"{name}: wrote plan + section")

    print("\n".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

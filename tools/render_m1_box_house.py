"""Render M1 box house from assembly placements (no Blender required)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "Saved" / "m1_placements.json").read_text(encoding="utf-8"))

COLORS = {
    "wall": "#8a8378",
    "floor": "#5c534a",
    "ground": "#3f4a38",
    "roof": "#3d4d6b",
}

FACES = [
    [0, 1, 2, 3],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]


def yaw_corners(loc, size, yaw):
    lx, ly, lz = loc
    sx, sy, sz = size
    local = np.array(
        [
            [0, 0, 0],
            [sx, 0, 0],
            [sx, sy, 0],
            [0, sy, 0],
            [0, 0, sz],
            [sx, 0, sz],
            [sx, sy, sz],
            [0, sy, sz],
        ],
        dtype=float,
    )
    r = np.radians(yaw)
    c, s = np.cos(r), np.sin(r)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return (local @ R.T) + np.array([lx, ly, lz])


def main() -> None:
    fig = plt.figure(figsize=(8, 6), dpi=140)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#d8e0e8")
    fig.patch.set_facecolor("#cfd8e2")

    all_pts = []
    for p in DATA["placements"]:
        corners = yaw_corners(p["loc_cm"], p["size_cm"], p["yaw"])
        all_pts.append(corners)
        polys = [[corners[i] for i in face] for face in FACES]
        pc = Poly3DCollection(
            polys,
            facecolors=COLORS.get(p["kind"], "#aaaaaa"),
            edgecolors="#222222",
            linewidths=0.35,
            alpha=0.92,
        )
        ax.add_collection3d(pc)

    pts = np.concatenate(all_pts, axis=0)
    mins, maxs = pts.min(axis=0), pts.max(axis=0)
    cx, cy = ((mins + maxs) / 2)[:2]
    span = float(max(maxs - mins))
    ax.set_xlim(cx - span / 2, cx + span / 2)
    ax.set_ylim(cy - span / 2, cy + span / 2)
    ax.set_zlim(mins[2], mins[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=28, azim=-55)
    ax.set_xlabel("X cm")
    ax.set_ylabel("Y cm")
    ax.set_zlabel("Z cm")
    ax.set_title(
        "PAE M1 Box House — 4×3 bays, 1 storey, door + 2 windows\n"
        f"validate ok · {DATA['n']} placements",
        fontsize=11,
    )
    ax.legend(
        handles=[Patch(color=c, label=k) for k, c in COLORS.items()],
        loc="upper left",
        fontsize=8,
    )

    out = ROOT / "Saved" / "Screenshots"
    out.mkdir(parents=True, exist_ok=True)
    png = out / "m1_box_house.png"
    fig.tight_layout()
    fig.savefig(png, dpi=140)
    print(png)
    print("extent_cm", (maxs - mins).tolist())


if __name__ == "__main__":
    main()

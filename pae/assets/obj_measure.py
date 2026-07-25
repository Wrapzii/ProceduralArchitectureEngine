"""Wavefront OBJ vertex bounds — Blender-optional measure helper (M5 demo)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

from pae.assets.import_ import MeasuredAABB

_Vertex = Tuple[float, float, float]


def _iter_obj_vertices(lines: Iterable[str]) -> Iterable[_Vertex]:
    for line in lines:
        if not line.startswith("v "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        yield (float(parts[1]), float(parts[2]), float(parts[3]))


def measure_obj_aabb(path: str | Path) -> MeasuredAABB:
    """Parse OBJ ``v`` lines and return the axis-aligned bounding box."""
    obj_path = Path(path)
    text = obj_path.read_text(encoding="utf-8")
    verts = list(_iter_obj_vertices(text.splitlines()))
    if not verts:
        raise ValueError(f"OBJ has no vertices: {obj_path}")

    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return MeasuredAABB(
        min_corner=(min(xs), min(ys), min(zs)),
        max_corner=(max(xs), max(ys), max(zs)),
    )


__all__ = ["measure_obj_aabb"]

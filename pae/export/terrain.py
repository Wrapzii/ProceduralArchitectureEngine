"""Terrain binding via heightmap sampling (§8.3) — never ray-cast."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Literal, Sequence, Tuple, Union

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, STOREY_CM, placement_origin_cm

TerrainMode = Literal["flatten_pad", "step_terraces", "stilts"]

Heightmap = Sequence[Sequence[float]]


def sample_heightmap(
    heightmap: Heightmap,
    x_cm: float,
    y_cm: float,
    *,
    origin_xy_cm: Tuple[float, float] = (0.0, 0.0),
    cell_size_cm: float = MODULE_CM,
) -> float:
    """Nearest-neighbour sample of a 2D heightmap array (Z in cm).

    Indices map as::

        ix = (x_cm - origin_x) / cell_size_cm
        iy = (y_cm - origin_y) / cell_size_cm

    Clamped to array bounds. **No ray-casting.**
    """
    if not heightmap or not heightmap[0]:
        raise ValueError("heightmap must be a non-empty 2D sequence")

    rows = len(heightmap)
    cols = len(heightmap[0])
    ox, oy = origin_xy_cm
    fx = (x_cm - ox) / cell_size_cm
    fy = (y_cm - oy) / cell_size_cm
    ix = int(round(fx))
    iy = int(round(fy))
    ix = max(0, min(cols - 1, ix))
    iy = max(0, min(rows - 1, iy))
    return float(heightmap[iy][ix])


def _placement_base_xy(p: SolidPlacement) -> Tuple[float, float]:
    wx, wy, _ = placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)
    # Sample near cell centre for terrace / stilts decisions.
    sx, sy, _ = p.size_cm
    return (wx + sx * 0.5, wy + sy * 0.5)


def _placement_min_z(p: SolidPlacement) -> float:
    _, _, wz = placement_origin_cm(p.cell[0], p.cell[1], p.level, p.offset_cm)
    return wz


def _with_z_delta(p: SolidPlacement, dz: float) -> SolidPlacement:
    ox, oy, oz = p.offset_cm
    return replace(p, offset_cm=(ox, oy, oz + dz))


def _footprint_sample_points(assembly: Assembly) -> list[Tuple[float, float]]:
    pts: list[Tuple[float, float]] = []
    for p in assembly.placements:
        pts.append(_placement_base_xy(p))
    return pts


def _terrace_step_cm() -> float:
    """Terrace quantum — one storey (from contract, not a magic literal)."""
    return STOREY_CM


def bind_to_terrain(
    assembly: Assembly,
    heightmap: Heightmap,
    mode: TerrainMode,
    *,
    origin_xy_cm: Tuple[float, float] = (0.0, 0.0),
    cell_size_cm: float = MODULE_CM,
    stilts_clearance_cm: Union[float, None] = None,
) -> Assembly:
    """Bind an assembly to a heightmap without ray-casting.

    Modes
    -----
    flatten_pad
        Sample the footprint; raise/lower the whole building so its lowest
        origin sits on the **median** sampled height (flat pad).
    step_terraces
        Per-placement: snap the local sample to the nearest storey terrace and
        shift that piece's Z so its origin sits on the terrace.
    stilts
        Keep relative structure; raise the whole building so its lowest origin
        sits at ``max(samples) + stilts_clearance_cm`` (gap left for stilts).
    """
    if mode not in ("flatten_pad", "step_terraces", "stilts"):
        raise ValueError(
            f"mode must be flatten_pad|step_terraces|stilts, got {mode!r}"
        )

    if stilts_clearance_cm is None:
        # Default clearance = one module quarter via contract MODULE (not a raw 100.0).
        stilts_clearance_cm = MODULE_CM * 0.25

    samples = [
        sample_heightmap(
            heightmap,
            x,
            y,
            origin_xy_cm=origin_xy_cm,
            cell_size_cm=cell_size_cm,
        )
        for x, y in _footprint_sample_points(assembly)
    ]
    if not samples:
        return deepcopy(assembly)

    if mode == "flatten_pad":
        ordered = sorted(samples)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            pad_z = ordered[mid]
        else:
            pad_z = 0.5 * (ordered[mid - 1] + ordered[mid])
        base_z = min(_placement_min_z(p) for p in assembly.placements)
        dz = pad_z - base_z
        new_placements = [_with_z_delta(p, dz) for p in assembly.placements]
        return replace(assembly, placements=new_placements)

    if mode == "stilts":
        top = max(samples)
        target = top + float(stilts_clearance_cm)
        base_z = min(_placement_min_z(p) for p in assembly.placements)
        dz = target - base_z
        new_placements = [_with_z_delta(p, dz) for p in assembly.placements]
        return replace(assembly, placements=new_placements)

    # step_terraces — shift each XY column as a unit so storeys stay relative.
    step = _terrace_step_cm()
    by_cell: dict[Tuple[int, int], list[SolidPlacement]] = {}
    for p in assembly.placements:
        by_cell.setdefault(p.cell, []).append(p)

    new_placements: list[SolidPlacement] = []
    for cell, pieces in by_cell.items():
        # Sample at cell centre (contract MODULE_CM — not a raw 400.0).
        x = cell[0] * cell_size_cm + cell_size_cm * 0.5
        y = cell[1] * cell_size_cm + cell_size_cm * 0.5
        h = sample_heightmap(
            heightmap,
            x,
            y,
            origin_xy_cm=origin_xy_cm,
            cell_size_cm=cell_size_cm,
        )
        terrace = round(h / step) * step
        lowest_level = min(p.level for p in pieces)
        base_z = min(
            _placement_min_z(p) for p in pieces if p.level == lowest_level
        )
        dz = terrace - base_z
        for p in pieces:
            new_placements.append(_with_z_delta(p, dz))
    return replace(assembly, placements=new_placements)


__all__ = [
    "TerrainMode",
    "Heightmap",
    "bind_to_terrain",
    "sample_heightmap",
]

"""Boundary-line placement for module-run pieces (barriers, arcades, kerbs).

WHY THIS EXISTS: trim and site both need to put a one-module-long piece on one edge of a
cell.  Getting that right means composing TWO offsets, and getting it wrong is the single
most expensive bug in this project's history:

  1. **Rotation compensation** (§2.2).  Yaw rotates about the piece's min-corner origin, so
     a piece yawed 90° lands in negative X and must be pushed back by its own size.  The
     first version of the trim stage skipped this and put parapets at x ∈ [−400, 0] —
     a full module outside the building, floating over nothing.
  2. **Boundary line** (§2.3).  North and east runs sit on the cell's FAR boundary
     (``+MODULE − thickness``), not on the cell origin.  Skipping this is what produced
     92 m wall gaps in the Unreal-era assembler.

Both are encoded here once, in one table, so no caller re-derives them from intuition.
"""

from __future__ import annotations

from typing import Tuple

from pae.contract import MODULE_CM

Face = str  # "south" | "north" | "west" | "east"

FACES = ("south", "north", "west", "east")

# Barriers/arcades are modelled thin on local X and one module long on local Y, so a run
# along the X axis (south/north faces) must be yawed 90°.
FACE_YAW = {"south": 90, "north": 90, "west": 0, "east": 0}

# Outward normal per face, for pieces that must face away from the building.
FACE_OUTWARD_YAW = {"south": 270, "north": 90, "west": 180, "east": 0}


def rotation_offset_cm(
    yaw: int,
    size_cm: Tuple[float, float, float],
) -> Tuple[float, float]:
    """Compensating offset so a yawed min-corner piece stays in its own cell (§2.2).

    yaw   0 -> X[0,sx]   Y[0,sy]   offset (0, 0)
    yaw  90 -> X[-sy,0]  Y[0,sx]   offset (+sy, 0)
    yaw 180 -> X[-sx,0]  Y[-sy,0]  offset (+sx, +sy)
    yaw 270 -> X[0,sy]   Y[-sx,0]  offset (0, +sx)
    """
    sx, sy = size_cm[0], size_cm[1]
    if yaw == 0:
        return (0.0, 0.0)
    if yaw == 90:
        return (sy, 0.0)
    if yaw == 180:
        return (sx, sy)
    if yaw == 270:
        return (0.0, sx)
    raise ValueError(f"yaw must be 0/90/180/270, got {yaw}")


def boundary_offset_cm(
    face: Face,
    size_cm: Tuple[float, float, float],
    *,
    yaw: int = None,
    module_cm: float = MODULE_CM,
    z_cm: float = 0.0,
) -> Tuple[float, float, float]:
    """Full offset placing a module-run piece on ``face`` of its cell.

    Composes the rotation compensation with the boundary line, so the resulting AABB lies
    inside the cell and flush against the requested edge.
    """
    if face not in FACE_YAW:
        raise ValueError(f"unknown face {face!r}; expected one of {FACES}")
    use_yaw = FACE_YAW[face] if yaw is None else yaw
    rx, ry = rotation_offset_cm(use_yaw, size_cm)
    thickness = size_cm[0]

    if face == "south":
        return (rx, ry, z_cm)
    if face == "north":
        return (rx, ry + module_cm - thickness, z_cm)
    if face == "west":
        return (rx, ry, z_cm)
    return (rx + module_cm - thickness, ry, z_cm)  # east


def outward_offset_cm(
    face: Face,
    size_cm: Tuple[float, float, float],
    *,
    module_cm: float = MODULE_CM,
    z_cm: float = 0.0,
) -> Tuple[int, Tuple[float, float, float]]:
    """Yaw + offset for a piece that must project OUTWARD from ``face`` (buttresses).

    Returns ``(yaw, offset_cm)``.  The piece's local +X points away from the wall, so the
    yaw comes from :data:`FACE_OUTWARD_YAW` rather than the run table.
    """
    yaw = FACE_OUTWARD_YAW[face]
    rx, ry = rotation_offset_cm(yaw, size_cm)
    depth = size_cm[0]
    if face == "south":
        return yaw, (rx, ry - depth, z_cm)
    if face == "north":
        return yaw, (rx, ry + module_cm, z_cm)
    if face == "west":
        return yaw, (rx - depth, ry, z_cm)
    return yaw, (rx + module_cm, ry, z_cm)  # east

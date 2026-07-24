"""Primitive descriptor types — Blender-free measurement contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

from pae.contract import MODULE_CM

Vec3 = Tuple[float, float, float]


def module_tag() -> str:
    """Socket compatibility tag derived from the grid module (never hard-coded)."""
    return f"module_{int(MODULE_CM)}"


@dataclass(frozen=True)
class SocketDesc:
    name: str
    pos_cm: Vec3
    normal: Vec3
    type: str
    tags: FrozenSet[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ApertureDesc:
    """Opening carved into a solid (window / door / arch / floor hole)."""

    kind: str
    min_cm: Vec3
    max_cm: Vec3

    @property
    def size_cm(self) -> Vec3:
        return (
            self.max_cm[0] - self.min_cm[0],
            self.max_cm[1] - self.min_cm[1],
            self.max_cm[2] - self.min_cm[2],
        )


@dataclass(frozen=True)
class PrimitiveDescriptor:
    """Declared kit piece — footprint, AABB, sockets, origin convention.

    ``size_cm`` is the axis-aligned bounding-box extent (max − min).
    ``aabb_min_cm`` is the AABB minimum relative to the piece origin.
    For ``origin == "min_corner"``, ``aabb_min_cm`` must be ``(0, 0, 0)``.
    Centred pieces (``rotates_about_center``) may have a negative min.
    """

    id: str
    kind: str
    footprint_modules: Tuple[int, int]
    height_storeys: float
    size_cm: Vec3
    sockets: Tuple[SocketDesc, ...]
    tags: FrozenSet[str]
    origin: str = "min_corner"
    rotates_about_center: bool = False
    aabb_min_cm: Vec3 = (0.0, 0.0, 0.0)
    aperture: Optional[ApertureDesc] = None
    notes: str = ""

    @property
    def aabb_max_cm(self) -> Vec3:
        return (
            self.aabb_min_cm[0] + self.size_cm[0],
            self.aabb_min_cm[1] + self.size_cm[1],
            self.aabb_min_cm[2] + self.size_cm[2],
        )

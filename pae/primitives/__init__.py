"""Parametric primitive library — WP-3.

Dual path:
1. Pure-Python ``PrimitiveDescriptor`` (footprint, size_cm, sockets, origin)
   — importable and testable without Blender.
2. Optional ``bpy`` mesh builders behind ``pae.primitives.bpy_util.HAS_BPY``.

Geometry authoring lives here; ``assemble.py`` only instances these pieces.
"""

from __future__ import annotations

from pae.primitives.catalog import all_descriptors, build_mesh, catalog_by_id, get, piece_ids
from pae.primitives.measure import (
    footprint_contract_errors,
    measurement_rows,
    measurement_table_markdown,
)
from pae.primitives.types import ApertureDesc, PrimitiveDescriptor, SocketDesc, module_tag

__all__ = [
    "ApertureDesc",
    "PrimitiveDescriptor",
    "SocketDesc",
    "all_descriptors",
    "build_mesh",
    "catalog_by_id",
    "footprint_contract_errors",
    "get",
    "measurement_rows",
    "measurement_table_markdown",
    "module_tag",
    "piece_ids",
]

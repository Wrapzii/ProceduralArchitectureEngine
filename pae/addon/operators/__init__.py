"""Operator package."""

from __future__ import annotations

from pae.addon.operators import assets_ops, export_ops, generate_ops, validate_ops

classes = (
    *validate_ops.classes,
    *generate_ops.classes,
    *export_ops.classes,
    *assets_ops.classes,
)

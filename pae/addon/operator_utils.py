"""Shared operator helpers (bpy-only)."""

from __future__ import annotations

from pae.addon.helpers import build_spec_from_ui
from pae.addon.properties import HAS_BPY

if not HAS_BPY:  # pragma: no cover
    raise ImportError("operator_utils requires bpy")


def scene_props(context):
    return context.scene.pae


def spec_from_context(context):
    props = scene_props(context)
    return build_spec_from_ui(
        name=props.building_name,
        style=props.style,
        storeys=props.storeys,
        bays_x=props.bays_x,
        bays_y=props.bays_y,
        footprint_kind=props.footprint_kind,
        seed=props.seed,
    )

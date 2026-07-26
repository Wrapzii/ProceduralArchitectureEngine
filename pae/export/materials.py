"""UE material slot + weathering mask contract for PAE exports.

PAE exports **real geometry** with per-piece ``material_slot`` ids and optional
mask channels. Surfacing (brick/stone normals, albedo) is authored in Unreal —
this module never invents baked textures.

Mask values are derived from Stage K detail tags (``wear:*``, ``dampness:*``,
``orient:*``, ``mat_var:*``, ``weather:*``) when present; otherwise zeros.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple, Union

# ---------------------------------------------------------------------------
# Kind → UE material slot name (assign MI / Nanite mesh material in-engine)
# ---------------------------------------------------------------------------

# Canonical slot names — stable contract for UE DataTables / MI params.
MATERIAL_SLOT_BY_KIND: Dict[str, str] = {
    "wall": "MI_Wall",
    "roof": "MI_Roof",
    "floor": "MI_Floor",
    "ground": "MI_Ground",
    "stair": "MI_Stair",
    "tower": "MI_Tower",
    "door": "MI_Door",
    "window": "MI_Window",
    "band": "MI_Trim",
    "trim": "MI_Trim",
    "plinth": "MI_Plinth",
    "cornice": "MI_Cornice",
    "prop": "MI_Prop",
    "barrier": "MI_Trim",
    "column": "MI_Trim",
    "roofline": "MI_Roof",
    "surface": "MI_Ground",
    "light_anchor": "None",
}

# Asset-id / tag refinements when ``kind`` alone is too coarse.
_ASSET_SLOT_PREFIXES: Tuple[Tuple[str, str], ...] = (
    ("wall_door", "MI_Door"),
    ("wall_window", "MI_Window"),
    ("door_", "MI_Door"),
    ("doorcase_", "MI_Trim"),
      ("forecourt_", "MI_Plinth"),
    ("planter_", "MI_Plinth"),
    ("porch_", "MI_Trim"),
    ("bargeboard", "MI_Trim"),
    ("chimney_stub", "MI_Roof"),
    ("window_sill", "MI_Trim"),
    ("window_hood", "MI_Trim"),
    ("window_box", "MI_Prop"),
    ("balcony_deck", "MI_Floor"),
    ("balcony_bracket", "MI_Trim"),
    ("window_", "MI_Window"),
    ("roof_", "MI_Roof"),
    ("stair_", "MI_Stair"),
    ("tower_", "MI_Tower"),
    ("floor", "MI_Floor"),
    ("ground", "MI_Ground"),
    ("band_", "MI_Trim"),
    ("coping_", "MI_Trim"),
)

_COURSE_TAG_SLOTS: Tuple[Tuple[str, str], ...] = (
    ("course:plinth", "MI_Plinth"),
    ("course:cornice", "MI_Cornice"),
    ("course:string", "MI_Trim"),
    ("course:bressummer", "MI_Trim"),
)

# Suggested vertex-color / PerInstanceCustomData channel map (documented contract).
MASK_CHANNEL_CONTRACT: Dict[str, Any] = {
    "schema": "pae.material_masks/1",
    "note": (
        "Metadata + suggested UE binding. PAE does not bake textures; "
        "UE materials read these as vertex colors or custom data floats."
    ),
    "vertex_color": {
        "R": "wear",
        "G": "dampness",
        "B": "height_band",
        "A": "streak",
    },
    "per_instance_custom_data": {
        "CustomData0": "wear",
        "CustomData1": "dampness",
        "CustomData2": "height_band",
        "CustomData3": "streak",
    },
    "orientation_field": "orientation",  # string on placement; optional CD encode
    "ranges": {
        "wear": "0.0..1.0 (none/low/medium/high → 0/0.25/0.55/0.9)",
        "dampness": "0.0..1.0 (none/base/damp → 0/0.65/0.85)",
        "height_band": "0.0..1.0 from mat_var:LN or level (N/max_levels)",
        "streak": "0.0 or 1.0",
    },
}

_WEAR_VALUES = {"wear:low": 0.25, "wear:medium": 0.55, "wear:high": 0.9}
_DAMP_VALUES = {"dampness:base": 0.65, "weather:damp": 0.85}

TagsLike = Union[Sequence[str], Set[str], frozenset]


def material_slot_for(
    kind: str,
    *,
    asset_id: str = "",
    tags: Optional[TagsLike] = None,
) -> str:
    """Resolve UE material slot name for a piece.

    Priority: course tags (plinth/cornice) → asset_id prefixes → kind map →
    ``MI_Generic``.
    """
    tag_set = frozenset(tags or ())
    for course_tag, slot in _COURSE_TAG_SLOTS:
        if course_tag in tag_set:
            return slot

    aid = asset_id or ""
    for prefix, slot in _ASSET_SLOT_PREFIXES:
        if aid.startswith(prefix) or aid == prefix.rstrip("_"):
            return slot

    if "window" in aid:
        return "MI_Window"
    if "door" in aid:
        return "MI_Door"

    slot = MATERIAL_SLOT_BY_KIND.get(kind)
    if slot is not None:
        return slot
    return "MI_Generic"


def _orientation_from_tags(tags: frozenset) -> Optional[str]:
    for t in tags:
        if t.startswith("orient:"):
            return t.split(":", 1)[1]
        if t.startswith("face:"):
            return t.split(":", 1)[1]
    return None


def _height_band_from_tags(tags: frozenset, level: int) -> float:
    for t in tags:
        if t.startswith("mat_var:L"):
            try:
                n = int(t[len("mat_var:L") :])
            except ValueError:
                continue
            # Map storey index into 0..1 (cap at L4).
            return max(0.0, min(1.0, n / 4.0))
    return max(0.0, min(1.0, float(level) / 4.0))


def masks_from_tags(
    tags: Optional[TagsLike] = None,
    *,
    level: int = 0,
) -> Dict[str, Any]:
    """Build consumable mask fields from Stage K / placement tags."""
    tag_set = frozenset(tags or ())
    wear = 0.0
    for key, val in _WEAR_VALUES.items():
        if key in tag_set:
            wear = max(wear, val)

    dampness = 0.0
    for key, val in _DAMP_VALUES.items():
        if key in tag_set:
            dampness = max(dampness, val)

    streak = 1.0 if "weather:streak" in tag_set else 0.0
    orientation = _orientation_from_tags(tag_set)
    height_band = _height_band_from_tags(tag_set, level)

    return {
        "wear": round(wear, 3),
        "dampness": round(dampness, 3),
        "height_band": round(height_band, 3),
        "streak": streak,
        "orientation": orientation,
        "channels": {
            "R": round(wear, 3),
            "G": round(dampness, 3),
            "B": round(height_band, 3),
            "A": streak,
        },
        "custom_data": [
            round(wear, 3),
            round(dampness, 3),
            round(height_band, 3),
            streak,
        ],
    }


def placement_material_fields(
    *,
    kind: str,
    asset_id: str,
    tags: Optional[TagsLike] = None,
    level: int = 0,
) -> Dict[str, Any]:
    """Fields to merge into a manifest / spawn placement row."""
    tag_set = frozenset(tags or ())
    return {
        "kind": kind,
        "material_slot": material_slot_for(kind, asset_id=asset_id, tags=tag_set),
        "masks": masks_from_tags(tag_set, level=level),
    }


def asset_material_slot(asset_id: str, kind_hint: str = "") -> str:
    """Default material slot for an ``assets[]`` / bind row."""
    return material_slot_for(kind_hint or "wall", asset_id=asset_id)


def material_contract_block() -> Dict[str, Any]:
    """Top-level manifest block documenting slots + mask channels for UE."""
    return {
        "schema": "pae.materials/1",
        "nanite": {
            "recommend": True,
            "note": (
                "Enable Nanite on imported static meshes. Geometric detail "
                "(bands, reveals, plinth/cornice) is real mesh — not baked normals."
            ),
        },
        "surfacing": (
            "Assign brick/stone/slate materials in UE. PAE does not export "
            "baked albedo/normal textures for architecture kits."
        ),
        "slots_by_kind": dict(MATERIAL_SLOT_BY_KIND),
        "mask_channels": MASK_CHANNEL_CONTRACT,
    }


def enrich_binding_with_material_slot(
    binding: Mapping[str, Any],
    *,
    kind_hint: str = "",
) -> Dict[str, Any]:
    """Copy a bind row and ensure ``material_slot`` is present."""
    row = dict(binding)
    asset_id = str(row.get("asset_id") or "")
    if not row.get("material_slot"):
        row["material_slot"] = asset_material_slot(asset_id, kind_hint=kind_hint)
    return row


__all__ = [
    "MASK_CHANNEL_CONTRACT",
    "MATERIAL_SLOT_BY_KIND",
    "asset_material_slot",
    "enrich_binding_with_material_slot",
    "masks_from_tags",
    "material_contract_block",
    "material_slot_for",
    "placement_material_fields",
]

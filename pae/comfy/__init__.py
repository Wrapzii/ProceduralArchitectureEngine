"""ComfyUI decorative asset pipeline (§9) — WP-8.

Decorative assets only (statues, banners, braziers, furniture, gargoyles, …).
Structural walls/floors/stairs are rejected. Generated textures are colour guides;
engine-authored materials ship.
"""

from pae.comfy.kinds import (
    DECORATIVE_KINDS,
    STRUCTURAL_KINDS,
    is_decorative,
    is_structural,
)
from pae.comfy.materials import (
    DEFAULT_MATERIAL_POLICY,
    MATERIAL_POLICY_VERSION,
    MaterialPolicy,
    TextureGuide,
)
from pae.comfy.normalize import (
    DEFAULT_LOD_TRI_BUDGET,
    GlbMetadata,
    NormalizeResult,
    normalize_glb_metadata,
    normalize_measured,
)
from pae.comfy.pipeline import (
    TAG_COMFY,
    TAG_CONFIRMED,
    TAG_NEEDS_CONFIRM,
    TAG_TEXTURE_GUIDE,
    ComfyIngestArtifact,
    ComfyIngestResult,
    confirm_decorative,
    ingest_decorative,
)
from pae.comfy.sockets_decor import propose_decorative_sockets

__all__ = [
    "DECORATIVE_KINDS",
    "DEFAULT_LOD_TRI_BUDGET",
    "DEFAULT_MATERIAL_POLICY",
    "MATERIAL_POLICY_VERSION",
    "STRUCTURAL_KINDS",
    "TAG_COMFY",
    "TAG_CONFIRMED",
    "TAG_NEEDS_CONFIRM",
    "TAG_TEXTURE_GUIDE",
    "ComfyIngestArtifact",
    "ComfyIngestResult",
    "GlbMetadata",
    "MaterialPolicy",
    "NormalizeResult",
    "TextureGuide",
    "confirm_decorative",
    "ingest_decorative",
    "is_decorative",
    "is_structural",
    "normalize_glb_metadata",
    "normalize_measured",
    "propose_decorative_sockets",
]

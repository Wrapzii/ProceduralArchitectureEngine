"""Material / texture policy for Comfy-generated assets (§9.1, §9.3).

Generated paint passes are a **colour guide**, never shipping textures.
Engine-authored materials (UE/Blender) own the final look.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Policy constants (not grid dimensions).
MATERIAL_POLICY_VERSION = "1"


@dataclass(frozen=True)
class TextureGuide:
    """Reference to a generated texture used only as a colour guide."""

    path: Optional[str] = None
    notes: str = (
        "Generated textures carry baked lighting and wrong palettes; "
        "use as desaturated colour reference only."
    )


@dataclass(frozen=True)
class MaterialPolicy:
    """How PAE treats materials for a Comfy ingest."""

    engine_authored: bool = True
    generated_texture_is_guide_only: bool = True
    prefer_triplanar_for_kit: bool = True
    texture_guide: Optional[TextureGuide] = None
    policy_version: str = MATERIAL_POLICY_VERSION

    def summary(self) -> str:
        return (
            "engine-authored materials; generated paint = colour guide only; "
            "kit pieces default to triplanar world-space (§9.3)"
        )


DEFAULT_MATERIAL_POLICY = MaterialPolicy(
    texture_guide=TextureGuide(),
)

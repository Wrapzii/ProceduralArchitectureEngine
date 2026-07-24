"""Decorative vs structural kind gates (§9).

ComfyUI / image-to-3D may only produce decorative assets. Structural kit pieces
must come from parametric code (WP-3) so they hit exact module dimensions.
"""

from __future__ import annotations

from typing import FrozenSet

# Spec §9 table — decorative / bespoke only on this path.
DECORATIVE_KINDS: FrozenSet[str] = frozenset(
    {
        "statue",
        "banner",
        "brazier",
        "furniture",
        "gargoyle",
        "fountain",
        "prop",
        "hero",  # bespoke hero pieces (throne, great door) — still decorative path
    }
)

# Structural kinds — rejected by the Comfy ingest path.
STRUCTURAL_KINDS: FrozenSet[str] = frozenset(
    {
        "wall",
        "floor",
        "stair",
        "roof",
        "tower_arc",
        "tower_crown",
        "tower_cap",
        "battlement",
        "plinth",
        "ground",
        "arch",
        "arcade",
    }
)


def normalize_kind(kind: str) -> str:
    return kind.strip().lower()


def is_decorative(kind: str) -> bool:
    return normalize_kind(kind) in DECORATIVE_KINDS


def is_structural(kind: str) -> bool:
    return normalize_kind(kind) in STRUCTURAL_KINDS


def reject_structural_message(kind: str) -> str:
    k = normalize_kind(kind)
    return (
        f"kind '{k}' is structural — ComfyUI path accepts decorative assets only "
        f"({', '.join(sorted(DECORATIVE_KINDS))}); use parametric primitives for kit pieces"
    )

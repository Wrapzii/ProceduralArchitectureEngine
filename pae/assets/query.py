"""Tag / kind queries over AssetDB (§4, M5).

Generator stages call these helpers — adding a confirmed decorative asset to the
DB is enough for decorate to pick it up; no assemble / solver code change.
"""

from __future__ import annotations

from typing import List, Optional, Set

from pae.assets.db import Asset, AssetDB
from pae.comfy.kinds import DECORATIVE_KINDS
from pae.comfy.pipeline import TAG_CONFIRMED, TAG_NEEDS_CONFIRM

# Default filter for generator decoration — confirmed decorative only.
DEFAULT_DECOR_TAGS: frozenset[str] = frozenset({"decorative", TAG_CONFIRMED})


def list_by_tags(
    db: AssetDB,
    tags: Optional[Set[str]] = None,
    *,
    kind: Optional[str] = None,
) -> List[Asset]:
    """Return assets whose tag set is a superset of ``tags`` (and optional kind)."""
    return db.list_assets(kind=kind, tags=set(tags) if tags else None)


def list_decorative_for_generator(
    db: AssetDB,
    *,
    tags: Optional[Set[str]] = None,
    require_confirmed: bool = True,
) -> List[Asset]:
    """Assets eligible for decorate placement without code changes.

    Requires decorative kind (or ``decorative`` tag) and, by default,
    ``human_confirmed``. Skips ``needs_human_confirm``.
    """
    required = set(tags) if tags is not None else set(DEFAULT_DECOR_TAGS)
    if require_confirmed:
        required.add(TAG_CONFIRMED)
        required.discard(TAG_NEEDS_CONFIRM)

    out: List[Asset] = []
    for asset in db.list_assets(tags=required if required else None):
        if TAG_NEEDS_CONFIRM in asset.tags and require_confirmed:
            continue
        kind_ok = asset.kind in DECORATIVE_KINDS or "decorative" in asset.tags
        if not kind_ok:
            continue
        out.append(asset)
    out.sort(key=lambda a: a.id)
    return out


__all__ = [
    "DEFAULT_DECOR_TAGS",
    "list_by_tags",
    "list_decorative_for_generator",
]

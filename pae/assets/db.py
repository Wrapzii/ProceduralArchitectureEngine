"""SQLite asset DB (§4) — WP-2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


@dataclass
class Socket:
    name: str
    pos_cm: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    type: str
    tags: Set[str] = field(default_factory=set)


@dataclass
class Asset:
    id: str
    path: str
    kind: str
    footprint_modules: Tuple[int, int]
    height_storeys: float
    size_cm: Tuple[float, float, float]
    origin: str = "min_corner"
    rotates_about_center: bool = False
    sockets: List[Socket] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    lod: Optional[dict] = None


class AssetDB:
    def __init__(self, path: str = "assets.db") -> None:
        raise NotImplementedError("WP-2: implement AssetDB")

"""Determinism helpers — stable assembly hashes for CI (§10.2).

Same (spec, seed, asset_db_version) must produce a byte-identical assembly hash.
WP-9 owns this harness; WP-5 owns assemble.py itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, List, Mapping, Sequence, Union

from pae.assemble import Placement

PlacementLike = Union[Placement, Mapping[str, Any]]


def _placement_to_dict(p: PlacementLike) -> dict:
    if isinstance(p, Placement) or is_dataclass(p):
        d = asdict(p) if is_dataclass(p) else dict(p)  # type: ignore[arg-type]
    elif isinstance(p, Mapping):
        d = dict(p)
    else:
        raise TypeError(f"unsupported placement type: {type(p)!r}")

    cell = d.get("cell")
    offset = d.get("offset_cm")
    return {
        "asset_id": str(d["asset_id"]),
        "cell": [int(cell[0]), int(cell[1])],
        "level": int(d["level"]),
        "yaw": int(d["yaw"]),
        "offset_cm": [
            round(float(offset[0]), 6),
            round(float(offset[1]), 6),
            round(float(offset[2]), 6),
        ],
    }


def normalize_placements(placements: Iterable[PlacementLike]) -> List[dict]:
    """Canonical sort of placements for hashing (order-independent)."""
    rows = [_placement_to_dict(p) for p in placements]
    rows.sort(
        key=lambda r: (
            r["level"],
            r["cell"][0],
            r["cell"][1],
            r["yaw"],
            r["asset_id"],
            r["offset_cm"][0],
            r["offset_cm"][1],
            r["offset_cm"][2],
        )
    )
    return rows


def hash_assembly(
    placements: Sequence[PlacementLike],
    *,
    asset_db_version: str = "0",
    seed: int | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Return a stable hex digest of an assembly.

    Includes optional seed / asset_db_version so CI can pin
    ``(spec, seed, asset_db_version) → identical hash``.
    """
    payload: dict[str, Any] = {
        "asset_db_version": str(asset_db_version),
        "placements": normalize_placements(placements),
    }
    if seed is not None:
        payload["seed"] = int(seed)
    if extra:
        # Stable key order via json.sort_keys
        payload["extra"] = dict(extra)

    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

"""ISM/HISM grouping for UE spawn tables — group flat rows by ``asset_id``."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

JsonDict = Dict[str, Any]


def group_rows_by_asset_id(rows: Sequence[Mapping[str, Any]]) -> List[JsonDict]:
    """Group spawn-table rows into ISM-ready batches keyed by ``asset_id``.

    Each group contains ``instance_count`` and ``instances[]`` with
  ``loc_cm``, ``yaw``, and ``piece_id`` per instance. Order within a group
    follows first-seen row order; groups are sorted by ``asset_id``.
    """
    buckets: MutableMapping[str, List[JsonDict]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("spawn table row must be an object")
        asset_id = row.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("spawn table row asset_id must be a non-empty string")
        loc_cm = row.get("loc_cm")
        if not isinstance(loc_cm, (list, tuple)) or len(loc_cm) != 3:
            raise ValueError(f"spawn table row for {asset_id!r} has invalid loc_cm")
        yaw = row.get("yaw")
        piece_id = row.get("piece_id")
        if not isinstance(piece_id, str) or not piece_id:
            raise ValueError(f"spawn table row for {asset_id!r} has invalid piece_id")
        buckets.setdefault(asset_id, []).append(
            {
                "loc_cm": [float(loc_cm[0]), float(loc_cm[1]), float(loc_cm[2])],
                "yaw": int(yaw),
                "piece_id": piece_id,
            }
        )

    groups: List[JsonDict] = []
    for asset_id in sorted(buckets):
        instances = buckets[asset_id]
        groups.append(
            {
                "asset_id": asset_id,
                "instance_count": len(instances),
                "instances": instances,
            }
        )
    return groups


__all__ = ["group_rows_by_asset_id"]

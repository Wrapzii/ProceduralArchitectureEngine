"""Roof-edge edging exclusivity — one style per edge (Roadmap 10.5 / D3-4).

``trim._roofline`` places solid parapets; ``compound._add_curtain_battlements`` and
``tower_rampart`` place crenels. Producers consult ``claimed_roof_edges`` so the
same edge is never claimed twice.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.report import Failure
from pae.boundary import FACE_YAW
from pae.contract import MODULE_CM, STOREY_CM, storey_datum_z_cm

Cell = Tuple[int, int]
EdgeKey = Tuple[int, Cell, str]

CHECK_ROOF_EDGING_EXCLUSIVE = "roof_edging_exclusive"

_YAW_FACE = {v: k for k, v in FACE_YAW.items()}

_PARAPET_MARKERS = frozenset({"parapet", "parapet_solid"})
_CRENEL_MARKERS = frozenset({"battlement", "crenel", "tower_rampart"})


def _edging_style(p: SolidPlacement) -> Optional[str]:
    aid = (p.asset_id or "").lower()
    tags = {t.lower() for t in p.tags}
    if p.kind == "battlement" or "battlement" in tags or "crenel" in tags:
        return "crenellated"
    if "parapet" in tags or "parapet" in aid:
        return "parapet"
    if p.kind in ("railing", "surface") and "parapet" in aid:
        return "parapet"
    return None


def _edge_face(p: SolidPlacement) -> Optional[str]:
    tail = p.piece_id.lower().rsplit("_", 1)[-1]
    if tail in ("east", "west", "north", "south"):
        return tail
    face = _YAW_FACE.get(int(p.yaw) % 360)
    if face is not None:
        return face
    if int(p.yaw) % 360 == 0:
        return "west"
    return None


def claimed_roof_edges(
    assembly: Assembly,
    *,
    extra: Optional[List[SolidPlacement]] = None,
) -> Dict[EdgeKey, str]:
    """Map (level, cell, face) → edging style already placed."""
    claimed: Dict[EdgeKey, str] = {}
    pieces = list(assembly.placements)
    if extra:
        pieces.extend(extra)
    for p in pieces:
        style = _edging_style(p)
        if style is None:
            continue
        face = _edge_face(p)
        if face is None:
            continue
        key = (p.level, p.cell, face)
        claimed.setdefault(key, style)
    return claimed


def edge_is_claimed(
    claimed: Dict[EdgeKey, str],
    *,
    level: int,
    cell: Cell,
    face: str,
) -> bool:
    return (level, cell, face) in claimed


def check_roof_edging_exclusive(assembly: Assembly) -> List[Failure]:
    """Critical: no roof edge carries two edging styles (D3-4)."""
    by_edge: Dict[EdgeKey, Set[str]] = {}
    for p in assembly.placements:
        style = _edging_style(p)
        if style is None:
            continue
        face = _edge_face(p)
        if face is None:
            continue
        key = (p.level, p.cell, face)
        by_edge.setdefault(key, set()).add(style)

    failures: List[Failure] = []
    for (level, cell, face), styles in sorted(by_edge.items()):
        if len(styles) < 2:
            continue
        failures.append(
            Failure(
                check=CHECK_ROOF_EDGING_EXCLUSIVE,
                message=(
                    f"roof edge {cell} face {face} L{level} carries multiple edging "
                    f"styles {sorted(styles)} — declare one producer"
                ),
                world_xyz=(
                    cell[0] * MODULE_CM + MODULE_CM * 0.5,
                    cell[1] * MODULE_CM + MODULE_CM * 0.5,
                    float(storey_datum_z_cm(level + 1)),
                ),
                critical=True,
            )
        )
    return failures


__all__ = [
    "CHECK_ROOF_EDGING_EXCLUSIVE",
    "check_roof_edging_exclusive",
    "claimed_roof_edges",
    "edge_is_claimed",
]

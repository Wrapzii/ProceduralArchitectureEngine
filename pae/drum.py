"""Tower drum geometry — the shared vocabulary for anything that touches a round tower.

WHY THIS MODULE EXISTS
----------------------
Four different passes need to answer "is this cell part of a tower drum, and is that
drum inside the building or hanging off it": the wall emitter, the window chooser, the
buttress pass, and the helix pass. Each had grown its own answer, and they disagreed.
The visible result was a tower with the rectangular perimeter wall running straight
through it, windows opening into the drum's interior, buttresses planted on a round
face that has no thrust to take, and a spiral stair that stopped two storeys short.

Everything here is PURE: it reads an assembly or a floor plan and returns cells. It
places nothing and mutates nothing, so it is safe to call from any stage.

THE OUTBOARD DISTINCTION — read this before using ``drum_cells``
----------------------------------------------------------------
A tower is *outboard* when its cells sit outside the body's rectangular footprint: it
is a turret bolted to a corner, enclosed entirely by its own drum. Suppressing the
box's perimeter wall there is correct — the drum IS the enclosure.

A tower is *inboard* when its cells lie within the footprint: a stair tower swallowed by
the plan, where the perimeter wall is still the building's outer skin and removing it
opens a hole in the elevation. The school and the m3 milestone both have these, which is
why a blanket "skip walls on tower cells" rule breaks seven tests. Always ask
``outboard_drum_cells``, never ``drum_cells``, before suppressing anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set, Tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pae.assembly_types import Assembly

Cell = Tuple[int, int]

#: Placement kinds that constitute a drum's own enclosure.
DRUM_KINDS = frozenset({"tower_arc", "tower_cap"})

#: Tag marking the doorway between the body and a drum. Mirrors
#: ``pae.existence.TOWER_ENTRY_TAG``; imported lazily to avoid an import cycle.
ENTRY_TAG = "tower_entry"


def drum_cells(assembly: "Assembly") -> Set[Cell]:
    """Every cell occupied by a tower drum, at any level.

    Derived from the PLACEMENTS, not the spec, so it stays true after trim has added
    caps and spires. Use this to test "does this piece collide with a tower".
    """
    from pae.trim import covered_cells

    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in DRUM_KINDS or "tower_arc" in p.asset_id:
            out |= covered_cells(p)
    return out


def body_cells(assembly: "Assembly") -> Set[Cell]:
    """Cells belonging to the non-tower mass — the box the drum is attached to."""
    from pae.trim import covered_cells

    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind == "floor" and p.asset_id != "floor_hole" and "tower" not in p.tags:
            out |= covered_cells(p)
    return out


def footprint_bbox(cells: Set[Cell]) -> Optional[Tuple[int, int, int, int]]:
    """``(x0, y0, x1, y1)`` inclusive, or None for an empty set."""
    if not cells:
        return None
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return (min(xs), min(ys), max(xs), max(ys))


def outboard_drum_cells(assembly: "Assembly") -> Set[Cell]:
    """Drum cells lying OUTSIDE the body's footprint bounding box.

    These are the only cells where suppressing the rectangular perimeter wall is safe:
    the drum encloses them by itself. A drum cell inside the bbox belongs to a tower
    swallowed by the plan, where the perimeter wall is still the building's outer skin.

    See the module docstring for why this distinction is load-bearing.
    """
    drums = drum_cells(assembly)
    if not drums:
        return set()
    box = footprint_bbox(body_cells(assembly))
    if box is None:
        return set(drums)
    x0, y0, x1, y1 = box
    return {c for c in drums if not (x0 <= c[0] <= x1 and y0 <= c[1] <= y1)}


def drum_levels(assembly: "Assembly") -> dict:
    """``cell -> sorted levels`` the drum SHAFT occupies. The height a helix must climb.

    Arcs only. The cap is a lid that exists at one level, and counting it made a
    cap-only cell look like a drum that starts three storeys in the air.
    """
    from pae.trim import covered_cells

    out: dict = {}
    for p in assembly.placements:
        if p.kind == "tower_arc" or "tower_arc" in p.asset_id:
            for c in covered_cells(p):
                out.setdefault(c, set()).add(p.level)
    return {c: sorted(v) for c, v in out.items()}


def has_entry(assembly: "Assembly", cell: Cell) -> bool:
    """True when some doorway tagged as a tower entry serves ``cell``.

    A drum with no entry is an ornament: you can see the stair through the windows and
    never reach it. ``validate`` already refuses a tower stair without one.
    """
    from pae.trim import covered_cells

    for p in assembly.placements:
        if p.kind != "wall":
            continue
        if ENTRY_TAG not in p.tags and not p.piece_id.startswith("tower_entry_"):
            continue
        cells = covered_cells(p)
        if cell in cells:
            return True
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if (cell[0] + dx, cell[1] + dy) in cells:
                return True
    return False


__all__ = [
    "Cell",
    "DRUM_KINDS",
    "ENTRY_TAG",
    "body_cells",
    "drum_cells",
    "drum_levels",
    "footprint_bbox",
    "has_entry",
    "outboard_drum_cells",
]

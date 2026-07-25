"""Sketch input — hand the engine an outline, let it solve the building.

WHY THIS EXISTS
---------------
PAE drifted into a catalogue. The only footprints were five named kinds (``rect``,
``L``, ``U``, ``school``, ``courtyard``), so anything else had to be written as a
hardcoded preset in Python, and the project filled up with fixed scenes instead of an
authoring path. That is backwards: the engine's value is that it **refuses to build
things that are wrong**, which only pays off if you can hand it an arbitrary shape.

A sketch is a text grid. You draw the outline and mark only what you care about;
everything you leave blank, the solver decides — stair positions, wall lines, corridors,
entrance bays, doors, windows, roof. That is the whole point: mark a square as a
staircase if you want it *there*, otherwise let it work it out.

    from pae.sketch import sketch_to_spec

    plan = '''
    ###########
    #.........#
    #..S......#
    #.........#
    ####E######
    '''
    spec = sketch_to_spec(plan, name="great_hall", storeys=3)

LEGEND (case-insensitive, extend via ``SKETCH_LEGEND``)

    ``#``  building        a cell the building occupies
    ``.``  open            courtyard / open ground inside the outline
    ``S``  stair           building cell that must host vertical circulation
    ``E``  entrance        building cell carrying the main way in
    ``T``  tower           building cell that becomes a round tower
    space  nothing         outside the building entirely

Rows read top-to-bottom in the text and are flipped so that **+Y is north**, i.e. the
first line you type is the far side. Column 0 is x=0.

DESIGN NOTE — why this is text and not a UI
-------------------------------------------
This is the format an LLM authors most naturally: no UI round-trip, diffs cleanly in
git, and testable without Blender. A drawing tool added later should *emit this same
grid* rather than construct specs directly, so there is one input path and two front
ends.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

Cell = Tuple[int, int]

#: character -> role. Anything not listed is treated as outside.
SKETCH_LEGEND: Dict[str, str] = {
    "#": "building",
    ".": "open",
    "s": "stair",
    "e": "entrance",
    "t": "tower",
}

#: Roles that occupy a built cell (as opposed to open ground).
BUILT_ROLES = frozenset({"building", "stair", "entrance", "tower"})


class SketchError(ValueError):
    """A sketch that cannot be read. Raised loudly — never guessed around."""


def parse_sketch(text: str) -> Dict[str, Set[Cell]]:
    """Text grid -> ``{role: cells}``. Pure; no spec construction.

    Rows are flipped so the first line typed is the highest Y, which is how people draw
    plans. Ragged rows are allowed — short rows are padded with 'outside'.
    """
    raw = [line for line in text.splitlines() if line.strip()]
    if not raw:
        raise SketchError("empty sketch")

    # Strip a common leading indent so triple-quoted literals work unmodified.
    indents = [len(line) - len(line.lstrip()) for line in raw if line.strip()]
    trim = min(indents) if indents else 0
    rows = [line[trim:] for line in raw]

    out: Dict[str, Set[Cell]] = {r: set() for r in SKETCH_LEGEND.values()}
    height = len(rows)
    unknown: Set[str] = set()
    for ry, line in enumerate(rows):
        y = height - 1 - ry  # first line typed is the far (high-Y) side
        for x, ch in enumerate(line):
            if ch == " ":
                continue
            role = SKETCH_LEGEND.get(ch.lower())
            if role is None:
                unknown.add(ch)
                continue
            out[role].add((x, y))
    if unknown:
        raise SketchError(
            f"unknown sketch characters {sorted(unknown)}; "
            f"legend is {sorted(set(SKETCH_LEGEND))}"
        )
    if not any(out[r] for r in BUILT_ROLES):
        raise SketchError("sketch has no building cells (nothing marked '#')")
    return out


def built_cells(marks: Dict[str, Set[Cell]]) -> Set[Cell]:
    """Every cell the building occupies, whatever it was marked as."""
    cells: Set[Cell] = set()
    for role in BUILT_ROLES:
        cells |= marks.get(role, set())
    return cells


def rect_cover(cells: Set[Cell]) -> List[Tuple[int, int, int, int]]:
    """Cover a cell set with maximal rectangles as ``(x0, y0, x1, y1)`` inclusive.

    The solver works in rectangular ``Volume``s, so an arbitrary mask has to be
    decomposed before it can become a building. Greedy and deterministic: take the
    lowest-leftmost remaining cell, grow east while the set allows, then grow north
    while every cell of the next row is present. Never emits overlapping rectangles,
    because consumed cells are removed as it goes.

    Determinism matters here — the same sketch must always produce the same volumes, or
    ``(spec, seed) -> identical building`` stops holding.
    """
    remaining = set(cells)
    out: List[Tuple[int, int, int, int]] = []
    while remaining:
        x0, y0 = min(remaining, key=lambda c: (c[1], c[0]))
        w = 1
        while (x0 + w, y0) in remaining:
            w += 1
        h = 1
        while all((x0 + i, y0 + h) in remaining for i in range(w)):
            h += 1
        for i in range(w):
            for j in range(h):
                remaining.discard((x0 + i, y0 + j))
        out.append((x0, y0, x0 + w - 1, y0 + h - 1))
    return out


def sketch_to_spec(
    text: str,
    *,
    name: str = "sketch",
    style: str = "gothic_academy",
    storeys: int = 1,
    storey_use: Optional[Sequence[str]] = None,
    seed: int = 0,
    stair_kind: str = "straight",
    roof_kind: str = "pitched",
    roof_pitch: float = 1.4,
):
    """Build a ``BuildingSpec`` from a sketch. Unmarked decisions are left to the solver.

    Only what the sketch actually marks is pinned:
      * the footprint (which cells are building)
      * stair cells, if any ``S`` were drawn — otherwise the solver allocates them
      * a tower per ``T`` cell

    Everything else — wall lines, corridors, room program, doors, windows, roof
    geometry — is derived downstream. That is deliberate: a sketch should be small.
    """
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        RoofSpec,
        TowerSpec,
    )

    marks = parse_sketch(text)
    cells = built_cells(marks)
    rects = rect_cover(cells)
    if not rects:
        raise SketchError("sketch produced no volumes")

    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    footprint = FootprintSpec(
        kind="cells",
        bays_x=max(xs) - min(xs) + 1,
        bays_y=max(ys) - min(ys) + 1,
        cells=tuple(sorted(cells)),
    )

    towers = [
        TowerSpec(cell=c, storeys=storeys) for c in sorted(marks.get("tower", set()))
    ]
    circulation = CirculationSpec(
        stair_kind=stair_kind,
        stair_cells=sorted(marks.get("stair", set())),
    )
    uses = list(storey_use) if storey_use else ["hall"] * max(1, storeys)
    if len(uses) < storeys:
        uses += [uses[-1]] * (storeys - len(uses))

    return BuildingSpec(
        name=name,
        style=style,
        footprint=footprint,
        storeys=storeys,
        storey_use=uses[:storeys],
        towers=towers,
        roof=RoofSpec(kind=roof_kind, pitch=roof_pitch),
        circulation=circulation,
        seed=seed,
    )


def sketch_summary(text: str) -> str:
    """One-line description of what a sketch contains. For error messages and logs."""
    marks = parse_sketch(text)
    cells = built_cells(marks)
    rects = rect_cover(cells)
    return (
        f"{len(cells)} built cell(s) in {len(rects)} rectangle(s); "
        f"{len(marks.get('stair', set()))} stair, "
        f"{len(marks.get('tower', set()))} tower, "
        f"{len(marks.get('entrance', set()))} entrance, "
        f"{len(marks.get('open', set()))} open"
    )


__all__ = [
    "BUILT_ROLES",
    "Cell",
    "SKETCH_LEGEND",
    "SketchError",
    "built_cells",
    "parse_sketch",
    "rect_cover",
    "sketch_summary",
    "sketch_to_spec",
]

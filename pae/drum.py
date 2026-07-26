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
    from pae.plan import FloorPlan

Cell = Tuple[int, int]

CHECK_DRUM_EXCLUSIVITY = "drum_exclusivity"
CHECK_APERTURE_FACES_OPEN_AIR = "aperture_faces_open_air"

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
    out: Set[Cell] = set()
    for p in assembly.placements:
        if (
            p.kind in DRUM_KINDS
            or "tower_arc" in p.asset_id
            or "square_tower" in p.tags
        ):
            # Drum placements are one logical tower cell. AABB-derived
            # ``covered_cells`` expands rotated quarter meshes into diagonal
            # neighbours and falsely classifies nearby façade windows as being
            # inside the bore.
            out.add(tuple(p.cell))
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


def drum_cells_from_plan(fp: "FloorPlan") -> Set[Cell]:
    """Tower volume cells from massing — pre-assembly twin of ``drum_cells``."""
    cells: Set[Cell] = set()
    if fp.massing is None:
        return cells
    for vol in fp.massing.volumes:
        if vol.role == "tower":
            cells |= vol.cells()
    return cells


def body_cells_from_plan(fp: "FloorPlan") -> Set[Cell]:
    """Non-tower wing cells from massing — pre-assembly twin of ``body_cells``."""
    from pae.solver import WING_ROLES

    cells: Set[Cell] = set()
    if fp.massing is None:
        return cells
    for vol in fp.massing.volumes:
        if vol.role in WING_ROLES:
            cells |= vol.cells()
    return cells


def outboard_drum_cells_from_plan(fp: "FloorPlan") -> Set[Cell]:
    """Pre-assembly equivalent of ``outboard_drum_cells``.

    Use in ``assemble`` face-wall emission — the finished assembly does not exist
    mid-build, but tower-minus-body-bbox is known from the floor plan.

    The catalog drum is one module in diameter and its logical anchor is the
    only cell that owns the bore.
    """
    drums = drum_cells_from_plan(fp)
    if not drums:
        return set()
    body = body_cells_from_plan(fp)
    box = footprint_bbox(body)

    def _outside(c: Cell) -> bool:
        if box is None:
            return True
        x0, y0, x1, y1 = box
        return not (x0 <= c[0] <= x1 and y0 <= c[1] <= y1)

    return {c for c in drums if _outside(c)}


def _opening_probe_for_face(cell: Cell, face: str) -> Cell:
    """Footprint cell behind a boundary-line wall — twin of ``assemble._opening_probe_cell``."""
    x, y = cell
    face = face.lower()
    if face == "east":
        return (x - 1, y)
    if face == "north":
        return (x, y - 1)
    return cell


def _outward_cell_for_face(cell: Cell, face: str) -> Cell:
    """Grid cell on the exterior side of a boundary-line wall run."""
    x, y = cell
    face = face.lower()
    dx, dy = {
        "west": (-1, 0),
        "east": (1, 0),
        "south": (0, -1),
        "north": (0, 1),
    }.get(face, (0, 0))
    return (x + dx, y + dy)


def should_suppress_perimeter_wall_on_outboard_drum(
    cell: Cell,
    face: str,
    outboard: Set[Cell],
) -> bool:
    """Whether ``_place_wall_run`` must skip ``cell`` on ``face`` (T-D1).

    Outboard drums bolt outside the footprint bbox. The drum anchor may sit on
    the boundary line (east) or one cell beyond the opening probe (north), so
    ``cell in outboard`` alone leaves box walls penetrating the bore.
    """
    if not outboard:
        return False
    probe = _opening_probe_for_face(cell, face)
    outward = _outward_cell_for_face(cell, face)
    return cell in outboard or probe in outboard or outward in outboard


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
    out: dict = {}
    for p in assembly.placements:
        if p.kind == "tower_arc" or "tower_arc" in p.asset_id:
            out.setdefault(tuple(p.cell), set()).add(p.level)
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


CHECK_SPIRAL_REACHES_TOP = "spiral_reaches_top"

# Neighbour deltas for party-face detection (body cell, face name).
_PARTY_FACE_FOR_DELTA = {
    (0, 1): "north",
    (0, -1): "south",
    (1, 0): "east",
    (-1, 0): "west",
}


def inboard_drum_party_faces_from_plan(fp: "FloorPlan") -> Set[Tuple[Cell, str]]:
    """``(body_cell, face)`` where perimeter wall is a drum party line (Stage F).

    Inboard drums swallowed by the rectangular footprint share an interior boundary
    with the hall body. The box perimeter must not place a solid exterior skin on
    that edge — ``tower_entry`` (or post-assemble party repair) supplies the
    opening. Outboard turrets are excluded (``outboard_drum_cells_from_plan``).
    """
    drums = drum_cells_from_plan(fp)
    body = body_cells_from_plan(fp)
    if not drums or not body:
        return set()
    box = footprint_bbox(body)
    if box is None:
        return set()
    x0, y0, x1, y1 = box
    inboard = {c for c in drums if x0 <= c[0] <= x1 and y0 <= c[1] <= y1}
    if not inboard:
        return set()
    party: Set[Tuple[Cell, str]] = set()
    for cx, cy in body:
        if (cx, cy) in inboard:
            continue
        for delta, face in _PARTY_FACE_FOR_DELTA.items():
            dx, dy = delta
            if (cx + dx, cy + dy) in inboard:
                party.add(((cx, cy), face))
    return party


def check_spiral_reaches_top(assembly: "Assembly") -> list:
    """Helix must climb every drum shaft storey up to the crown landing.

    For each tower cell with ``stair_spiral_quarter``, the highest flight level
    must be ``max(drum arc levels) - 1`` so the top tread opens onto the upper
    deck under ``tower_deck``.
    """
    from pae.report import Failure

    levels = drum_levels(assembly)
    habitable_cells = {
        p.cell
        for p in assembly.placements
        if p.asset_id == "stair_spiral_quarter" and "habitable_drum" in p.tags
    }
    if not habitable_cells:
        return []
    max_spiral: dict = {}
    for p in assembly.placements:
        if p.asset_id != "stair_spiral_quarter":
            continue
        if habitable_cells and p.cell not in habitable_cells:
            continue
        max_spiral[p.cell] = max(max_spiral.get(p.cell, p.level), p.level)

    failures = []
    for cell, top_arc in levels.items():
        if cell not in max_spiral:
            continue
        expected = max(top_arc) - 1
        got = max_spiral[cell]
        if got < expected:
            failures.append(
                Failure(
                    check=CHECK_SPIRAL_REACHES_TOP,
                    message=(
                        f"spiral at cell {cell} stops at level {got}; expected "
                        f"level {expected} to reach crown under tower_deck "
                        f"(drum arcs through level {max(top_arc)})"
                    ),
                    world_xyz=None,
                    piece_id=None,
                    critical=True,
                )
            )
    return failures


def check_drum_exclusivity(assembly: "Assembly") -> list:
    """No rectangular wall/floor may share an outboard drum cell+level with a tower arc.

    Inboard stair towers legitimately keep the box perimeter through the drum
    overlap — only outboard turrets are drum-exclusive (T-D1).
    """
    from pae.report import Failure
    from pae.trim import covered_cells

    outboard = outboard_drum_cells(assembly)
    if not outboard:
        return []

    arc_levels: dict = {}
    for p in assembly.placements:
        if p.kind == "tower_arc" or "tower_arc" in p.asset_id:
            c = tuple(p.cell)
            if c in outboard:
                arc_levels.setdefault(c, set()).add(p.level)

    failures = []
    for p in assembly.placements:
        if p.kind == "tower_arc" or "tower_arc" in p.asset_id:
            continue
        if p.kind not in ("wall", "floor"):
            continue
        if p.asset_id == "floor_hole":
            continue
        if "tower_deck" in p.tags or p.kind in ("tower_crown", "tower_cap"):
            continue
        if "tower_room" in p.tags or "tower_stair_core" in p.tags:
            continue
        if "tower_entry" in p.tags or p.piece_id.startswith("tower_entry_"):
            continue
        if "drum_window" in p.tags:
            continue
        for c in covered_cells(p):
            if c not in outboard:
                continue
            shared = arc_levels.get(c)
            if shared is None or p.level not in shared:
                continue
            failures.append(
                Failure(
                    check=CHECK_DRUM_EXCLUSIVITY,
                    message=(
                        f"{p.kind} {p.piece_id} at cell {c} level {p.level} "
                        f"co-occupies outboard drum cell with tower_arc"
                    ),
                    world_xyz=None,
                    piece_id=p.piece_id,
                    critical=True,
                )
            )
            break
    return failures


def check_aperture_faces_open_air(assembly: "Assembly") -> list:
    """Perimeter box-wall windows must not glaze into a drum bore (T-D3).

    Drum-rim ``drum_window`` / crown crenel openings are excluded — they are
  designed to sit on the round shell, not the rectangular perimeter run.
    """
    from pae.report import Failure

    drums = drum_cells(assembly)
    if not drums:
        return []
    walls = {p.piece_id: p for p in assembly.placements}
    failures = []
    for ap in assembly.apertures:
        if ap.kind != "window":
            continue
        wall = walls.get(ap.wall_piece_id)
        if wall is not None:
            tags = set(wall.tags)
            if tags & {"drum_window", "tower_crenel", "crenel"}:
                continue
            if "tower" in tags:
                continue
        ext = ap.exterior_cell
        if ext is None or ext not in drums:
            continue
        failures.append(
            Failure(
                check=CHECK_APERTURE_FACES_OPEN_AIR,
                message=(
                    f"window {ap.piece_id} exterior cell {ext} is inside "
                    f"a drum bore"
                ),
                world_xyz=ap.world_xyz,
                piece_id=ap.piece_id,
                critical=True,
            )
        )
    return failures


__all__ = [
    "Cell",
    "DRUM_KINDS",
    "ENTRY_TAG",
    "body_cells",
    "body_cells_from_plan",
    "drum_cells",
    "drum_cells_from_plan",
    "drum_levels",
    "footprint_bbox",
    "has_entry",
    "outboard_drum_cells",
    "outboard_drum_cells_from_plan",
    "inboard_drum_party_faces_from_plan",
    "should_suppress_perimeter_wall_on_outboard_drum",
    "CHECK_SPIRAL_REACHES_TOP",
    "CHECK_DRUM_EXCLUSIVITY",
    "CHECK_APERTURE_FACES_OPEN_AIR",
    "check_spiral_reaches_top",
    "check_drum_exclusivity",
    "check_aperture_faces_open_air",
]

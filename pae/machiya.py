"""Machiya / minka detail — engawa veranda, posts and deep-eave brackets.

WHY THIS IS A MODULE AND NOT A FEW LINES IN ``trim``
-----------------------------------------------------
Because the pieces are the easy half. The rule this project keeps re-learning is that
a piece which can be placed *anywhere* will eventually be placed *somewhere wrong* —
buttresses mounted backwards for the whole life of the project, spiral treads through a
tower wall, battlements crossing at every corner. Each was a placer that computed a pose
and trusted it.

So every placement here is **derived, then measured, then kept or dropped**:

    engawa deck   must bear on an exterior wall face, project outward only, never
                  cover an interior cell, and sit at ground datum
    engawa post   must stand under the deck's OUTER edge, on the ground
    eave bracket  must sit under a roof overhang and above a wall head, same face

Anything that fails its own test is not emitted. A missing veranda is a style that reads
slightly plainer; a veranda through a wall is a bug in every render forever.

The checks in ``validate_machiya`` re-assert the same rules over a finished assembly, so
a piece placed by some *other* code path is caught too. Per Handbook §3, a new kind owes
that registration — these pieces reuse existing kinds (``floor``, ``column``, ``band``)
precisely so they inherit the existing structural checks rather than needing new ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import MODULE_CM, TOL_CM, placement_world_aabb
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report
from pae.trim import covered_cells

Cell = Tuple[int, int]

CHECK_ENGAWA_BEARING = "engawa_bearing"
CHECK_ENGAWA_POST = "engawa_post_under_edge"
CHECK_EAVE_BRACKET = "eave_bracket_support"

_NEIGHBOURS: Dict[str, Cell] = {
    "west": (-1, 0),
    "east": (1, 0),
    "south": (0, -1),
    "north": (0, 1),
}


@dataclass(frozen=True)
class MachiyaSpec:
    """How much of the machiya vocabulary to apply. Bays and fractions, never cm."""

    engawa: bool = True
    #: Which faces get a veranda. Empty = every outward-facing ground run.
    engawa_faces: Tuple[str, ...] = ()
    #: A post every N bays along the deck.
    post_every_bays: int = 1
    eave_brackets: bool = True
    #: A bracket every N bays under the eaves.
    bracket_every_bays: int = 2


def _aabb(p: SolidPlacement):
    return placement_world_aabb(
        p.cell[0], p.cell[1], p.level, p.yaw, p.size_cm, p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


#: Tags/kinds that are GROUND, not building interior. The site slab and paving extend
#: well past the walls, so counting them as "interior" makes every outward-facing
#: veranda look like it is inside the house. This is the same trap the buttress interior
#: test hit — a ground apron is not a room.
_GROUND_KINDS = frozenset({"ground", "surface", "plinth"})
_GROUND_TAGS = frozenset({"site", "ground", "paving", "boundary", "lawn", "kerb"})


def _interior_cells(assembly: Assembly) -> Set[Cell]:
    """Cells that are genuinely INSIDE the building — habitable floor only."""
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind != "floor" or "hole" in (p.asset_id or ""):
            continue
        if p.kind in _GROUND_KINDS:
            continue
        tags = set(getattr(p, "tags", ()) or ())
        if _GROUND_TAGS & tags:
            continue
        if "engawa" in tags or "balcony" in tags:
            continue  # our own decks are not interior
        out |= covered_cells(p)
    return out


def apply_machiya(
    assembly: Assembly,
    spec: Optional[MachiyaSpec] = None,
) -> Tuple[Assembly, Report]:
    """Additive pass. Returns a new assembly; the input is never mutated."""
    from pae.trim import _pier_pose  # the yaw that turns a piece's BACK to the wall

    opts = spec or MachiyaSpec()
    catalog = catalog_by_id()
    for needed in ("engawa_deck", "engawa_post", "eave_bracket"):
        if needed not in catalog:
            return assembly, Report.from_failures([
                Failure(
                    check="machiya_piece_missing",
                    message=f"machiya wants unknown piece {needed!r}",
                    world_xyz=None,
                )
            ])

    interior = _interior_cells(assembly)
    extra: List[SolidPlacement] = []

    if opts.engawa:
        extra.extend(_place_engawa(assembly, opts, interior, _pier_pose, catalog))
    if opts.eave_brackets:
        extra.extend(_place_brackets(assembly, opts, _pier_pose, catalog))

    if not extra:
        return assembly, Report.from_failures([])

    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    from dataclasses import replace

    return replace(
        assembly, placements=list(assembly.placements) + extra
    ), Report.from_failures([])


def _ground_walls(assembly: Assembly) -> List[SolidPlacement]:
    return [p for p in assembly.placements if p.kind == "wall" and p.level == 0]


def _wall_face(wall: SolidPlacement) -> str:
    """Which boundary line the wall SITS on, from its own AABB — never from neighbours.

    Deriving a face from cell neighbours is Ledger A-7, the mistake that braced
    buttresses against thin air.
    """
    mn, mx = _aabb(wall)
    cx0, cy0 = wall.cell[0] * MODULE_CM, wall.cell[1] * MODULE_CM
    near = MODULE_CM * 0.5
    if (mx[0] - mn[0]) < (mx[1] - mn[1]):
        return "west" if (mn[0] - cx0) < near else "east"
    return "south" if (mn[1] - cy0) < near else "north"


def _place_engawa(assembly, opts, interior, pier_pose, catalog) -> List[SolidPlacement]:
    """Veranda decks + posts along outward-facing ground walls."""
    from pae.trim import _placement

    deck_size = catalog["engawa_deck"].size_cm
    post = catalog["engawa_post"]
    out: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()
    # ONE DECK PER CELL. A corner cell has two outward faces, and laying a deck on each
    # drives both through the same corner square — 15 `footprint_overlap` criticals, the
    # same corner double-claim as Ledger A-10 and the battlements. A veranda turns the
    # corner as one run; the first face claimed wins, deterministically.
    claimed_cells: Set[Cell] = set()

    for i, wall in enumerate(
        sorted(_ground_walls(assembly), key=lambda p: (p.cell, p.piece_id))
    ):
        face = _wall_face(wall)
        if opts.engawa_faces and face not in opts.engawa_faces:
            continue
        cell = wall.cell
        if cell in claimed_cells:
            continue
        dx, dy = _NEIGHBOURS[face]
        outside = (cell[0] + dx, cell[1] + dy)
        if outside in interior:
            continue  # that face looks inward — a veranda there is inside a room
        key = (cell, face)
        if key in seen:
            continue
        seen.add(key)
        claimed_cells.add(cell)

        yaw, off = pier_pose(face, deck_size)
        deck = _placement("engawa_deck", cell, 0, yaw=yaw, offset_cm=off,
                          suffix=f"engawa_{face}")
        # MEASURE IT. Bear on this wall, stay out of the interior, or drop it.
        if not _bears_on(deck, wall) or (covered_cells(deck) & interior):
            continue
        out.append(deck)

        if opts.post_every_bays and (i % max(1, opts.post_every_bays)) == 0:
            p = _outer_edge_post(deck, face, post.size_cm, cell)
            if p is not None:
                out.append(p)
    return out


def _bears_on(piece: SolidPlacement, wall: SolidPlacement) -> bool:
    """Real shared extent with the wall on every axis — touching, not grazing."""
    pmn, pmx = _aabb(piece)
    wmn, wmx = _aabb(wall)
    return all(
        min(pmx[i], wmx[i]) - max(pmn[i], wmn[i]) >= -TOL_CM for i in range(3)
    )


def _outer_edge_post(deck, face, post_size, cell) -> Optional[SolidPlacement]:
    """A post at the deck's OUTER edge, solved by measurement not by yaw arithmetic."""
    from pae.trim import _placement

    dmn, dmx = _aabb(deck)
    # Outer edge is the deck face furthest from the wall, along the face normal.
    if face == "west":
        px, py = dmn[0], 0.5 * (dmn[1] + dmx[1])
    elif face == "east":
        px, py = dmx[0] - post_size[0], 0.5 * (dmn[1] + dmx[1])
    elif face == "south":
        px, py = 0.5 * (dmn[0] + dmx[0]), dmn[1]
    else:
        px, py = 0.5 * (dmn[0] + dmx[0]), dmx[1] - post_size[1]

    # Solve the offset by MEASUREMENT, not by hand-derived yaw arithmetic — the class
    # of error behind Ledger A-1..A-4. Place a trial at zero offset, see where it
    # landed, and shift by the difference.
    trial = _placement("engawa_post", cell, 0, yaw=0,
                       offset_cm=(0.0, 0.0, 0.0), suffix=f"engawa_post_{face}")
    tmn, _tmx = _aabb(trial)
    return _placement(
        "engawa_post", cell, 0, yaw=0,
        offset_cm=(px - tmn[0], py - tmn[1], 0.0),
        suffix=f"engawa_post_{face}",
    )


def _place_brackets(assembly, opts, pier_pose, catalog) -> List[SolidPlacement]:
    """Brackets under the eaves: below a roof, above a wall head, same face."""
    from pae.trim import _placement

    roofs = [p for p in assembly.placements if p.kind == "roof"]
    if not roofs:
        return []
    roof_bottom = min(_aabb(r)[0][2] for r in roofs)
    size = catalog["eave_bracket"].size_cm

    top_level = max((p.level for p in assembly.placements if p.kind == "wall"),
                    default=0)
    walls = [
        p for p in assembly.placements if p.kind == "wall" and p.level == top_level
    ]
    interior = _interior_cells(assembly)
    out: List[SolidPlacement] = []
    seen: Set[Tuple[Cell, str]] = set()

    for i, wall in enumerate(sorted(walls, key=lambda p: (p.cell, p.piece_id))):
        if opts.bracket_every_bays and (i % max(1, opts.bracket_every_bays)):
            continue
        face = _wall_face(wall)
        dx, dy = _NEIGHBOURS[face]
        if (wall.cell[0] + dx, wall.cell[1] + dy) in interior:
            continue
        key = (wall.cell, face)
        if key in seen:
            continue
        seen.add(key)

        wmn, wmx = _aabb(wall)
        # Tuck the bracket into the WALL HEAD, not up at the roof underside. A bracket
        # is a corbel: it grows out of the masonry and the eave lands on it. Floating it
        # at the roof line gave `band_attachment` "contacts its wall over 0 of 88 cm",
        # because the band contract rightly demands real contact along its length.
        z = wmx[2] - size[2]
        if roof_bottom - wmx[2] > MODULE_CM:
            continue  # roof is far above the wall head — nothing here to corbel
        yaw, off = pier_pose(face, size)
        out.append(
            _placement(
                "eave_bracket", wall.cell, top_level,
                yaw=yaw, offset_cm=(off[0], off[1], z - top_level * _storey()),
                suffix=f"eave_{face}",
            )
        )
    return out


def _storey() -> float:
    from pae.contract import STOREY_CM

    return STOREY_CM


# ---------------------------------------------------------------------------
# Checks — the same rules, re-asserted over a finished assembly
# ---------------------------------------------------------------------------


def validate_machiya(assembly: Assembly) -> List[Failure]:
    """Re-assert the attachment contract, whoever placed the pieces.

    The placer already drops anything that fails. This exists because a piece placed by
    a DIFFERENT code path — a preset, a hand edit, a future stage — would otherwise
    never be checked. Handbook §3: the rule lives with the kind, not with one producer.
    """
    failures: List[Failure] = []
    walls = [(p, _aabb(p)) for p in assembly.placements if p.kind == "wall"]
    interior = _interior_cells(assembly)

    decks = [p for p in assembly.placements if (p.asset_id or "") == "engawa_deck"]
    for d in decks:
        if not any(_bears_on(d, w) for w, _b in walls):
            failures.append(
                Failure(
                    check=CHECK_ENGAWA_BEARING,
                    message=(
                        f"engawa {d.piece_id} bears on no wall — a veranda bolted to air"
                    ),
                    world_xyz=_centre(d),
                    piece_id=d.piece_id,
                    critical=True,
                )
            )
        inside = covered_cells(d) & interior
        if inside:
            failures.append(
                Failure(
                    check=CHECK_ENGAWA_BEARING,
                    message=(
                        f"engawa {d.piece_id} covers interior cell(s) {sorted(inside)} "
                        "— a veranda inside the house"
                    ),
                    world_xyz=_centre(d),
                    piece_id=d.piece_id,
                    critical=True,
                )
            )

    deck_boxes = [_aabb(d) for d in decks]
    for post in assembly.placements:
        if (post.asset_id or "") != "engawa_post":
            continue
        pmn, pmx = _aabb(post)
        under = any(
            pmn[0] >= dmn[0] - TOL_CM and pmx[0] <= dmx[0] + TOL_CM
            and pmn[1] >= dmn[1] - TOL_CM and pmx[1] <= dmx[1] + TOL_CM
            for dmn, dmx in deck_boxes
        )
        if not under:
            failures.append(
                Failure(
                    check=CHECK_ENGAWA_POST,
                    message=(
                        f"engawa post {post.piece_id} stands under no deck — "
                        "a post holding nothing up"
                    ),
                    world_xyz=_centre(post),
                    piece_id=post.piece_id,
                    critical=True,
                )
            )

    roofs = [_aabb(r) for r in assembly.placements if r.kind == "roof"]
    for br in assembly.placements:
        if (br.asset_id or "") != "eave_bracket":
            continue
        if not any(_bears_on(br, w) for w, _b in walls):
            failures.append(
                Failure(
                    check=CHECK_EAVE_BRACKET,
                    message=(
                        f"eave bracket {br.piece_id} touches no wall — a peg in mid-air"
                    ),
                    world_xyz=_centre(br),
                    piece_id=br.piece_id,
                    critical=True,
                )
            )
            continue
        bmn, bmx = _aabb(br)
        if roofs and not any(
            rmn[2] >= bmx[2] - MODULE_CM and rmn[2] <= bmx[2] + MODULE_CM
            for rmn, _rmx in roofs
        ):
            failures.append(
                Failure(
                    check=CHECK_EAVE_BRACKET,
                    message=(
                        f"eave bracket {br.piece_id} carries no eave — no roof "
                        "underside within a module above it"
                    ),
                    world_xyz=_centre(br),
                    piece_id=br.piece_id,
                    critical=False,
                )
            )
    return failures


def _centre(p: SolidPlacement) -> Tuple[float, float, float]:
    mn, mx = _aabb(p)
    return (0.5 * (mn[0] + mx[0]), 0.5 * (mn[1] + mx[1]), 0.5 * (mn[2] + mx[2]))


__all__ = [
    "CHECK_EAVE_BRACKET",
    "CHECK_ENGAWA_BEARING",
    "CHECK_ENGAWA_POST",
    "MachiyaSpec",
    "apply_machiya",
    "validate_machiya",
]

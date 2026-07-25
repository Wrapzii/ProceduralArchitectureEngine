"""Fortress / castle compound validation — Phase 4 / Phase 6 existence + orientation.

WHY THIS EXISTS: the fortress kit and bailey compound place towers, gates, curtains,
buttresses, spires and grand approach steps. Without fail-closed checks those pieces
can be omitted, face inward, or float as islands while every generic check still passes
(Handbook §0 — the bug is in the reasoning about where geometry goes).

Checks (stable slugs):
  * ``fortress_tower_capped`` — min towers finished with cap and/or spire (critical)
  * ``fortress_gate_exists`` — gate / entrance leaf on fortress compounds (critical)
  * ``curtain_battlement_continuity`` — curtain wall-walk battlement stub (warning)
  * ``buttress_outward`` — buttresses bear on exterior walls, not interior (critical)
  * ``spire_freestanding`` — spires/finials must meet tower/roof envelope (critical)
  * ``fortress_grand_approach`` — exterior grand steps when tagged (critical)

Rule 5.1: all cell reasoning uses ``covered_cells``, never bare ``p.cell`` for
span/support questions. Tower *identity* for caps/spires that ``rotates_about_center``
uses the placement anchor cell with an explicit comment (one drum per cell by design).

Config: tags ``fortress`` / ``fortress_compound`` / ``building:fortress*``,
``fortress_min_towers:N``, ``grand_approach``. Optional knobs on
``CastleBaileySpec`` / ``FortressBaileySpec`` via getattr when present.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    MODULE_CM,
    TOL_CM,
    aabb_intersects,
    placement_world_aabb,
)
from pae.existence import placed_entrance_roles
from pae.report import Failure

Cell = Tuple[int, int]

# Tags that mark a fortress / bailey compound (massing + interim curtain).
FORTRESS_TAG = "fortress"
FORTRESS_COMPOUND_TAG = "fortress_compound"
GRAND_APPROACH_TAG = "grand_approach"
FORTRESS_MIN_TOWERS_TAG_PREFIX = "fortress_min_towers:"

# Curtain range markers from castle_curtain / fortress massing.
_CURTAIN_TAGS = frozenset(
    {
        "curtain",
        "west_curtain",
        "east_curtain",
        "north_curtain",
        "south_curtain",
    }
)

DEFAULT_MIN_CAPPED_TOWERS = 2

# Continuity stub: max uncovered curtain bays in a sorted run before warning.
_CURTAIN_BATTLEMENT_MAX_GAP_CELLS = 2
# Fraction of curtain wall bays that must carry a battlement/parapet overhead.
_CURTAIN_BATTLEMENT_MIN_COVERAGE = 0.50

_SPIRE_ASSET_PREFIXES = ("spire_",)
_SPIRE_KINDS = frozenset({"roofline"})
_FINIAL_ASSETS = frozenset({"finial"})
_APPROACH_ASSETS = frozenset({"steps_grand", "steps_external"})
_APPROACH_TAGS = frozenset(
    {"grand_approach", "ensemble_steps", "steps", "approach"}
)


def _placement_aabb(
    p: SolidPlacement,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _all_tags(assembly: Assembly) -> Set[str]:
    tags: Set[str] = set()
    for p in assembly.placements:
        tags |= set(p.tags)
    return tags


def assembly_is_fortress(assembly: Assembly) -> bool:
    """True when this assembly is a fortress / bailey / curtain compound.

    Detection (any one):
      * ``fortress_compound`` / ``fortress:*`` / ``building:fortress*``
      * ``fortress`` on a non-roofline piece (kit spires carry ``fortress`` as a
        style tag — that alone must NOT promote a keep into a compound)
      * west+east curtain tags (interim ``build_castle_curtain_compound``)
      * ``FortressBaileySpec``-style north curtain + gatehouse
    """
    tags = _all_tags(assembly)
    if FORTRESS_COMPOUND_TAG in tags:
        return True
    if any(t.startswith("fortress:") for t in tags):
        return True
    if any(t.startswith("building:fortress") for t in tags):
        return True
    for p in assembly.placements:
        if FORTRESS_TAG not in p.tags:
            continue
        # Style tags on spires/steps must not imply a full fortress compound.
        if p.kind == "roofline" or "spire" in p.asset_id:
            continue
        if p.asset_id in _APPROACH_ASSETS or "steps" in p.tags:
            continue
        return True
    if "west_curtain" in tags and "east_curtain" in tags:
        return True
    if "north_curtain" in tags and (
        "gatehouse" in tags or "building:gatehouse" in tags
    ):
        return True
    return False


def assembly_requires_grand_approach(assembly: Assembly) -> bool:
    """Grand approach steps are required when explicitly tagged."""
    tags = _all_tags(assembly)
    if GRAND_APPROACH_TAG in tags or "fortress_grand_approach" in tags:
        return True
    # Spec knobs (massing may stamp these onto a sentinel / keep piece).
    for p in assembly.placements:
        if "require_grand_approach" in p.tags:
            return True
    return False


def fortress_min_capped_towers(assembly: Assembly) -> int:
    """Configurable minimum finished towers (caps and/or spires)."""
    tags = _all_tags(assembly)
    for t in sorted(tags):
        if t.startswith(FORTRESS_MIN_TOWERS_TAG_PREFIX):
            try:
                return max(1, int(t[len(FORTRESS_MIN_TOWERS_TAG_PREFIX) :]))
            except ValueError:
                continue
    # Optional CastleBaileySpec / FortressBaileySpec fields when callers pass
    # them via a tagged sentinel — getattr keeps us decoupled from WIP massing.
    for name in ("min_capped_towers", "min_towers_with_caps"):
        for p in assembly.placements:
            raw = getattr(p, name, None)
            if isinstance(raw, int) and raw >= 1:
                return raw
    return DEFAULT_MIN_CAPPED_TOWERS


def _is_spire_or_finial(p: SolidPlacement) -> bool:
    if p.asset_id in _FINIAL_ASSETS or "finial" in p.tags:
        return True
    if any(p.asset_id.startswith(pref) for pref in _SPIRE_ASSET_PREFIXES):
        return True
    if p.kind in _SPIRE_KINDS and (
        "spire" in p.tags or "spire" in p.asset_id or "fortress" in p.tags
    ):
        # Narrow: conical/needle fortress spires carry fortress/spire tags;
        # dormers/chimneys are roofline but must not count as tower finishes.
        if any(x in p.asset_id for x in ("dormer", "chimney", "cupola", "gablet")):
            return False
        return "spire" in p.asset_id or "spire" in p.tags
    return False


def _is_buttress(p: SolidPlacement) -> bool:
    return (
        p.asset_id == "buttress"
        or "buttress" in p.tags
        or (p.kind == "column" and "buttress" in p.asset_id)
    )


def _is_curtain_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall" and "wall" not in p.tags:
        return False
    return bool(_CURTAIN_TAGS & set(p.tags))


def _is_battlement_or_parapet(p: SolidPlacement) -> bool:
    if p.kind == "battlement":
        return True
    if p.kind == "barrier" and "parapet" in p.tags:
        return True
    if "battlement" in p.tags or "parapet" in p.tags:
        return True
    return "battlement" in p.asset_id or "parapet" in p.asset_id


def _is_approach_steps(p: SolidPlacement) -> bool:
    if p.asset_id in _APPROACH_ASSETS:
        return True
    if _APPROACH_TAGS & set(p.tags) and p.kind in ("surface", "stair", "prop"):
        return True
    if "ensemble_steps" in p.tags:
        return True
    return False


def _tower_finish_anchors(assembly: Assembly) -> Set[Cell]:
    """Cells of towers finished with a ``tower_cap`` and/or spire.

    Centered tower pieces share one drum cell by design — ``p.cell`` is the
    tower identity here (not a spanning-slab origin). See ``rotates_about_center``.
    """
    finished: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind == "tower_cap":
            finished.add(p.cell)
        elif _is_spire_or_finial(p) and (
            "spire" in p.asset_id or p.asset_id in _FINIAL_ASSETS or "spire" in p.tags
        ):
            # Finials alone do not finish a tower; spires do.
            if "finial" in p.asset_id and "spire" not in p.asset_id:
                continue
            if any(p.asset_id.startswith(pref) for pref in _SPIRE_ASSET_PREFIXES) or (
                "spire" in p.tags and "finial" not in p.asset_id
            ):
                finished.add(p.cell)
    return finished


def check_fortress_tower_capped(assembly: Assembly) -> List[Failure]:
    """Fortress compounds need ≥ N towers finished with a cap and/or spire."""
    if not assembly_is_fortress(assembly):
        return []
    need = fortress_min_capped_towers(assembly)
    finished = _tower_finish_anchors(assembly)
    if len(finished) >= need:
        return []
    # Locate a representative XYZ — prefer a tower_arc / gatehouse piece.
    xyz: Optional[Tuple[float, float, float]] = None
    pid: Optional[str] = None
    for p in assembly.placements:
        if p.kind in ("tower_arc", "tower_cap", "tower_crown") or "gatehouse" in p.tags:
            bb = _placement_aabb(p)
            xyz = _centre(bb[0], bb[1])
            pid = p.piece_id
            break
    return [
        Failure(
            check="fortress_tower_capped",
            message=(
                f"fortress compound has {len(finished)} tower(s) with cap/spire, "
                f"need ≥ {need} (tag {FORTRESS_MIN_TOWERS_TAG_PREFIX}N to override)"
            ),
            world_xyz=xyz,
            piece_id=pid,
            critical=True,
        )
    ]


def check_fortress_gate_exists(assembly: Assembly) -> List[Failure]:
    """Fortress compounds must place a gate / entrance leaf."""
    if not assembly_is_fortress(assembly):
        return []
    roles = placed_entrance_roles(assembly)
    if "gate" in roles:
        return []
    # Asset fallback — wall_gate_arch without role tag still counts as a gate leaf.
    gates = [
        p
        for p in assembly.placements
        if "gate" in (p.asset_id or "").lower()
        or ("gate" in p.tags and p.kind == "wall")
    ]
    if gates:
        return []
    xyz: Optional[Tuple[float, float, float]] = None
    pid: Optional[str] = None
    for p in assembly.placements:
        if "gatehouse" in p.tags or "building:gatehouse" in p.tags:
            bb = _placement_aabb(p)
            xyz = _centre(bb[0], bb[1])
            pid = p.piece_id
            break
    return [
        Failure(
            check="fortress_gate_exists",
            message=(
                "fortress compound has no gate/entrance leaf "
                "(expected entrance_role_gate or wall_gate_arch)"
            ),
            world_xyz=xyz,
            piece_id=pid,
            critical=True,
        )
    ]


def check_curtain_battlement_continuity(assembly: Assembly) -> List[Failure]:
    """Curtain walls should carry battlement/parapet along the wall-walk (stub).

    WARNING while triage lands full wall-walk circuits (roadmap 4.1 gap). Uses
    ``covered_cells`` for both walls and battlements (Rule 5.1).
    """
    from pae.trim import covered_cells

    curtain_walls = [p for p in assembly.placements if _is_curtain_wall(p)]
    if not curtain_walls:
        return []

    # Top storey of curtain walls only — battlements sit on the wall-walk.
    top_level = max(p.level for p in curtain_walls)
    top_walls = [p for p in curtain_walls if p.level == top_level]
    if not top_walls:
        return []

    batt_cells: Set[Cell] = set()
    for p in assembly.placements:
        if not _is_battlement_or_parapet(p):
            continue
        # Battlement may sit on the storey above the wall head.
        if p.level < top_level:
            continue
        batt_cells |= covered_cells(p)

    wall_cells: List[Cell] = []
    seen: Set[Cell] = set()
    for p in sorted(top_walls, key=lambda w: (w.cell[0], w.cell[1], w.piece_id)):
        for c in sorted(covered_cells(p)):
            if c not in seen:
                seen.add(c)
                wall_cells.append(c)

    if not wall_cells:
        return []

    covered = [c for c in wall_cells if c in batt_cells]
    ratio = len(covered) / len(wall_cells)
    failures: List[Failure] = []

    if ratio + 1e-9 < _CURTAIN_BATTLEMENT_MIN_COVERAGE:
        rep = top_walls[0]
        bb = _placement_aabb(rep)
        failures.append(
            Failure(
                check="curtain_battlement_continuity",
                message=(
                    f"curtain battlement coverage {ratio:.0%} of wall-walk bays "
                    f"({len(covered)}/{len(wall_cells)}); "
                    f"need ≥ {_CURTAIN_BATTLEMENT_MIN_COVERAGE:.0%} (continuity stub)"
                ),
                world_xyz=_centre(bb[0], bb[1]),
                piece_id=rep.piece_id,
                critical=False,
            )
        )

    # Gap stub: sort by dominant axis and flag runs with large uncovered stretches.
    xs = {c[0] for c in wall_cells}
    ys = {c[1] for c in wall_cells}
    axis = 0 if len(xs) >= len(ys) else 1
    ordered = sorted(wall_cells, key=lambda c: (c[1 - axis], c[axis]))
    gap = 0
    worst_gap = 0
    gap_cell: Optional[Cell] = None
    for c in ordered:
        if c in batt_cells:
            gap = 0
        else:
            gap += 1
            if gap > worst_gap:
                worst_gap = gap
                gap_cell = c
    if worst_gap > _CURTAIN_BATTLEMENT_MAX_GAP_CELLS:
        xyz = (
            (gap_cell[0] + 0.5) * MODULE_CM,
            (gap_cell[1] + 0.5) * MODULE_CM,
            top_level * MODULE_CM,
        ) if gap_cell else None
        failures.append(
            Failure(
                check="curtain_battlement_continuity",
                message=(
                    f"curtain battlement gap of {worst_gap} bay(s) exceeds "
                    f"stub max {_CURTAIN_BATTLEMENT_MAX_GAP_CELLS} "
                    f"(uncovered run along curtain)"
                ),
                world_xyz=xyz,
                piece_id=None,
                critical=False,
            )
        )
    return failures


def check_buttress_outward(assembly: Assembly) -> List[Failure]:
    """Every buttress must bear on a wall and must not occupy interior deck cells.

    Handbook §2 Q1/Q5 + Rule 5.4. Critical whenever buttresses are present
    (not fortress-gated — inward piers are wrong on any building).
    """
    from pae.trim import covered_cells

    butts = [p for p in assembly.placements if _is_buttress(p)]
    if not butts:
        return []

    walls = [
        p
        for p in assembly.placements
        if p.kind == "wall" or (p.kind == "tower_arc")
    ]
    wall_boxes = [_placement_aabb(p) for p in walls]

    interior: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("floor", "ground", "plinth"):
            interior |= covered_cells(p)

    failures: List[Failure] = []
    for butt in butts:
        bmn, bmx = _placement_aabb(butt)
        touches_wall = any(
            aabb_intersects(bmn, bmx, wmn, wmx) for wmn, wmx in wall_boxes
        )
        interior_hit = covered_cells(butt) & interior
        if touches_wall and not interior_hit:
            continue
        reasons: List[str] = []
        if not touches_wall:
            reasons.append("meets no wall within TOL")
        if interior_hit:
            reasons.append(
                f"covers {len(interior_hit)} interior deck cell(s) — projects inward"
            )
        failures.append(
            Failure(
                check="buttress_outward",
                message=(
                    f"buttress {butt.piece_id} ({butt.asset_id}) is not an outward "
                    f"bearing pier: {'; '.join(reasons)}"
                ),
                world_xyz=_centre(bmn, bmx),
                piece_id=butt.piece_id,
                critical=True,
            )
        )
    return failures


def check_spire_freestanding(assembly: Assembly) -> List[Failure]:
    """Spires/finials must meet a tower cap/crown/roof — not float as islands.

    Distinct from generic ``freestanding``: a spire on posts/ground can still join
    the touch graph transitively. Connection class (Handbook §1 #4) for roofline.
    """
    spires = [p for p in assembly.placements if _is_spire_or_finial(p)]
    if not spires:
        return []

    envelope = [
        p
        for p in assembly.placements
        if p.kind in ("tower_cap", "tower_crown", "tower_arc", "roof", "roofline")
        or (p.kind == "barrier" and "parapet" in p.tags)
        or p.kind == "battlement"
    ]
    # Allow spire↔spire / spire↔finial chains that eventually meet envelope.
    carriers = list(envelope) + [
        p for p in spires if any(p.asset_id.startswith(pref) for pref in _SPIRE_ASSET_PREFIXES)
        or p.kind == "roofline"
    ]
    if not carriers:
        # No tower/roof at all — every spire is freestanding.
        carriers = []

    carrier_boxes = [_placement_aabb(p) for p in carriers]
    # Seed attachment: touch a non-spire envelope piece.
    env_only = [
        p
        for p in envelope
        if not _is_spire_or_finial(p) or p.kind in ("tower_cap", "tower_crown", "roof")
    ]
    env_boxes = [_placement_aabb(p) for p in env_only]

    attached = []
    for p in spires:
        box = _placement_aabb(p)
        ok = any(aabb_intersects(box[0], box[1], eb[0], eb[1]) for eb in env_boxes)
        attached.append(ok)

    # Spread through spire/finial contact (finial on spire apex).
    spire_boxes = [_placement_aabb(p) for p in spires]
    changed = True
    while changed:
        changed = False
        for i, ok in enumerate(attached):
            if ok:
                continue
            for j, ok_j in enumerate(attached):
                if not ok_j or i == j:
                    continue
                if aabb_intersects(
                    spire_boxes[i][0],
                    spire_boxes[i][1],
                    spire_boxes[j][0],
                    spire_boxes[j][1],
                ):
                    attached[i] = True
                    changed = True
                    break

    failures: List[Failure] = []
    for p, box, ok in zip(spires, spire_boxes, attached):
        if ok:
            continue
        # Finials that touch nothing are critical; dormer mis-tags already filtered.
        failures.append(
            Failure(
                check="spire_freestanding",
                message=(
                    f"freestanding spire/finial {p.piece_id} ({p.asset_id}) — "
                    f"meets no tower_cap/crown/roof or attached spire"
                ),
                world_xyz=_centre(box[0], box[1]),
                piece_id=p.piece_id,
                critical=True,
            )
        )
    return failures


def check_fortress_grand_approach(assembly: Assembly) -> List[Failure]:
    """When tagged for grand approach, exterior steps must exist at grade."""
    if not assembly_requires_grand_approach(assembly):
        return []
    steps = [
        p
        for p in assembly.placements
        if _is_approach_steps(p) and p.level == 0
    ]
    if steps:
        return []
    xyz: Optional[Tuple[float, float, float]] = None
    pid: Optional[str] = None
    for p in assembly.placements:
        if GRAND_APPROACH_TAG in p.tags or "fortress_grand_approach" in p.tags:
            bb = _placement_aabb(p)
            xyz = _centre(bb[0], bb[1])
            pid = p.piece_id
            break
    return [
        Failure(
            check="fortress_grand_approach",
            message=(
                f"assembly tagged {GRAND_APPROACH_TAG!r} has no exterior approach "
                f"steps (expected steps_grand / steps_external / ensemble_steps)"
            ),
            world_xyz=xyz,
            piece_id=pid,
            critical=True,
        )
    ]


def check_fortress_compound(assembly: Assembly) -> List[Failure]:
    """Run all fortress / castle building checks (for validate pipeline)."""
    failures: List[Failure] = []
    failures.extend(check_fortress_tower_capped(assembly))
    failures.extend(check_fortress_gate_exists(assembly))
    failures.extend(check_curtain_battlement_continuity(assembly))
    failures.extend(check_buttress_outward(assembly))
    failures.extend(check_spire_freestanding(assembly))
    failures.extend(check_fortress_grand_approach(assembly))
    return failures


__all__ = [
    "FORTRESS_TAG",
    "FORTRESS_COMPOUND_TAG",
    "GRAND_APPROACH_TAG",
    "DEFAULT_MIN_CAPPED_TOWERS",
    "assembly_is_fortress",
    "assembly_requires_grand_approach",
    "fortress_min_capped_towers",
    "check_fortress_tower_capped",
    "check_fortress_gate_exists",
    "check_curtain_battlement_continuity",
    "check_buttress_outward",
    "check_spire_freestanding",
    "check_fortress_grand_approach",
    "check_fortress_compound",
]

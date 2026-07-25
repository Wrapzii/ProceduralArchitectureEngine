"""Variation stage — seeded difference within the rules.

WHY THIS EXISTS: the engine produced buildings where every storey was identical from the
outside, window for window, and where the assembler put a door on the same bay of EVERY
level — so a four-storey tower had three doorways opening into open air.

Two jobs, both deterministic from a seed:

  1. LEGALITY   demote apertures that cannot exist. An upper-level door with no balcony,
                gallery or landing outside it becomes a window. This is a fix, not a
                preference — ``aperture_reachability`` reports it as critical.
  2. VARIETY    vary window placement per storey and per bay so elevations are not
                stamped copies, while respecting rules: a minimum number of lights per
                elevation, never remove a reachable door, never open a blind wall that
                must stay solid.

Determinism: every decision derives from ``hash((seed, piece_id))`` via a seeded RNG keyed
per piece, so the same ``(spec, seed)`` always produces the same building, and changing the
seed produces a *different but equally legal* one. That is what "regen the exact same thing
and it should vary" means — vary with the seed, not vary at random.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure, Report
from pae.trim import covered_cells

Cell = Tuple[int, int]


@dataclass(frozen=True)
class VariationSpec:
    """How much difference, and of what kind. All choices are seed-driven."""

    seed: int = 0
    vary_windows: bool = True
    window_pieces: Tuple[str, ...] = (
        "wall_window",
        "wall_window_round",
        "wall_window_lancet",
        "wall_window_mullioned",
    )
    blank_piece: str = "wall_plain"
    #: Chance a given bay on a given storey is left blank rather than glazed.
    blank_chance: float = 0.28
    #: Never leave an elevation with fewer than this many lights per storey.
    min_lights_per_elevation: int = 1
    #: Upper storeys may use a different window type from the ground floor.
    vary_type_by_storey: bool = True
    #: Demote upper-level doors that open onto nothing.
    fix_unreachable_doors: bool = True
    demote_door_to: str = "wall_window"
    #: Move ground doors off the corner to a seeded bay along the elevation.
    reposition_doors: bool = True
    #: A door must be at least this many bays from either end of its run.
    door_corner_margin_bays: int = 1
    door_pieces: Tuple[str, ...] = ("wall_door", "wall_door_arched", "wall_door_gothic")
    #: Minimum bays between two doors. Two entrances side by side read as a mistake.
    door_min_separation_bays: int = 3
    #: At most this many doors per elevation.
    max_doors_per_elevation: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.blank_chance < 1.0:
            raise ValueError("blank_chance must be in [0, 1)")
        if self.min_lights_per_elevation < 0:
            raise ValueError("min_lights_per_elevation must be >= 0")


def _rng(seed: int, key: str) -> random.Random:
    """A stable RNG per (seed, key). Never use a shared stream — order would matter."""
    return random.Random(f"{seed}:{key}")


def _walkable_outside(assembly: Assembly) -> Tuple[Dict[int, Set[Cell]], Dict[int, Set[Cell]]]:
    walk: Dict[int, Set[Cell]] = {}
    inside: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind in ("floor", "surface") and "hole" not in p.asset_id:
            walk.setdefault(p.level, set()).update(covered_cells(p))
        elif p.kind == "stair":
            walk.setdefault(p.level, set()).update(covered_cells(p))
        if p.kind == "floor" and "hole" not in p.asset_id:
            inside.setdefault(p.level, set()).update(covered_cells(p))
    return walk, inside


def _door_is_reachable(
    p: SolidPlacement,
    walk: Dict[int, Set[Cell]],
    inside: Dict[int, Set[Cell]],
) -> bool:
    if p.level == 0:
        return True  # the site is outside a ground door
    deck = walk.get(p.level, set())
    room = inside.get(p.level, set())
    for c in covered_cells(p):
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (c[0] + dx, c[1] + dy)
            if n in deck and n not in room:
                return True
    return False


def _elevation_key(p: SolidPlacement) -> Tuple[int, int]:
    """Group walls into elevations: (level, orientation). Yaw 0/180 run along Y."""
    return (p.level, 0 if p.yaw in (0, 180) else 1)


def _swap(p: SolidPlacement, asset_id: str, note: str) -> SolidPlacement:
    desc = catalog_by_id()[asset_id]
    return SolidPlacement(
        piece_id=p.piece_id,
        asset_id=asset_id,
        kind=desc.kind,
        cell=p.cell,
        level=p.level,
        yaw=p.yaw,
        offset_cm=p.offset_cm,
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        tags=desc.tags | frozenset({"varied", note}),
    )


def vary(
    assembly: Assembly,
    spec: Optional[VariationSpec] = None,
) -> Tuple[Assembly, Report]:
    """Apply seeded variation and aperture legality fixes. Piece COUNT is unchanged."""
    opts = spec or VariationSpec()
    catalog = catalog_by_id()

    wanted = set(opts.window_pieces) | {opts.blank_piece, opts.demote_door_to}
    missing = sorted(w for w in wanted if w not in catalog)
    if missing:
        return assembly, Report.from_failures([
            Failure(
                check="variation_piece_missing",
                message=f"variation wants unknown pieces {missing}",
                world_xyz=None,
            )
        ])

    walk, inside = _walkable_outside(assembly)

    # One window family per storey, decided up front so the demotion and repair steps use
    # the SAME family as the choice step. Deciding it lazily let a demoted door introduce a
    # second window type onto a storey that had already picked one.
    from pae.banding import band_faces_of

    exterior_faces = band_faces_of(assembly)
    pieces_avail = [q for q in opts.window_pieces if q in catalog] or ["wall_window"]
    storey_family: Dict[int, str] = {}
    for lvl in sorted({p.level for p in assembly.placements}):
        key = f"storey:{lvl}" if opts.vary_type_by_storey else "family"
        storey_family[lvl] = _rng(opts.seed, key).choice(pieces_avail)

    # --- door repositioning ------------------------------------------------
    # The assembler puts every door on the first bay it finds, which is a corner. A door
    # in the corner of a facade reads as a service hatch, not an entrance, and it collides
    # with quoins and buttresses. Choose a seeded interior bay of the same run instead.
    door_moves: Dict[str, str] = {}   # piece_id -> new asset ("" means becomes plain)
    # One entrance style per building, seeded — not per door.
    building_door_style = _rng(opts.seed, "door_style").choice(
        [q for q in opts.door_pieces if q in catalog] or ["wall_door"]
    )
    if opts.reposition_doors:
        runs: Dict[Tuple[int, int, int], List[SolidPlacement]] = {}
        for p in assembly.placements:
            if p.kind != "wall":
                continue
            # yaw 0/180: thin on X, so the wall RUNS along Y (axis 1). Inverting this
            # silently grouped every wall into one bucket and no door ever moved.
            axis = 1 if p.yaw in (0, 180) else 0
            plane = p.cell[1 - axis]
            runs.setdefault((p.level, axis, plane), []).append(p)

        for key, members in runs.items():
            level, axis, _plane = key
            if level != 0:
                continue
            doors = [m for m in members if "door" in m.asset_id or "gate" in m.asset_id]
            if not doors:
                continue
            ordered = sorted(members, key=lambda m: m.cell[axis])
            margin = opts.door_corner_margin_bays
            candidates = ordered[margin:len(ordered) - margin] if len(ordered) > 2 * margin else []
            if not candidates:
                candidates = ordered
            if len(candidates) <= 1:
                continue
            r = _rng(opts.seed, f"door:{key}")
            # ONE door style for the whole building. Mixing an arched entrance with a
            # square-headed one on the same elevation reads as two different buildings
            # bolted together — which is exactly what it looked like.
            wanted = min(len(doors), opts.max_doors_per_elevation)
            chosen: List[SolidPlacement] = []
            pool = list(candidates)
            r.shuffle(pool)
            for cand in pool:
                if len(chosen) >= wanted:
                    break
                # Enforce separation so two entrances never sit side by side.
                if any(
                    abs(cand.cell[axis] - c.cell[axis]) < opts.door_min_separation_bays
                    for c in chosen
                ):
                    continue
                chosen.append(cand)
            for d in doors:
                door_moves[d.piece_id] = ""            # every old bay loses its door
            for cand in chosen:
                door_moves[cand.piece_id] = building_door_style

    out: List[SolidPlacement] = []
    # Track lights per elevation so we can guarantee the minimum afterwards.
    lights: Dict[Tuple[int, int], List[int]] = {}
    blanked: Dict[Tuple[int, int], List[int]] = {}
    family_of: Dict[Tuple[int, int], str] = {}

    for p in assembly.placements:
        if p.kind != "wall":
            out.append(p)
            continue

        moved = door_moves.get(p.piece_id)
        if moved is not None:
            if moved == "":
                out.append(_swap(p, opts.blank_piece, "door_moved_away"))
            else:
                out.append(_swap(p, moved, "door_moved_here"))
            continue

        is_door = "door" in p.asset_id or "gate" in p.asset_id
        is_window = "window" in p.asset_id

        # 1. Legality — an upper door with nothing outside it is not a door.
        if is_door and opts.fix_unreachable_doors and not _door_is_reachable(p, walk, inside):
            out.append(_swap(p, storey_family.get(p.level, opts.demote_door_to),
                             "door_demoted"))
            key = _elevation_key(p)
            lights.setdefault(key, []).append(len(out) - 1)
            continue

        if is_door or not opts.vary_windows:
            out.append(p)
            continue

        # 2. Variety — glaze along the WHOLE elevation, not only where the assembler
        # happened to put windows. The assembler glazes the first few bays of a run and
        # leaves the rest plain, which is why every window ended up clustered on one
        # corner. Any OUTWARD-FACING wall bay is a candidate; interior partitions are not.
        if p.piece_id not in exterior_faces:
            # Interior partitions keep their role, but if the assembler glazed one, hold it
            # to the storey's family so a stray type never appears on the building.
            if is_window:
                out.append(_swap(p, storey_family.get(p.level, pieces_avail[0]),
                                 "interior_normalised"))
            else:
                out.append(p)
            continue

        key = _elevation_key(p)
        # WINDOW TYPE: one family per storey, absolutely. The previous version fell back
        # to a random type 28% of the time, which put four different window shapes on one
        # elevation at random — the "different kinds of windows on the same building"
        # complaint. A storey now reads as one design.
        family = storey_family.get(p.level, pieces_avail[0])

        # BLANKING: a rhythm along the elevation, not an independent coin flip per bay.
        # Independent flips clustered every window onto one corner and left whole
        # elevations blind. A pattern distributes them evenly and still varies by seed.
        axis = 1 if p.yaw in (0, 180) else 0
        bay = p.cell[axis]
        pattern = _rng(opts.seed, f"rhythm:{key}").choice(
            ("solid", "solid", "alternate", "pairs")
        )
        if pattern == "solid":
            blank = False
        elif pattern == "alternate":
            blank = (bay % 2) == 1
        else:  # pairs — two glazed, one blank
            blank = (bay % 3) == 2

        if blank:
            out.append(_swap(p, opts.blank_piece, "blanked"))
            blanked.setdefault(key, []).append(len(out) - 1)
        else:
            out.append(_swap(p, family, "glazed"))
            lights.setdefault(key, []).append(len(out) - 1)
        family_of[key] = family

    # 3. Restore the minimum: if an elevation lost all its lights, glaze some back.
    for key, idxs in blanked.items():
        have = len(lights.get(key, []))
        need = opts.min_lights_per_elevation - have
        if need <= 0:
            continue
        # Deterministic choice of which blanks to reopen.
        order = sorted(idxs, key=lambda i: out[i].piece_id)
        # Re-glaze with the ELEVATION'S OWN family. Using window_pieces[0] here quietly
        # introduced a second window type onto storeys that had already chosen one — the
        # "different kinds of windows on the same building" complaint, coming from the
        # repair step rather than the choice step.
        fam = family_of.get(key, opts.window_pieces[0])
        for i in order[:need]:
            out[i] = _swap(out[i], fam, "glazed_minimum")

    # 4. Spread windows along long wall runs. Door bays and rhythm blanking can leave
    # every light on one end of an 8-bay elevation even when the pattern is "alternate".
    runs: Dict[Tuple[int, int, int], List[int]] = {}
    for i, p in enumerate(out):
        if p.kind != "wall" or p.piece_id not in exterior_faces:
            continue
        axis = 1 if p.yaw in (0, 180) else 0
        rk = (p.level, axis, p.cell[1 - axis])
        runs.setdefault(rk, []).append(i)

    for rk, idxs in runs.items():
        if len(idxs) < 6:
            continue
        axis = rk[1]
        ordered = sorted(idxs, key=lambda i: out[i].cell[axis])
        bays = [out[i].cell[axis] for i in ordered]
        full = max(bays) - min(bays) + 1
        win_idxs = [i for i in ordered if "window" in out[i].asset_id]
        if not win_idxs:
            continue
        win_bays = [out[i].cell[axis] for i in win_idxs]
        span = max(win_bays) - min(win_bays) + 1
        if span >= full * 0.5:
            continue

        door_idxs = {
            i
            for i in ordered
            if "door" in out[i].asset_id or "gate" in out[i].asset_id
        }
        blank_idxs = [
            i
            for i in ordered
            if i not in door_idxs
            and "window" not in out[i].asset_id
            and out[i].asset_id == opts.blank_piece
        ]
        if not blank_idxs:
            continue

        lo, hi = min(bays), max(bays)
        cluster_mid = (min(win_bays) + max(win_bays)) * 0.5
        run_mid = (lo + hi) * 0.5
        # Cluster biased high → open blanks toward the low end, and vice versa.
        toward_lo = cluster_mid > run_mid
        lvl = out[ordered[0]].level
        fam = storey_family.get(lvl, opts.window_pieces[0])
        target_span = max(int(full * 0.5 + 0.999), span + 1)

        while span < target_span and blank_idxs:
            if toward_lo:
                candidates = [i for i in blank_idxs if out[i].cell[axis] < min(win_bays)]
                if not candidates:
                    candidates = [i for i in blank_idxs if out[i].cell[axis] <= cluster_mid]
            else:
                candidates = [i for i in blank_idxs if out[i].cell[axis] > max(win_bays)]
                if not candidates:
                    candidates = [i for i in blank_idxs if out[i].cell[axis] >= cluster_mid]
            if not candidates:
                break
            pick = (
                min(candidates, key=lambda i: out[i].cell[axis])
                if toward_lo
                else max(candidates, key=lambda i: out[i].cell[axis])
            )
            out[pick] = _swap(out[pick], fam, "spread_glazed")
            blank_idxs.remove(pick)
            win_bays.append(out[pick].cell[axis])
            span = max(win_bays) - min(win_bays) + 1

    varied = Assembly(
        placements=out,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    return varied, Report.from_failures([])


def vary_spec(spec, seed: int):
    """Seeded jitter of the SPEC itself — pitch and proportion, within legal bounds.

    Sizes stay whole bays (a half-bay building is a gap), and pitch stays inside a range
    that the roof primitives can actually build. Variation that breaks the contract is not
    variation, it is a defect — see Ledger C-7.
    """
    import copy

    from pae.spec import RoofSpec

    out = copy.deepcopy(spec)
    r = _rng(seed, f"spec:{spec.name}")
    pitch = spec.roof.pitch * r.uniform(0.85, 1.25)
    pitch = max(0.8, min(2.1, pitch))
    out.roof = RoofSpec(kind=spec.roof.kind, pitch=round(pitch, 3))
    out.seed = seed
    return out

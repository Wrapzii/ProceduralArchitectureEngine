#!/usr/bin/env python3
"""Diagnostic: are multi-storey stairs actually walkable?

Checks three invariants that must hold for every flight, independent of stair
kind or building type:

  INV1  deck under a flight is SOLID       -- a flight at level L stands on deck L
  INV2  deck above a flight is OPEN        -- the run rises through deck L+1
  INV3  flights chain                      -- the top landing of flight L is the
                                              bottom landing of flight L+1

    python tools/diag_stair_walkability.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Cell = Tuple[int, int]


def _sketch(bays_x: int, bays_y: int, stair_at: Cell) -> str:
    rows = []
    for y in range(bays_y):
        row = ["#"] * bays_x
        if y == stair_at[1]:
            row[stair_at[0]] = "S"
        rows.append("".join(row))
    return "\n".join(rows)


def _floor_maps(placements) -> Tuple[Dict[int, Set[Cell]], Dict[int, Set[Cell]]]:
    """(solid_by_level, hole_by_level) from floor placements."""
    from pae.trim import covered_cells

    solid: Dict[int, Set[Cell]] = {}
    hole: Dict[int, Set[Cell]] = {}
    for p in placements:
        if p.kind != "floor":
            continue
        bucket = hole if p.asset_id == "floor_hole" else solid
        bucket.setdefault(p.level, set()).update(covered_cells(p))
    return solid, hole


def audit(name: str, spec) -> List[str]:
    from pae.pipeline import run_through_assemble
    from pae.stair_occupancy import landing_cells_for_stair
    from pae.trim import covered_cells

    defects: List[str] = []
    try:
        _massing, _plan, assembly, report = run_through_assemble(spec)
    except Exception as exc:  # noqa: BLE001 - diagnostic
        return [f"{name}: EXCEPTION {type(exc).__name__}: {exc}"]
    if assembly is None:
        return [f"{name}: ASSEMBLY FAILED {[f.check for f in report.critical][:4]}"]

    stairs = [p for p in assembly.placements if p.kind == "stair"]
    # Spiral helices are four quarters per level in one cell - different contract.
    stairs = [p for p in stairs if "spiral" not in p.asset_id]
    if not stairs:
        return []
    solid, hole = _floor_maps(assembly.placements)

    print(f"\n=== {name} ===")
    by_level: Dict[int, List] = {}
    for s in stairs:
        by_level.setdefault(s.level, []).append(s)

    for level in sorted(by_level):
        for st in by_level[level]:
            cells = sorted(covered_cells(st))
            pads = {n: (c, lv) for (n, c, lv, _f, _t) in landing_cells_for_stair(st)}
            print(
                f"  L{level} {st.asset_id} yaw={st.yaw} cells={cells} "
                f"bottom_pad={pads.get('bottom', ('-',))[0]} "
                f"top_pad={pads.get('top', ('-',))[0]}"
            )

            # INV1 - deck under the flight is solid (level 0 sits on grade).
            if level > 0:
                punched = [c for c in cells if c in hole.get(level, set())]
                if punched:
                    defects.append(
                        f"{name}: INV1 flight L{level} stands over a HOLE at {punched}"
                    )

            # INV2 - deck above the flight is open.
            above = level + 1
            if above in solid or above in hole:
                blocked = [c for c in cells if c not in hole.get(above, set())]
                if blocked:
                    defects.append(
                        f"{name}: INV2 flight L{level} has no opening in deck "
                        f"L{above} at {blocked}"
                    )

            # A landing may only be a hole when the flight it connects to occupies
            # that cell - stepping straight off one run onto the next is fine.
            for pad_name, (pad_cell, pad_level) in pads.items():
                if pad_cell not in hole.get(pad_level, set()):
                    continue
                neighbour = level - 1 if pad_name == "bottom" else level + 1
                touches_neighbour = any(
                    pad_cell in covered_cells(o) for o in by_level.get(neighbour, [])
                ) or pad_cell in covered_cells(st)
                if not touches_neighbour:
                    defects.append(
                        f"{name}: PAD {pad_name} landing of L{level} flight at "
                        f"{pad_cell} on deck L{pad_level} is a HOLE"
                    )

    # INV3 - walking off flight L must actually reach the foot of flight L+1
    # across the deck, not merely land somewhere on the same storey.
    levels = sorted(by_level)
    for a, b in zip(levels, levels[1:]):
        deck = a + 1
        walkable = solid.get(deck, set()) - hole.get(deck, set())
        # Stepping off the top of flight L is allowed even though that bay is open.
        for st in by_level[a]:
            walkable |= covered_cells(st)
        tops = {
            c
            for st in by_level[a]
            for n, c, _lv, _f, _t in landing_cells_for_stair(st)
            if n == "top"
        }
        bottoms = {
            c
            for st in by_level[b]
            for n, c, _lv, _f, _t in landing_cells_for_stair(st)
            if n == "bottom"
        } | {c for st in by_level[b] for c in covered_cells(st)}
        if not tops or not bottoms:
            continue
        seen, frontier = set(tops & walkable) or set(tops), list(tops)
        while frontier:
            cx, cy = frontier.pop()
            for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nb in seen or nb not in walkable:
                    continue
                seen.add(nb)
                frontier.append(nb)
        if not (seen & bottoms):
            defects.append(
                f"{name}: INV3 L{a} arrives at {sorted(tops)} but cannot walk to "
                f"L{b} foot {sorted(bottoms)} across deck L{deck}"
            )
        else:
            steps = min(
                abs(tx - bx) + abs(ty - by_)
                for (tx, ty) in tops
                for (bx, by_) in bottoms
            )
            if steps > 2:
                defects.append(
                    f"{name}: SPREAD L{a}->L{b} landing walk is {steps} bays "
                    f"({sorted(tops)} -> {sorted(bottoms)}) - stair core not compact"
                )
    return defects


def main() -> int:
    from pae.sketch import sketch_to_spec

    cases = []
    for storeys in (2, 3, 4, 5):
        for kind, (bx, by) in (
            ("townhouse", (8, 5)),
            ("keep", (9, 7)),
        ):
            cases.append(
                (
                    f"{kind}_{bx}x{by}_s{storeys}",
                    sketch_to_spec(
                        _sketch(bx, by, (bx // 2, by // 2)),
                        name=f"diag_{kind}_{storeys}",
                        style=kind,
                        storeys=storeys,
                        seed=7,
                    ),
                )
            )

    all_defects: List[str] = []
    for name, spec in cases:
        all_defects.extend(audit(name, spec))

    print("\n================ DEFECTS ================")
    if not all_defects:
        print("none")
    for d in all_defects:
        print(f"  {d}")
    print(f"\ntotal: {len(all_defects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

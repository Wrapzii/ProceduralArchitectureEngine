#!/usr/bin/env python3
"""Diagnostic: multi-storey stair shaft alignment + orphan floor holes.

    python tools/diag_stair_holes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SKETCH_3 = """
########
########
########
####S###
########
"""

SKETCH_4 = """
#########
#########
#########
####S####
#########
"""


def dump(name: str, sketch: str, storeys: int, style: str = "townhouse") -> None:
    from pae.pipeline import run_through_assemble
    from pae.sketch import sketch_to_spec
    from pae.trim import covered_cells

    spec = sketch_to_spec(sketch, name=name, style=style, storeys=storeys, seed=7)
    _massing, _plan, assembly, report = run_through_assemble(spec)
    if assembly is None:
        print(f"{name}: ASSEMBLY FAILED {[f.check for f in report.critical][:6]}")
        return

    stairs = [p for p in assembly.placements if p.kind == "stair"]
    holes = [p for p in assembly.placements if p.asset_id == "floor_hole"]

    print(f"\n=== {name} storeys={storeys} style={style} ===")
    print(f"stairs={len(stairs)} holes={len(holes)}")
    stair_cells_by_level = {}
    for s in stairs:
        cells = sorted(covered_cells(s))
        stair_cells_by_level.setdefault(s.level, set()).update(cells)
        print(f"  stair L{s.level} {s.asset_id} cell={s.cell} yaw={s.yaw} cells={cells}")

    # A hole at level L is justified when a stair at L-1 (emerging) or L (open well)
    # covers that cell.
    for h in sorted(holes, key=lambda p: (p.level, p.cell)):
        cells = sorted(covered_cells(h))
        justified = []
        for c in cells:
            below = c in stair_cells_by_level.get(h.level - 1, set())
            same = c in stair_cells_by_level.get(h.level, set())
            justified.append(bool(below or same))
        flag = "OK  " if all(justified) else "ORPHAN"
        print(f"  {flag} hole L{h.level} cell={h.cell} cells={cells} just={justified}")

    # Shaft alignment: consecutive levels should share cells or be adjacent pads.
    levels = sorted(stair_cells_by_level)
    for a, b in zip(levels, levels[1:]):
        ca, cb = stair_cells_by_level[a], stair_cells_by_level[b]
        shared = ca & cb
        touching = any(
            abs(x1 - x2) + abs(y1 - y2) <= 1 for (x1, y1) in ca for (x2, y2) in cb
        )
        print(
            f"  shaft L{a}->L{b} shared={len(shared)} touching={touching} "
            f"{'OK' if (shared or touching) else 'DISCONNECTED'}"
        )


if __name__ == "__main__":
    dump("diag_3storey", SKETCH_3, 3)
    dump("diag_4storey", SKETCH_4, 4)
    dump("diag_3storey_keep", SKETCH_3, 3, style="keep")

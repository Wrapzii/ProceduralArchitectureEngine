"""Thin end-to-end pipeline helpers (M1 gate)."""

from __future__ import annotations

from typing import Tuple

from pae.assembly_types import Assembly
from pae.plan import FloorPlan
from pae.report import Report
from pae.solver import Massing


def run_through_assemble(
    spec,
    *,
    asset_db=None,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """spec → solve → plan → assemble with a single validation-ready assembly."""
    from pae.assemble import assemble
    from pae.plan import plan
    from pae.solver import solve
    from pae.spec import load_style

    massing, mreport = solve(spec)
    if not mreport.ok or massing is None:
        return massing, None, Assembly(placements=[]), mreport  # type: ignore[arg-type]

    floor_plan, preport = plan(massing)
    if not preport.ok or floor_plan is None:
        return massing, floor_plan, Assembly(placements=[]), preport  # type: ignore[arg-type]

    style, _ = load_style(spec.style)
    assembly, areport = assemble(floor_plan, asset_db, style)
    if not areport.ok:
        return massing, floor_plan, assembly, areport

    return massing, floor_plan, assembly, Report.from_failures([])

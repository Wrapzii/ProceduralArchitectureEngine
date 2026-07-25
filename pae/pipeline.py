"""Thin end-to-end pipeline helpers (M1 / M5 gates)."""

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


def run_through_decorate(
    spec,
    *,
    asset_db=None,
    seed: int | None = None,
    tags=None,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """spec → assemble → decorate (M5 dynamic props from AssetDB tags)."""
    from pae.decorate import decorate

    massing, floor_plan, assembly, report = run_through_assemble(
        spec, asset_db=asset_db
    )
    if not report.ok:
        return massing, floor_plan, assembly, report

    decor_seed = int(seed if seed is not None else getattr(spec, "seed", 0))
    decorated, dreport = decorate(
        assembly,
        asset_db,
        seed=decor_seed,
        tags=tags,
    )
    if not dreport.ok:
        return massing, floor_plan, decorated, dreport
    # Non-critical decorate warnings (empty DB) still return ok assembly.
    return massing, floor_plan, decorated, dreport

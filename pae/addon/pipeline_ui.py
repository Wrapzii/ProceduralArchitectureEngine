"""Thin pipeline wrappers for the add-on Generate panel (calls core modules)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from pae.addon.structure_helpers import coerce_pipeline_spec
from pae.assembly_types import Assembly
from pae.plan import FloorPlan
from pae.report import Failure, Report
from pae.solver import Massing
from pae.spec import BuildingSpec


def run_stage(
    stage: str,
    spec: Any,
    *,
    massing: Optional[Massing] = None,
    floor_plan: Optional[FloorPlan] = None,
    assembly: Optional[Assembly] = None,
    asset_db=None,
) -> Tuple[Optional[Massing], Optional[FloorPlan], Optional[Assembly], Report]:
    """Run one pipeline stage by name."""
    from pae.assemble import assemble
    from pae.plan import plan
    from pae.solver import solve
    from pae.spec import load_style
    from pae.validate import validate

    spec = coerce_pipeline_spec(spec)
    stage = stage.lower()
    if stage == "solve":
        massing, report = solve(spec)
        return massing, None, None, report
    if stage == "plan":
        if massing is None:
            massing, mreport = solve(spec)
            if not mreport.ok or massing is None:
                return massing, None, None, mreport
        floor_plan, report = plan(massing)
        return massing, floor_plan, None, report
    if stage == "assemble":
        if massing is None:
            massing, mreport = solve(spec)
            if not mreport.ok or massing is None:
                return massing, None, None, mreport
        if floor_plan is None:
            floor_plan, preport = plan(massing)
            if not preport.ok or floor_plan is None:
                return massing, floor_plan, None, preport
        style, sreport = load_style(spec.style)
        if not sreport.ok:
            return massing, floor_plan, None, sreport
        assembly, report = assemble(floor_plan, asset_db, style)
        return massing, floor_plan, assembly, report
    if stage == "validate":
        if assembly is None:
            _, _, assembly, areport = run_stage("assemble", spec, asset_db=asset_db)
            if not areport.ok or assembly is None:
                return None, None, assembly, areport
        _, report = validate(assembly)
        return massing, floor_plan, assembly, report
    return (
        massing,
        floor_plan,
        assembly,
        Report.from_failures(
            [
                Failure(
                    check="pipeline_stage",
                    message=f"unknown stage: {stage}",
                    critical=True,
                )
            ]
        ),
    )


def run_full_pipeline(
    spec: Any,
    *,
    asset_db=None,
) -> Tuple[Optional[Massing], Optional[FloorPlan], Optional[Assembly], Report]:
    """spec → solve → plan → assemble → validate."""
    from pae.pipeline import run_through_assemble
    from pae.validate import validate

    building = coerce_pipeline_spec(spec)
    massing, floor_plan, assembly, preport = run_through_assemble(
        building, asset_db=asset_db
    )
    if not preport.ok:
        return massing, floor_plan, assembly, preport
    _, vreport = validate(assembly)
    return massing, floor_plan, assembly, vreport

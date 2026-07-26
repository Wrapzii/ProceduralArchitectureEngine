"""Clean style-shell pipeline hooks (decorate/pipeline may be Codex-dirty).

Use these helpers from gallery/matrix/tools until ``run_through_decorate`` can
call ``apply_style_shell`` inline. Codex merge hook (one line, before detail)::

    from pae.style_apply import apply_style_shell
    assembly, sreport = apply_style_shell(
        assembly, style_id=getattr(spec, "style", None), seed=decor_seed
    )
"""

from __future__ import annotations

from typing import Optional, Tuple

from pae.assembly_types import Assembly
from pae.plan import FloorPlan
from pae.report import Failure, Report
from pae.solver import Massing


def _merge_reports(*reports: Report) -> Report:
    failures = []
    for report in reports:
        failures.extend(report.failures)
    return Report.from_failures(failures)


def apply_style_then_detail(
    assembly: Assembly,
    *,
    style_id: Optional[str],
    seed: int,
    apply_style_shell: bool = True,
    apply_detail: bool = True,
    floor_plan: Optional[object] = None,
) -> Tuple[Assembly, Report]:
    """Style shell then Stage K detail — shared by gallery/matrix paths."""
    from pae.detail_layer import apply_detail_layer
    from pae.style_apply import (
        apply_style_shell as _apply_shell,
        reconcile_stair_wall_clearance,
    )

    reports: list[Report] = []
    current = assembly
    from pae.facade_shell import is_facade_shell_assembly

    if is_facade_shell_assembly(current):
        return current, Report.from_failures(
            [
                Failure(
                    check="style_pipeline_shell_skip",
                    message=(
                        "facade_shell assembly — modular style/detail dress skipped"
                    ),
                    critical=False,
                )
            ]
        )
    # Clear assemble stair/wall kisses even when shell is opted out.
    current = reconcile_stair_wall_clearance(current)
    if apply_style_shell and style_id:
        current, sreport = _apply_shell(
            current, style_id=style_id, seed=seed, floor_plan=floor_plan
        )
        reports.append(sreport)
        if not sreport.ok:
            return current, _merge_reports(*reports)
    if apply_detail:
        current, kreport = apply_detail_layer(current, style_id=style_id, seed=seed)
        reports.append(kreport)
        if not kreport.ok:
            return current, _merge_reports(*reports)
    return current, _merge_reports(*reports) if reports else Report.from_failures([])


def assemble_with_style_shell_and_detail(
    spec,
    *,
    seed: int | None = None,
    apply_style_shell: bool = True,
    apply_detail: bool = True,
    validate_assembly: bool = True,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """assemble → style_shell → detail_layer → validate (no decorate/fitout)."""
    from pae.pipeline import run_through_assemble
    from pae.validate import validate

    decor_seed = int(seed if seed is not None else getattr(spec, "seed", 0))
    style_id = getattr(spec, "style", None)

    massing, floor_plan, assembly, stage_report = run_through_assemble(spec)
    if not stage_report.ok:
        return massing, floor_plan, assembly, stage_report

    assembly, mid_report = apply_style_then_detail(
        assembly,
        style_id=style_id,
        seed=decor_seed,
        apply_style_shell=apply_style_shell,
        apply_detail=apply_detail,
        floor_plan=floor_plan,
    )
    if not mid_report.ok:
        return massing, floor_plan, assembly, mid_report

    if not validate_assembly:
        return massing, floor_plan, assembly, _merge_reports(stage_report, mid_report)
    assembly, vreport = validate(assembly)
    return massing, floor_plan, assembly, _merge_reports(stage_report, mid_report, vreport)


def run_with_style_shell(
    spec,
    *,
    asset_db=None,
    seed: int | None = None,
    tags=None,
    apply_trim: bool = True,
    apply_anchors: bool = False,
    apply_style_shell: bool = True,
    apply_detail: bool = True,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """Full decorate path with style shell before Stage K detail.

    Mirrors ``pipeline.run_through_decorate`` but lives in a clean module so
    gallery/matrix tools and tests do not depend on Codex-dirty pipeline edits.
    """
    from pae.decorate import decorate
    from pae.fitout import fitout_greybox
    from pae.pipeline import run_through_assemble, run_through_validate_trim
    from pae.validate import validate

    if apply_trim:
        massing, floor_plan, assembly, report = run_through_validate_trim(
            spec, asset_db=asset_db, apply_anchors=apply_anchors
        )
    else:
        massing, floor_plan, assembly, report = run_through_assemble(
            spec, asset_db=asset_db, apply_trim=False
        )
        if report.ok:
            assembly, report = validate(assembly)
    if not report.ok:
        return massing, floor_plan, assembly, report

    decor_seed = int(seed if seed is not None else getattr(spec, "seed", 0))
    style_id = getattr(spec, "style", None)

    decorated, dreport = decorate(
        assembly,
        asset_db,
        seed=decor_seed,
        tags=tags,
    )
    if not dreport.ok:
        return massing, floor_plan, decorated, dreport

    decorated, freport = fitout_greybox(decorated, seed=decor_seed)
    if not freport.ok:
        return massing, floor_plan, decorated, freport

    kreport = Report.from_failures([])
    if apply_style_shell or apply_detail:
        decorated, kreport = apply_style_then_detail(
            decorated,
            style_id=style_id,
            seed=decor_seed,
            apply_style_shell=apply_style_shell,
            apply_detail=apply_detail,
            floor_plan=floor_plan,
        )
        if not kreport.ok:
            return massing, floor_plan, decorated, kreport

    decorated, vreport = validate(decorated)
    if not vreport.ok:
        return massing, floor_plan, decorated, vreport
    return massing, floor_plan, decorated, _merge_reports(
        dreport, freport, kreport, vreport
    )


__all__ = [
    "apply_style_then_detail",
    "assemble_with_style_shell_and_detail",
    "run_with_style_shell",
]

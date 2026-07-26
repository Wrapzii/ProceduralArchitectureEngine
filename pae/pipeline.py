"""Thin end-to-end pipeline helpers (M1 / M5 / school gates).

Default structural path: solve → plan → assemble.
School / campus path: assemble → validate → trim → decorate.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pae.assembly_types import Assembly
from pae.plan import FloorPlan
from pae.report import Report
from pae.solver import Massing


def _merge_reports(*reports: Report) -> Report:
    """Combine failures/warnings from multiple stage reports."""
    failures = []
    for report in reports:
        failures.extend(report.failures)
    return Report.from_failures(failures)


def run_through_assemble(
    spec,
    *,
    asset_db=None,
    apply_trim: bool = False,
    apply_arcade: bool = False,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """spec → solve → plan → assemble (+ optional trim / arcade).

    ``spec`` may be a ``BuildingSpec`` or a Stage A/B ``StructureSpec`` (converted
    via ``structure_to_building_spec``).

    Trim is off by default so M1–M4 unit tests assert bare assembler output.
    Pass ``apply_trim=True`` or use ``run_through_validate_trim`` for the
    school / campus default. ``apply_arcade=True`` runs the Stage G walkable
    courtyard arcade after trim (DESIGN_COURTYARD_ARCADE — a room, not colonnade).
    """
    from pae.assemble import assemble
    from pae.plan import plan
    from pae.solver import solve
    from pae.spec import BuildingSpec, load_style

    if not isinstance(spec, BuildingSpec):
        from pae.structure_spec import StructureSpec, structure_to_building_spec

        if isinstance(spec, StructureSpec):
            spec = structure_to_building_spec(spec)

    massing, mreport = solve(spec)
    if not mreport.ok or massing is None:
        return massing, None, Assembly(placements=[]), mreport  # type: ignore[arg-type]

    floor_plan, preport = plan(massing)
    if not preport.ok or floor_plan is None:
        return massing, floor_plan, Assembly(placements=[]), preport  # type: ignore[arg-type]

    style, sreport = load_style(spec.style)
    if not sreport.ok or style is None:
        return massing, floor_plan, Assembly(placements=[]), sreport
    assembly, areport = assemble(floor_plan, asset_db, style)
    if not areport.ok:
        return massing, floor_plan, assembly, areport

    if apply_trim:
        from pae.trim import trim

        assembly, treport = trim(assembly)
        if not treport.ok:
            return massing, floor_plan, assembly, treport

    if apply_arcade:
        from pae.arcade import arcade

        assembly, arc_report = arcade(assembly)
        if not arc_report.ok:
            return massing, floor_plan, assembly, arc_report

    return massing, floor_plan, assembly, Report.from_failures([])


def run_through_validate_trim(
    spec,
    *,
    asset_db=None,
    apply_anchors: bool = False,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """spec → assemble → validate (fail-closed) → trim → re-validate.

    Wave 5 school default: never trim a shell that fails validation.
    Pass ``apply_anchors=True`` to append light-anchor placements after trim
    (no full re-validate — anchor void check is warning-only in ``pae.anchors``).
    """
    from pae.trim import trim
    from pae.validate import validate

    massing, floor_plan, assembly, report = run_through_assemble(
        spec, asset_db=asset_db, apply_trim=False
    )
    if not report.ok:
        return massing, floor_plan, assembly, report

    assembly, vreport = validate(assembly)
    if not vreport.ok:
        return massing, floor_plan, assembly, vreport

    trimmed, treport = trim(assembly)
    if not treport.ok:
        return massing, floor_plan, trimmed, treport

    trimmed, post_report = validate(trimmed)
    if not post_report.ok:
        return massing, floor_plan, trimmed, post_report

    reports = [vreport, treport, post_report]
    if apply_anchors:
        from pae.anchors import apply_light_anchors, validate_anchor_placements

        trimmed, anchor_report = apply_light_anchors(trimmed)
        reports.append(anchor_report)
        reports.append(Report.from_failures(validate_anchor_placements(trimmed)))

    return massing, floor_plan, trimmed, _merge_reports(*reports)


def run_through_decorate(
    spec,
    *,
    asset_db=None,
    seed: int | None = None,
    tags=None,
    apply_trim: bool = True,
    apply_anchors: bool = False,
    apply_detail: bool = True,
) -> Tuple[Massing, FloorPlan, Assembly, Report]:
    """spec → assemble → validate → trim → decorate → detail (M5 + Stage K).

    ``apply_detail`` (default True) runs the generic Stage K detail layer after
    fitout and before the final validate. Opt out with ``apply_detail=False``
    for bare decorate regressions.
    """
    from pae.decorate import decorate

    if apply_trim:
        massing, floor_plan, assembly, report = run_through_validate_trim(
            spec, asset_db=asset_db, apply_anchors=apply_anchors
        )
    else:
        massing, floor_plan, assembly, report = run_through_assemble(
            spec, asset_db=asset_db, apply_trim=False
        )
        if report.ok:
            from pae.validate import validate

            assembly, report = validate(assembly)
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

    from pae.fitout import fitout_greybox

    decorated, freport = fitout_greybox(decorated, seed=decor_seed)
    if not freport.ok:
        return massing, floor_plan, decorated, freport

    kreport = Report.from_failures([])
    if apply_detail:
        from pae.detail_layer import apply_detail_layer

        style_id = getattr(spec, "style", None)
        decorated, kreport = apply_detail_layer(
            decorated,
            style_id=style_id,
            seed=decor_seed,
        )
        if not kreport.ok:
            return massing, floor_plan, decorated, kreport

    from pae.validate import validate

    decorated, vreport = validate(decorated)
    if not vreport.ok:
        return massing, floor_plan, decorated, vreport
    # Non-critical decorate / fitout / detail warnings still return ok assembly.
    return massing, floor_plan, decorated, _merge_reports(
        dreport, freport, kreport, vreport
    )

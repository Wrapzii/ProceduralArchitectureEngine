"""Stage L filesystem delivery pipeline — export → manifest → spawn → bind.

Orchestrates the UE handoff chain without Unreal Editor. Writes per-milestone
artifacts plus a ``pae.delivery/1`` summary report. Fails closed when any stage
or cross-artifact consistency check fails.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

from pae.export.spawn_groups import group_rows_by_asset_id

DELIVERY_SCHEMA = "pae.delivery/1"

JsonDict = Dict[str, Any]
PathLike = Union[str, Path]

_LOC_EPSILON = 1e-6


def delivery_out_path(milestone: str, root: Path) -> Path:
    """Per-milestone delivery summary JSON."""
    return root / "Saved" / "exports" / f"{milestone}_delivery.json"


def batch_delivery_out_path(root: Path) -> Path:
    """Combined summary when multiple milestones run in one invocation."""
    return root / "Saved" / "exports" / "delivery_batch_report.json"


def dry_run_report_path(milestone: str, root: Path) -> Path:
    """Per-milestone dry-run report (not the legacy m6 default)."""
    return root / "Saved" / "exports" / f"{milestone}_dry_run_report.json"


def _normalize_loc(loc: Any) -> Optional[List[float]]:
    if not isinstance(loc, (list, tuple)) or len(loc) != 3:
        return None
    try:
        return [float(loc[0]), float(loc[1]), float(loc[2])]
    except (TypeError, ValueError):
        return None


def _loc_equal(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(abs(float(x) - float(y)) <= _LOC_EPSILON for x, y in zip(a, b))


def check_artifact_consistency(
    manifest: Mapping[str, Any],
    spawn_table: Mapping[str, Any],
    asset_bind: Mapping[str, Any],
) -> JsonDict:
    """Cross-check manifest, spawn table, and asset bind table for drift."""
    failures: List[str] = []

    placements = manifest.get("placements")
    if not isinstance(placements, list):
        failures.append("manifest placements must be an array")
        placements = []

    rows = spawn_table.get("rows")
    if not isinstance(rows, list):
        failures.append("spawn table rows must be an array")
        rows = []

    bindings = asset_bind.get("bindings")
    if not isinstance(bindings, list):
        failures.append("asset bind bindings must be an array")
        bindings = []

    if len(rows) != len(placements):
        failures.append(
            f"spawn row_count {len(rows)} != manifest placement_count {len(placements)}"
        )

    manifest_by_piece: Dict[str, Mapping[str, Any]] = {}
    for idx, placement in enumerate(placements):
        if not isinstance(placement, Mapping):
            failures.append(f"manifest placements[{idx}] must be an object")
            continue
        piece_id = placement.get("piece_id")
        if not isinstance(piece_id, str) or not piece_id:
            failures.append(f"manifest placements[{idx}] missing piece_id")
            continue
        if piece_id in manifest_by_piece:
            failures.append(f"duplicate manifest piece_id {piece_id!r}")
        manifest_by_piece[piece_id] = placement

    seen_pieces: MutableMapping[str, None] = {}
    spawn_asset_ids: set[str] = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            failures.append(f"spawn rows[{idx}] must be an object")
            continue
        piece_id = row.get("piece_id")
        asset_id = row.get("asset_id")
        if isinstance(asset_id, str):
            spawn_asset_ids.add(asset_id)
        if not isinstance(piece_id, str) or not piece_id:
            failures.append(f"spawn rows[{idx}] missing piece_id")
            continue
        if piece_id in seen_pieces:
            failures.append(f"duplicate spawn piece_id {piece_id!r}")
        seen_pieces[piece_id] = None

        placement = manifest_by_piece.get(piece_id)
        if placement is None:
            failures.append(f"spawn row piece_id {piece_id!r} not in manifest placements")
            continue

        if row.get("asset_id") != placement.get("asset_id"):
            failures.append(
                f"asset_id drift for {piece_id!r}: "
                f"spawn={row.get('asset_id')!r} manifest={placement.get('asset_id')!r}"
            )

        row_loc = _normalize_loc(row.get("loc_cm"))
        man_loc = _normalize_loc(placement.get("loc_cm"))
        if row_loc is None or man_loc is None:
            failures.append(f"invalid loc_cm for {piece_id!r}")
        elif not _loc_equal(row_loc, man_loc):
            failures.append(
                f"loc_cm drift for {piece_id!r}: spawn={row_loc} manifest={man_loc}"
            )

        if row.get("yaw") != placement.get("yaw"):
            failures.append(
                f"yaw drift for {piece_id!r}: "
                f"spawn={row.get('yaw')!r} manifest={placement.get('yaw')!r}"
            )

    for piece_id in manifest_by_piece:
        if piece_id not in seen_pieces:
            failures.append(f"manifest piece_id {piece_id!r} missing from spawn rows")

    bind_ids = {
        b.get("asset_id")
        for b in bindings
        if isinstance(b, Mapping) and isinstance(b.get("asset_id"), str)
    }
    missing_bind = sorted(spawn_asset_ids - bind_ids)
    if missing_bind:
        failures.append(
            f"spawn asset_id(s) without bind entry: {', '.join(missing_bind)}"
        )

    extra_bind = sorted(bind_ids - spawn_asset_ids)
    if extra_bind and spawn_asset_ids:
        failures.append(
            f"bind entries without spawn rows: {', '.join(extra_bind)}"
        )

    ism_groups = spawn_table.get("ism_groups")
    if ism_groups is not None:
        if not isinstance(ism_groups, list):
            failures.append("spawn table ism_groups must be an array when present")
        else:
            ism_instance_total = 0
            ism_asset_ids: set[str] = set()
            for gidx, group in enumerate(ism_groups):
                if not isinstance(group, Mapping):
                    failures.append(f"ism_groups[{gidx}] must be an object")
                    continue
                asset_id = group.get("asset_id")
                instances = group.get("instances")
                count = group.get("instance_count")
                if not isinstance(asset_id, str):
                    failures.append(f"ism_groups[{gidx}] missing asset_id")
                    continue
                ism_asset_ids.add(asset_id)
                if not isinstance(instances, list):
                    failures.append(f"ism_groups[{gidx}] instances must be an array")
                    continue
                if count != len(instances):
                    failures.append(
                        f"ism_groups[{asset_id!r}] instance_count {count!r} "
                        f"!= len(instances) {len(instances)}"
                    )
                ism_instance_total += len(instances)

            if ism_instance_total != len(rows):
                failures.append(
                    f"ism_groups total instances {ism_instance_total} "
                    f"!= spawn row_count {len(rows)}"
                )
            if ism_asset_ids != spawn_asset_ids:
                failures.append(
                    "ism_groups asset_id set does not match spawn row asset_ids"
                )

    return {
        "ok": len(failures) == 0,
        "failures": failures,
        "placement_count": len(placements),
        "spawn_row_count": len(rows),
        "bind_count": len(bindings),
        "ism_group_count": len(ism_groups) if isinstance(ism_groups, list) else 0,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rel_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def run_milestone_delivery(
    milestone: str,
    *,
    root: Path,
    write_csv: bool = False,
    force_export: bool = True,
) -> Tuple[JsonDict, int]:
    """Run the full filesystem delivery chain for one milestone.

    Returns ``(delivery_report, exit_code)``. Exit code ``0`` only when
    ``delivery_report['ok']`` is true.
    """
    from tools.export_manifest import manifest_out_path, run_export
    from tools.ue_asset_bind_table import asset_bind_out_path, run_asset_bind_table
    from tools.ue_manifest_dry_run import dry_run_manifest, load_manifest, write_report
    from tools.ue_spawn_table import spawn_table_out_path, run_spawn_table

    stages: JsonDict = {}
    failures: List[str] = []
    artifacts: JsonDict = {}

    manifest_path = manifest_out_path(milestone, root=root)
    dry_path = dry_run_report_path(milestone, root=root)
    spawn_path = spawn_table_out_path(milestone, root=root)
    bind_path = asset_bind_out_path(milestone, root=root)
    summary_path = delivery_out_path(milestone, root=root)

    # Stage 1 — export manifest (always re-export for fresh delivery)
    try:
        if force_export or not manifest_path.is_file():
            rc, manifest_data, report = run_export(milestone, out_path=manifest_path)
            if rc != 0 or manifest_data is None:
                detail = "; ".join(f.message for f in report.critical[:3])
                raise RuntimeError(
                    f"export refused for {milestone}"
                    + (f" ({detail})" if detail else "")
                )
        else:
            manifest_data = load_manifest(manifest_path)
        stages["export"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001 — stage boundary
        msg = f"export: {exc}"
        failures.append(msg)
        stages["export"] = {"ok": False, "error": str(exc)}
        report_doc = _build_milestone_report(
            milestone=milestone,
            ok=False,
            stages=stages,
            failures=failures,
            artifacts=artifacts,
            root=root,
        )
        write_report(report_doc, summary_path)
        return report_doc, 1

    artifacts["manifest"] = _rel_path(manifest_path, root)

    # Stage 2 — dry-run
    try:
        dry = dry_run_manifest(manifest_data)
        write_report(dry, dry_path)
        if not dry["ok"]:
            detail = "; ".join(dry.get("failures", [])[:3])
            raise RuntimeError(f"dry-run failed ({detail})")
        stages["dry_run"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        msg = f"dry_run: {exc}"
        failures.append(msg)
        stages["dry_run"] = {"ok": False, "error": str(exc)}
        report_doc = _build_milestone_report(
            milestone=milestone,
            ok=False,
            stages=stages,
            failures=failures,
            artifacts=artifacts,
            root=root,
        )
        write_report(report_doc, summary_path)
        return report_doc, 1

    artifacts["dry_run_report"] = _rel_path(dry_path, root)

    # Stage 3 — spawn table (manifest already on disk; no auto re-export)
    try:
        spawn_table = run_spawn_table(
            milestone,
            out_path=spawn_path,
            write_csv=write_csv,
            auto_export=False,
            root=root,
        )
        stages["spawn_table"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        msg = f"spawn_table: {exc}"
        failures.append(msg)
        stages["spawn_table"] = {"ok": False, "error": str(exc)}
        report_doc = _build_milestone_report(
            milestone=milestone,
            ok=False,
            stages=stages,
            failures=failures,
            artifacts=artifacts,
            root=root,
        )
        write_report(report_doc, summary_path)
        return report_doc, 1

    artifacts["spawn_table"] = _rel_path(spawn_path, root)
    if write_csv:
        artifacts["spawn_table_csv"] = _rel_path(
            root / "Saved" / "exports" / f"{milestone}_spawn_table.csv",
            root,
        )

    # Stage 4 — asset bind (uses spawn table on disk)
    try:
        asset_bind = run_asset_bind_table(
            milestone,
            out_path=bind_path,
            spawn_table_path=spawn_path,
            auto_export=False,
            root=root,
        )
        stages["asset_bind"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        msg = f"asset_bind: {exc}"
        failures.append(msg)
        stages["asset_bind"] = {"ok": False, "error": str(exc)}
        report_doc = _build_milestone_report(
            milestone=milestone,
            ok=False,
            stages=stages,
            failures=failures,
            artifacts=artifacts,
            root=root,
        )
        write_report(report_doc, summary_path)
        return report_doc, 1

    artifacts["asset_bind"] = _rel_path(bind_path, root)

    # Stage 5 — cross-artifact consistency
    consistency = check_artifact_consistency(manifest_data, spawn_table, asset_bind)
    stages["consistency"] = {"ok": consistency["ok"]}
    if not consistency["ok"]:
        failures.extend(consistency["failures"])
        stages["consistency"]["failures"] = consistency["failures"]

    ism_groups = spawn_table.get("ism_groups")
    ism_group_count = len(ism_groups) if isinstance(ism_groups, list) else 0
    ism_instance_count = (
        sum(g.get("instance_count", 0) for g in ism_groups)
        if isinstance(ism_groups, list)
        else 0
    )

    ok = len(failures) == 0
    report_doc = _build_milestone_report(
        milestone=milestone,
        ok=ok,
        stages=stages,
        failures=failures,
        artifacts=artifacts,
        root=root,
        counts={
            "placements": len(manifest_data.get("placements", [])),
            "spawn_rows": spawn_table.get("row_count", 0),
            "bind_entries": asset_bind.get("bind_count", 0),
            "ism_groups": ism_group_count,
            "ism_instances": ism_instance_count,
        },
        consistency=consistency,
        schemas={
            "manifest": manifest_data.get("schema"),
            "spawn_table": spawn_table.get("schema"),
            "asset_bind": asset_bind.get("schema"),
        },
    )
    write_report(report_doc, summary_path)
    artifacts["delivery_report"] = _rel_path(summary_path, root)
    return report_doc, 0 if ok else 1


def _build_milestone_report(
    *,
    milestone: str,
    ok: bool,
    stages: Mapping[str, Any],
    failures: Sequence[str],
    artifacts: Mapping[str, str],
    root: Path,
    counts: Optional[Mapping[str, int]] = None,
    consistency: Optional[Mapping[str, Any]] = None,
    schemas: Optional[Mapping[str, Any]] = None,
) -> JsonDict:
    doc: JsonDict = {
        "schema": DELIVERY_SCHEMA,
        "milestone": milestone,
        "generated_at": _utc_now_iso(),
        "ok": ok,
        "stages": dict(stages),
        "artifacts": dict(artifacts),
        "failures": list(failures),
    }
    if counts is not None:
        doc["counts"] = dict(counts)
    if consistency is not None:
        doc["consistency"] = dict(consistency)
    if schemas is not None:
        doc["schemas"] = dict(schemas)
    return doc


def run_delivery_batch(
    milestones: Sequence[str],
    *,
    root: Path,
    write_csv: bool = False,
    force_export: bool = True,
) -> Tuple[JsonDict, int]:
    """Run delivery for multiple milestones; write a combined batch report."""
    from tools.export_manifest import VALID_MILESTONES

    unknown = [m for m in milestones if m not in VALID_MILESTONES]
    if unknown:
        choices = ", ".join(sorted(VALID_MILESTONES))
        raise ValueError(f"unknown milestone(s) {unknown!r}; expected one of: {choices}")

    milestone_reports: List[JsonDict] = []
    batch_failures: List[str] = []
    exit_code = 0

    for milestone in milestones:
        report, rc = run_milestone_delivery(
            milestone,
            root=root,
            write_csv=write_csv,
            force_export=force_export,
        )
        milestone_reports.append(report)
        if rc != 0 or not report.get("ok"):
            exit_code = 1
            batch_failures.append(f"{milestone}: delivery failed")

    batch_doc: JsonDict = {
        "schema": DELIVERY_SCHEMA,
        "generated_at": _utc_now_iso(),
        "milestones": list(milestones),
        "ok": exit_code == 0,
        "milestone_reports": milestone_reports,
        "failures": batch_failures,
    }
    batch_path = batch_delivery_out_path(root)
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(
        json.dumps(batch_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return batch_doc, exit_code


__all__ = [
    "DELIVERY_SCHEMA",
    "batch_delivery_out_path",
    "check_artifact_consistency",
    "delivery_out_path",
    "dry_run_report_path",
    "run_delivery_batch",
    "run_milestone_delivery",
]

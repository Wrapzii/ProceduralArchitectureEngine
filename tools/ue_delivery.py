#!/usr/bin/env python3
"""Stage L filesystem delivery entrypoint — full export → UE handoff chain.

Runs export, dry-run, spawn table (with ISM groups), asset bind, and
cross-artifact consistency checks for one or more milestones. Writes a
per-milestone ``pae.delivery/1`` summary plus an optional batch report.

Usage::

    python tools/ue_delivery.py --milestone m1
    python tools/ue_delivery.py --milestone m1 m3 m4_l --csv
    python tools/ue_delivery.py --milestone m1 --no-force-export

No Unreal Editor or Blender required.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.export.delivery import (  # noqa: E402
    batch_delivery_out_path,
    delivery_out_path,
    run_delivery_batch,
    run_milestone_delivery,
)
from tools.export_manifest import VALID_MILESTONES  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run full Stage L filesystem delivery chain for milestone(s).",
    )
    parser.add_argument(
        "--milestone",
        "-m",
        nargs="+",
        default=["m1"],
        choices=sorted(VALID_MILESTONES),
        metavar="MILESTONE",
        help="one or more milestones (default: m1)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="also write spawn table CSV alongside JSON",
    )
    parser.add_argument(
        "--no-force-export",
        action="store_true",
        help="reuse existing manifest when present (still validates downstream)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    milestones: List[str] = list(args.milestone)
    write_csv = args.csv
    force_export = not args.no_force_export

    try:
        if len(milestones) == 1:
            report, rc = run_milestone_delivery(
                milestones[0],
                root=ROOT,
                write_csv=write_csv,
                force_export=force_export,
            )
            summary_path = delivery_out_path(milestones[0], ROOT)
            print(f"Wrote {summary_path}")
            print(
                f"  milestone={milestones[0]} ok={report['ok']} "
                f"schema={report['schema']}"
            )
            counts = report.get("counts", {})
            if counts:
                print(
                    f"  placements={counts.get('placements')} "
                    f"spawn_rows={counts.get('spawn_rows')} "
                    f"bind_entries={counts.get('bind_entries')} "
                    f"ism_groups={counts.get('ism_groups')}"
                )
            if report.get("failures"):
                for line in report["failures"]:
                    print(f"  FAIL: {line}", file=sys.stderr)
            return rc

        batch_doc, rc = run_delivery_batch(
            milestones,
            root=ROOT,
            write_csv=write_csv,
            force_export=force_export,
        )
        batch_path = batch_delivery_out_path(ROOT)
        print(f"Wrote {batch_path}")
        print(
            f"  milestones={','.join(milestones)} ok={batch_doc['ok']} "
            f"schema={batch_doc['schema']}"
        )
        for mreport in batch_doc.get("milestone_reports", []):
            m = mreport.get("milestone", "?")
            counts = mreport.get("counts", {})
            print(
                f"  {m}: ok={mreport.get('ok')} "
                f"rows={counts.get('spawn_rows')} "
                f"ism_groups={counts.get('ism_groups')}"
            )
        if batch_doc.get("failures"):
            for line in batch_doc["failures"]:
                print(f"  FAIL: {line}", file=sys.stderr)
        return rc
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

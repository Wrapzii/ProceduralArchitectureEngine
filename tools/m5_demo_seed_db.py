#!/usr/bin/env python3
"""M5 demo — seed decorative OBJ fixture into AssetDB and decorate M1.

No assemble / solver code changes: measured asset in DB → ``run_through_decorate``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.assets.db import AssetDB  # noqa: E402
from pae.assets.demo_seed import (  # noqa: E402
    DEFAULT_M5_DEMO_DB,
    M5_DEMO_CRATE_ID,
    seed_m5_demo_assets,
)
from pae.pipeline import run_through_assemble, run_through_decorate  # noqa: E402
from pae.spec import m1_box_house_spec  # noqa: E402
from pae.validate import validate  # noqa: E402


def _default_db_path() -> Path:
    return ROOT / DEFAULT_M5_DEMO_DB


def run_demo(db_path: Path, *, seed: int = 0) -> dict:
    db = AssetDB(db_path)
    try:
        ingested = seed_m5_demo_assets(db, root=ROOT)
        if ingested.artifact is None or not ingested.artifact.written_to_db:
            raise SystemExit(f"seed failed: {ingested.report.failures}")

        stored = db.get_asset(M5_DEMO_CRATE_ID)
        assert stored is not None

        _, _, bare, _ = run_through_assemble(m1_box_house_spec(seed=seed))
        _, _, decorated, dreport = run_through_decorate(
            m1_box_house_spec(seed=seed),
            asset_db=db,
            seed=seed,
        )
        _, vreport = validate(decorated)

        bare_n = len(bare.placements)
        decor_n = len(decorated.placements)
        prop_n = sum(1 for p in decorated.placements if p.kind == "prop")
        prop_ids = sorted({p.asset_id for p in decorated.placements if p.kind == "prop"})

        return {
            "db_path": str(db_path),
            "asset_id": M5_DEMO_CRATE_ID,
            "measured_size_cm": list(stored.size_cm),
            "socket_names": [s.name for s in stored.sockets],
            "tags": sorted(stored.tags),
            "bare_placement_count": bare_n,
            "decorated_placement_count": decor_n,
            "prop_placement_count": prop_n,
            "prop_asset_ids": prop_ids,
            "decorate_report_ok": dreport.ok,
            "validate_ok": vreport.ok,
            "validate_critical": [f.check for f in vreport.failures if f.critical],
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed M5 demo decorative AssetDB and run M1 decorate.")
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db_path(),
        help=f"SQLite DB path (default: {DEFAULT_M5_DEMO_DB})",
    )
    parser.add_argument("--seed", type=int, default=0, help="Decorate RNG seed")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable summary")
    args = parser.parse_args(argv)

    summary = run_demo(args.db.resolve(), seed=args.seed)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Seeded {summary['asset_id']} -> {summary['db_path']}")
        print(
            f"M1 placements: {summary['bare_placement_count']} bare -> "
            f"{summary['decorated_placement_count']} decorated "
            f"({summary['prop_placement_count']} props)"
        )
        print(f"Prop asset ids: {', '.join(summary['prop_asset_ids']) or '(none)'}")
        print(f"validate ok={summary['validate_ok']} critical={summary['validate_critical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

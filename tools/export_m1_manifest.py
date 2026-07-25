#!/usr/bin/env python3
"""Export validated M1 box-house manifest to Saved/exports/m1_manifest.json.

No Blender or Unreal Editor required. Fails closed when validation has critical defects.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.assemble import assemble
from pae.export.manifest import export_manifest
from pae.plan import plan
from pae.solver import solve
from pae.spec import load_style, m1_box_house_spec
from pae.validate import validate

OUT_PATH = ROOT / "Saved" / "exports" / "m1_manifest.json"


def build_m1_assembly():
    spec = m1_box_house_spec()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly


def main() -> int:
    assembly = build_m1_assembly()
    _, report = validate(assembly)
    if not report.ok:
        print("validate failed — export refused", file=sys.stderr)
        for f in report.critical:
            print(f"  [{f.check}] {f.message}", file=sys.stderr)
        return 1

    data, out_report = export_manifest(assembly, OUT_PATH, report=report)
    n_assets = len(data["assets"])
    n_placements = len(data["placements"])
    print(f"Wrote {OUT_PATH}")
    print(f"  schema={data['schema']} ok={out_report.ok}")
    print(f"  assets={n_assets} placements={n_placements}")
    print(f"  module_cm={data['module_cm']} storey_cm={data['storey_cm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

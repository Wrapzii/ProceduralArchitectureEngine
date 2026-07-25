#!/usr/bin/env python3
"""Export validated PAE manifests to Saved/exports/{milestone}_manifest.json.

Supports milestones m1, m2, m3, m4_l, m4_u, m4_c, school. No Blender or Unreal
Editor required. Fails closed when validation has critical defects.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pae.assemble import assemble  # noqa: E402
from pae.export.manifest import export_manifest  # noqa: E402
from pae.plan import plan  # noqa: E402
from pae.report import Report  # noqa: E402
from pae.solver import solve  # noqa: E402
from pae.spec import load_style  # noqa: E402
from pae.validate import validate  # noqa: E402

# Milestone label → ``pae.spec`` factory attribute name.
MILESTONE_SPECS: Dict[str, str] = {
    "m1": "m1_box_house_spec",
    "m2": "m2_two_storey_stair_spec",
    "m3": "m3_keep_tower_spec",
    "m4_l": "m4_l_plan_spec",
    "m4_u": "m4_u_plan_spec",
    "m4_c": "m4_courtyard_spec",
    "school": "school_academy_spec",
}

VALID_MILESTONES = frozenset(MILESTONE_SPECS)


def manifest_out_path(milestone: str, root: Path = ROOT) -> Path:
    """Default on-disk path for a milestone manifest."""
    return root / "Saved" / "exports" / f"{milestone}_manifest.json"


def resolve_spec_factory(milestone: str):
    """Return the spec factory callable for *milestone*."""
    attr = MILESTONE_SPECS.get(milestone)
    if attr is None:
        choices = ", ".join(sorted(MILESTONE_SPECS))
        raise ValueError(f"unknown milestone {milestone!r}; expected one of: {choices}")
    from pae import spec as spec_mod

    factory = getattr(spec_mod, attr, None)
    if not callable(factory):
        raise ValueError(f"spec factory {attr!r} is not callable in pae.spec")
    return factory


def milestone_from_manifest_path(path: Path) -> Optional[str]:
    """Infer milestone label from ``{milestone}_manifest.json`` filename."""
    name = path.name
    suffix = "_manifest.json"
    if name.endswith(suffix):
        label = name[: -len(suffix)]
        if label in VALID_MILESTONES:
            return label
    return None


def build_assembly(milestone: str):
    """Run solve → plan → assemble for the given milestone."""
    factory = resolve_spec_factory(milestone)
    spec = factory()
    massing, _ = solve(spec)
    floor_plan, _ = plan(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, None, style)
    return assembly


def run_export(
    milestone: str,
    out_path: Optional[Path] = None,
) -> Tuple[int, Optional[dict], Report]:
    """Validate and export one milestone manifest.

    Returns ``(exit_code, manifest_dict_or_none, validation_report)``.
    """
    out = out_path or manifest_out_path(milestone)
    assembly = build_assembly(milestone)
    _, report = validate(assembly)
    if not report.ok:
        return 1, None, report

    data, _out_report = export_manifest(assembly, out, report=report)
    return 0, data, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export validated PAE UE manifest for a milestone.",
    )
    parser.add_argument(
        "--milestone",
        "-m",
        default="m1",
        choices=sorted(MILESTONE_SPECS),
        help="milestone to export (default: m1)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="override output path (default: Saved/exports/{milestone}_manifest.json)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    milestone = args.milestone
    out_path = Path(args.out) if args.out else manifest_out_path(milestone)
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()

    try:
        rc, data, report = run_export(milestone, out_path=out_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if rc != 0:
        print("validate failed — export refused", file=sys.stderr)
        for f in report.critical:
            print(f"  [{f.check}] {f.message}", file=sys.stderr)
        return 1

    assert data is not None
    n_assets = len(data["assets"])
    n_placements = len(data["placements"])
    print(f"Wrote {out_path}")
    print(f"  milestone={milestone} schema={data['schema']} ok={report.ok}")
    print(f"  assets={n_assets} placements={n_placements}")
    print(f"  module_cm={data['module_cm']} storey_cm={data['storey_cm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

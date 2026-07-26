"""M-A visual proof — sketched U pitched roof → single ridge family (Stage C / D3-9).

Builds the canonical sketched U from ``test_roof_height_field.py``, measures ridge
heights from ``roof_pitched_slope`` placements, writes JSON proof artifacts, and
optionally captures a Blender screenshot when MCP or bpy is available.

Usage::

    python tools/ma_roof_ridge_proof.py
    python tools/ma_roof_ridge_proof.py --blender
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PAE_ROOT = Path(__file__).resolve().parent.parent
if str(PAE_ROOT) not in sys.path:
    sys.path.insert(0, str(PAE_ROOT))

# Classic U: 4-bay legs + 2-bay bridge — rect_cover yields three plates whose
# short spans differ (2 vs 4). Pre-Stage-C ridge heights split ~590 / 1150.
SKETCHED_U = """
####  ####
####  ####
####  ####
####  ####
############
############
"""

ROOF_PITCH = 1.4
ROOF_SEED = 5
RIDGE_SPAN_MODULES = 4
SCREENSHOT_REL = Path("Saved") / "Screenshots" / "ma_sketched_u_roof_proof.png"
EXPORT_REL = Path("Saved") / "exports" / "ma_roof_ridge_report.json"


def _expected_ridge_height_cm() -> float:
    from pae.contract import FLOOR_T_CM, MODULE_CM
    from pae.primitives.roofs import roof_rise_cm

    return roof_rise_cm(ROOF_PITCH, RIDGE_SPAN_MODULES * MODULE_CM) + FLOOR_T_CM


def measure_sketched_u_ridge() -> Dict[str, Any]:
    """Assemble sketched U and return ridge-family metrics."""
    from pae.pipeline import run_through_assemble
    from pae.primitives.roofs import structure_ridge_span_modules
    from pae.sketch import sketch_to_spec
    from pae.validate import validate

    spec = sketch_to_spec(
        SKETCHED_U,
        name="sketched_u_roof",
        storeys=1,
        seed=ROOF_SEED,
        roof_kind="pitched",
        roof_pitch=ROOF_PITCH,
    )
    _massing, _plan, assembly, stage_report = run_through_assemble(spec)
    if assembly is None or not assembly.placements:
        raise RuntimeError(f"assemble produced no placements: {stage_report}")

    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    valleys = [p for p in assembly.placements if p.asset_id == "roof_valley"]
    gables = [p for p in assembly.placements if p.asset_id == "roof_gable_infill"]

    ridge_heights: Set[float] = {round(p.size_cm[2], 1) for p in slopes}
    expected = round(_expected_ridge_height_cm(), 1)
    ma_one_roof = len(ridge_heights) == 1 and next(iter(ridge_heights)) == expected

    _, report = validate(assembly)
    critical = [f.message for f in report.critical]

    return {
        "skill": "ma-roof-ridge-proof",
        "stage": "MP-WS2 Stage C",
        "defect": "D3-9",
        "spec_name": spec.name,
        "roof_kind": "pitched",
        "roof_pitch": ROOF_PITCH,
        "ridge_span_modules": RIDGE_SPAN_MODULES,
        "structure_ridge_span_modules": structure_ridge_span_modules(
            [(0, 0, 11, 1), (0, 2, 3, 5), (8, 2, 11, 5)]
        ),
        "ridge_heights_cm": sorted(ridge_heights),
        "ridge_family_count": len(ridge_heights),
        "expected_ridge_height_cm": expected,
        "ma_one_roof": ma_one_roof,
        "ridge_family": sorted(ridge_heights),
        "slope_count": len(slopes),
        "valley_count": len(valleys),
        "gable_count": len(gables),
        "placement_count": len(assembly.placements),
        "assemble_ok": stage_report.ok,
        "validate_critical": critical,
        "validate_ok": report.ok and not critical,
        "gates": {
            "ma_one_roof": ma_one_roof,
            "ridge_family": sorted(ridge_heights),
            "critical_empty": not critical,
        },
    }


def _gate_path(measurement: Dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = PAE_ROOT / "Saved" / "agent_gates" / f"{stamp}_ma_sketched_u_roof.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(measurement, indent=2) + "\n", encoding="utf-8")
    return out


def _export_path(measurement: Dict[str, Any], *, screenshot: Optional[str]) -> Path:
    out = PAE_ROOT / EXPORT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {**measurement, "screenshot": screenshot}
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def _try_blender_mcp_screenshot() -> Optional[str]:
    """Capture proof shot via RE Blender MCP client when available."""
    re_root = Path(r"C:\Users\WhiteWidow\Documents\GitHub\Unreal Projects\RE")
    client = re_root / "Content" / "Python" / "blender" / "_blender_mcp_client.py"
    if not client.is_file():
        return None

    sys.path.insert(0, str(re_root))
    from Content.Python.blender._blender_mcp_client import execute  # noqa: E402

    build = PAE_ROOT / "pae" / "blender_build.py"
    shot = PAE_ROOT / SCREENSHOT_REL
    code = rf"""
import runpy
from pathlib import Path
ns = runpy.run_path(r"{build.as_posix()}", run_name="pae_blender_build")
reload_pae = ns["reload_pae"]
assemble_and_validate = ns["assemble_and_validate"]
instance_assembly = ns["instance_assembly"]
frame_camera_on_meshes = ns["frame_camera_on_meshes"]
write_screenshot = ns["write_screenshot"]
_ensure_collection = ns["_ensure_collection"]
_clear_pae_objects = ns.get("_clear_pae_objects")

from pae.sketch import sketch_to_spec

SKETCHED_U = '''{SKETCHED_U.strip()}'''
reload_pae()
factory = lambda: sketch_to_spec(
    SKETCHED_U,
    name="sketched_u_roof",
    storeys=1,
    seed={ROOF_SEED},
    roof_kind="pitched",
    roof_pitch={ROOF_PITCH},
)
assembly, report = assemble_and_validate("ma_u", factory)
coll_name = "PAE_MA_RoofProof"
if _clear_pae_objects:
    _clear_pae_objects()
coll = _ensure_collection(coll_name)
instance_assembly(assembly, label="ma_u", target_coll=coll)
frame_camera_on_meshes(collection=coll_name)
out = Path(r"{shot.as_posix()}")
out.parent.mkdir(parents=True, exist_ok=True)
write_screenshot(out)
print("MA_ROOF_PROOF_SCREENSHOT", out, report.ok)
"""
    try:
        execute(code, timeout=300)
    except Exception as exc:
        print(f"blender MCP screenshot skipped: {exc}", file=sys.stderr)
        return None
    return str(shot.relative_to(PAE_ROOT)).replace("\\", "/") if shot.is_file() else None


def _try_local_bpy_screenshot() -> Optional[str]:
    from pae.primitives import bpy_util

    if not bpy_util.HAS_BPY:
        return None

    from pae.blender_build import (
        _ensure_collection,
        assemble_and_validate,
        frame_camera_on_meshes,
        instance_assembly,
        reload_pae,
        write_screenshot,
    )
    from pae.sketch import sketch_to_spec

    reload_pae()
    factory = lambda: sketch_to_spec(
        SKETCHED_U,
        name="sketched_u_roof",
        storeys=1,
        seed=ROOF_SEED,
        roof_kind="pitched",
        roof_pitch=ROOF_PITCH,
    )
    assembly, _report = assemble_and_validate("ma_u", factory)
    coll_name = "PAE_MA_RoofProof"
    coll = _ensure_collection(coll_name)
    instance_assembly(assembly, label="ma_u", target_coll=coll)
    frame_camera_on_meshes(collection=coll_name)
    out = PAE_ROOT / SCREENSHOT_REL
    write_screenshot(out)
    return str(SCREENSHOT_REL).replace("\\", "/")


def capture_screenshot(*, use_blender: bool) -> Optional[str]:
    if not use_blender:
        return None
    shot = _try_blender_mcp_screenshot()
    if shot:
        return shot
    return _try_local_bpy_screenshot()


def append_agent_sync(lines: List[str]) -> None:
    sync = PAE_ROOT / "AGENT_SYNC.md"
    block = "\n".join(lines) + "\n"
    with sync.open("a", encoding="utf-8") as fh:
        fh.write(block)


def main() -> int:
    parser = argparse.ArgumentParser(description="M-A sketched U roof ridge proof")
    parser.add_argument(
        "--blender",
        action="store_true",
        help="Attempt Blender screenshot (MCP client or local bpy)",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip AGENT_SYNC log append",
    )
    args = parser.parse_args()

    measurement = measure_sketched_u_ridge()
    screenshot = capture_screenshot(use_blender=args.blender)
    measurement["screenshot"] = screenshot

    gate_path = _gate_path(measurement)
    export_path = _export_path(measurement, screenshot=screenshot)

    summary = {
        "gate_json": str(gate_path.relative_to(PAE_ROOT)).replace("\\", "/"),
        "export_json": str(export_path.relative_to(PAE_ROOT)).replace("\\", "/"),
        "ridge_heights_cm": measurement["ridge_heights_cm"],
        "ma_one_roof": measurement["ma_one_roof"],
        "screenshot": screenshot,
        "gates": measurement["gates"],
    }
    print(json.dumps(summary, indent=2))

    if not args.no_sync:
        ridge = measurement["ridge_heights_cm"]
        gates = (
            f"ma_one_roof={measurement['ma_one_roof']} "
            f"ridge_family={ridge} "
            f"critical_empty={not measurement['validate_critical']}"
        )
        append_agent_sync(
            [
                f">>> DONE @MA_ROOF_PROOF — sketched U pitched ridge family {ridge} "
                f"(expected {measurement['expected_ridge_height_cm']}); "
                f"gate `{gate_path.name}`; export `{export_path.relative_to(PAE_ROOT)}`"
                + (f"; screenshot `{screenshot}`" if screenshot else "; screenshot=n/a")
                + f". Gates: {gates}.",
            ]
        )

    return 0 if measurement["ma_one_roof"] and measurement["validate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

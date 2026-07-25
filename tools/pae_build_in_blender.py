"""Launch ``pae.blender_build`` inside live Blender via RE Blender MCP TCP client.

Usage (from any shell with RE + PAE on disk)::

    python tools/pae_build_in_blender.py
    python tools/pae_build_in_blender.py --gallery
    python tools/pae_build_in_blender.py --stair-proof
    python tools/pae_build_in_blender.py --openings-proof

Inside Blender MCP ``execute_blender_code`` directly (preferred for agents)::

    exec(open(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py",
        encoding="utf-8",
    ).read())

Gallery (M1–M4 L/U/courtyard side-by-side)::

    from pae.blender_build import build_gallery
    build_gallery()

M2 stair + floor-hole proof (isolated collection, hides roof/upper slab)::

    from pae.blender_build import build_m2_stair_proof
    build_m2_stair_proof()

M1 door + window openings proof (south/west exterior shell, SE elevated)::

    from pae.blender_build import build_m1_openings_proof
    build_m1_openings_proof()
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RE = Path(r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE")
PAE = Path(r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine")
sys.path.insert(0, str(RE))
sys.path.insert(0, str(PAE))

from Content.Python.blender._blender_mcp_client import execute  # noqa: E402

BUILD = PAE / "pae" / "blender_build.py"
LIVE_PNG = PAE / "Saved" / "Screenshots" / "m1_live.png"
GALLERY_PNG = PAE / "Saved" / "Screenshots" / "gallery_m1_m4.png"
STAIR_PROOF_PNG = PAE / "Saved" / "Screenshots" / "m2_stair_proof.png"
OPENINGS_PROOF_PNG = PAE / "Saved" / "Screenshots" / "m1_openings_proof.png"


def _gallery_code() -> str:
    return rf"""
import runpy
ns = runpy.run_path(
    r"{BUILD.as_posix()}",
    run_name="pae_blender_build",
)
result = ns["build_gallery"](write_png=True)
print("PAE_GALLERY_BUILD", result)
"""


def _stair_proof_code() -> str:
    return rf"""
import runpy
ns = runpy.run_path(
    r"{BUILD.as_posix()}",
    run_name="pae_blender_build",
)
result = ns["build_m2_stair_proof"](write_png=True)
print("PAE_STAIR_PROOF_BUILD", result)
"""


def _openings_proof_code() -> str:
    return rf"""
import runpy
ns = runpy.run_path(
    r"{BUILD.as_posix()}",
    run_name="pae_blender_build",
)
result = ns["build_m1_openings_proof"](write_png=True)
print("PAE_OPENINGS_PROOF_BUILD", result)
"""


def _live_code() -> str:
    return rf"""
import runpy
result = runpy.run_path(
    r"{BUILD.as_posix()}",
    run_name="__main__",
)
print("PAE_BUILD_DONE", result.get("main") is not None or True)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PAE blender_build in live Blender")
    parser.add_argument(
        "--gallery",
        action="store_true",
        help="Build M1–M4 L/U/courtyard gallery row (default: live M1/M2/M3 stack)",
    )
    parser.add_argument(
        "--stair-proof",
        action="store_true",
        help="Build isolated M2 stair + floor-hole proof shot (m2_stair_proof.png)",
    )
    parser.add_argument(
        "--openings-proof",
        action="store_true",
        help="Build isolated M1 door+window proof shot (m1_openings_proof.png)",
    )
    args = parser.parse_args()

    if not BUILD.is_file():
        raise SystemExit(f"missing build script: {BUILD}")

    flags = sum(bool(x) for x in (args.stair_proof, args.openings_proof, args.gallery))
    if flags > 1:
        raise SystemExit("choose one of --gallery, --stair-proof, or --openings-proof")

    if args.stair_proof:
        code = _stair_proof_code()
        png = STAIR_PROOF_PNG
    elif args.openings_proof:
        code = _openings_proof_code()
        png = OPENINGS_PROOF_PNG
    elif args.gallery:
        code = _gallery_code()
        png = GALLERY_PNG
    else:
        code = _live_code()
        png = LIVE_PNG

    r = execute(code, timeout=300)
    print(json.dumps(r, indent=2)[:4000])

    print("screenshot", png, "exists", png.exists(), "bytes", png.stat().st_size if png.exists() else 0)


if __name__ == "__main__":
    main()

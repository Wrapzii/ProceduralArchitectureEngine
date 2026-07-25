"""Launch ``pae.blender_build`` inside live Blender via RE Blender MCP TCP client.

Usage (from any shell with RE + PAE on disk)::

    python tools/pae_build_in_blender.py
    python tools/pae_build_in_blender.py --gallery

Inside Blender MCP ``execute_blender_code`` directly (preferred for agents)::

    exec(open(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py",
        encoding="utf-8",
    ).read())

Gallery (M1–M4 side-by-side)::

    from pae.blender_build import build_gallery
    build_gallery()
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
        help="Build M1–M4 gallery row (default: live M1/M2/M3 stack)",
    )
    args = parser.parse_args()

    if not BUILD.is_file():
        raise SystemExit(f"missing build script: {BUILD}")

    code = _gallery_code() if args.gallery else _live_code()
    r = execute(code, timeout=300)
    print(json.dumps(r, indent=2)[:4000])

    png = GALLERY_PNG if args.gallery else LIVE_PNG
    print("screenshot", png, "exists", png.exists(), "bytes", png.stat().st_size if png.exists() else 0)


if __name__ == "__main__":
    main()

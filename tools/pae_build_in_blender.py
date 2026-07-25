"""Launch ``pae.blender_build`` inside live Blender via RE Blender MCP TCP client.

Usage (from any shell with RE + PAE on disk)::

    python tools/pae_build_in_blender.py

Inside Blender MCP ``execute_blender_code`` directly (preferred for agents)::

    exec(open(
        r"C:\\Users\\WhiteWidow\\Documents\\GitHub\\ProceduralArchitectureEngine\\pae\\blender_build.py",
        encoding="utf-8",
    ).read())
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RE = Path(r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE")
PAE = Path(r"C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine")
sys.path.insert(0, str(RE))
sys.path.insert(0, str(PAE))

from Content.Python.blender._blender_mcp_client import execute  # noqa: E402

BUILD = PAE / "pae" / "blender_build.py"
PNG = PAE / "Saved" / "Screenshots" / "m1_live.png"

CODE = rf"""
import runpy
result = runpy.run_path(
    r"{BUILD.as_posix()}",
    run_name="__main__",
)
print("PAE_BUILD_DONE", result.get("main") is not None or True)
"""


def main() -> None:
    if not BUILD.is_file():
        raise SystemExit(f"missing build script: {BUILD}")
    r = execute(CODE, timeout=300)
    print(json.dumps(r, indent=2)[:4000])
    print("screenshot", PNG, "exists", PNG.exists(), "bytes", PNG.stat().st_size if PNG.exists() else 0)


if __name__ == "__main__":
    main()

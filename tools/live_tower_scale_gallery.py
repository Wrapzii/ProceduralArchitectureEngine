"""Build the RAM-safe tower scale proof in the already-open Blender instance."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


CLIENT = Path(
    r"C:\Users\WhiteWidow\Documents\Unreal Projects\RE\Content\Python"
    r"\blender\_blender_mcp_client.py"
)
REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    spec = importlib.util.spec_from_file_location("_pae_blender_client", CLIENT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Blender client: {CLIENT}")
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    code = f"""
import json
import runpy
import sys
from pathlib import Path
repo = {str(REPO)!r}
if repo not in sys.path:
    sys.path.insert(0, repo)
namespace = runpy.run_path(str(Path(repo) / "pae" / "blender_build.py"))
result = namespace["build_gallery"](
    milestones=("tiny_spire", "square_spire", "lighthouse"),
    write_png=True,
)
print(json.dumps(result, default=str))
"""
    print(json.dumps(client.execute(code, timeout=300.0), indent=2))


if __name__ == "__main__":
    main()

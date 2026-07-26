"""PAE package root — also Blender add-on / extension entry."""

from __future__ import annotations

__version__ = "0.2.0"

# Plain dict at module level — NO heavy imports.
# Blender 5.2 discovery fails silently if top-level import of pae.addon errors.
bl_info = {
    "name": "Procedural Architecture Engine",
    "author": "PAE",
    "version": (0, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > PAE",
    "description": "Deterministic procedural buildings for Blender and UE 5.8",
    "category": "Object",
}


def _ensure_repo_on_path() -> None:
    """Put the repo root on sys.path so ``import pae.*`` resolves.

    Works for both legacy ``scripts/addons/pae`` and
    ``extensions/user_default/pae`` junctions (``Path.resolve`` follows them).
    """
    import sys
    from pathlib import Path

    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def register():
    _ensure_repo_on_path()
    from pae import addon as _addon

    _addon.register()


def unregister():
    _ensure_repo_on_path()
    from pae import addon as _addon

    _addon.unregister()


__all__ = ["__version__", "bl_info", "register", "unregister"]

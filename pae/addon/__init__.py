"""Blender add-on UI (§10) — WP-7.

Highest-value feature: validation panel — click defect → select + frame object.

Install: see ``pae/addon/README.md``.
"""

from __future__ import annotations

bl_info = {
    "name": "Procedural Architecture Engine",
    "author": "PAE",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > PAE",
    "description": "Deterministic procedural buildings for Blender and UE 5.8",
    "category": "Object",
}

_modules = (
    "pae.addon.properties",
    "pae.addon.operators",
    "pae.addon.panels",
)


def _collect_classes():
    from pae.addon import operators, panels, properties

    return (
        *properties.classes,
        *operators.classes,
        *panels.classes,
    )


def register():
    import importlib

    import bpy  # type: ignore

    for name in _modules:
        importlib.reload(importlib.import_module(name))

    from pae.addon import operators, panels, properties

    for cls in _collect_classes():
        bpy.utils.register_class(cls)  # type: ignore[union-attr]

    bpy.types.Scene.pae = bpy.props.PointerProperty(type=properties.PAESceneProperties)  # type: ignore[attr-defined]


def unregister():
    try:
        import bpy  # type: ignore
    except ImportError:
        return

    from pae.addon import operators, panels, properties

    if hasattr(bpy.types.Scene, "pae"):
        del bpy.types.Scene.pae

    for cls in reversed(_collect_classes()):
        try:
            bpy.utils.unregister_class(cls)  # type: ignore[union-attr]
        except RuntimeError:
            pass

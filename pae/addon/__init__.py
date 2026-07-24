"""Blender add-on UI (§10) — WP-7.

Highest-value feature: validation panel — click defect → select + frame object.
"""

bl_info = {
    "name": "Procedural Architecture Engine",
    "author": "PAE",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > PAE",
    "description": "Deterministic procedural buildings for Blender and UE 5.8",
    "category": "Object",
}


def register():
    raise NotImplementedError("WP-7: implement addon UI")


def unregister():
    pass

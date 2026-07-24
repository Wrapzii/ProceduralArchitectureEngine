# PAE Blender add-on — install

The add-on lives in the `pae` Python package. Blender must be able to import `pae.*`
(solver, assemble, validate, etc.).

## Option A — symlink (recommended for development)

1. Locate Blender’s scripts folder, e.g.  
   `%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`
2. Create a junction/symlink named `pae` pointing at this repo’s `pae` folder:

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\pae" -Target "C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine\pae"
```

3. In Blender: **Edit → Preferences → Add-ons → search “Procedural Architecture Engine”** → enable.

The registered module is `pae.addon` (package `pae/addon/__init__.py`).

## Option B — copy

Copy the entire `pae` directory into Blender’s `scripts/addons/` folder (same path as above).

## Option C — zip

Zip the `pae` folder so the archive root contains `pae/__init__.py` and `pae/addon/__init__.py`.
Install via **Preferences → Add-ons → Install…** (Blender still needs the parent repo on
`sys.path` unless you vendor the full package).

For a self-contained zip, add a top-level `__init__.py` that re-exports `pae.addon` or install
the repo root on `PYTHONPATH`.

## PYTHONPATH (if imports fail)

If `import pae` fails inside Blender, add the repo root to `PYTHONPATH` before launching:

```powershell
$env:PYTHONPATH = "C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine"
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
```

## UI location

**3D Viewport → Sidebar (N) → PAE tab**

Panels: Spec, Assets, Generate, **Validate** (click defect to select + frame), Export.

## Workflow

1. **Spec** — set style, bays, seed (or **Load M1 Box House**).
2. **Generate** — **Generate Full Pipeline** syncs placeholder meshes and caches validation.
3. **Validate** — click any defect row to select `PAE_<piece_id>` and frame the viewport.
4. **Export** — gated on validation pass (WP-6 export backends may still raise until implemented).

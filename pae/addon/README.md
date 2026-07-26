# PAE Blender add-on — install

The add-on lives in the `pae` Python package. Blender must be able to import `pae.*`
(solver, assemble, validate, etc.).

**Verified on Blender 5.2 LTS** (Steam, 2026-07-25): extension
`bl_ext.user_default.pae` appears in Preferences, enables cleanly, and registers
the N-panel PAE tab.

## Blender 5.2 — Extensions only (recommended)

On Blender 5.2, use **one** install: the **User Default** extension entry in
Preferences. Do **not** create or enable a parallel junction under
`scripts/addons/pae` — that legacy path shows a second **Legacy (User)** listing
and can double-register the add-on.

### Dev install (junction into User Default)

```powershell
$pae = "C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine\pae"
$ext = "$env:APPDATA\Blender Foundation\Blender\5.2\extensions\user_default\pae"
New-Item -ItemType Directory -Force -Path (Split-Path $ext) | Out-Null
if (-not (Test-Path $ext)) {
  New-Item -ItemType Junction -Path $ext -Target $pae
}
```

Enable **Procedural Architecture Engine** from **User Default** in
**Edit → Preferences → Extensions**.

## UI location

**3D Viewport → Sidebar (N) → PAE**

| Panel | Purpose |
|---|---|
| **Procedural Building** | CITY&BEYOND-style sliders (seed, archetype, palette, frontage, storeys, wealth, row) → **Generate Building** |
| **Structure** | Name, style, seed, optional foundation, roof/stair, YAML load/export, **Generate Structure**, Validate |
| **Levels** | Level stack list (add/remove), per-level `height_units`, wall style, sketch text |
| **Spec (Legacy)** | Classic rectangle + storeys footprint UI |
| **Generate** | Primary actions + scene clear checkbox |
| **Validate** | Cached report; click defect → select + frame |
| **Export** | Blend / FBX / UE manifest (validation gate) |
| **Assets** | Tag browse stub (full DB still CLI) |

## Workflow (in Blender)

1. **Structure** — set name/style/seed or **Load Gatehouse Preset** / **Load Structure YAML**.
2. **Levels** — add/remove levels; edit sketch text and `height_units` per level.
3. **Generate Structure** — runs `StructureSpec` → `run_through_assemble` → `validate`
   (placeholder cubes in `PAE_Building`).
4. **Spec (Legacy)** — classic rectangle path via **Generate Current Spec** (unchanged).
5. **Generate → Generate Fortress / Generate School / Build Gallery** — compound builders.
6. **Export Structure YAML** — round-trip §3.1 YAML from the current UI state.
3. **Generate → Generate Fortress / Generate School / Build Gallery** — call
   `pae.blender_build` compound/gallery builders (real meshes in named collections).
4. **Clear PAE Scene First** — when checked, removes prior `PAE_*` collections
   before Gallery/Fortress/School (same as `clear_pae_scene()`).
5. **Reload PAE** — `reload_pae()` after editing Python without restarting Blender.
6. **Validate** — re-run validator; failures show in panel with click-to-frame.
7. **Export** — blocked until cached report has zero critical defects.

### Explicit buttons (Generate panel)

| Button | Core API |
|---|---|
| Generate Structure | `StructureSpec` → `pipeline.run_through_assemble` + `validate` |
| Generate Current Spec | `BuildingSpec` → `pipeline.run_through_assemble` + `validate` |
| Load / Export Structure YAML | `load_structure_yaml` / `StructureSpec.to_yaml()` |
| Load Gatehouse Preset | §3.1 example from `structure_helpers.GATEHOUSE_PRESET_YAML` |
| Generate Fortress | `compound.build_fortress_compound` via `build_fortress_live` |
| Generate School | `build_school_showcase` → `build_gallery(milestones=("school",))` |
| Build Gallery | `build_gallery()` (M1–M4 + fortress) |
| Reload PAE | `blender_build.reload_pae()` |
| Run Validation (Validate panel) | same as generate + cache report |

Errors from `RuntimeError` / validation criticals appear in the status line and
**Last error** box on the Generate panel (not console-only).

## CLI-only (not in UI yet)

These capabilities exist in core but are **not** exposed as single-spec UI fields
because they live on compound builders or need multi-entrance editors:

- **ConnectionPolicy** (`merge` / `connect` / `separate`) — `pae/compound.py`
  presets (`fortress_compound_connections`, `school_compound_connections`)
- **Arcade / balcony gallery** — `BalconySpec` on compound ranges (fortress cloister)
- **Interior fitout** — `decorate` pass / room program beyond `school` footprint kind
- **Multi-entrance lists** — only one optional entrance in Spec panel today
- **Tower specs** — per-tower spiral drums via `TowerSpec` JSON / factories;
  `radius_bays` is continuous from `0.5` to `16`, `shape` is `round` or
  `square`, and `cap_style` / `spire_height_storeys` scale the roof
  independently from the shaft
- **Stage stepping screenshots** — use `tools/pae_build_in_blender.py` flags

Use factories in `pae/spec.py`, `pae/compound.py`, and CLI
`tools/pae_build_in_blender.py` for those paths.

## Headless verify

```powershell
$blender = "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
& $blender --background --python-expr "import addon_utils; print([m.__name__ for m in addon_utils.modules() if 'pae' in m.__name__.lower()])"
```

Extension operator smoke test (generate + validate + fortress):

```powershell
& $blender --background --python tools/pae_addon_blender_smoke.py
```

Writes `Saved/pae_addon_smoke.json` on success.

Unit tests (no Blender):

```powershell
python -m pytest pae/tests/unit/test_addon_helpers.py pae/tests/unit/test_addon_structure.py pae/tests/unit/test_addon_registration.py -q
```

## PYTHONPATH

Usually unnecessary when the junction points at the repo `pae` folder —
`register()` inserts the repo root onto `sys.path` via `Path(__file__).resolve()`.

---

# The add-on is the product surface — work through it

**Rule: test, validate and demo through the add-on, not around it.**

For most of this project's life the add-on has been bypassed. Everything was driven by
calling `pae.*` functions directly from a scripting console — which works, and which is
exactly how two builders shipped for weeks returning `Report.from_failures([])`, a
hardcoded empty report, while the geometry they produced was visibly broken. Nobody saw
it because nobody ran the thing users run.

If a change cannot be exercised through an operator, that is a finding about the add-on,
not a reason to go around it. Add the operator.

### The path that matters

```
Structure / Levels panels ─► structure_from_context() ─► run_full_pipeline(StructureSpec)
Legacy Spec panel       ─► spec_from_context()        ─► run_full_pipeline(BuildingSpec)
                                              │
                     solve → plan → assemble → validate
                                              │
                     sync_assembly_preview()  ▼   validation_report_json
                        (Blender objects)      Validate panel → Frame Defect
```

`Frame Defect` selects and frames the offending object. That is the fastest defect loop
in the project and it is under-used.

### Driving it from outside Blender (LLM / MCP / scripting)

Every panel action is a real operator, so anything that can execute Python in Blender can
drive the add-on end to end — verified working:

```python
p = bpy.context.scene.pae
p.storeys, p.bays_x, p.bays_y, p.seed = 3, 5, 4, 7
bpy.ops.pae.run_full_generate()          # solve → plan → assemble → validate → preview
bpy.ops.pae.run_validate()               # refresh the report
report = json.loads(p.validation_report_json)   # {"ok": bool, "failures": [...]}
bpy.ops.pae.frame_defect(failure_index=0)       # select + frame the offender
```

Prefer these over hand-rolled pipeline calls. They exercise the same code the user does.

## What the add-on actually exposes today — an honest inventory

| panel | what it can do |
|---|---|
| Structure | name, style, seed, optional foundation sketch, roof/stair, YAML load/export, generate + validate |
| Levels | level stack (add/remove), per-level `height_units`, wall style, ASCII sketch text |
| Spec (Legacy) | `building_name`, `style`, `storeys`, `bays_x`, `bays_y`, `footprint_kind`, `seed` |
| Assets | tag filter; browse is a **stub** |
| Generate | run a stage, run the full pipeline, load the m1/school presets, build fortress/school/gallery |
| Validate | run validate, list failures, frame a defect |
| Export | `.blend`, `.fbx`, manifest JSON |

**The structure stack path is the Master Plan §5 authoring surface.** Legacy Spec is still
a rectangle + storeys shortcut. Grid paint (§3.2) is intentionally not started here.

`BuildingSpec` supports far more than either panel can reach — towers, courtyards, room
programs beyond sketch marks, compound connections — and `compound.py` / `site.py` build
whole compounds and streets. Preset buttons for fortress/school/gallery remain hardcoded.

## The gap, and the shape of the fix

The interesting design point is that PAE's real value is not the UI — it is that the
engine **refuses to build things that are wrong**. The natural division is:

- an **LLM authors** the spec (this is a wizardry school: four ranges round a court, a
  gate tower here, arcades on the inner faces)
- **PAE places, and validates** — the guard rail that catches the doorway to nothing, the
  stair into a wall, the floating tower

For that, the add-on now has **StructureSpec YAML round-trip** via Structure / Levels
panels plus load/export operators. Remaining gaps:

1. Grid paint panel (§3.2) — emits the same YAML; not started in MP-WS8.
2. Program region painting (§5 Panel 4) — YAML `program:` blocks are hand-edited for now.
3. Site/compound spec as data — still compound presets / CLI.
4. Report JSON stable enough to feed straight back to an LLM: check name, message,
   `world_xyz`, `piece_id`, severity.

With those, the loop becomes: LLM writes §3.1 YAML → **Load Structure YAML** →
**Generate Structure** → report JSON goes back to the LLM → it revises. That is the product.

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
| **Spec** | Style, footprint, seed, roof, stair, wall height, optional entrance |
| **Generate** | Primary actions + scene clear checkbox |
| **Validate** | Cached report; click defect → select + frame |
| **Export** | Blend / FBX / UE manifest (validation gate) |
| **Assets** | Tag browse stub (full DB still CLI) |

## Workflow (in Blender)

1. **Spec** — set fields or **Load M1 Box House** / **Load School Preset**.
2. **Generate → Generate Current Spec** — runs the same `run_full_pipeline` /
   `validate` path as CLI (placeholder cubes in `PAE_Building`).
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
| Generate Current Spec | `pipeline.run_through_assemble` + `validate` |
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
- **Tower specs** — per-tower spiral drums via `TowerSpec` JSON / factories
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
python -m pytest pae/tests/unit/test_addon_helpers.py pae/tests/unit/test_addon_registration.py -q
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
Spec panel fields ─► spec_from_context() ─► run_full_pipeline()
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
| Spec | `building_name`, `style`, `storeys`, `bays_x`, `bays_y`, `footprint_kind`, `seed` |
| Assets | tag filter; browse is a **stub** |
| Generate | run a stage, run the full pipeline, load the m1/school presets, build fortress/school/gallery |
| Validate | run validate, list failures, frame a defect |
| Export | `.blend`, `.fbx`, manifest JSON |

**That is the whole authoring surface: a rectangle, N storeys, a seed.**

`BuildingSpec` supports far more than the panel can reach — towers, courtyards, room
programs, circulation, aperture policy, roof kinds — and `compound.py` / `site.py` build
whole compounds and streets. None of it is reachable from the UI. The preset buttons are
hardcoded Python (`fortress_bailey_compound_spec()` and friends), so what looks like
authoring is really a menu of fixed scenes.

**So the honest answer to "can I design my own buildings or city plans in it?" is no.**
You can resize a box and press Generate. Everything richer requires editing Python.

## The gap, and the shape of the fix

The interesting design point is that PAE's real value is not the UI — it is that the
engine **refuses to build things that are wrong**. The natural division is:

- an **LLM authors** the spec (this is a wizardry school: four ranges round a court, a
  gate tower here, arcades on the inner faces)
- **PAE places, and validates** — the guard rail that catches the doorway to nothing, the
  stair into a wall, the floating tower

For that, the add-on needs one thing it does not have: **a spec that is data, not panel
fields or hardcoded presets.** `BuildingSpec` is already a dataclass; there is no JSON
in/out for it, and no operator that accepts one.

That work is scoped in `Docs/CASTLE_SCHOOL_ROADMAP.md` Phase 11. The short version:

1. `spec_to_dict` / `spec_from_dict` round-tripping every field, with a schema version.
2. `pae.generate_from_spec_json` — takes a filepath or text block, runs the pipeline,
   writes the report back to `validation_report_json`.
3. A **site/compound** spec so several buildings and their relationships are expressible
   as data, not only single buildings.
4. Report JSON stable enough to feed straight back to an LLM: check name, message,
   `world_xyz`, `piece_id`, severity.

With those four, the loop becomes: LLM writes spec JSON → operator builds and validates →
report JSON goes back to the LLM → it revises. That is the product.

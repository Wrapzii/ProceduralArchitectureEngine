# Facade grammar — Georgian townhouse demo

Parametric **slider → bays/modules** grammar for CITY&BEYOND-style Georgian merchant
townhouses. Metres compile through `pae.contract.MODULE_CM` (400 cm per bay).
Door and stair piece ids come from `pae.shared_ids` so exterior openings and
interior circulation stay aligned.

## Continuous shell (default)

**Default build path:** `build_from_params(...)` and the Blender **Generate Building**
operator use `mode="shell"` — a **continuous exterior shell** via `pae.facade_shell`.

- One solid cream panel per face × storey (not a per-cell modular wall farm).
- Door and window openings are **grammar-cut apertures** in that shell (frames, jambs,
  lintels) — not full-bay `wall_window_*` kit modules standing in for the facade skin.
- Interior partition grids are never shell-tagged; only street/party faces get exterior skin.

**Do not use modular window kits on the shell.** Legacy per-bay `wall_window`,
`wall_window_plain`, `wall_window_cross`, and `wall_window_mullioned` placements must
not appear on exterior shell faces. Regression: `test_shell_has_no_modular_window_kits`
in `pae/tests/unit/test_facade_shell.py`.

Legacy per-cell modular assembly remains available as `build_from_params(...,
mode="modular")` for debugging only — not for CITY&BEYOND demo or user-facing builds.

## Recommended slider sets

| Use case | Frontage | Depth | Storeys | Wealth | Row context | Notes |
|----------|----------|-------|---------|--------|-------------|-------|
| **Quick test** | 10 m | 8 m | 2 | 2 | `freestanding` | Fits switchback stairs on default plot |
| **User demo** | 22 m | 12 m | 4 | 4 | `end_left` | Wide end-terrace showcase; party wall on left |

Wealth drives window density, door tag, and stair kind. Storeys 4 on a small footprint
needs ~16×12 m minimum for switchback circulation — use the user-demo row above for
tall / rich builds.

## Quick test (no Blender)

```powershell
cd C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine
python tools/build_georgian_townhouse_blender.py --dry-run --export-json
```

Writes `Saved/georgian_townhouse/townhouse_summary.json` with bays, placement
count, `report.ok`, and shared door/stair ids.

## Blender build

**Quick (10×8 m, 2 storeys, wealth 2):**

```powershell
blender --background --python tools/build_georgian_townhouse_blender.py -- ^
  --seed 1812 --frontage-m 10 --depth-m 8 --storeys 2 --wealth 2 ^
  --out Saved/georgian_townhouse/townhouse.blend --export-json
```

**User demo (22×12 m, 4 storeys, wealth 4, end_left):**

```powershell
blender --background --python tools/build_georgian_townhouse_blender.py -- ^
  --seed 1812 --frontage-m 22 --depth-m 12 --storeys 4 --wealth 4 ^
  --row-context end_left --out Saved/georgian_townhouse/townhouse.blend --export-json
```

On macOS/Linux replace `^` with `\` and adjust the repo path.

Collection: `PAE_GeorgianTownhouse`. Materials preview as cream render exterior
(`mat_cream_render`) and plaster/board interior via shared material ids.

## Slider meanings

| Slider | Maps to |
|--------|---------|
| `--seed` | Deterministic variation seed |
| `--archetype` | Style pack id (`georgian_merchant`) |
| `--frontage-m` | Street width in metres → `bays_x` (ceil) |
| `--depth-m` | Plot depth in metres → `bays_y` |
| `--storeys` | Storey count (`0` = auto → 3). Use `2` on default 10×8 m; `4` needs ~16×12 m+ |
| `--wealth` | Tier 1–5 richness (`-1` = auto → 2); windows, door tag, stair kind |
| `--weathering` | Wear 0–1 (`-1` = auto from wealth) |
| `--lit-windows` | Night-window intent (metadata; default 0.4) |
| `--row-context` | `freestanding` \| `end_left` \| `end_right` \| `mid` — party-wall faces |

## Shared interior / exterior IDs

`pae.shared_ids.resolve_shared(kind, wealth, role)` picks canonical ids:

- **Doors** — `door_plain` / `door_georgian` (exterior main == interior at high wealth)
- **Stairs** — `stair_straight` or `stair_switchback` by wealth and footprint
- **Materials** — `mat_cream_render` exterior → `mat_plaster_interior` interior

Style substitutions in `pae/styles/georgian_merchant.json` map tags to kit
pieces (`door_georgian` → `wall_door_double`, etc.) for **doors and trim** — not
modular `wall_window_*` bays on the shell.

## Blender add-on

View3D sidebar → **PAE** → **Procedural Building** (top panel).

Sliders match the CITY&BEYOND control surface:

| UI | Property |
|---|---|
| Seed | `facade_seed` |
| Archetype | `facade_archetype` |
| Palette Family | `facade_palette_family` |
| Frontage (m, 0=Auto) | `facade_frontage_m` |
| Depth (m, 0=Auto) | `facade_depth_m` |
| Storeys (0=Auto) | `facade_storeys` |
| Wealth (-1=Auto) | `facade_wealth` |
| Weathering (-1=Auto) | `facade_weathering` |
| Lit Windows | `facade_lit_windows` |
| Row Context | `facade_row_context` |
| Grit District (NF) | `facade_grit_district` |

Then **Generate Building** (`pae.generate_facade`) or **Copy Parameters JSON**.

**Presets** (Procedural Building panel):

| Button | Frontage | Depth | Storeys | Wealth | Row |
|--------|----------|-------|---------|--------|-----|
| Quick Test | 10 m | 8 m | 2 | 2 | freestanding |
| User Demo | 22 m | 12 m | 4 | 4 | end_left |

Operators: `pae.load_facade_quick_preset`, `pae.load_facade_demo_preset`.

### Reload PAE (after a code pull)

Blender caches `pae.*` in `sys.modules`. After pulling shell/grammar changes you
must reload before **Generate Building** or edits appear to do nothing.

1. **PAE → Generate → Reload PAE (pick up UI)** (`pae.reload_pae`) — preferred.
2. Or disable/enable the extension in Blender preferences.
3. Or restart Blender.

Add-on version should read **0.2.1** in preferences after this branch. Background
scripts call `pae.blender_build.reload_pae()` automatically at entry.

## API

```python
from pae.facade_grammar import FacadeParams, build_from_params

params = FacadeParams(seed=42, frontage_m=10, depth_m=8, storeys=2, wealth=2)
massing, plan, assembly, report, params = build_from_params(params)  # mode="shell"
```

## Tests

```powershell
pytest pae/tests/unit/test_facade_grammar.py pae/tests/unit/test_facade_shell.py pae/tests/unit/test_georgian_blender_tool.py -q
```

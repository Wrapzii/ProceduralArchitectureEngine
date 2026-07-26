# Facade grammar — Georgian townhouse demo

Parametric **slider → bays/modules** grammar for CITY&BEYOND-style Georgian merchant
townhouses. Metres compile through `pae.contract.MODULE_CM` (400 cm per bay).
Door and stair piece ids come from `pae.shared_ids` so exterior openings and
interior circulation stay aligned.

## Quick test (no Blender)

```powershell
cd C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine
python tools/build_georgian_townhouse_blender.py --dry-run --export-json
```

Writes `Saved/georgian_townhouse/townhouse_summary.json` with bays, placement
count, `report.ok`, and shared door/stair ids.

## Blender build

```powershell
blender --background --python tools/build_georgian_townhouse_blender.py -- ^
  --seed 1812 --frontage-m 10 --depth-m 8 --storeys 4 --wealth 3 ^
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
| `--storeys` | Storey count (`0` = auto → 3). Use `2` on default 10×8 m; `4` needs ~16×12 m |
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
pieces (`door_georgian` → `wall_door_double`, etc.).

## Blender add-on

View3D sidebar → **PAE** → **Facade Grammar (Georgian)**. Adjust sliders, then
**Generate Georgian Facade** (`pae.generate_facade`).

## API

```python
from pae.facade_grammar import FacadeParams, build_from_params

params = FacadeParams(seed=42, frontage_m=10, depth_m=8, storeys=4, wealth=3)
massing, plan, assembly, report, params = build_from_params(params)
```

## Tests

```powershell
pytest pae/tests/unit/test_facade_grammar.py pae/tests/unit/test_georgian_blender_tool.py -q
```

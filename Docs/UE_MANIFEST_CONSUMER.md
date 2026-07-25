# UE manifest consumer — `pae.manifest/1`

PAE exports a JSON manifest (§8.2) that Unreal reads to spawn **instanced static mesh
actors**. The UE side contains **zero placement logic** — no grid math, no yaw
compensation, no module snapping. If a piece is in the wrong place, fix PAE
(`assemble.py` / export), not the spawner.

## Workflow

```
BuildingSpec → solve → plan → assemble → validate → [bind_to_terrain] → export_manifest
                                                                              │
                                                                              ▼
                                                                    m1_manifest.json
                                                                              │
                                                                              ▼
                                                         UE: load assets + spawn at loc_cm/yaw
```

1. Run the full PAE pipeline in Python (or Blender add-on **Export manifest**).
2. Export is **refused** when `validation.ok` is false or `critical_count > 0`.
3. Optionally call `bind_to_terrain(assembly, heightmap, mode)` **before** export.
   Terrain binding uses **heightmap sampling only** — never landscape raycasts.
4. UE imports FBX/static meshes listed under `assets[]`, then spawns one instance per
   `placements[]` row.

Helper script (no editor required):

```bash
python tools/export_m1_manifest.py
# → Saved/exports/m1_manifest.json
```

### Dry-run consumer (no UE editor)

Before opening Unreal, prove a manifest is spawn-ready:

```bash
python tools/ue_manifest_dry_run.py
# default: Saved/exports/m1_manifest.json (auto-exported when missing)
# → Saved/exports/m6_dry_run_report.json
```

Checks: `schema` = `pae.manifest/1`, required top-level fields, every placement has
`loc_cm` (3 numbers) and `yaw` ∈ `{0, 90, 180, 270}`, each `asset_id` exists in
`assets[]`, and `validation.ok` with `critical_count == 0`. Exit code `0` when
`ok`, else `1`.

### Spawn table (ISM-ready, zero placement math)

For Unreal Editor Python or a one-shot import script, prefer the **spawn table**
over parsing the full manifest. PAE strips debug fields (`cell`, `level`) and
emits one flat row per instance:

```bash
python tools/ue_spawn_table.py --milestone m1
# → Saved/exports/m1_spawn_table.json
python tools/ue_spawn_table.py --milestone m1 --csv
# → Saved/exports/m1_spawn_table.json + m1_spawn_table.csv
```

Refuses when `validation.ok` is false or the manifest fails dry-run checks.
Auto-exports the milestone manifest when missing (same as dry-run).

Spawn table schema (`pae.spawn_table/1`):

| Field | Meaning |
|---|---|
| `schema` | Always `"pae.spawn_table/1"` |
| `milestone` | Source milestone label (`m1`, `m3`, …) |
| `source_manifest` | Relative path to the manifest JSON |
| `row_count` | Number of `rows[]` |
| `rows[]` | One ISM instance: `asset_id`, `loc_cm` (3 floats, cm), `yaw` (int), `piece_id` |

CSV columns (optional): `asset_id`, `loc_cm_x`, `loc_cm_y`, `loc_cm_z`, `yaw`, `piece_id`.

#### UE Editor Python (copy-paste)

```python
# Content/Python/pae_spawn_from_table.py — run in UE with editor open
import json
import unreal
from pathlib import Path

PROJECT_ROOT = Path(unreal.Paths.project_dir())  # or absolute path to PAE checkout
TABLE_PATH = PROJECT_ROOT / "Saved/exports/m1_spawn_table.json"
ASSET_MAP = {
    "wall_plain": "/Game/RE/Architecture/SM_WallPlain.SM_WallPlain",
    "wall_window": "/Game/RE/Architecture/SM_WallWindow.SM_WallWindow",
    # … bind every asset_id from manifest assets[] …
}

def load_spawn_table(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "pae.spawn_table/1":
        raise ValueError(f"unsupported spawn table schema: {data.get('schema')}")
    return data

def spawn_ism_rows(table: dict, parent_actor: unreal.Actor) -> None:
    by_asset: dict[str, list[unreal.Transform]] = {}
    for row in table["rows"]:
        mesh_path = ASSET_MAP.get(row["asset_id"])
        if not mesh_path:
            unreal.log_warning(f"skip unknown asset_id: {row['asset_id']}")
            continue
        loc = row["loc_cm"]
        xform = unreal.Transform(
            unreal.Vector(loc[0], loc[1], loc[2]),
            unreal.Rotator(0.0, float(row["yaw"]), 0.0),
            unreal.Vector(1.0, 1.0, 1.0),
        )
        by_asset.setdefault(row["asset_id"], []).append(xform)

    for asset_id, transforms in by_asset.items():
        mesh = unreal.EditorAssetLibrary.load_asset(ASSET_MAP[asset_id])
        ism = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.InstancedStaticMeshComponent,  # use AInstancedStaticMeshActor BP in practice
            unreal.Vector(0, 0, 0),
        )
        # Typical pattern: spawn AInstancedStaticMeshActor, set StaticMesh, AddInstances
        # piece_id is for debugging — do not use for placement math
        unreal.log(f"PAE spawn {asset_id}: {len(transforms)} instances")

table = load_spawn_table(TABLE_PATH)
spawn_ism_rows(table, parent_actor=None)
unreal.log(f"PAE spawn table done: {table['row_count']} rows from {TABLE_PATH}")
```

**Rules for UE consumers:**

1. Read `rows[]` only — never recompute from `cell` / `level`.
2. `loc_cm` is world position in centimetres; `yaw` is degrees about +Z.
3. Map `asset_id` → static mesh via the **asset bind table** (below) or a DataTable.
4. Use `piece_id` for defect reports and selection labels only.

### Asset bind table (`asset_id` → Content path)

The spawn table carries `asset_id` only — no Unreal soft paths. Generate a bind
stub from the milestone manifest (and optional spawn table for row coverage):

```bash
python tools/ue_asset_bind_table.py --milestone m1
# → Saved/exports/m1_asset_bind.json
```

Refuses when `validation.ok` is false or the manifest fails dry-run checks.
When `Saved/exports/{milestone}_spawn_table.json` exists, asset ids are taken
from spawn-table rows (collision presets still come from the manifest).

Bind table schema (`pae.asset_bind/1`):

| Field | Meaning |
|---|---|
| `schema` | Always `"pae.asset_bind/1"` |
| `milestone` | Source milestone label (`m1`, `m3`, …) |
| `source_manifest` | Relative path to the manifest JSON |
| `source_spawn_table` | Optional — present when spawn table was used for id list |
| `bind_count` | Number of `bindings[]` |
| `bindings[]` | One row per unique `asset_id` |

Each `bindings[]` row:

| Field | Meaning |
|---|---|
| `asset_id` | PAE mesh id (matches manifest `assets[].id` and spawn `rows[].asset_id`) |
| `suggested_content_path` | Stub UE soft path under `/Game/RE/PAE/{MILESTONE}/SM_{asset_id}` |
| `lod0` | LOD0 soft path — initially same stub as `suggested_content_path` |
| `collision_profile` | From manifest `collision[].ue_collision_preset` when present, else `BlockAll` |

#### Filling real paths in UE

1. **Import FBX** from PAE export (or Blender add-on) into
   `/Game/RE/PAE/{MILESTONE}/` — one `UStaticMesh` per `asset_id`.
2. **Rename or retarget** so the asset name matches the bind stub
   (`SM_wall_plain`, `SM_floor`, …) or edit `m1_asset_bind.json` to point at your
   actual mesh paths.
3. **Wire a DataTable or Python map** in RE:

```python
# Content/Python/pae_load_asset_bind.py — run once after import
import json
from pathlib import Path
import unreal

BIND_PATH = Path(unreal.Paths.project_dir()) / "Saved/exports/m1_asset_bind.json"

def load_asset_bind(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "pae.asset_bind/1":
        raise ValueError(f"unsupported bind schema: {data.get('schema')}")
    return {
        row["asset_id"]: row["lod0"]
        for row in data["bindings"]
        if row.get("lod0")
    }

ASSET_MAP = load_asset_bind(BIND_PATH)
mesh = unreal.EditorAssetLibrary.load_asset(ASSET_MAP["wall_plain"])
```

4. **Collision** — update each static mesh's collision (complex-as-simple or
   custom) to match `collision_profile` (`BlockAll`, `OverlapAll`, …). PAE does
   not export physics meshes; the manifest `collision[]` block is advisory only.
5. **LOD1/LOD2** — add optional keys in a forked bind file or DataTable when
   Nanite/LOD chains exist; `lod0` is the only required slot for M6 handoff.

Pair with the spawn table: load `ASSET_MAP` from the bind file, then iterate
`rows[]` from `m1_spawn_table.json` as in the spawn-table example above.

## Schema (`pae.manifest/1`)

| Field | Meaning |
|---|---|
| `schema` | Always `"pae.manifest/1"` |
| `module_cm`, `storey_cm` | Grid contract (duplicate of `contract` for quick reads) |
| `origin_convention` | Always `"min_corner"` — `loc_cm` is the mesh min-corner world origin |
| `contract` | Full contract block: `module_cm`, `storey_cm`, `wall_t_cm`, `floor_t_cm` |
| `assets[]` | Unique meshes: `id`, `fbx` path, `lod` placeholder map `{"0","1","2"}` |
| `placements[]` | One row per instance: `asset_id`, `piece_id`, `loc_cm`, `yaw`, `cell`, `level` |
| `collision[]` | Per-asset collision **stubs** — bind UE presets / complex collision in editor |
| `validation` | Export-time validator snapshot (`ok`, counts, `failures`, `checks`) |
| `terrain_bind` | Optional `{mode, source}` when export followed `bind_to_terrain` |

### Placement spawn (UE pseudocode)

```cpp
for (const auto& Row : Manifest.Placements)
{
    UStaticMesh* Mesh = AssetTable[Row.asset_id].LOD0; // from assets[].lod["0"]
    FTransform Xf;
    Xf.SetLocation(FVector(Row.loc_cm[0], Row.loc_cm[1], Row.loc_cm[2])); // cm → ue units
    Xf.SetRotation(FRotator(0.f, Row.yaw, 0.f).Quaternion());
    SpawnInstanced(Mesh, Xf); // ISM/HISM or AInstancedStaticMeshActor
}
```

**Do not** recompute position from `cell` / `level` in UE — those fields are for
debugging and tooling only. `loc_cm` is authoritative.

### Units and rotation

- All positions are **centimetres** in world space (UE import scale 0.01 unless project
  uses cm-native).
- `yaw` is degrees about +Z: `0 | 90 | 180 | 270` only.
- Pieces with `rotates_about_center` in PAE are already baked into `loc_cm` at export
  time.

### Assets, LOD, collision

- `assets[].fbx` may be empty in stub exports; map `id` → content path in a DataTable.
- `assets[].lod` keys `"0"`, `"1"`, `"2"` are placeholders until meshes are assigned.
- `collision[]` stubs list `asset_id` + `profile` + `ue_collision_preset` — replace with
  real SM collision or custom profiles in UE.

### Validation block

UE **may** refuse to spawn when `validation.ok` is false (export should already gate this).
`validation.checks` groups failures by check name for in-editor defect UI.

## Terrain binding (PAE-side only)

```python
from pae.export import bind_to_terrain, export_manifest

bound = bind_to_terrain(assembly, heightmap_2d, "flatten_pad")
export_manifest(bound, path, report=report, terrain_mode="flatten_pad")
```

Modes: `flatten_pad` (whole building on median pad), `step_terraces` (per-cell storey
snap), `stilts` (clearance above max sample).

Heightmap layout: 2D array `[row_y][col_x]`, Z in cm, indexed by
`(x_cm - origin_x) / module_cm` (nearest neighbour). See `pae/export/terrain.py`.

**Never** raycast the landscape to place PAE buildings — streamed-out regions and
collision lag produce buried cities.

## What UE must not implement

- Module / storey grid math
- Wall boundary-line placement rules (§2.3)
- Yaw footprint compensation
- Socket connection or validator logic

Those belong exclusively to PAE Python. UE is a dumb, fast instancing consumer.

## Related

- Spec: `Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md` §8.2, §8.3, §11 M6
- Export API: `pae/export/manifest.py`
- M1 export: `tools/export_m1_manifest.py`
- M6 dry-run: `tools/ue_manifest_dry_run.py`
- M6 spawn table: `tools/ue_spawn_table.py`
- M6 asset bind: `tools/ue_asset_bind_table.py`

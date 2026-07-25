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

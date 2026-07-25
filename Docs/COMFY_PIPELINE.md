# ComfyUI / image-to-3D decorative pipeline (PAE §9)

Decorative assets only. Structural kit pieces (walls, floors, stairs, arches,
tower arcs) must come from parametric primitives — image-to-3D cannot hit
module dimensions reliably.

## Pipeline

```
ComfyUI ──▶ GLB ──▶ normalise ──▶ measure ──▶ auto-socket
        ──▶ human confirm ──▶ assets.db
```

API entry points (`pae.comfy`):

| Function | Role |
|---|---|
| `ingest_decorative(...)` | Kind gate → normalise → measure → propose sockets → optional DB |
| `confirm_decorative(artifact, db)` | Human confirm → `AssetDB.upsert_asset` |
| `normalize_glb_metadata(GlbMetadata)` | Pure-Python normalise (tests / offline) |
| `propose_decorative_sockets(size, kind)` | `base` prop socket (+ assets proposals) |

### Kind gate

- **Accept:** `statue`, `banner`, `brazier`, `furniture`, `gargoyle`, `fountain`, `prop`, `hero`
- **Reject:** `wall`, `floor`, `stair`, `roof`, `tower_arc`, `tower_crown`, `tower_cap`, `battlement`, `plinth`, `ground`, `arch`, `arcade`

### Pure-Python / test path

Pass `MeasuredAABB` or `GlbMetadata` — no ComfyUI and no Blender required.
Declared prompt sizes are never trusted; measured AABB wins.

### Human confirm

Until `human_confirmed=True` (or `confirm_decorative`), the asset is tagged
`needs_human_confirm` and is **not** written to `assets.db`.

## Material policy

Generated Hunyuan/Comfy paint passes are a **colour guide only**. They often
bake lighting and wrong palettes. Ship **engine-authored** materials (UE/Blender).
Kit geometry elsewhere uses triplanar world-space materials (§9.3); decorative
props follow the same engine-authored rule with the generated texture as optional
desaturated reference (`texture_guide_only` tag).

See `pae.comfy.materials.DEFAULT_MATERIAL_POLICY`.

## Reuse (WP-2)

This module calls into `pae.assets` (`MeasuredAABB`, `normalize_to_min_corner`,
`import_asset_measured`, `propose_sockets`, `module_count`, `height_storeys`,
`AssetDB`) — it does not fork import / fit / DB logic.

## M5 — Generator uses DB without code change

Once a decorative asset is **human-confirmed** and written to `assets.db`, the
generator picks it up by tag:

| API | Role |
|---|---|
| `pae.assets.list_decorative_for_generator(db, tags=…)` | Query confirmed decorative rows |
| `pae.decorate.decorate(assembly, db, seed=…, tags=…)` | Sparse interior-cell prop placement |
| `pae.pipeline.run_through_decorate(spec, asset_db=db)` | assemble → decorate |

Structural `snap_fit` reject (e.g. 1.76 m pillars) is **unchanged** — Comfy /
decorate never weaken the structural import path. Decorative sizes may be
off-grid; precision is irrelevant for props.

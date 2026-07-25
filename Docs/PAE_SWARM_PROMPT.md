# PAE — Swarm Kickoff Prompt

Hand this to each agent. It is written so agents can work in parallel without colliding.

---

## System prompt (give to every agent)

You are building **PAE (Procedural Architecture Engine)**, a Blender add-on that
deterministically generates walkable buildings for Blender and Unreal Engine 5.8.

**Read `Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md` first. It is the specification. Do not
redesign it — implement it.**

### Non-negotiables

1. **The AI describes architecture; deterministic code produces geometry.** No LLM call ever
   emits a coordinate. Specs are declarative and in *bays*, not metres.
2. **All dimensions come from `pae/contract.py`.** Never hard-code 400, 350, 60 or 30.
3. **Every stage returns `(artifact, report)`** where `report.ok: bool` and
   `report.failures: list[str]` — each failure carries a world coordinate.
4. **Never trust a declared asset size. Measure the mesh.**
5. **Geometry is only created in `assemble.py`** (and the parametric primitive library it
   calls). No other module touches meshes.
6. **A check that cannot fail is not a check.** Write the failing test first, watch it fail,
   then fix.

### Definition of done for any task

- Unit tests pass.
- `pae/validate.py` reports `ok=True, critical=[]` on the affected demo building.
- Determinism holds: same `(spec, seed, db_version)` produces a byte-identical assembly hash.
- No new hard-coded dimensions (CI greps for magic numbers).

---

## Work packages

These are ordered by dependency. **WP-1 and WP-2 must land before anything else merges.**

### WP-1 — `contract.py` + `validate.py` ⚠ FIRST, blocks everything
Owner: 1 agent. No dependencies.

Implement the grid contract (§2) and the full validator (§7): end connectivity, vertical
support, collinear gaps, interpenetration, enclosure flood fill, floor coverage, stair
reachability, run fit, aperture sanity.

**Test-first requirement:** build a deliberately broken assembly fixture containing one of
each defect — a wall with a dangling end, a floating piece, two walls with a 3 m gap, two
interpenetrating slabs, an enclosure leak, an unreachable storey, a run with a 1.76 m
leftover. The validator must find **all** of them with correct coordinates before you
implement anything that generates geometry.

*Rationale: the previous system's checker verified that piece origins landed on grid
multiples. It passed while walls had 92 m gaps between them. Validation is the product.*

### WP-2 — Asset DB, sockets, import, fit
Owner: 1 agent. Depends on WP-1.

`pae/assets/{db,import,sockets,fit}.py` per §4. SQLite. Socket auto-proposal from geometry,
`snap_fit` with a 6 % stretch ceiling, min-corner origin normalisation, and the
`rotates_about_center` flag for curved pieces.

Acceptance: import a mesh whose footprint is 1.76 m in a 4 m module and confirm the importer
**rejects or stretches** it rather than accepting it silently.

### WP-3 — Parametric primitive library
Owner: 1–2 agents. Depends on WP-1.

Wall (plain / window / arrowslit / door / arcade with the arch cut **into** the module),
floor, floor-with-hole, straight stair, spiral quarter, tower arc quarter, tower crown,
tower cap, battlement, pitched roof **with gable infill**, ground plinth.

Acceptance: every piece's measured bounding box matches its declared module footprint within
6 cm, and origin sits at the min corner. Ship the measurement table in the PR.

**Blender gotchas that will cost you a day if ignored:**
- Cut booleans on the **core** mesh before joining decorative bands. Cutting a joined mesh
  gives the EXACT solver coplanar faces and silently collapses it to a bare box.
- `bpy.ops.object.modifier_apply` needs the target **active *and* selected**, everything else
  deselected — otherwise it raises and the piece is never exported.
- Smooth-shade only the curved faces of arcs. Flat-shading a 40-segment circle reads as a
  faceted prism; use ≥ 96 segments per full circle.

### WP-4 — Spec, solver, plan
Owner: 1–2 agents. Depends on WP-1.

§3 and §5. Greedy placement plus local repair — **do not reach for a SAT solver**; building
scale is under ~40 volumes. Circulation is a graph problem: prove ground-to-top connectivity
before emitting.

### WP-5 — Assembly
Owner: 1 agent. Depends on WP-2, WP-3, WP-4.

§6. Pure function. Implements the yaw-offset table (§2.2), the boundary-line wall rule
(§2.3), the floor `−FLOOR_T` rule (§2.4) and the ground rule (§2.5).

**These four rules are the entire history of this project's bugs. Implement them from the
table, not from intuition.**

### WP-6 — Export
Owner: 1 agent. Depends on WP-5.

Blender `.blend` with linked duplicates, FBX, and the UE manifest (§8.2). Export **refuses**
to run when validation reports critical defects. Terrain binding samples a **heightmap**,
never a ray-cast.

### WP-7 — Add-on UI
Owner: 1 agent. Depends on WP-4, WP-5.

§10. The highest-value feature is the validation panel: **clicking a defect selects and frames
the offending object**. Build that before the cosmetic panels.

### WP-8 — ComfyUI asset pipeline
Owner: 1 agent. Depends on WP-2.

§9. Decorative assets only. Normalise → measure → auto-socket → human confirm → DB.
Treat generated textures as a colour guide; ship engine-authored materials.

### WP-9 — Tests and CI
Owner: 1 agent. Runs alongside everything.

§10.2: determinism hash, golden-image renders with a 2 % diff threshold, property tests over
random specs, and a magic-number grep.

---

## Milestone gate

Nothing merges to `main` until **M1 (box house)** runs end to end and the validator passes:
one storey, 4 × 3 bays, one door, two windows, flat roof, ground slab.

It is deliberately trivial. The point is to prove the *pipeline*, not the architecture.

---

## Failure modes already paid for — do not rediscover these

| Symptom | Root cause |
|---|---|
| Walls with 92 m gaps | East/north runs placed on `x1`/`y1` instead of the boundary lines `x1+1`/`y1+1` |
| Pieces a full module out of place | Rotation about the min-corner origin with no compensating offset |
| Tower with no curved wall | Four arc quarters offset to four cells instead of sharing the circle centre |
| 8 m hole at each gable | Walls stop at the eaves; nothing generated the gable infill |
| Whole building floating in a void | No ground slab, and no check that anything rests on something |
| Characters stepping up at every threshold | Floor slab top at `+FLOOR_T` instead of placed at `level_z − FLOOR_T` |
| Arcade impossible to tile | 1.76 m pillar in a 4 m module → 2.24 m daylight, two dangling ends each |
| Long vertical smears on every wall | Single XY world projection instead of triplanar |
| Edits appear to do nothing | Blender/UE Python caches modules — drop `sys.modules["pae*"]` / `reload_pae()` |
| Boolean fails / wrong solver on Blender 5 | Use `FLOAT`/`EXACT`/`MANIFOLD` — never `FAST` (renamed to `FLOAT`) |
| Editor locked at 20 GB, force-killed twice | Unbounded loop over ~9,000 actors on the UE game thread |
| Terrain-placed actors buried | Ray-cast landscape collision instead of sampling the heightmap |
| 16-bit heightmap imported as 8-bit stair-steps | `RTF_RGBA8` ignores `rg_channel`; requires `RTF_RGBA32F` |

# Procedural Architecture Engine — Design Document

**Target:** a Blender add-on that deterministically generates walkable buildings for Blender
and Unreal Engine 5.8, with no manual mesh placement.

**Status:** greenfield. This document is the build specification. It is written to be
executed by multiple agents working in parallel, so every module below states its contract,
its inputs, its outputs, and its acceptance test.

---

## 0. Core principle

> **The AI describes architecture. Deterministic code produces geometry.**

An LLM is good at "a three-storey academy with a cloistered courtyard and a stair tower on
the north-east corner." It is bad at placing 1,800 meshes without one of them ending up 4 m
inside a wall. So the LLM emits a **spec** (structured data), and a solver turns that spec
into geometry using integer arithmetic on a fixed grid.

Nothing in the pipeline is allowed to "eyeball" a placement. If a stage cannot prove its
output is correct, it fails loudly rather than emitting plausible-looking geometry.

### Why this document exists

A previous iteration built a castle by having an LLM place pieces directly. Every defect —
walls with 92 m gaps, an 8 m hole in a gable, towers with no curved wall, a building floating
in a void with no ground — was found by a human looking at a render, never by the code. The
automated check that was running verified that piece *origins* landed on grid multiples,
which passed happily while the walls did not touch.

**Section 7 (Validation) is therefore the most important section in this document.** Build it
first. A generator without a validator is a defect generator.

---

## 1. Pipeline

```
  spec ──▶ constraint solver ──▶ floor plan ──▶ module assembly ──▶ validation
                                                                        │
                                                     ┌──────────────────┘
                                                     ▼
                                              decoration ──▶ export
```

Every arrow is a **typed, serialisable hand-off** (JSON). Any stage can be run standalone
against a saved artefact from the previous stage. This matters for a swarm: agents can work
on different stages without a live dependency on each other.

Every stage **self-checks** its own output before passing it on, and returns
`(artifact, report)` where `report.ok` is a boolean and `report.failures` is a list of
human-readable defects **with coordinates**.

| Stage | Input | Output | Owner module |
|---|---|---|---|
| 1. Spec | natural language or UI sliders | `BuildingSpec` | `pae/spec.py` |
| 2. Constraint solve | `BuildingSpec` | `Massing` (volumes, storeys) | `pae/solver.py` |
| 3. Floor plan | `Massing` | `FloorPlan` (cell grid per storey) | `pae/plan.py` |
| 4. Assembly | `FloorPlan` + asset DB | `Assembly` (placements) | `pae/assemble.py` |
| 5. Validation | `Assembly` | `ValidationReport` | `pae/validate.py` |
| 6. Decoration | `Assembly` | `Assembly` + props | `pae/decorate.py` |
| 7. Export | `Assembly` | `.blend`, FBX, manifest JSON | `pae/export.py` |

---

## 2. The grid contract

Everything derives from three numbers. They live in `pae/contract.py` and nothing may
hard-code them.

```python
MODULE_CM  = 400.0   # grid cell, XY
STOREY_CM  = 350.0   # floor-to-floor
WALL_T_CM  =  60.0   # nominal wall thickness
FLOOR_T_CM =  30.0   # floor slab thickness
```

**Cell → world is integer arithmetic:**

```python
world_cm = (cell_x * MODULE_CM + off_x,
            cell_y * MODULE_CM + off_y,
            level * STOREY_CM   + off_z)
```

### 2.1 Origin rule

**Every asset's origin is its minimum corner** `(min_x, min_y, min_z)` — never its centre.
Both Blender and Unreal place at the origin; a centred origin puts every piece half a module
out of position.

### 2.2 Rotation offset rule — *read this twice*

Because the origin is the min corner, **rotation swings a piece out of its own cell.**

For a piece with unrotated footprint `(sx, sy)`:

| yaw | local box maps to | required offset |
|---|---|---|
| 0° | `X[0,sx] Y[0,sy]` | `(0, 0)` |
| 90° | `X[-sy,0] Y[0,sx]` | `(+sy, 0)` |
| 180° | `X[-sx,0] Y[-sy,0]` | `(+sx, +sy)` |
| 270° | `X[0,sy] Y[-sx,0]` | `(0, +sx)` |

A 60 × 400 wall placed at yaw 90 with no offset lands **a full module into the previous
cell**. This produced 46 wall gaps in the prior system, the worst measuring 92 m.

**Exception — centred pieces.** Curved pieces (tower arc quarters) are authored about their
circle centre, so their origin *is* the rotation centre. These take **no** offset, and all
four quarters of a tower are placed at the **same** cell. Offsetting them to four cells
scatters the arcs and the tower ends up with no curved wall at all. Assets declare this via
the `rotates_about_center` flag (§4).

### 2.3 Wall run rule

A wall occupies the **low-X strip of its cell** (thin in X, spanning Y, at local `X[0, 60]`).
Therefore a rectangular room's four wall runs sit on the **boundary lines**:

```
  west  run: x = x0            yaw 0
  east  run: x = x1 + 1        yaw 180
  south run: y = y0            yaw 270
  north run: y = y1 + 1        yaw 90
```

Placing the east/north runs on `x1`/`y1` leaves them a full module inside the footprint.
That single off-by-one is where the 92 m gaps came from.

### 2.4 Floor rule

A floor slab spans `z[0, FLOOR_T]` after origin normalisation, so its **top** is at
`+FLOOR_T`. Place at `level_z − FLOOR_T` so the walking surface lands on the storey.
Otherwise every floor sits 30 cm proud and characters step up at every threshold.

### 2.5 Ground rule

**A building must rest on something.** Emit a ground/plinth slab whose top is at
`z = −FLOOR_T` under the whole footprint, or bind to terrain (§8.3). The prior system
produced a complete castle floating in a void because nothing ever checked this.

---

## 3. Stage 1 — Spec

`BuildingSpec` is the only thing an LLM writes. It is **declarative and dimensionless where
possible** (bays, not metres).

```python
@dataclass
class BuildingSpec:
    name: str
    style: str                      # "gothic_academy", "keep", "townhouse"
    footprint: FootprintSpec        # see below
    storeys: int
    storey_use: list[str]           # ["hall", "library", "dormitory"]
    towers: list[TowerSpec]
    roof: RoofSpec
    circulation: CirculationSpec    # stairs, corridors
    openings: OpeningPolicy         # window/door frequency per storey and face
    seed: int
```

```python
@dataclass
class FootprintSpec:
    kind: str                       # "rect" | "L" | "U" | "courtyard" | "compound"
    bays_x: int                     # in MODULES, not metres
    bays_y: int
    wing_depth: int = 2             # for L/U/courtyard: range depth in modules
    courtyard: bool = False
```

**Rule:** the spec never contains world coordinates. If an LLM emits centimetres, the spec
loader rejects it. This is what stops the model from "placing" anything.

### 3.1 Style presets

Styles live in `pae/styles/*.json` and bind a style name to asset tags, proportions and
policies:

```json
{
  "id": "gothic_academy",
  "roof_pitch": 1.05,
  "window": {"tag": "window_gothic", "per_bay": 1, "skip_ground": false},
  "wall_bands": {"plinth_cm": 45, "cornice_cm": 30},
  "tower": {"cap": "cone_steep", "crown": true, "finial": true},
  "materials": {"wall": "stone_ashlar", "roof": "slate_blue", "trim": "stone_light"}
}
```

Roof pitch, band heights and window shape are the three biggest silhouette drivers. Do not
let them be implicit.

---

## 4. Asset database

The engine is **asset-agnostic**. It knows nothing about specific meshes; it queries by
capability.

### 4.1 Asset record

```python
@dataclass
class Asset:
    id: str
    path: str                       # .blend/.fbx/library link
    kind: str                       # wall | floor | roof | stair | tower_arc | prop
    footprint_modules: tuple[int, int]
    height_storeys: float
    size_cm: tuple[float, float, float]   # MEASURED, not declared
    origin: str = "min_corner"
    rotates_about_center: bool = False
    sockets: list[Socket]
    tags: set[str]                  # {"window_gothic","exterior","defensive"}
    lod: dict[int, str] | None = None
```

### 4.2 Sockets — the connection contract

A socket is a named attachment point with a position, a direction, and a type. Sockets are
what make assets composable without the engine knowing their geometry.

```python
@dataclass
class Socket:
    name: str            # "end_a", "end_b", "top", "bottom", "face_out"
    pos_cm: tuple[float, float, float]   # local, origin-relative
    normal: tuple[float, float, float]   # outward direction
    type: str            # "wall_end" | "floor_edge" | "stair_top" | "roof_eave"
    tags: set[str]       # {"module_400"} for compatibility filtering
```

**Compatibility rule:** socket `A` may connect to socket `B` if
`A.type == B.type`, tags intersect, and normals are anti-parallel within tolerance.

Every `wall` asset **must** declare `end_a` and `end_b`. The validator uses these to prove no
wall terminates in mid-air (§7.1).

### 4.3 Import & annotation (dynamic assets)

New assets — including anything produced by ComfyUI (§9) — enter through
`pae/assets/import.py`, which:

1. Imports the mesh, applies transforms, and **measures** the real bounding box.
   *Never trust a declared size.* A prior kit shipped a "1 module" pillar that measured
   1.76 m in a 4 m cell, leaving 2.24 m of daylight and two dangling ends per pillar.
2. Normalises the origin to the min corner (or flags `rotates_about_center`).
3. **Auto-proposes sockets** from geometry:
   - `wall`: ends are the faces perpendicular to the long axis.
   - `floor`: four edge sockets at the slab perimeter.
   - `stair`: `bottom` at the lowest tread, `top` at the highest.
4. Opens the **socket annotation panel** for a human to confirm or adjust.
5. Runs `snap_fit` (§4.4) and refuses the asset if it cannot be made to fit a module.
6. Writes the record to `assets.db` (SQLite) — the asset is now first-class and every
   generator can use it immediately.

### 4.4 Fit and scale policy

If an asset's footprint is not a whole number of modules:

```python
def snap_fit(size_cm, module=MODULE_CM, tol=6.0, max_stretch=0.06):
    n = max(1, round(size_cm / module))
    target = n * module
    err = abs(size_cm - target) / target
    if err <= tol / target:  return ("ok", 1.0)
    if err <= max_stretch:   return ("scale", target / size_cm)   # stretch to fit
    return ("reject", target / size_cm)                            # needs re-authoring
```

Non-uniform stretch is applied on the **long axis only**, so wall thickness and storey height
never drift. Anything needing more than ~6 % is rejected with the required factor reported,
because beyond that the masonry scale visibly distorts.

---

## 5. Stage 2–3 — Solver and floor plan

### 5.1 Constraint solver

Input `BuildingSpec` → output `Massing`: a set of rectangular volumes in **cell coordinates**
with storey counts.

Hard constraints (violations = failure, not warning):

- Volumes may abut but never overlap.
- Every volume is reachable from an entrance volume through door-permitting boundaries.
- Every storey above ground is served by at least one stair (§5.3).
- Tower volumes attach to a wall run or a corner, never free-float.
- Courtyards are explicitly *outside* the enclosed envelope, not a hole in it.

Implementation: greedy placement + local repair. This is not a hard packing problem at
building scale (typically < 40 volumes) so do **not** reach for a SAT solver first.

### 5.2 Floor plan

`Massing` → `FloorPlan`: for each storey, a 2D grid of `CellRole`:

```python
class CellRole(Enum):
    EXTERIOR   = 0
    INTERIOR   = 1
    WALL_LINE  = 2
    DOOR       = 3
    STAIR      = 4
    VOID       = 5   # stairwell / light well - no floor
    COURTYARD  = 6   # open to sky, has ground, no roof
```

The plan is the single source of truth for what goes where. Assembly may not invent cells.

### 5.3 Circulation

Stairs are solved as a graph problem, not decorated in afterwards:

- Nodes = (storey, region). Edges = stair runs.
- Requirement: the graph is connected from ground to top for every region.
- A straight run spans exactly 2 modules and rises exactly 1 storey — so runs stack.
- A spiral is 4 × 90° quarters per storey, each raised `STOREY/4`.
- Every stair top requires a `VOID` cell above it, or the character walks into a ceiling.

---

## 6. Stage 4 — Assembly

Pure function: `(FloorPlan, AssetDB, style) -> Assembly`.

```python
@dataclass
class Placement:
    asset_id: str
    cell: tuple[int, int]
    level: int
    yaw: int                  # 0/90/180/270 only
    offset_cm: tuple[float, float, float]   # from §2.2 + §2.4 rules
```

Assembly **selects** assets by tag from the style, applies the offset rules, and emits
placements. It contains no geometry code and no aesthetic judgement.

**Instances, not merged meshes.** Blender uses linked duplicates (shared mesh data); the
export manifest carries transforms. This preserves instancing, per-piece LOD and World
Partition streaming in UE. A merged mesh costs full memory per copy and cannot stream.

---

## 7. Stage 5 — Validation ⚠ build this first

Treat every wall as a **solid rectangular prism**. Ask the questions a person would ask.
Each check returns defects **with world coordinates**.

### 7.1 End connectivity — the primary rule

> A wall may never terminate in mid-air. Both ends must butt against something: another
> wall, a corner, a tower, a buttress, or a terminating pilaster.

For each wall, probe a thin slab beyond each end face (`TOL = 6 cm`). If no geometry
intersects the probe, that end is **dangling** — report `(piece, end, world_xyz)` and,
where possible, suggest the asset that would close it.

This check alone caught 24 real defects the render-based review had missed.

### 7.2 Vertical support

Nothing floats. Every piece rests on ground, a floor slab, or the piece below (within
35 cm). Report floaters with coordinates. *This is the check that would have caught an entire
castle suspended in a void.*

### 7.3 Collinear gaps

Walls sharing a plane, axis and level must butt edge to edge. Report any daylight `> TOL`
with its size and the two pieces involved.

### 7.4 Interpenetration

Solids may not overlap by more than `TOL` on all three axes — overlapping geometry z-fights
and is as wrong as a gap.

### 7.5 Enclosure

Per storey, voxelise at chest height (~1.2 m above the floor) and flood-fill from outside the
bounding box. Any `INTERIOR` cell the flood reaches is a hole in the envelope. Courtyard
cells are excluded by role, not by guesswork.

### 7.6 Floor coverage

Every `INTERIOR` cell has a slab beneath it. `VOID` cells are exempt by role.

### 7.7 Stair reachability

Walk the circulation graph from the ground storey. Any storey not reached is unreachable —
report it.

**Stair exit clearance (fail-closed).** Every stair top must open into a walkable bay:
- Each stair footprint cell on the storey above requires a `floor_hole` (VOID opened).
- A solid 1×1 floor pad on those cells is a critical defect (ceiling plug).
- Head clearance above each hole must not be filled by a wall, roof, or solid floor.
Spanning upper decks may cover the bay in AABB terms only when `floor_hole` rims exist;
the mesh builder punches those openings. A stair that dead-ends into a ceiling or wall
**must not** validate.

### 7.8 Run fit

For each wall run, `length % MODULE` must be `< TOL` or `> MODULE − TOL`. Otherwise report
the leftover **and the scale factor that would close it**, so §4.4 can stretch a piece rather
than leaving a gap.

### 7.9 Aperture sanity

Doors reach the floor; windows do not. Sill heights fall in a per-style band. A door in an
exterior wall opens to a walkable cell on both sides.

### Acceptance gate

```python
report.ok == True  and  report.critical == []
```

Critical = dangling ends, floaters, enclosure leaks, unreachable storeys. **Export refuses to
run on a failing assembly.**

### 7.10 Known limitation — state it in the UI

Validation proves a building is *physically coherent*. It cannot prove it is *attractive*.
Proportion faults — a roof pitch that reads as a barn, windows too small for the wall, a
cone floating above its drum — pass every check above. Mitigation: the golden-image tests in
§10.2 plus a human review gate before a building is promoted to the library.

---

## 8. Stage 7 — Export

### 8.1 Blender

Native `.blend` with linked duplicates, collections per storey/system, and a `PAE_meta`
custom property carrying the spec hash and validation report.

### 8.2 Unreal manifest

```json
{
  "schema": "pae.manifest/1",
  "module_cm": 400.0, "storey_cm": 350.0,
  "origin_convention": "min_corner",
  "assets": [{"id": "wall_gothic_window", "fbx": "…", "lod": {...}}],
  "placements": [{"asset_id": "…", "loc_cm": [x, y, z], "yaw": 90}],
  "collision": [...],
  "validation": {"ok": true, "checks": {...}}
}
```

UE reads this and spawns instanced pieces. **UE contains zero placement logic**, so
placement bugs cannot exist on that side.

### 8.3 Terrain binding

Buildings bind to terrain by sampling a **heightmap**, never by ray-casting the landscape.
Landscape collision lags edits and is wrong in streamed-out regions; a prior system placed
7,000 actors from traces and buried a whole city because traces read 14–44 m where the
heightmap said a flat 32 m.

Provide `bind_to_terrain(assembly, heightmap, mode)` with modes `flatten_pad`,
`step_terraces`, `stilts`.

---

## 9. ComfyUI / image-to-3D integration

Generated assets are **decorative or bespoke**, never structural. Structural pieces must hit
exact module dimensions, which image-to-3D cannot reliably do. Hybrid policy:

| Class | Source | Why |
|---|---|---|
| Walls, floors, stairs, arches, tower arcs | **Parametric code** | must snap exactly |
| Statues, banners, braziers, furniture, gargoyles, fountains | **ComfyUI / Hunyuan3D** | precision irrelevant |
| Bespoke hero pieces (throne, great door) | ComfyUI + manual socket annotation | one-off |

### 9.1 Practical hints

- **Generate on a plain background.** Backgrounds become geometry.
- **One object per prompt.** Multi-object images produce welded blobs.
- **Ask for orthographic, eye-level, front-facing.** Perspective bakes distortion into the mesh.
- **State scale in the prompt** ("a 2 m tall iron brazier") and still measure on import.
- **Paint pass is a colour guide, not a shipping texture.** Hunyuan's paint carries baked
  lighting and wrong palettes — one prior lamp post came back with mean RGB 0.47/0.10/0.06,
  i.e. bright red, when it should have been wrought iron. Ship UE-authored materials and use
  the generated texture only as reference or as a desaturated base.
- **Reference boards beat single images** for kits: one image showing 20 pieces on a grid
  gives consistent style across the set.
- **Cutaway/section references are worth more than hero shots** for structure — they reveal
  storey heights, wall depth and how stairs connect.

### 9.2 Import pipeline for generated assets

```
ComfyUI ──▶ GLB ──▶ normalise (scale, origin, orientation, decimate)
        ──▶ measure ──▶ socket auto-propose ──▶ human confirm ──▶ assets.db
```

Normalisation must: apply transforms, recentre origin to min corner, orient +Y forward,
decimate to an LOD budget, and generate a UV set if absent.

### 9.3 UV and material policy

Kit pieces get **triplanar world-space materials** by default — three samples blended by the
world normal. A single XY projection smears every vertical face into long vertical streaks
(this was a real, ugly bug). Triplanar also means no per-mesh UV authoring, which is what
makes an asset-agnostic kit viable.

---

## 10. Blender add-on interface

### 10.1 Panels

- **Spec** — style dropdown, storeys, bays X/Y, footprint kind, seed. Sliders write the same
  `BuildingSpec` an LLM would.
- **Assets** — browse DB by tag, import, socket annotation editor, fit report.
- **Generate** — run pipeline; per-stage progress; **stage-by-stage stepping**.
- **Validate** — the report, grouped by severity. **Clicking a defect selects the offending
  object and frames it in the viewport.** This is the highest-value feature in the add-on;
  a defect with a coordinate you can jump to gets fixed, a defect in a log does not.
- **Export** — Blender / FBX / manifest, with the validation gate visible.

### 10.2 Determinism and tests

- Same `(spec, seed, asset_db_version)` ⇒ **byte-identical** output. Hash the assembly and
  assert it in CI.
- **Golden images:** render fixed cameras per demo building; diff against approved renders;
  flag > 2 % pixel change for human review. This is the only automated guard against
  proportion regressions (§7.10).
- **Property tests:** for random specs within sane bounds, the validator must pass. Any spec
  that produces a failing assembly is a bug in the solver, not in the spec.

---

## 11. Milestones

**M1 — Box house (proves the spine).**
One storey, 4 × 3 bays, one door, two windows, flat roof, ground slab. Full pipeline runs;
validator passes; exports to Blender + manifest. *Deliberately trivial so the pipeline, not
the architecture, is what is being tested.*

**M2 — Two storeys + stairs.** Straight stair, floor hole, reachability check passes.

**M3 — Roofs and towers.** Pitched roof with gable infill (a prior build left an 8 m open
triangle at each gable because the walls stopped at the eaves and nothing checked it);
round tower with true cylindrical arcs, crown and cap.

**M4 — Courtyard / L / U plans.** Multi-wing, inhabited wall ranges with an inner face.

**M5 — Dynamic assets.** ComfyUI import → socket annotation → used by the generator with no
code change.

**M6 — Unreal round trip.** Manifest → instanced actors → terrain-bound → walkable in PIE.

**M7 — School / academy.** Programmed massing (`school_academy_spec`) with fail-closed
footprint / classroom program contract (`school_program`), 2×2 switchback stairwells with
exit clearance, double-loaded corridor classrooms, style-driven facade walls. School export
and gallery use **validate → trim → re-validate** (parity with campus path). Auto
`stair_kind` is straight | switchback | wide; **spiral is rejected** (showcase kit only).
Gallery `PAE_School` + school manifest dry-run. UE PIE remains a follow-on to M6.

---

## 12. Repository layout

```
pae/
  contract.py          # MODULE_CM, STOREY_CM, offset rules — single source of truth
  spec.py              # BuildingSpec + loader/validator
  solver.py            # spec -> massing
  plan.py              # massing -> floor plan
  assemble.py          # plan -> placements
  validate.py          # ⚠ build first
  decorate.py
  export/
    blender.py  fbx.py  manifest.py
  assets/
    db.py  import.py  sockets.py  fit.py
  styles/*.json
  addon/               # Blender UI
  tests/
    golden/  property/  unit/
```

---

## 13. Rules for contributing agents

1. **Never hard-code a dimension.** Import from `contract.py`.
2. **Never place geometry outside `assemble.py`.**
3. **Never trust a declared asset size** — measure the mesh.
4. **Every stage returns `(artifact, report)`.** No silent success.
5. **A check that cannot fail is not a check.** Write the failing case first and watch it
   fail before you fix it. *(The prior system's grid check passed while walls had 92 m gaps
   because it verified origins, not geometry.)*
6. **Booleans in Blender:** cut the core mesh *before* joining decorative bands. Cutting a
   joined mesh gives the EXACT solver coplanar faces and silently collapses the result.
   `modifier_apply` also requires the target to be both **active and selected** — otherwise
   it raises and the piece is never written. **Blender 5.x solver enums are
   `FLOAT` / `EXACT` / `MANIFOLD`** — never write `FAST` (renamed to `FLOAT` in 5.0). Prefer
   `scene.collection` when linking objects; guard `select_set` against `None`.
7. **Blender/UE Python caches modules.** Call `importlib.reload` / drop `sys.modules["pae*"]`
   in any script an agent will re-run (`pae.blender_build.reload_pae`), or edits appear to
   have no effect. *(This cost a full debugging cycle: a rotation fix produced byte-identical
   output because the old module was still loaded.)*
8. **Never run an unbounded loop on the UE game thread.** Batch heavy work and let the editor
   tick between chunks. Two full editor lockups (20 GB RSS, force-kill) came from iterating
   ~9,000 actors synchronously.
9. **Review at eye level, not just from above.** The void under the castle was invisible from
   40 m up and obvious from 1.7 m.
```

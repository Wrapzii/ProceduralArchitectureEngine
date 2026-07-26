# PAE Master Plan — from here to "generate me a city"

**Status:** the plan of record. Written 2026-07-25 after a session of measuring what
actually works.

**This document absorbs and supersedes** the scattered forward-looking material in
`CASTLE_SCHOOL_ROADMAP.md` (Phases 10, 11), `DESIGN_TOWER_DRUM.md` and
`DESIGN_COURTYARD_ARCADE.md`. Those stay as detail specs for their own lanes; this is
the spine they hang off. Nothing new should be added as a fresh markdown file — extend
this, the roadmap, the ledger or the handbook.

---

## 0. First, the honest question: why not just hand-place it?

The challenge was put directly: *"if I just asked you to place that stuff yourself, you'd
probably do that same thing, maybe better, without me having to do anything."*

**For one building, that is true.** Twenty or thirty pieces, I can place by hand and get
a good result faster than specifying it.

**At the scale actually wanted, it is not close.** This session is the evidence, and it
is not flattering to me: I wrote the code, and I still put a spiral stair *through* a
tower wall, mounted every buttress in the project backwards by 180°, stacked two flights
of stairs in the same footprint, and shipped a roof at three different heights on one
building. Every one of those was found by *measuring*, not by looking. Hand-placing 2,000
pieces across 100 buildings, I would make those mistakes constantly and silently.

So the value proposition is precise, and it is **not** "the engine designs better than a
person." It is:

1. **Invariants held at scale.** A stair always lands where a hole is punched. A door
   always opens onto something. A floor is always supported. Across hundreds of
   buildings, without anyone checking.
2. **Interiors that work.** Walkable, enterable, with real circulation. Kitbashing gives
   you façades; this gives you buildings you can go inside.
3. **Determinism.** `(spec, seed)` → the identical building. Change the seed, get a
   different but equally legal one. That is what makes a *town* rather than 40 copies.
4. **Iteration speed at the end.** "Same street, 30% steeper roofs, all gothic" is a
   parameter change, not a week of remodelling.

**The honest counter-case:** if the goal were five hero buildings, this project would be
the wrong tool and hand-modelling would win. The engine pays off at *a city*. That is the
stated goal, so it pays off — but it has to actually reach the "big stuff works" bar
first, and it has not.

---

## 1. Where we actually are

Measured, not estimated.

### Works
- **Grid + placement contract.** Cell arithmetic, yaw offsets, boundary lines, floor
  datum. Hard-won (Ledger §A) and now solid.
- **Solve-from-minimal-spec.** Give it a shape, a height and a use; it derives stair
  cells, wall lines, interiors, corridors, entrance bays, doors and windows. A minimal
  `rect` spec produces 136 correct pieces.
- **Arbitrary footprints.** `FootprintSpec(kind="cells")` + `pae/sketch.py` — draw a
  text grid, get a building. A sketched U built 242 pieces and validated.
- **Validators.** Extensive and genuinely good — 40+ checks including the subtle ones
  (stair landing clearance, aperture reachability, structural islands, headroom).
- **Style packs.** Eight JSON packs in `pae/styles/*.json` (`townhouse`, `keep`,
  `gothic_academy`, `wizard_academy`, `rustic`, `medieval`, `manor`, `civic`).
  Same sketch + different pack → different roof/window read (**M-E** proof:
  `Saved/exports/me_style_interchange_report.json`, @MP-WS6b).
- **Structure + level stack (Stages A+B).** `StructureSpec` / YAML §3.1 — foundation
  mask, per-level sketches, cumulative datum (`@MP-WS1`).
- **Roof as height field (Stage C).** One ridge family per structure; D3-9 closed
  (`@MP-WS2`, `test_roof_height_field.py`, M-A proof `ma_roof_ridge_report.json`).
- **Circulation at scale (Stage D).** Per-level stair wells; D3-3 preserved; grand/
  imperial deferred (`@MP-WS3`; school 4×2 well → `@MP-WS3b`).
- **Tower drum outboard suppress (Stage E, partial).** T-D1/T-D3 green (`@MP-WS4`);
  entry trim path + `library_tower` still blocked.
- **UE delivery tooling (Stage L, filesystem).** Export → dry-run → spawn table → bind
  (`@MP-WS11`; in-editor spawn/collision/nav still M-I).
- **Blender add-on StructureSpec UI (§5).** Level-stack panels + `generate_from_structure`
  (`@MP-WS8`).
- **Blender add-on.** Real, installable, 5 panels, 9 operators, and `frame_defect`
  selects the offending object. Drivable end-to-end from outside Blender.
- **Determinism.** Seeded throughout.

### Does not work (honest, 2026-07-25)
| | evidence |
|---|---|
| One building reads as several — roof per volume, ridges at different heights | **FIXED** Stage C / @MP-WS2 — sketched U one ridge family `{1150}` |
| Towers: box wall through drum, no entry, helix short | **PARTIAL** — outboard wall suppress T-D1/T-D3 (@MP-WS4); D3-6 entry/helix/T-D2 still open |
| Stairs stack in the same footprint | **FIXED** D3-3 preserved — `_MONUMENTAL_PAD_KINDS` + fail-closed pads (@MP-WS3) |
| Auto stair allocation one-per-building | **FIXED** per-level wells (@MP-WS3); **school 4×2** library_tower reserve → @MP-WS3b |
| No per-level footprint | **FIXED** `StructureSpec` levels (@MP-WS1); void/balcony auto-railings still stub |
| No structure identity | **FIXED** declared `structure:` + party-wall checks (@STRUCTURE_IDENTITY); Stage F wiring → @MP-WS5 |
| Authoring surface is a rectangle and a seed | **PARTIAL** — StructureSpec level-stack UI (@MP-WS8); grid paint §3.2 deferred |
| Program region carving | **PARTIAL @MP-WS7** — hall/classroom/service/corridor (+ arcade) carve plan roles; sketch H/C/V/R/A; walkable courtyard arcade producer (`pae/arcade.py`). Stage H openings still open. |
| Fortress collateral reds | **OPEN** — `tower_hall_kiss` / `aperture_sanity` on some fortress paths (not ridge) |
| Valley merge on irregular roofs | **OPEN** — S-021 stub; band valleys only (S-019 greybox) |
| Style pack hints unconsumed | `wall_bands.*`, `materials.*` authored but not in assemble (`storey_height_cm` **consumed** @MP-WS-Z) |
| Two builders discarded validation reports | fixed `b31eb35` |

### The pattern behind most of it
Six recurring root causes are catalogued in `DEFECT_LEDGER.md` under *Patterns*. The two
that matter most for this plan:

- **Something decides locally what should be decided for the building as a whole**
  (roof per volume, stair per body, edging per producer).
- **An internal implementation detail leaking into the output** (how `rect_cover` slices
  a mask decided how the roof looks).

Both are symptoms of one missing concept, which is the centre of this plan.

---

## 2. The one idea: foundation first, then a stack of levels

The instinct in the brief was right — *"maybe we start from the bottom, and we do
foundation first."* That is the correct data model, and it dissolves most of the open
problems at once.

Today a building is **one footprint + a storey count**. That single fact is why:
- you cannot say "this wing has no second floor"
- you cannot say "level 2 is an open balcony ring around a void"
- the roof is derived per volume instead of per building
- masses that touch are separate buildings

Replace it with:

```
Structure                     ← the thing that is ONE building
├── Foundation                ← ground mask; the plot, the datum, the identity
├── Level 0   sketch + program + height
├── Level 1   sketch + program + height      (may cover LESS than level 0)
├── Level 2   sketch + program + height      (may be 3 units tall)
└── Roof                      ← DERIVED from the topmost built cell of each column
```

**A level is a sketch.** Same grid format as `pae/sketch.py`, one per level. Everything
asked for falls out of this without new machinery:

| what was asked for | how it is expressed |
|---|---|
| "this area doesn't have a second floor" | level 1's sketch simply omits those cells |
| "2nd floor is an open balcony ring, 1st is enclosed" | level 1 marks the middle `void` and the ring `balcony` |
| "a floor 3 blocks high with arches" | that level's `height_units: 3`, wall style `arcade` |
| "great hall on the right of the U, door to the back" | level 0 program marks that region `hall`, one cell `door` |
| "this many staircases" | mark that many `S`, or leave blank and let it solve |
| one roof, one building, one foundation | roof derived from the column stack, not per volume |

**The foundation is the identity.** Two masses on one foundation are one building —
which answers the three-guardhouses problem without adjacency guessing. It is declared,
because a terrace is adjacent *and* separate.

**Roof becomes derivable, not authored.** For each column of cells, find the topmost
built level; the roof is a surface over that height-field. One building gets one roof
plane, stepping where the building steps. This is the single highest-value change in the
plan and it is only possible once levels are a stack.

---

## 3. The authoring format

### 3.1 Text now
```yaml
name: gatehouse
style: medieval          # a pack in pae/styles/
seed: 7
unit_cm: 400             # optional; see §7

foundation: |            # optional — defaults to the union of all levels
  ##########
  ##########

levels:
  - height_units: 1
    sketch: |
      T########E
      ##########
      ####  ####
    program:
      hall: [[6,0],[9,3]]      # rectangle regions, or paint a letter in the sketch
  - height_units: 1
    sketch: |
      #########.
      #.......#
      ####  ####
      # '.' here = open to below → balcony ring, railed automatically
  - height_units: 3         # tall arcaded level over the hall
    sketch: |
      ......####
      ......####
    wall_style: arcade
```

Legend, extended from `pae/sketch.py`:

| char | meaning |
|---|---|
| `#` | built |
| `.` | open to below (void / balcony / courtyard, disambiguated by context) |
| `S` | stair here |
| `E` | entrance here |
| `T` | tower |
| `A` | arcade wall on this edge |
| ` ` | outside the building |

**Rule: marks are optional.** Anything not marked is solved. A sketch of nothing but `#`
is a legal building.

### 3.2 Drawing later
A Blender tool that lets you paint cells per level and **emits this same YAML**. One
input path, two front ends — nothing gets thrown away. Grid paint on a plane, level
selector, marker brush. This is the fix for "the UI doesn't work for me at all," but it
comes *after* the engine can build what the text describes, not before.

### 3.3 Why text is first
It is what an LLM authors natively (no UI round-trip), it diffs in git, it is testable
without Blender, and it is a stable target for the drawing tool to emit.

---

## 4. Engine work, in dependency order

Each stage lists what unblocks it. **Do not reorder** — the sequencing is the plan.

### Stage A — Structure and foundation — **DONE @MP-WS1**
- `Structure` = foundation mask + ordered levels + style + seed
- `structure:<id>` tag on every piece
- `freestanding` partitions on **structure** (change the key in the same commit — see
  Handbook §11d, this is a trap)
- Foundation slab emitted once per structure

**Done when:** two touching masses declared as one structure produce one connected
building with one stair core.

### Stage B — Level stack — **DONE @MP-WS1** *(gaps: void/balcony auto-railings; program carve stub)*
- `LevelSpec`: sketch, `height_units`, program, wall style
- Per-level footprints; upper level may be a subset
- Datum accumulates: level z = sum of heights below, **not** `level * STOREY_CM`
  (route every hardcoded `level * STOREY_CM` through one accessor first, in its own
  commit, with no behaviour change — there are ~26)
- `void` cells → no floor, railed edges, double-height space below

**Done when:** a U with no second floor over one leg, and a 3-unit-tall hall, both build.

### Stage C — Roof as a height field *(needs B)* — **DONE @MP-WS2**
- Roof derived from the topmost built level per column
- One roof surface per structure, stepping where the building steps
- Valleys, hips and gables derived from the field, not from volumes
- Ridge height from the structure, not from the decomposition (fixes D3-9)

**Done when:** the sketched U produces **one** roof, not three at three heights.
**Proof:** `test_roof_height_field.py` — sketched U pitched ridge family `{1150}` @ pitch 1.4; `critical=[]`.

### Stage D — Circulation that scales — **DONE @MP-WS3** *(grand/imperial deferred; school 4×2 → @MP-WS3b)*
- Auto stair allocation **per region per level**, not per building (fixes L/U)
- Flights offset in plan between levels; extend the pad mechanism to straight runs
  (needs a 2-bay-wide well allocated by the solver — fixes D3-3)
- Stair typology: straight, dog-leg, switchback, spiral, **grand/imperial** (a wide
  ceremonial flight splitting into two returns — does not exist)
- Landing edges left unrailed (already fixed, keep it)

**Done when:** an unmarked multi-region sketch solves, and no two flights share a
footprint.

### Stage E — Towers — **PARTIAL @MP-WS4** *(T-D1 outboard suppress + T-D3 exclusivity green; T-D2 entry trim, T-D6 parapet continuity, `library_tower` blocked by WS3b)*
Per `DESIGN_TOWER_DRUM.md`. Outboard drum suppresses the box wall; entry door; helix
climbs the full shaft; hatch to the top deck; no windows into the bore. **Read the trap
in that document before starting.**

### Stage F — Party walls and connections — **DONE @MP-WS5**
Where two masses of one structure meet, the boundary becomes an interior wall carrying an
opening or arch. **Ranges and drums are the same problem — one mechanism.**

### Stage G — Program and rooms *(needs B)* — **PARTIAL @MP-WS7** *(Stage H openings DONE @MP-WS-H)*
- Regions marked `hall`, `classroom`, `service`, `corridor` → plan CellRoles + partitions/doors
- Sketch letters `H`/`C`/`V`/`R`/`A` + StructureSpec program rectangles
- Courtyard arcade as walkable gallery room (`pae/arcade.py`) — not colonnade / not bare wall_arcade trim
- Great hall = a region with `height_units > 1` and no partitions *(height still via level stack)*
- **Gaps:** arcade vault; full handbook arcade_* checks + showcase `arcade_court`

### Stage H — Openings as a style choice — **DONE @MP-WS-H**
- Window shape per structure/level (lancet, mullioned, round, square, oculus)
- Door types via style pack + entrance roles; grand entrance doorcase partial
- **Gaps:** oculus gable-only auto-placement; door_double grand only when pack tags it

### Stage I — Style packs — **DONE @MP-WS6**; **M-E interchange @MP-WS6b**; **storey height @MP-WS-Z**
Already JSON. Eight packs ship. **Interchangeable by design** — same sketch + different pack =
same building in a different architecture. Proof: `Saved/exports/me_style_interchange_report.json`
(8/8 `critical=[]`). **`geometry.storey_height_cm`** consumed in assemble via
``storey_datum_z_cm(..., storey_cm=)`` (@MP-WS-Z). **Gaps:** `wall_bands` / `materials` hints
authored but not yet consumed by assemble.

### Stage J — Site and city *(needs A–D)* — **SKELETON @MP-WS-J** *(M-G city deferred)*
- **Landed (@MP-WS-J):** `SiteSpec` / `PlacedStructureSpec` in `pae/site_spec.py` —
  several structures with cell offsets, site style/seed, optional road/plot
  *placeholders*, dict+YAML round-trip, `build_from_site_spec` merges ≤3 via
  pipeline + `place_buildings` with distinct `structure:<id>` tags.
- Street/plot subdivision from a road network sketch — **not started**
- Per-plot seeded variation so a row reads as a street, not a repeat — **not started**
- **M-G "generate me a city" deferred.** Skeleton only; a city of broken buildings
  is worse than one good building.

### Stage K — Detail layer *(last, explicitly — **DEFERRED by design**)*
- Seeded surface variation: wall roughness, stone courses, timber grain
- Wear/weathering driven by the same seed
- Props and decor: lamps, signage, planters, market stalls
- Interior fit-out beyond greybox

**Deliberately last.** Detail on broken massing is polish on a crooked house — and it is
also the part that is genuinely easier to add once everything else is stable.

### Stage L — Unreal delivery — **PARTIAL @MP-WS11** *(filesystem chain green; in-editor spawn/collision/nav/LOD = M-I)*
- Manifest already exists (`UE_MANIFEST_CONSUMER.md`)
- Collision, nav-mesh sanity, LODs
- Instanced static meshes per piece type — the reason a city is even feasible
- Light anchors already emitted; wire them to UE placement

---

## 5. The UI, concretely

**Status (@MP-WS8):** StructureSpec level-stack panels, YAML load/export, and
`generate_from_structure` operator ship in the add-on. Grid paint (§3.2) and program-region
UI remain deferred.

The current panel is a rectangle and a seed, which is why it feels useless. Target:

**Panel 1 — Structure.** Name, style pack, seed, unit size. Buttons: load sketch, save
sketch, generate, validate.

**Panel 2 — Levels.** A list. Add/remove level, set `height_units`, pick wall style.
Selecting a level shows its grid.

**Panel 3 — Draw.** Grid paint on a plane at the selected level's height. Brushes:
built, open, stair, entrance, tower, arcade. Shows the level below ghosted so you can
line things up. **Emits YAML** — it is a front end for §3.1, not a parallel path.

**Panel 4 — Program.** Paint regions: hall, classroom, service, corridor.

**Panel 5 — Validate.** Already exists and already good. Keep `frame_defect`.

**Panel 6 — Export.** Already exists.

**Working rule, already in `CHANGE_PROTOCOL.md`:** a change is not verified until it has
been exercised through an operator. Two builders shipped hardcoded empty reports for
weeks precisely because nobody ran the path the user runs.

---

## 6. Milestones — each is a demo, not a checkbox

| M | Deliverable | Acceptance |
|---|---|---|
| **M-A** | One building, one roof | **DONE** — sketched U → ridge family `{1150}`; `ma_roof_ridge_report.json` |
| **M-B** | Per-level footprints | U with no 2nd floor over one leg; balcony ring on level 1; both walkable |
| **M-C** | Circulation at scale | Unmarked sketches of any shape solve; no two flights share a footprint |
| **M-D** | The tiny house, instantly | `house(2 storeys, side stair, windows)` in one call; **100 placed**, each valid, seeded-varied |
| **M-E** | Styles interchange | **DONE @MP-WS6b** — M2 4×3 × 8 packs, 8/8 `critical=[]`, packs differ; `me_style_interchange_report.json`; storey height @MP-WS-Z |
| **M-F** | The set piece | U-shaped hall: great hall one wing, 3-unit arcaded level above, tower, grand stair, balcony ring. 0 critical |
| **M-G** | A town | **DEFERRED** — Stage J skeleton only; city generation blocked until M-F stable |
| **M-H** | Detail pass | Seeded surface variation + props on M-G |
| **M-I** | In Unreal | **DEFERRED** — filesystem export chain @MP-WS11; in-editor spawn/collision/nav = open |

**M-D is the one to aim at first after M-A/B/C** — it is the daily-value milestone, the
one that makes the engine worth using rather than worth finishing.

---

## 7. Decisions to make now

**The 4 m module.** `MODULE_CM = 400.0` is a single named constant, always referenced by
name — so a **global** rescale is a one-line change plus a test pass. Per-building unit
sizes are **not** feasible: pieces are sized as fractions of the module and two modules
in one scene would not tile. Recommendation: expose `unit_cm` per *project*, default 400,
and treat 4 m as a bay (a room is 2–3 bays), not as a room. If a finer grain is wanted,
300 cm is the realistic alternative — below that, piece counts explode.

**Sub-cell placement.** Doors and windows already position within a bay, so the grid
constrains *massing*, not detail. This is the right compromise and should stay.

**What gets demoted.** `showcase.py`, `street_scene.py`, `open_stair_showcase.py` and the
hardcoded fortress/castle scene builders move to `pae/tests/fixtures/` — they were tests
of the engine, and keeping them as product is what made this look like a preset library.

---

## 8. Sequencing summary

```
A structure/foundation ─┬─► B level stack ─┬─► C roof height field   ◄── DONE (@MP-WS1–2, M-A)
                        │                  ├─► D circulation           ◄── DONE (@MP-WS3; imperial deferred)
                        │                  └─► G program ──► H openings
                        ├─► E towers        ◄── PARTIAL (@MP-WS4)
                        └─► F party walls   ◄── DONE (@MP-WS5)
I styles (parallel)       ◄── DONE + M-E + storey height (@MP-WS6/6b/Z)
                     A–D ──► J site/city ──► K detail (deferred) ──► L Unreal
                              ▲ SKELETON (@MP-WS-J); M-G city deferred
                              L filesystem (@MP-WS11); M-I in-editor deferred
```

**If only one thing is done next:** finish **Stage F** party-wall wiring (@MP-WS5) or
**school 4×2** stair reserve (@MP-WS3b) — massing/circulation blockers before city scale.
Stage C (one roof) is **shipped**; do not re-litigate ridge family work.

---

## 9. What this plan refuses to do

- **No auto-merging of adjacent buildings.** Declared only. Adjacency cannot distinguish
  a terrace from a joined range.
- **No weakening of checks to go green.** Ledger §D3 exists because checks caught real
  defects and the output was discarded. If a check starts failing after a change, the
  geometry is the thing to fix.
- **No detail before massing.** Stage K is last on purpose.
- **No second authoring path.** The drawing tool emits the same YAML the text path uses.

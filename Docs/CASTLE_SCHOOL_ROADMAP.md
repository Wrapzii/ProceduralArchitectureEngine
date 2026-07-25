# Roadmap — everything still needed for the castle / school

Status of the engine as of this document: PAE can assemble multi-storey ranges, trim them
with railings / buttresses / roofline / colonnades, arrange several into a compound around
a courtyard with a balcony gallery, lay a site (paving, walks, kerbs, lawn, fence, gates),
validate the result against 14 checks, and export a UE manifest.

What it **cannot** do is everything below. Ordered by what blocks what.

A note on how this list is written: each item says what is missing, **why it matters**, and
**how it is verified**. An item without a verification is not done, it is only claimed —
every defect this project has shipped was caught by a human looking at a render, and the
fix each time was a check, not a patch.

---

> **Companion document:** `Docs/STYLE_AND_DETAIL_ROADMAP.md` carries 135 numbered
> style-and-detail objectives (S-001…S-135) for the wizarding-school / medieval read —
> roof profiles, spires, grand entrances, attachable doors, lighting and prop anchors,
> seeded surface variation, interiors, grounds. This document is *structure*; that one is
> *style*. Work the two together: a structural feature with no style hooks gets hard-coded
> twice.

## Phase 0 — Open defects (blocking, known now)

| # | Defect | Evidence | Notes |
|---|---|---|---|
| ~~0.1~~ | ~~Random-spec towers fully detached~~ | **DONE (M7)** — solver perimeter attach snap + assemble drum offset `2r→r` so arcs kiss the hall. Random validate green for freestanding towers. | Ledger C-5 |
| ~~0.2~~ | ~~Stair-top clearance cell-based~~ | **DONE (M7)** — `_check_stair_exit_clearance` uses `covered_cells` for stair footprint, holes, and solid plugs (Rule 5.1). | Ledger D-5 |
| ~~0.3~~ | ~~`roof_penetration` check is a warning, not critical~~ | **DONE (M7)** — school academy triaged: 0 hits (flat roofs sit ``FLOOR_T`` above wall heads; no blades). Eave-tuck and gable-ridge designed pairs exempted; check promoted to **critical**. Tests: ``test_roof_penetration_triage.py``. | |
| ~~0.5~~ | ~~`aperture_reachability`, `storey_egress` GROUND/VOLUME are WARNINGS~~ | **DONE** — checks are **critical**. Fixtures/generators fixed: assemble south-face upper glazing (no doorway-to-nothing stack; VOLUME on empty `windows_per_bay`), variation keeps gallery doors via balcony landing set, compound only punches balcony doors onto deck-adjacent bays, property factory glazes multi-storey. Tests: ``test_aperture_reachability_critical.py``. | |
| ~~0.6~~ | ~~Circular towers have no windows and a poor roof junction~~ | **DONE** — helical / perimeter drum windows (`tower_arc_quarter_window` + wall overlays); `tower_junction` ring under crown/cap. Tests: `test_tower_windows.py`. | Phase 4.7 |
| ~~0.4~~ | ~~Gallery roof partial edge attachment~~ | **DONE (M7)** — one spanning gallery roof per range with court-face eaves (`EAVE_OVERHANG_CM`). | |
| 0.7 | Stacked flights share a footprint and face the same way | **DONE (@D3_WIRING_FIX)** — `_MONUMENTAL_PAD_KINDS` + solver expansion + assemble fail-closed `return` on undersized well; `fortress_gatehouse_spec` 8-cell straight well. Tests: `test_d3_wiring.py` (8), `test_stair_flight_offset.py` | Ledger D3-3 → Phase 10.4 |
| ~~0.8~~ | ~~Roof edge carries parapet **and** crenellation, overlapping~~ | **DONE (@DOC_D3_PHASE10_AUDIT)** — `roof_edging_exclusive` critical + producer deferral (`pae/roof_edging.py`). Tests: `test_roof_edging_exclusive.py::test_double_edging_on_same_edge_fires_roof_edging_exclusive`, `::test_single_edging_style_passes`, `::test_castle_curtain_compound_has_no_double_edging` | Ledger D3-4 → Phase 10.5 |
| ~~0.9~~ | ~~Exterior approach flights too tall to enter the gate~~ | **DONE (@DOC_D3_PHASE10_AUDIT)** — `trim()` calls `repair_approach_stairs` when `exterior_steps=True`. Tests: `test_approach_stair_mate.py::test_trim_exterior_steps_strips_poison_grid`, `::test_trim_exterior_steps_mated_height`, `::test_repair_strips_grid_and_replans` | Ledger D3-5 |
| 0.10 | Tower drum: wall through it, windows into it, no entry, helix short | One cell claimed by two enclosures | `Docs/DESIGN_TOWER_DRUM.md`, lane `@DRUM_ENCLOSURE`. Foundations: `pae/drum.py` + `test_drum.py` green (street_scene widened 5×4/5×5 so `build()` assembles). **Open:** T-D1..T-D6 in design doc. Ledger D3-6 |
| ~~0.11~~ | ~~Buttresses face the wrong way, oversized~~ | **DONE** — `5de4b0d`. `buttress()` mates with its BACK (+X is the wall side); `outward_offset_cm` is for pieces whose +X points away. Use `trim._pier_pose` | Ledger D3-7 |

> **Not a defect, recorded because it was asked:** stairs are **auto-allocated**. `solver.py:827`
> — `storeys > 1` with no `stair_cells` calls `_default_stair_cells`. A building with no stairs
> is single-storey in its spec, or the solver raised `stair_serves_upper` (`solver.py:838`),
> which is critical and appears in the report. Agents do not hand-place stairs. Ledger D3-8.

---

## Phase 1 — Entrances and thresholds

The single largest missing concept. Right now a door is a wall variant with a hole in it;
it has no *role*. You cannot say "this is the grand entrance" or "this is the service door".

**1.1 Door roles.** An `EntranceSpec` naming each opening's role: `grand`, `main`, `side`,
`service`, `postern`, `gate`, `balcony`, `internal`. Role drives piece choice (a grand
entrance is a `gate_arch`, a service door is `door_plain`), bay width, and what must be on
the other side of it.
*Verified by:* every declared role resolves to a placed piece; no role left unplaced.

**1.2 Entrance placement policy.** Which façade, which bay, how many. "Big open entrance on
the south front, two side entrances east and west, service door at the back."
*Verified by:* requested count per façade equals placed count; no two entrances share a bay.

**1.3 Entrance ensembles.** A grand entrance is not a door — it is a composition: arched
opening, flanking columns or pilasters, a porch or portico, steps up from the walk, and
**twin staircases rising left and right inside**, with railings. This is the thing you
described and it needs to be a single declarative unit that expands into ~30 pieces.
*Verified by:* the ensemble's stairs are reachable from the entrance cell; both flights
land on the same upper deck; railings guard both.
**DONE greybox (a4acc24 / RM_M9_ENSEMBLE):** `EntranceSpec.ensemble` +
`pae/entrance_ensemble.py` expands grand entrances to greybox arch + `steps_external` +
flanking `pilaster` (and twin `stair_half` when storeys≥2); `entrance_ensemble_existence`
check. Tests: `test_entrance_ensemble.py`. Gaps: full ~30-piece portico/railings, stair
reachability to upper deck. Does not weaken 1.5 `no_bare_aperture`.

**1.4 Vertical stacking of openings.** A doorway onto a first-floor balcony directly above
the ground entrance. Openings need to know about each other vertically so they align.
*Verified by:* a new `aperture_alignment` check — stacked openings share a centre line
within tolerance.
**DONE (eabf1f8 / RM_ALIGN_1_4):** `validate._check_aperture_alignment` (warning);
`APERTURE_ALIGNMENT_TOL_CM = TOL_CM`. Tests: `test_aperture_alignment.py`. Gaps:
generators do not yet deliberately stack openings — check catches misalignment only.

**1.5 No opening without a door.** Already enforced for balconies. Must become general:
any breach in the envelope carries a door or gate piece, never a bare hole.
*Verified by:* extend `aperture_sanity` to fail on an opening with no door/gate asset.
**DONE (RM_ENTRANCE_ADV):** `no_bare_aperture` check — door apertures, `balcony_door`, and
`entrance_role_*` placements must resolve to a door/gate asset (`pae/existence.py` +
`validate._check_no_bare_aperture_holes`). Tests in `test_entrances.py`.

---

## Phase 2 — Rooms, program and interiors

The building is currently a shell with floors. A school is a *program*.

**2.1 Room graph.** Declare rooms by type and count — classrooms, great hall, refectory,
library, chapel, dormitories, kitchens, stores, undercroft — with adjacency rules ("kitchen
adjacent to refectory", "dormitories not adjacent to the forge").
*Verified by:* every declared room exists at its declared area; adjacency constraints hold.

**2.2 Interior partitions.** Internal walls dividing the shell into those rooms, with door
openings between them. Partitions are thinner than exterior walls and carry no roof.
*Verified by:* enclosure per room; every room has ≥1 door; no room is sealed.

**2.3 Corridors and circulation spine.** Rooms hang off a corridor; the corridor reaches
every stair. Without this a range is one huge undivided hall.
*Verified by:* graph reachability — every room to every stair to the exterior.
**DONE (1aafb21 / RM_ROOMS_CORRIDOR):** `plan._extend_corridor_spine_to_stairs` grows
CORRIDOR through INTERIOR to STAIR/VOID wells; `corridor_stair_connectivity` (critical).
Tests: `test_corridor_spine.py`. Gaps: room→exterior egress graph still via existing
`storey_egress` (not per-room exterior path).

**2.4 Double-height volumes.** A great hall or chapel that omits the intermediate floor.
Requires the floor stage to accept per-cell suppression and the walls to run two storeys.
*Verified by:* no floor slab in the volume; walls continuous; balcony/gallery edges railed.

**2.5 Interior fit-out.** Fireplaces, benches, tables, altars, bookcases, beds. This is the
Comfy decorative pipeline's real job — it exists but has only a demo crate.
*Verified by:* props inside rooms only, on floors, not intersecting circulation.

---

## Phase 3 — Vertical circulation (beyond the straight flight)

**3.1 Spiral stairs placed.** **DONE (RM_SPIRAL_POLISH):** `stair_kind=spiral` on tower
drum cells; solver single-cell tower gate; plan STAIR/VOID on drum; assemble stacks 4×
`stair_spiral_quarter` per storey climb; exit holes punched via `covered_cells` (Rule 5.1).
Tests: `test_spiral_stairs.py`. Gaps: headroom / walkable-path checks (Phase 3 verify block).
**3.2 Switchback and grand flights.** Partially present in the swarm's stair kit; needs
solver integration and landings.
**3.3 Stair enclosures.** Stairwells as rooms with walls and doors, not open holes.
**3.4 Ramps and level changes.** Undercroft to courtyard, terraces.
*Verified by:* headroom check (no piece within 2.1 m above any tread), landing continuity,
and a walkable-path check from ground to every storey.

---

## Phase 4 — Castle-specific structures

**Greybox landed (4.1–4.2):** `castle_gatehouse_spec()`, `castle_curtain_wall_spec()`,
`castle_bailey_spec()`, and `build_castle_curtain_compound()` in `pae/spec.py` /
`pae/compound.py` compose twin-tower gatehouses (`wall_gate_arch` via entrance role
`gate`) with west/east curtain runs (`wall_plain`, `parapet_solid`, `battlement` trim).
Validated with `critical=[]`; portcullis, murder holes, and barbican remain future work.

**4.1 Curtain walls** — **DONE greybox (RM_CASTLE_POLISH):** west/east `wall_plain` curtain
runs with `parapet_solid` + `battlement` trim via `castle_curtain_wall_spec()` /
`build_castle_curtain_compound()`; `critical=[]`. Gaps: full wall-walk circuit, moat-scale
enclosure.
**4.2 Gatehouse** — **DONE greybox (RM_CASTLE_POLISH):** twin-tower gatehouse with
`wall_gate_arch` (`entrance_role` `gate`) in `castle_gatehouse_spec()`. Gaps: portcullis
slot, murder holes, barbican.
**4.3 Corner and flanking towers** integrated into curtain walls rather than bolted onto a
range. (Perimeter attach + drum offset fixed in M7 / defect 0.1; curtain integration still
open.)
**4.4 Moat, bridge, drawbridge.** Needs terrain interaction.
**4.5 Keep** — a tall multi-storey block with its own internal program.
**4.7 Habitable towers and spires.** **DONE (@TOWER_KEEP_HABITABLE) for fortress/castle
keep drums:** `TowerSpec.stair_kind=spiral` places helix + newel inside each multi-storey
drum (hall may keep switchback); outward `tower_arc_quarter_window` / rim windows; hall↔drum
`tower_entry` at ground + landings; inner plain walls / fitout / parapets skipped in the
drum; post-merge strip of helix quarters blocked by neighbour roofs. Tests:
`test_tower_keep_habitable.py`. Crown rampart + newel/drum shell already landed
(@VAL_TOWER_RAMPART / @VAL_SPIRAL_SHELL). Still open: spires large enough to contain rooms;
true circular railing continuity; hatch onto crown pad (T-D5 — pad is unopenable by design).
*Verified by:* fortress keep assemble spiral+windows+entry; no plain-wall junk on drum
anchors; `tower_entry` aperture_reachability; shell checks.

**4.6 Baileys** — inner and outer wards, i.e. nested compounds. `site.py` merges buildings;
it does not yet nest enclosures.
*Verified by:* wall-walk continuity (you can walk the whole circuit), tower-to-curtain
attachment, and enclosure of each ward.

---

## Phase 5 — Roofs done properly

**5.1 Hip, mansard, shed, conical, lead-flat** — only flat and gabled exist.
**5.2 Roof over irregular plans.** L, U and courtyard plans need valleys and hips where
wings meet; currently each wing gets its own independent roof and they collide or gap.
**5.3 Dormers and chimneys placed by rule** rather than by index rhythm — dormers over
rooms that need light, chimneys over rooms that have a hearth.
**5.4 Gutters, downpipes, ridge lines, verges.**
*Verified by:* watertight-envelope check — project the roof down and assert every enclosed
cell is covered; no roof piece freestanding (exists); no wall through roof (exists, warning).

---

## Phase 6 — Verification (the part that actually protects you)

Existing: end connectivity, vertical support, collinear gaps, interpenetration, enclosure,
floor coverage, stair reachability, stair exit clearance, classroom/corridor connectivity,
run fit, aperture sanity, **freestanding groups**, **canopy attachment**, roof penetration.

Still needed:

| Check | Catches |
|---|---|
| **Walkability / navmesh** | Rooms you cannot reach; stairs that lead nowhere; a courtyard with no way in |
| **Headroom** | Stairs under low ceilings, doors under beams |
| **Egress** | Every room within N metres of an exit; a building with one door |
| **Watertight envelope** | Holes in the roof plane over enclosed space |
| ~~**Aperture reachability**~~ | ~~A door opening onto a 4 m drop~~ — **DONE (0.5):** check is **critical**; milestone fixtures + variation/generators green (`test_aperture_reachability_critical.py`) |
| ~~**Stacked-opening alignment**~~ | ~~Windows that wander bay to bay between storeys~~ — **DONE (1.4 / eabf1f8):** `aperture_alignment` check (`test_aperture_alignment.py`) |
| **Proportion sanity** | Roof pitch, window-to-wall ratio, storey height vs span — the *aesthetic* faults the structural checks cannot see |
| **Terrain conformance** | Buildings buried in or floating over the landscape |
| **Instance budget** | A site that will not stream in UE |

Two structural improvements to validation itself:

- **Every check must use `covered_cells`, never `p.cell`.** Spanning slabs have caused
  five separate bugs this session. Defect 0.2 is the last known offender.
- **Golden-image diffs per milestone.** Structural checks pass buildings that look wrong.
  A render diff is the only automated thing that catches proportion faults.

---

## Phase 7 — Materials, LODs and UE delivery

**7.1 Real materials** — triplanar stone/plaster/timber/lead, not workbench tints.
**7.2 UV unwrapping and lightmap UVs.**
**7.3 LOD chains and HLOD** for a site of this size.
**7.4 Collision primitives** per kind — walls box, stairs ramp, railings capsule.
**7.5 Interactive actors** — doors, gates and portcullises exported as actors, not static
meshes, with their role from Phase 1 carried through.
**7.6 Terrain binding** — sample the heightmap, never ray-cast. (Stub exists.)
**7.7 World Partition streaming** — cell assignment and HLOD layers.

---

## Phase 8 — Authoring experience

**8.1 Add-on panels for every spec** introduced above — entrances, rooms, balconies,
roofs — with sliders the AI and the user manipulate identically.
**8.2 Presets** — "castle", "abbey school", "academy", "gatehouse".
**8.3 Live preview** at massing level before committing to geometry.
**8.4 Defect click-to-frame** (exists) extended to the new checks.
**8.5 Seed control and variant browsing.**

---

## Suggested milestone order

| Milestone | Contents | Why here |
|---|---|---|
| **M7** | Phase 0 defects + Phase 6 covered-cells sweep | Never build on a red suite |
| **M8** | Entrances: roles, placement, stacked openings, no-hole rule | Unblocks everything about how a building is entered |
| **M9** | Grand entrance ensemble with twin staircases | The showcase piece; proves ensembles work |
| **M10** | Rooms, partitions, corridors, double-height | Turns a shell into a school |
| **M11** | Roofs: hip/conical/valleys over L and U plans | Fixes the biggest visual weakness |
| **M12** | Castle structures: curtain walls, gatehouse, towers, wards | The castle half of the brief |
| **M13** | Walkability, egress, headroom, watertight checks | Verification catches up with capability |
| **M14** | Materials, LODs, collision, interactive doors, UE streaming | Delivery |

---

## The rule that matters most

Every item above is a *capability* plus a *check*. Ship them together. The engine's history
is unambiguous on this: capability without verification produces a building that passes
every test and is visibly wrong, and the cost is paid later by a person looking at a render
and saying "the walls are sticking through the roof."

---

## Phase 9 — Sloped ground, stepped buildings, upper-storey entrances

**Reference:** a medieval hill town — buildings stepping up a slope at different ground
levels, jettied upper floors overhanging the street, external stone stairs climbing to
first-floor doors, ground-floor undercrofts opening onto the lower path.

**Status: started (@RM_PHASE9).** Ground model (T-001..T-006) and jetties remain
unscheduled. First verified slice is validation-first upper-storey entrances (below).

It does change an assumption baked into the engine — everything today sits at z = 0 on flat
ground — so the three facts below are what any future lane would start from. They are
observations about current capability, not gates on other work:

| Current limitation | Evidence |
|---|---|
| `BuildingInstance` has `cell_offset` only — no Z, no base level | `pae/site.py` |
| Heightmap sampling exists only in `export/terrain.py`, applied AFTER assembly | binding, not placement |
| `steps_external` is a 3-riser one-bay piece; nothing places it and it cannot climb a storey | catalog |

### 9.1 Ground model

| # | Objective | Check owed |
|---|---|---|
| T-001 | `BuildingInstance.base_z_cm` / `base_level` so buildings sit at different heights | placement respects it; no building buried or floating **[V]** |
| T-002 | A site **ground surface** — per-cell ground height, sampled from a heightmap or authored as steps | every cell has exactly one ground height |
| T-003 | Buildings snap their plinth to the ground under their footprint, not to z = 0 | `terrain_conformance`: plinth top within tolerance of ground at every footprint cell **[V]** |
| T-004 | Split-level buildings — one range whose wings sit at different base heights | floor continuity across the split; a step, never a gap |
| T-005 | Undercroft / cellar storey exposed on the downhill side, buried uphill | enclosure still valid where buried |
| T-006 | Retaining walls where the cut exceeds one storey | support; both ends attached |

### 9.2 Upper-storey entrances

**This interacts directly with an existing check.** `aperture_reachability` currently makes
an upper-storey exterior door ILLEGAL unless something walkable sits outside it. That is the
correct coupling and must stay: you may not have a first-floor door without a stair, landing
or gallery reaching it. The feature and its access must land together.

| # | Objective | Check owed |
|---|---|---|
| ~~T-007~~ | ~~`EntranceSpec` role `upper_exterior` — a door on storey N opening to outside air~~ | **DONE (partial @RM_PHASE9)** — role + `storey` field + parse defaults; must pair with landing; `aperture_reachability` + `upper_entrance_landing` enforce. Assemble placement of upper doors still future. |
| T-008 | **External stair run** climbing a full storey against a facade, with landing | landing cell clear at both ends (`stair_landing_clearance`); railed on the open side |
| ~~T-009~~ | ~~External **landing / porch platform** at storey height, reached by a stair~~ | **DONE (partial @RM_PHASE9)** — `make_upper_landing` greybox + critical `upper_entrance_landing`; shared helper with `aperture_reachability`. Stair climb to landing still T-008. |
| T-010 | Stair may be perpendicular OR parallel to the facade it serves | no clash with openings on that facade **[V]** |
| T-011 | Stairs shared between two buildings (one flight, two doors) | both doors reachable from the same landing |
| T-012 | Ground-level door AND upper door on the same facade, vertically offset | aperture alignment; stair does not block the lower door **[V]** |

### 9.3 Jetties and overhangs

The reference's defining feature: the first floor projects beyond the ground floor.

| # | Objective | Check owed |
|---|---|---|
| T-013 | **Real jetty** — upper floor slab projects past the wall below by a style fraction | projection within style range; slab supported by the wall below **[V]** |
| T-014 | Jetty brackets / corbels under the overhang | attachment to the wall below |
| T-015 | `band_course_jettied` (exists, decorative) becomes the *visible edge* of a real jetty | the course aligns with the actual slab edge **[V]** |
| T-016 | Upper storey wider than the one below, on one or more faces | wall above must land on the jetty, not on air |
| T-017 | Overhang must not collide with the neighbouring building across a narrow street | inter-building clearance **[V]** |

### 9.4 Compact irregular placement

| # | Objective | Check owed |
|---|---|---|
| T-018 | Buildings abutting party-wall to party-wall with no gap | no interpenetration; shared wall counted once |
| T-019 | Non-orthogonal / rotated placement on the site grid (45° steps at minimum) | the yaw table (§2.2) must extend or the piece must be re-cut |
| T-020 | Irregular street edge — buildings set back varying depths | walk still reaches every entrance **[V]** |
| T-021 | Stepped street with stair runs between levels | continuous walkable path along the street **[V]** |
| T-022 | Buildings of differing storey heights side by side | roofline still resolves; no roof through a neighbour's wall |

### Dependency order *within* the phase, if and when it is scheduled

T-001 → T-002 → T-003 first: without a ground model nothing else here is expressible. Then
T-007 → T-009 (upper entrances, the visible win), then jetties T-013 → T-016, then the
irregular-placement work. This is an internal ordering, not a claim on priority against
anything else on the roadmap.

### The caution

Every existing check assumes flat ground and a single base level. When T-001 lands, sweep
these and prove they still hold: `vertical_support` (a plinth on a slope), `enclosure`
(a buried storey), `floor_coverage` (a split level), `freestanding` (a building touching
only its retaining wall), and `terrain_conformance` (new). A ground model that quietly
breaks five checks is worse than flat ground.

### 9.5 Buildings that span a route — archways, gate ranges, bridges of rooms

**Recorded, not scheduled.** From the reference street: a masonry range *crosses over* the
road, with a tall arch at street level and inhabited rooms above it. The route passes
THROUGH the building. Nothing in the engine can express this today — a building is a
footprint of solid cells, and a street is cells with no building on them. There is no
concept of a cell that is *open at ground level and built above*.

| # | Objective | Check owed |
|---|---|---|
| T-023 | `passage` cell role — no ground-floor walls or slab, full structure above | headroom under the passage; upper floor fully supported at both abutments **[V]** |
| T-024 | Archway spanning a street: two piers either side, arch head, rooms over | both piers land on ground; arch head continuous **[V]** |
| T-025 | Gate range — a whole wing crossing the road, several bays deep | walkable route through it, unbroken **[V]** |
| T-026 | Bridge of rooms between two buildings at upper level | both ends attached to a real building, not floating **[V]** |
| T-027 | Vaulted or beamed ceiling over the passage | clearance for the route below |
| T-028 | The route through the passage must remain continuous for pathing | site walk connects both sides **[V]** |

Interaction to respect: `enclosure` and `floor_coverage` both assume a cell that is built on
is built on at EVERY level. A passage cell breaks that — it is open below and closed above.
Both checks need a role-aware exemption, written in code, before T-023 can pass.

Related existing gap: `wall_gate_arch` and `arch_freestanding` exist as pieces, but nothing
places them to span a route — they are currently facade decoration only.

---

## Phase 10 — One building out of many masses, and the grid assumptions behind it

Raised by the user 2026-07-25 from a fortress render. Defects in `DEFECT_LEDGER.md` §D3.

The unifying problem: **the engine can place buildings next to each other, but it has no
idea when they are meant to be the same building.** Everything in 10.1–10.3 falls out of
that one gap. 10.4 and 10.5 are independent and can proceed in parallel.

### 10.1 Structure identity — declared, never inferred

**Status: started, not done.** `BuildingInstance.structure` and `CompoundConnections.structure_id`
stamp `structure:<name>` (fortress/castle presets). `freestanding` partitions on `structure:`
when present (Handbook §11d trap). Checks are wired but **silent on untagged builds**.

A `structure` group on a building instance. Instances sharing it are **one building**, and
that changes what is legal: one stair core instead of one per mass, a continuous roof plane,
floors that run through.

**This must be declared in the spec, not detected from adjacency.** A terrace of townhouses
is adjacent *and* separate; a courtyard range is adjacent *and* joined. There is no geometric
test that separates those two cases, and guessing wrong silently welds a street into one
building and then deletes two of its three staircases. If authoring convenience is wanted,
the right shape is a prompt or a lint ("these three masses touch — same structure?"), never a
silent merge.

| # | Objective | Check owed | Status |
|---|---|---|---|
| T-101 | `structure` group on `BuildingInstance`; pieces tagged `structure:<name>` | a structure group is contiguous — no member isolated from the rest **[V]** | **Started** — field + fortress/castle stamping. Poison: `test_structure_checks.py::test_detached_masses_fire_structure_contiguous` |
| T-102 | `freestanding` partitions on **structure**, not on `building:` | *(see caution below)* | **Started** — `partition_key` prefers structure. Poison: `test_structure_identity.py::test_street_of_houses_still_partitions_by_building` |
| T-103 | One stair core per structure, not per mass; solver allocates against the merged footprint | every storey of the structure reachable **[V]** | **Check only** — `structure_single_stair_core`: `test_structure_checks.py::test_triple_stair_wells_fire_structure_single_stair_core`. Solver merge not done (D3-1 open) |

> **Caution on T-102.** `freestanding` currently partitions on the `building:` tag, and that
> was deliberate — without it a street of six houses reported five freestanding groups. Once
> structures exist, the partition key must become the structure, or previously-clean builds
> will start failing and the natural reaction will be to weaken the check. Change the key in
> the same commit as T-101.

### 10.2 Party walls — where two masses of one structure meet

**Status: open.** Checks can fire on poison fixtures; party-wall replacement not shipped (D3-2).

Once membership is declared, a shared boundary is an **interior** wall and must carry a way
through: an opening, an arch, or a door. Today it is two exterior walls back to back.

**Ranges and drums are the same problem — one mechanism covers both.** The user's framing was
"extrude the inside and cut away"; the equivalent in a grid engine is that the shared cells
stop hosting an exterior wall and start hosting a connection piece. Do not build a separate
system for round towers.

| # | Objective | Check owed | Status |
|---|---|---|---|
| T-104 | Detect shared boundaries between masses of one structure | | **Check only** — `structure_party_wall_open` |
| T-105 | Replace the doubled exterior wall with one party wall carrying an opening | no back-to-back exterior walls inside a structure **[V]** | **Open** — poison: `test_structure_checks.py::test_party_walls_fire_structure_party_wall_open`, `test_structure_identity.py::test_three_sealed_with_structure_fires_party_wall_check` |
| T-106 | Same rule where a drum meets a range | every mass of a structure reachable from every other **[V]** | **Check only** — `structure_masses_reachable`: `test_structure_checks.py::test_sealed_party_walls_fire_structure_masses_reachable` |

### 10.3 Sequencing — do 10.1 before 10.2

The opening rule needs to know which walls are interior, and that is only knowable once
membership is declared. In the other order the opening logic gets written twice.

### 10.4 Stacked flights — extend the pads mechanism to straight runs

**Status: partial (D3-3).** `_MONUMENTAL_PAD_KINDS` now includes `straight`; solver expands
well for multi-storey straight runs; `stair_flight_stack` covers `stair_straight`. **Open:**
`fortress_gatehouse_spec` 6×3 shallow hall cannot host expanded well.

`_monumental_flight_pads` does the right thing (two 2×2 pads shifted by the stair width,
alternating anchor **and** yaw). A 180° yaw flip alone is not the fix — it corrects direction
while leaving the flights on top of each other.

**This is solver work, not assembler work** — a straight run needs a well allocated 2 bays
wide before the assembler has anywhere to put the second pad.

| # | Objective | Check owed | Status |
|---|---|---|---|
| T-107 | Solver allocates a 2-bay-wide well for multi-storey straight runs | | **Done** for 8×5+ halls — `test_stair_flight_offset.py::test_fortress_gatehouse_straight_flights_are_laterally_offset`. **Open** for 6×3 gatehouse |
| T-108 | Extend pad alternation to `kind="straight"` | no two flights of one core share a footprint on consecutive levels **[V]** | **Partial** — `stair_flight_stack` + `::test_school_switchback_flights_are_laterally_offset`, `::test_industrial_wide_flights_are_laterally_offset`, `::test_undersized_2x2_well_on_three_storeys_fails_closed_at_assemble`. Gap: `::test_random_monumental_multi_storey_never_stacks` |

### 10.5 Roof edging — one style per edge, declared

**Status: done (D3-4 wiring + check).** `roof_edging_exclusive` critical; trim/compound defer to
`claimed_roof_edges`. Declared `edging` on roofline spec remains future (T-109).

Solid parapet and crenellation are placed by producers that do not consult each other, so an
edge can carry both, overlapping.

| # | Objective | Check owed | Status |
|---|---|---|---|
| T-109 | One `edging` choice on the roofline spec: `parapet` \| `crenellated` \| `none` | no roof edge carries two edging styles **[V]** | **Check done** — `roof_edging_exclusive`: `test_roof_edging_exclusive.py::test_double_edging_on_same_edge_fires_roof_edging_exclusive`, `::test_single_edging_style_passes`, `::test_castle_curtain_compound_has_no_double_edging`. Spec-level choice still open |
| T-110 | Single producer honouring it; `tower_rampart` and `compound` defer to it | | **Done** — `pae/roof_edging.py` producer deferral |

### 10.6 Variable storey datum — the half that is missing

**Already works:** `RoomSpec.height_storeys` is `Optional[float]`, and
`contract.resolve_height_storeys` returns a float. A room with a **1.5-storey ceiling** is
expressible today; `double_height=True` is just shorthand for `height_storeys=2`.

**Does not work:** the storey *datum* is rigid. `contract.floor_placement_z_cm(level)` is
`storey_datum_z_cm(level) - FLOOR_T_CM` (accessor routes uniform `level * STOREY_CM` today).

> **Done (@STOREY_DATUM_ACCESSOR):** every production `level * STOREY_CM` datum site now calls
> `contract.storey_datum_z_cm` — no behaviour change; volume-aware datums remain T-111.

Consequence: a grand hall with a raised ceiling is fine. A **mezzanine**, or a wing whose
floors sit half a storey off its neighbour, is not — and that second case is exactly what
Phase 9 (sloped ground, stepped buildings) needs. Scope this as **variable storey datum**, not
as "taller ceilings"; the ceiling half is done.

| # | Objective | Check owed |
|---|---|---|
| T-111 | Per-volume storey datum: a level's z comes from its volume, not `level * STOREY_CM` | headroom and stair rise measured against the volume's own datum **[V]** |
| T-112 | Stairs spanning two volumes with different datums | run fits the real rise, not the nominal one **[V]** |
| T-113 | Mezzanine — a half-level deck inside a taller volume | reachable, and railed at its open edges **[V]** |

> **Caution.** T-111 touches every hardcoded `level * STOREY_CM`. Route all of them through a
> single accessor first, in its own commit, with no behaviour change — then make the accessor
> volume-aware. Doing both at once makes the diff unreviewable.

### 10.7 The wiring gap

D3-3, D3-4 and D3-5 share a root cause worth naming: **a capability was built correctly and
then not connected.** Pads exist but are gated to two stair kinds; approach-stair repair
exists but is reached only from `compound.py`; the two edging producers never consult each
other. No check asks *"is this feature reachable from the build the user actually runs?"*

Cheapest useful answer: for each showcase/street/fortress build, assert that the features its
spec asks for actually appear in the output. That is a smoke test, not a validator, and it
would have caught all three before a render did.

---

## Phase 11 — Spec as data: the authoring surface an LLM can drive

Raised by the user 2026-07-25 after installing the add-on: *"we only have a couple of
things in there… I'm not sure how we would design our own objects or buildings or city
plans… is there a way for the LLM to nicely connect to it?"*

Correct on both counts. The add-on's entire authoring surface is `building_name`,
`style`, `storeys`, `bays_x`, `bays_y`, `footprint_kind`, `seed` — a rectangle and a
seed. Everything richer (towers, courtyards, room programs, circulation, compounds,
sites) exists in Python and is unreachable from the UI. The preset buttons are hardcoded
scene builders, so what looks like authoring is a menu of fixed scenes.

### The division of labour this phase assumes

The engine's value is not the UI. It is that it **refuses to build things that are
wrong**. So:

- the **LLM authors intent** — four ranges round a court, a gate tower, arcades inboard
- **PAE places and validates** — catching the doorway to nothing, the stair into a wall,
  the floating tower, the three stair cores in one structure

The missing piece is that the spec is not data. `BuildingSpec` is a dataclass with no
serialisation and no operator that accepts one.

| # | Objective | Check owed |
|---|---|---|
| T-114 | `spec_to_dict` / `spec_from_dict` covering **every** field, with `schema_version` | round-trip equality: `from_dict(to_dict(s)) == s` for every fixture spec **[V]** |
| T-115 | `pae.generate_from_spec_json` operator — filepath or text block in, pipeline run, report written to `validation_report_json` | rejects unknown keys loudly rather than silently ignoring them **[V]** |
| T-116 | A **site/compound** spec: several buildings, their offsets, and their `structure` grouping (Phase 10.1) expressed as data | a compound spec round-trips and rebuilds identically **[V]** |
| T-117 | Stable report JSON: `check`, `message`, `world_xyz`, `piece_id`, `critical` | schema is versioned; adding a field never breaks a consumer **[V]** |
| T-118 | Spec **lint** distinct from validate — "this spec is incoherent" before anything is placed (2 storeys, no stair cell reachable; a tower attached to nothing) | every lint has a failing fixture **[V]** |

### Why T-118 matters more than it looks

Validation currently runs on *placed geometry*. An LLM iterating against it pays a full
solve/assemble cycle to learn its spec was nonsense. A cheap lint on the spec itself
closes that loop far faster and gives a much better error: *"storeys=3 but the footprint
has no cell that can host a stair"* beats a stack of downstream placement failures.

### Sequencing

T-114 first — everything else depends on the spec being data. T-117 next, because a
stable report is what makes the loop closeable. T-116 depends on Phase 10.1 (`structure`
grouping) landing first, or it will serialise a concept that does not exist yet.

### The rule this phase must not break

Determinism. `(spec, seed)` must still produce an identical building. Serialisation
introduces the temptation to carry incidental state (timestamps, absolute paths, dict
ordering) into the spec. It must round-trip to the same building, not merely to an equal
dataclass — T-114's check is written against the **assembly**, not the spec object.

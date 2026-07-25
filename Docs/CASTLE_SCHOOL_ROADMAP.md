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
**4.7 Habitable towers and spires.** Drum windows + `tower_junction` ring landed (defect
0.6 / `test_tower_windows.py`). **Partial (@VAL_SPIRAL_SHELL):** central `spiral_newel`
pillar + continuous `tower_arc` drum enclosure checks (`spiral_newel_exists`,
`spiral_drum_enclosure`; door-bay exempt hook for @VAL_TOWER_DOOR). Still open: spires
large enough to contain rooms; walkable top platform with a **circular** railing
following the drum (@VAL_TOWER_RAMPART); hall→tower door (@VAL_TOWER_DOOR).
*Verified by:* stair reachability to the top platform; every drum window at a tread height;
railing continuity around a curve; headroom on the spiral; newel+drum shell checks.

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

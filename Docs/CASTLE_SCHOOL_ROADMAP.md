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
| 0.5 | `aperture_reachability`, `storey_egress` GROUND/VOLUME are WARNINGS | They are correct and find 25 real doorway-to-nothing defects across the milestone fixtures (M2's first-floor door opens into air) | Promoting now breaks 26 tests in other lanes. Fix the fixtures with `pae.variation`, then promote to critical. **A warning that stays a warning past one milestone is decoration.** Partial: assemble no longer stacks L0 doors onto upper storeys; M3 aperture polish green. |
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

**1.4 Vertical stacking of openings.** A doorway onto a first-floor balcony directly above
the ground entrance. Openings need to know about each other vertically so they align.
*Verified by:* a new `aperture_alignment` check — stacked openings share a centre line
within tolerance.

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

**2.4 Double-height volumes.** A great hall or chapel that omits the intermediate floor.
Requires the floor stage to accept per-cell suppression and the walls to run two storeys.
*Verified by:* no floor slab in the volume; walls continuous; balcony/gallery edges railed.

**2.5 Interior fit-out.** Fireplaces, benches, tables, altars, bookcases, beds. This is the
Comfy decorative pipeline's real job — it exists but has only a demo crate.
*Verified by:* props inside rooms only, on floors, not intersecting circulation.

---

## Phase 3 — Vertical circulation (beyond the straight flight)

**3.1 Spiral stairs placed.** `stair_spiral_quarter` exists and is still unreachable from
any spec. Towers need them.
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

**4.1 Curtain walls** with wall-walks, parapets and battlements — a run between towers,
not a building.
**4.2 Gatehouse** — twin towers, portcullis slot, murder holes, barbican.
**4.3 Corner and flanking towers** integrated into curtain walls rather than bolted onto a
range. (Tower geometry exists; attachment is the gap — see defect 0.1.)
**4.4 Moat, bridge, drawbridge.** Needs terrain interaction.
**4.5 Keep** — a tall multi-storey block with its own internal program.
**4.7 Habitable towers and spires.** Today a spire is a solid decorative cone and a tower
drum is blind. Needed: spires large enough to contain rooms and a stair; drum windows placed
along the internal spiral so they light the stair and read correctly from outside; a walkable
platform at the top with a **circular** railing following the drum, not a straight run.
*Verified by:* stair reachability to the top platform; every drum window at a tread height;
railing continuity around a curve; headroom on the spiral.

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
| **Aperture reachability** | A door opening onto a 4 m drop — the balcony bug, generalised |
| **Stacked-opening alignment** | Windows that wander bay to bay between storeys |
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

# Defect Ledger

Every real defect found in PAE and its predecessor, with root cause and the rule it
produced. **Append, never delete.** A bug that reappears must be findable here by symptom.

**Why this file exists:** these bugs cost days each. Most of them are not obvious from the
code — they are obvious only from a render, after the fact. If an agent hits one of these
symptoms again, this file turns a day into ten minutes.

### How to add an entry

Append to the table for your area with: symptom as *observed* (what it looked like, not what
the code did), root cause in one sentence, the fix, and the standing rule if it produced one.
If the defect was caught by a check, name the check. If it was caught by a human looking at a
render, **say so** — that tells us where our coverage is thin.

Severity: **S1** shipped and visible · **S2** caught in review/CI · **S3** near-miss.

---

## A. Cell arithmetic and placement

| ID | Sev | Symptom (as observed) | Root cause | Fix / rule |
|---|---|---|---|---|
| A-1 | S1 | Walls with 92 m gaps between them | East/north runs placed on `x1`/`y1` instead of boundary lines `x1+1`/`y1+1` | Boundary-line rule §2.3 |
| A-2 | S1 | Pieces a full module out of place | Rotation about the min-corner origin with no compensating offset | Yaw offset table §2.2 |
| A-3 | S1 | Parapets at x ∈ [−400, 0] — outside the building, floating | Face offset applied without yaw rotation compensation | **`pae/boundary.py`** — one table, all callers |
| A-4 | S1 | Fences and gates broken at every corner | `site.py` kept a private `_face_offset` doing the boundary line but NOT rotation compensation | Rule 5.2: never hand-roll offsets |
| A-5 | S1 | Parapets on one roof corner, other four bays bare; site classified building interiors as courtyard, cantilevering a balcony deck over a stairwell | Reasoned per `p.cell`, but floors/roofs/ground are ONE spanning placement per wing | **`covered_cells()`**; Rule 5.1 |
| A-6 | S1 | Balcony decks 4 m from the wall they serve; every range measured one cell too big | `covered_cells` inset by a flat `MODULE/4` = 100 cm — *larger than a 60 cm wall* — so a wall flush against cell 9's boundary reported as cell 10 | Inset = `min(MODULE/4, half the piece)`; Rule 4.3 |
| A-7 | S1 | Buttresses braced against thin air | Face chosen from cell neighbours, which says nothing about where the wall actually sits | Derive face from the wall's own AABB; Rule 5.4 |
| A-8 | S1 | Tower with no curved wall | Four arc quarters offset to four cells instead of sharing the circle centre | `rotates_about_center` |
| A-9 | S1 | Characters step up at every threshold | Floor slab top at `+FLOOR_T` instead of placed at `level_z − FLOOR_T` | Floor datum rule §2.4 |
| A-10 | S2 | 20 balcony decks for 16 cells | A courtyard corner cell touches two ranges and was claimed once per range | Resolve shared cells once, globally |

## B. Tolerances

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| B-1 | S1 | An 11 cm railing standing squarely on a floor slab reported as *floating* | The 35 cm **vertical** support tolerance was reused as the **horizontal** overlap threshold, so nothing thinner than 35 cm could ever be supported | `_support_overlap_tol` scales with the piece; Rule 4.1/4.2 |

## C. Connection and coherence

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| C-1 | S1 | Whole building floating in a void | No ground slab, and no check that anything rests on anything | `vertical_support` |
| C-2 | S1 | Gallery roof standing apart from the building | Roof carried on its own posts — *transitively* connected, so the touch graph passed it | `canopy_attachment`: a roof must meet a wall/parapet/attached roof; columns don't count |
| C-3 | S1 | Grey walls standing up through the middle of the blue roof | Trim gave each range a parapet on its court-facing edge (correct then); roofing the gallery extended the roof past that edge, stranding it mid-plane | Drop parapets fully surrounded by roof |
| C-4 | S1 | Gallery canopy meets the range roof with a step and a gap | Canopy offset by `STOREY − FLOOR_T`, putting it 30 cm below the range roof plane | Offset by `STOREY` — same plane |
| C-5 | S2 | 26-piece tower entirely detached from its building | Solver's local repair nudges overlapping towers toward a wall but never asserts contact; assemble drum offset was `2r` leaving an air gap | **FIXED (M7)** — perimeter attach snap in solver; drum offset `r` so AABB kisses hall. Random freestanding tower arcs cleared. |
| C-6 | S1 | 8 m hole at each gable | Walls stop at the eaves; nothing generated the gable infill | `roof_gable_infill` |
| C-7 | S1 | Arcade impossible to tile | 1.76 m pillar in a 4 m module → 2.24 m daylight and two dangling ends | `snap_fit` with a 6 % stretch ceiling; reject otherwise |
| C-8 | S2 | Collinear façade gap missed when coplanar segments differed by ≤ `TOL_CM` on the plane axis | `collinear_gap` bucketed on `round(plane, 3)` — near-coplanar runs never shared a bucket | **FIXED (@VAL_ENG_CONNECT)** — cluster spans with plane diameter ≤ `TOL_CM`; `end_connectivity` counts structure only (not props) |
| C-9 | S2 | Detached / air-gapped tower drum could pass if stairs/floors kept the touch graph alive | No validate-time kiss between `tower_arc` and hall walls (solver attach ≠ assembled AABB kiss) | **FIXED (@VAL_ENG_CONNECT)** — critical `tower_hall_kiss`; freestanding poison fails, M3 attach passes |
| C-10 | S2 | Roof/parapet “supported” by posts/props alone satisfied generic `vertical_support` | Support asked only “is something underneath?”, not “is it a wall head?” | **FIXED** — roofs: `roof_bears_on_wall` (@VAL_ROOF_CONNECT); parapet/battlement: `vertical_support` wall-head bearer audit (@VAL_ENG_CONNECT) |

## D. Reachability and use

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| D-1 | S1 | Balcony with no way onto it | Nothing required an opening | `doors_per_range`: wall bays behind the gallery are swapped for door pieces |
| D-2 | S1 | Court filled with a grid of fences (~3.8 rails/cell) | Railing placed on every face that was not a building, including faces onto other walkway cells | Rail only where the deck meets open air |
| D-3 | S1 | Railing planted in the stairwell void | "Deck beside the hole" was true because the spanning deck covers the hole cells too | Subtract hole cells from the deck set before testing |
| D-4 | S2 | Gallery roof floating a storey above the balustrade | Posts stopped at the deck when `under_roof` was on | Posts continue to the roof |
| D-5 | S2 | Stair top plugged / unclear | `stair_exit_clearance` matches holes by `h.cell` — violates Rule 5.1 | **FIXED (M7)** — hole/stair/plug matching uses `covered_cells` |
| D-16 | S2 | Gallery canopy only partially met range roof | Per-cell gallery `roof_flat` without eaves vs spanning range roofs | **FIXED (M7)** — one spanning canopy per range with court-face eaves |
| D-17 | S2 | School `great_hall` critical `room_spec`: "double_height but plan has no DOUBLE_VOID cells" after `test_build_m1_openings_proof_headless` (passes in isolation) | `reload_pae()` drops `pae.*`; later assemble emits a fresh `CellRole` enum while stale `validate._check_room_specs` still compared with `==` against the pre-reload enum — identity mismatch false-failed even with 21 real DOUBLE_VOID cells | **FIXED (@VAL_ROOMS)** — `_cell_role_is` compares by `.value`; plan carve fail-closed (`double_height_carve`) + gallery-ring fallback so declared double-height always opens a void or fails plan |

## D2. Apertures and variation (user-reported from renders)

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| D-6 | S1 | Four-storey tower with three doorways opening into open air | Assembler places a door on the same bay of EVERY storey; nothing asked what was outside | **FIXED (@VAL_APERTURE / roadmap 0.5)** — `aperture_reachability` + `storey_egress` GROUND/VOLUME promoted **critical**; assemble south-face upper glazing, variation balcony landing set, compound deck-adjacent balcony doors, property factory multi-storey glaze. Tests: `test_aperture_reachability_critical.py` (5); random 100 seeds critical empty |
| D-7 | S1 | Every door in the corner of its elevation | Assembler takes the first bay of a run | Seeded mid-elevation placement with a corner margin |
| D-8 | S1 | Two entrances side by side | Doors repositioned independently, no separation rule | `door_min_separation_bays`, `max_doors_per_elevation` |
| D-9 | S1 | An arched door beside a square-headed one on one elevation | Door style chosen per door | ONE entrance style per building, seeded |
| D-10 | S1 | Four window shapes scattered at random on one building | Per-bay random type, plus a 28% "pick anything" escape | One family per storey, decided up front |
| D-11 | S1 | A second window type appearing despite one-family rule | The *repair* step re-glazed with `window_pieces[0]`, and door demotion used a fixed piece | Both now use the storey's own family — a rule enforced at the choice step must also hold at every repair step |
| D-12 | S1 | Every window clustered on one corner; whole elevations blind | Variation only substituted bays the assembler had already glazed, and the assembler glazes the first few bays of a run | Glaze the whole elevation with a seeded rhythm |
| D-13 | S1 | Half of every perimeter had no banding and no windows | `band_faces_of` discarded a wall when the neighbour in its face direction was interior — but north/east walls sit on the boundary cell BEYOND the interior, so they classify as south/west facing | Flip the face instead of discarding; only skip when interior on both sides |
| D-14 | S1 | Stringcourses ploughing straight through windows | Banding placed without consulting the host wall's aperture | Skip a course whose z-range crosses the opening |
| D-15 | S1 | Diagonal braces read as a staircase of rectangles | Brace built from stacked axis-aligned boxes | Real rotated parallelogram prism along the diagonal |

| D-17 | S1 | Banding appeared as random strips, not at edges or connections | Courses placed per BAY and skipped bays with openings, leaving disconnected fragments | Group by ELEVATION; one continuous run at a height that clears every opening; verticals at corners/junctions |
| D-18 | S1 | Stairs starting or ending inside a wall (29 across all builds) | `stair_exit_clearance` only checked the void ABOVE a flight; first landing check treated any wall-tagged neighbor as solid | **FIXED (@STAIR_LANDING_WALL_BLOCK)** — critical `stair_landing_clear` (covered_cells + interior landing-edge / solid-pad); autofix strips blockers; spiral skipped. See D-27. |
| D-19 | S1 | Four spiral stair quarters at yaw 0/90/180/270 share covered_cells | Quarters *are* one Z-stacked helix on the tower anchor; integrity test treated shared cells as competing stairs | **FIXED (@VAL_STAIR)** — `spiral_cooccupancy_allowed` / `is_spiral_quarter_helix_stack` in `pae/stair_occupancy.py`; integrity allows complementary-yaw stack on same `p.cell` |
| D-20 | S2 | `light_anchor` pieces validated by nothing | Kind added to the catalog with no `measure.py` branch — falls to "unknown kind" | Handbook §3 completeness checklist |
| D-21 | S1 | Spiral tower helix with no touching core support / open drum bay | Assemble emitted quarters only; no existence/containment check for the shell | **FIXED (@VAL_SPIRAL_SHELL)** — conditional touching `spiral_newel` + `spiral_newel_exists` / `spiral_drum_enclosure`; disconnected poles are omitted for open-well stairs (door-bay exempt hook for @VAL_TOWER_DOOR) |
| D-22 | S2 | House got monumental `stair_wide`; industrial kept undersized `stair_straight` when a 2×2 well fit; buttress trim confused with stairs | No `building_class` / stair allow-list; variation could pick any `stair_kind` | **FIXED (@VAL_STAIR_TYPOLOGY)** — `STAIR_TYPOLOGY_POLICY` + `derive_building_class`; `vary_spec` picks continuity-safe kinds; `stair_typology_match` (critical house/buttress, warning undersized institutional) |
| D-23 | S1 | Multi-storey monumental stairs stacked in the same XY (upper flight on lower treads; 180° flip only) — unwalkable | Assemble placed every storey's `stair_switchback`/`stair_wide` in one 2×2 well | **FIXED (@VAL_STAIR_OFFSET)** — solver expands to 4×2/2×4 when storeys≥3; alternate flights shift by stair width; critical `stair_flight_stack` (cells **or** AABB); assemble fails closed on undersized well; property factory passes `storeys=`; Handbook §5.6. Tests: `test_stair_flight_offset.py` |
| D-24 | S1 | Floor gaps under stairs only ~half the run (stairs buried under solid upper deck) | Assemble emitted correct spanning `floor_hole` (`size_cm` 1×2 / 2×1); Blender `spanning_floor_hole_rects_cm` punched only `h.cell` (one bay) | **FIXED (@STAIR_FLOOR_HOLE_SPAN)** — punch uses `covered_cells` + merged rects; critical `stair_run_floor_clear`; Rule 5.7. See also F-7. |
| D-25 | S1 | Gatehouse twin towers with tiny one-block arches; exterior approach steps block walking through the gate; gatehouse too small vs reference castle | Causeway / trim placed steps in gate-leaf columns flush with the opening; fortress gatehouse stayed 4×3 / 2-storey with ordinary `wall_gate_arch` | **FIXED (@GATEHOUSE_MONUMENTAL)** — 6×4 / 3-storey gatehouse + taller drums; `wall_gate_arch_grand`; approach clearance + flanking; critical `gate_passage_clear` / `gate_opening_size`. Handbook §11b. |
| D-26 | S1 | Fortress/castle keep towers: no stair inside, no windows, junk walls/fitout in the drum, no hall connection, no floor-to-floor entry | Hall `stair_kind=switchback` left drums empty; compound `_strip_trim_tower_helixes` deleted trim helixes; tower cells stayed `WALL_LINE` so `tower_entry` skipped; inner `wall_plain` + spanning floors/roofs cut through outboard drums | **FIXED (@TOWER_KEEP_HABITABLE)** — `TowerSpec.stair_kind=spiral`; assemble helix+newel+helical windows+entry; skip inner walls/fitout/parapets in drums; exclude towers from flat roof + upper deck AABB; post-merge headroom strip. Tests: `test_tower_keep_habitable.py`. |
| D-27 | S1 | 1–2 solid walls on stair top landing block exit onto the floor | Landing check was WARNING / wall-without-floor only; missed interior edge blockers on floored pads | **FIXED (@STAIR_LANDING_WALL_BLOCK)** — critical `stair_landing_clear`; assemble/compound `repair_stair_landing_walls` strips blockers (open bay). Tests: `test_stair_landing_wall_block.py`. Fail-closed — not demotable. |
| D-28 | S1 | Linear hall/fortress placed as 3 sealed buildings — party walls, stairs cannot reach next flight | Each range assembled as its own exterior envelope; merge kept back-to-back solid skins with no doorway | **FIXED (@STAIR_LANDING_WALL_BLOCK)** — `compound_not_partitioned_as_buildings` + `compound_range_doors` + `building_doorway_exists` + `building_in_building` (all critical); `unify_compound_assembly` punches link doors / strips dup skins / merges nests. Handbook §5.8–5.9. |
| D-29 | S1 | Fortress gatehouse: 9–12 scattered `steps_grand` (3×N causeway grid), misaligned with twin arches; step tops at 175 cm while L0 floor / gate sill is z≈0 | `_add_approach_causeway` stamped a rectangular apron (`approach_rows`×`width_bays`) with fixed catalog height; trim flanking logic not shared | **FIXED (@APPROACH_STAIR_MATE)** — `pae/approach_stairs.py` per-gate flanking + `mated_step_pose`; critical `approach_stair_height_mate` + `approach_stair_aligned_to_gate`; `stair_flight_stack` extended for exterior duplicate XY; `repair_approach_stairs` autofix. Tests: `test_approach_stair_mate.py`. |
| D-30 | S1 | Landing autofix strips walls all the way through the building — entire floor-blocks away from stairs | `repair_stair_landing_walls` removed any landing blocker by `piece_id` even when `covered_cells` spanned far outside the pad | **FIXED (@STAIR_WALL_STRIP_SCOPE)** — strip zone = landing pad + stair ends + ≤1 cell along run axis; critical `stair_landing_strip_scope`; `measure_stair_landing_strip`. Tests: `test_stair_landing_wall_block.py` (through-wall + distant-wall fixtures). Fail-closed — not demotable. |
| D-31 | S1 | Compact tower floors show solid blue hole frames, every helix is missing 90°, large stairs retain a disconnected pole, and the entry frame cuts through the walking band | `floor_hole` cutter metadata was instanced as geometry; doorway yaw was deleted from each climb; tread `size_cm` was misread as diameter instead of outer radius; newel was unconditional | **FIXED (@TOWER_CIRCULATION_FULL_TURN)** — builders skip physical `floor_hole` instances; four quarters/storey ordered from the entry landing; outer radius clamped to the masonry inner face; `tower_entry_clears_stair` measures the actual inner-face radius; newel emitted only when tread and pole meet. Focused tower suite: 38 passed. |

## E. Kind registration

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| E-1 | S2 | `unknown kind 'column'` from the footprint checker | New kinds added to the catalog but not to `measure.py` | §3 completeness checklist |
| E-2 | S2 | Two stair variants with indistinguishable material tints | New asset added without a distinct colour | Material colour is part of registration |
| E-3 | S2 | `light_anchor` placements empty / measure unknown-kind; school sconces missing in suite | Half-registered kind (catalog/measure/build_mesh/island exempt/manifest collision) + chandelier only scanned `INTERIOR` (missed `DOUBLE_VOID` halls) | Register `light_anchor` end-to-end; chandelier roles include `DOUBLE_VOID`; NoCollision stub |
| E-4 | S2 | StylePack unknown-key / inheritance-cycle tests flake green | Cycle path returned silent `None` instead of raising; schema failures must stay critical | `resolve_style_pack` raises on cycle; `load_style_pack` always emits `style_schema` / `style_extends` critical |
| E-5 | S3 | `magic_number_grep` fails on `test_entrances.py` bare-aperture fixture | Hard-coded `(60.0, 400.0, 300.0)` instead of contract module constants | Use `(WALL_T_CM, MODULE_CM, STOREY_CM)` |

## F. Blender / mesh

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| F-1 | S1 | Boolean collapses a piece to a bare box (8 verts) | Cutting a *joined* mesh gives the EXACT solver coplanar faces | Cut the **core** before joining decorative bands |
| F-2 | S1 | Five kit pieces silently missing from export | `modifier_apply` needs the target **active AND selected**, everything else deselected | — |
| F-3 | S1 | Edits appear to do nothing | Blender/UE Python caches modules | `importlib.reload` |
| F-4 | S1 | A 40-segment circle reads as a faceted prism | Flat shading + too few segments | ≥96 segments per full circle; smooth-shade curved faces only |
| F-5 | S2 | Object bounds read 28× too large right after instancing | Depsgraph not updated; matrices stale | `bpy.context.view_layer.update()` + `evaluated_get(dg)` before measuring |
| F-6 | S1 | Long vertical smears on every wall | Single XY world projection | Triplanar |
| F-7 | S1 | Stairwell floor gap only half the flight in live Blender (placements OK) | Mesh punch used `h.cell` origin, ignored spanning `floor_hole.size_cm` / `covered_cells` | `hole_rects_merged_for_deck_cm` + Rule 5.7; `stair_run_floor_clear` |

## G. Unreal / pipeline (predecessor project)

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| G-1 | S1 | 16-bit heightmap imported as 8-bit stair-steps | `RTF_RGBA8` silently ignores `rg_channel` | Requires `RTF_RGBA32F` |
| G-2 | S1 | Terrain-placed actors buried | Ray-cast landscape collision | Sample the heightmap |
| G-3 | S1 | Editor locked at 20 GB, force-killed twice | Unbounded loop over ~9,000 actors on the game thread | Bound every editor-side loop |
| G-4 | S1 | Landscape flattened to −256 m | RT sanity gate threw and was bypassed | Gates are unconditional; a gate that can be skipped is not a gate |
| G-5 | S1 | Constant-height test passed while 8-bit bug was live | Test used 50.0 m — low byte exactly 0, hiding the truncation | Test values must exercise the low byte (50.5) |

## D3. Structure, circulation and roofline — user-reported from renders, 2026-07-25

Reported by the user against a fortress/compound render. Every row here was **measured**
before being written down; the "Evidence" column names the command or the count so the
next person does not have to re-derive it. Open items carry the lane that owns them.

| ID | Sev | Symptom (as observed) | Root cause | Evidence | Fix / rule |
|---|---|---|---|---|---|
| D3-1 | S1 | Three guardhouses in a row render as three separate buildings — walls between them on the roof, and a separate staircase in each | The engine had **no concept of one building assembled from several placed masses**. `site.place_buildings` merges assemblies but deliberately tags each piece `building:<name>` and keeps them distinct | Visual; `site.py:141` | **FIXED (@STRUCTURE_IDENTITY)** — declared `structure:fortress_bailey`; merge south bar to `building:fortress_campus`; `primary_circulation_mass=north_keep` + `repair_structure_single_stair_core`; critical `structure_single_stair_core`. Green path: `test_structure_identity.py::test_fortress_compound_green_path_structure_identity` |
| D3-2 | S1 | Connected ranges keep full walls between them where they meet; connected drums likewise | Follows from D3-1 — with no structure identity, a shared boundary is still two exterior walls, never an interior party wall | Visual | **FIXED (@STRUCTURE_IDENTITY)** — `structure_party_wall_open` + strengthened `compound_not_partitioned` for same-structure interfaces; `unify_compound_interfaces` strips/punches party lines. Green path: same fortress test + poison fixtures. One mechanism for ranges and drums |
| D3-3 | S1 | Stacked flights face the same way, directly on top of each other — "you couldn't walk up this if you wanted to" | The correct mechanism EXISTS (`_monumental_flight_pads`, two 2×2 pads shifted by stair width, alternating anchor **and** yaw) but was gated to `kind in ("switchback","wide")`. `straight` got `pads=None` and fell back to reusing the same cells | `assemble.py:1125`; measured 1/1 same-yaw on old `fortress_gatehouse_spec` (6×3) | **FIXED (@D3_WIRING_FIX)** — `_MONUMENTAL_PAD_KINDS` includes `straight`; solver expands well (`fortress_gatehouse_spec` 8 cells); assemble **fail-closed** `return` when `pads is None` and `climbed ≥ 2` (no silent stack). Critical `stair_flight_stack`. Tests: `test_d3_wiring.py` (8), `test_stair_flight_offset.py` (`::test_fortress_gatehouse_straight_flights_are_laterally_offset`, `::test_undersized_2x2_well_on_three_storeys_fails_closed_at_assemble`, `::test_random_monumental_multi_storey_never_stacks`). Roadmap 10.4 |
| D3-4 | S1 | Roof carries two edging styles at once — solid parapet and crenellation overlapping on the same edge | Two independent producers with no knowledge of each other: `trim._roofline` places `parapet_solid`; `tower_rampart` / `compound._add_curtain_battlements` place crenels. Nothing asks whether the edge is already claimed | Visual; `trim.py:712`, `tower_rampart.py:295`, `compound.py:834` | **FIXED (@D3_WIRING_FIX)** — `pae/roof_edging.py` + critical `roof_edging_exclusive`; trim/compound defer to `claimed_roof_edges`; `CURTAIN_TRIM` / `FORTRESS_CURTAIN_TRIM` `parapets=False` so `_add_curtain_battlements` owns curtain edges. Tests: `test_roof_edging_exclusive.py` (4), `test_d3_wiring.py` (`::test_fortress_curtain_trim_defers_parapets_for_battlements`, `::test_fortress_compound_approach_and_edging_wired`). Handbook §11d |
| D3-5 | S1 | Grid of exterior flights in front of a gate, each far too tall to climb into the threshold | Approach stairs mated to grade, not to the gate sill | `approach_stairs.py` header | **FIXED (@D3_WIRING_FIX)** — `repair_approach_stairs` wired from `trim()` when `exterior_steps=True` (`GATEHOUSE_TRIM`, `FORTRESS_GATEHOUSE_TRIM`) and post-merge `_add_approach_causeway` on `build_fortress_compound` + `build_castle_curtain_compound` (module unchanged). Tests: `test_d3_wiring.py` (`::test_fortress_compound_approach_and_edging_wired`, `::test_castle_curtain_compound_approach_repaired_post_merge`, `::test_gatehouse_trim_wires_exterior_steps_repair`, `::test_fortress_gatehouse_trim_alone_still_repairs_approach`), `test_approach_stair_mate.py`; critical `approach_stair_height_mate` / `approach_stair_aligned_to_gate` |
| D3-6 | S1 | Tower drum: perimeter wall runs through it, windows open into its interior, no entry, helix stops two storeys short | A tower cell is claimed by **two enclosures at once** — the drum arcs and the body's rectangular wall run | `scratchpad/diag3.py`: 15 walls + 2 floors interpenetrating; helix at levels 0–1 of 0–3; 6 windows | **PARTIAL (@MP-WS4)** — T-D1 outboard-only wall suppress + T-D3 `drum_exclusivity` / `aperture_faces_open_air` green (`test_tower_drum_enclosure.py`). **OPEN:** T-D2 trim-only entry, full-shaft helix, `library_tower` (@MP-WS3b). See `Docs/DESIGN_TOWER_DRUM.md` trap |
| D3-7 | S1 | Buttresses "not even facing the buildings", oversized stepped blocks | `buttress()` mates to the wall with its **back** (socket at `pos_cm=(depth,..)`, `+X` normal), so its local +X **is** the wall side. `outward_offset_cm` is for pieces whose +X points **away** — every buttress was yawed 180° wrong | Visual + `diag3.py` | **DONE** — commit `5de4b0d`. `trim._pier_pose` for pieces that BEAR on a face; `outward_offset_cm` only for pieces that project away. **Do not merge the two back together** |
| D3-8 | S3 | "Is it not spawning stairs? Does the agent have to place them?" | Not a defect — the solver auto-allocates. `solver.py:827`: `storeys > 1` and no `stair_cells` → `_default_stair_cells`. `assemble._place_stairs` returns early only if that list is empty | `solver.py:827`, `assemble.py:1176` | No action. A building with no stairs is either **single-storey in its spec**, or the solver raised `stair_serves_upper` ("storeys > 1 but no stair cells could be placed", `solver.py:838`) — that is critical and will be in the report |
| D3-9 | S1 | West cloister court face shows `wall_plain` + `wall_arcade` coplanar (double skin) | `trim._colonnade` / `_add_cloister_arcade` place arcade while assemble already emitted plain walls; post-unify merge retags range names so arcade pass missed cloister walls | measured **2** coplanar arcade pairs (west cloister poison) before `repair_wall_face_stacks`; **0** after | **FIXED (@CLOISTER_WALL_STACK)** — `pae/wall_faces.py` critical `wall_face_exclusive` + `repair_wall_face_stacks`; trim/compound share `claimed_wall_arcade_faces`; `_placement_matches_range` for post-unify piece_ids; `FORTRESS_CURTAIN_TRIM.parapets=False` so `_add_curtain_battlements` can claim edges. Tests: `test_wall_face_exclusive.py` |
| D3-9 | S1 | One building reads as several — a sketched U produced a tall block, a low block and another tall block | Roof is emitted PER VOLUME. `rect_cover` splits an arbitrary mask into rectangles so the solver can reason in boxes — an internal detail — but ridge height is then derived per rectangle, so a 2-bay bridge gets a low ridge and the 4-bay legs a tall one | Measured on the sketched U: 3 pitched slopes at z-tops 2200 / 2200 / 1640 plus valleys at 1220; **0** internal seam walls, so walls are already correct | **CLOSED (@MP-WS2 / Stage C)** — column height field (`roof_height_field_bands`) + `structure_ridge_span_modules` (max short-span per eaves band). Sketched U pitched/hip → one ridge family `{1150}`; M-A proof `ma_roof_ridge_report.json`. Tests: `test_roof_height_field.py` |

### MP-WS6b — M-E style interchange (2026-07-25)

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| ME-1 | S3 | Same sketch should read as different architecture when style pack changes | Style packs were loaded but no interchange proof tied sketch → assemble → validate across all eight builtins | **DONE (@MP-WS6b)** — M2 4×3 × 8 packs, 8/8 `critical=[]`; report `Saved/exports/me_style_interchange_report.json`; tests `test_style_interchange.py`. **Gaps (authored, unconsumed):** `wall_bands.*`, `materials.*` — engine lane, not demoted. **`storey_height_cm` consumed @MP-WS-Z** |

### What D3 says about our coverage

D3-3, D3-4 and D3-5 are all the same failure of *method*: *a capability was built correctly
and then not connected*. Pads exist but are gated; approach-stair repair exists but is called
from one path; edging producers exist but do not consult each other. None of these is hard
engineering — all three are **wiring**, and no check asks "is this feature reachable from the
build the user actually runs?"

That is a gap worth a check of its own, and it is a different gap from the one in the Coverage
confession below. It is not that the check was missing; it is that the code was unreachable.
---

## Patterns — what keeps happening

Four root causes account for most of the S1 entries. Check these first:

1. **Cell-level reasoning against spanning pieces** (A-5, A-6, D-3, D-5) — five bugs.
2. **Offsets composed by hand instead of from the table** (A-1…A-4, A-7).
3. **A tolerance borrowed from a different purpose or axis** (B-1, A-6).
4. **A check that asks an adjacent, easier question than the real one** (A-5's origin-on-grid
   check; C-2's transitive connectivity) — the check passes, the building is wrong.
6. **An internal implementation detail leaking into the output** (D3-9) — how the solver slices a shape decided how the roof looks.
5. **A capability built, then left unwired** (D3-3, D3-4, D3-5) — the code is correct and simply never runs on the path the user builds.

## Coverage confession

Of the S1 defects above, **the overwhelming majority were found by a human looking at a
render**, not by a check. Checks were added *after*. That ratio is the honest measure of the
validator's maturity, and improving it is the point of the Handbook.

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
| C-5 | S2 | 26-piece tower entirely detached from its building | Solver's local repair nudges overlapping towers toward a wall but never asserts contact | **OPEN** — roadmap defect 0.1 |
| C-6 | S1 | 8 m hole at each gable | Walls stop at the eaves; nothing generated the gable infill | `roof_gable_infill` |
| C-7 | S1 | Arcade impossible to tile | 1.76 m pillar in a 4 m module → 2.24 m daylight and two dangling ends | `snap_fit` with a 6 % stretch ceiling; reject otherwise |

## D. Reachability and use

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| D-1 | S1 | Balcony with no way onto it | Nothing required an opening | `doors_per_range`: wall bays behind the gallery are swapped for door pieces |
| D-2 | S1 | Court filled with a grid of fences (~3.8 rails/cell) | Railing placed on every face that was not a building, including faces onto other walkway cells | Rail only where the deck meets open air |
| D-3 | S1 | Railing planted in the stairwell void | "Deck beside the hole" was true because the spanning deck covers the hole cells too | Subtract hole cells from the deck set before testing |
| D-4 | S2 | Gallery roof floating a storey above the balustrade | Posts stopped at the deck when `under_roof` was on | Posts continue to the roof |
| D-5 | — | Stair top plugged / unclear | `stair_exit_clearance` matches holes by `h.cell` — violates Rule 5.1 | **OPEN** — roadmap defect 0.2 |

## E. Kind registration

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| E-1 | S2 | `unknown kind 'column'` from the footprint checker | New kinds added to the catalog but not to `measure.py` | §3 completeness checklist |
| E-2 | S2 | Two stair variants with indistinguishable material tints | New asset added without a distinct colour | Material colour is part of registration |

## F. Blender / mesh

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| F-1 | S1 | Boolean collapses a piece to a bare box (8 verts) | Cutting a *joined* mesh gives the EXACT solver coplanar faces | Cut the **core** before joining decorative bands |
| F-2 | S1 | Five kit pieces silently missing from export | `modifier_apply` needs the target **active AND selected**, everything else deselected | — |
| F-3 | S1 | Edits appear to do nothing | Blender/UE Python caches modules | `importlib.reload` |
| F-4 | S1 | A 40-segment circle reads as a faceted prism | Flat shading + too few segments | ≥96 segments per full circle; smooth-shade curved faces only |
| F-5 | S2 | Object bounds read 28× too large right after instancing | Depsgraph not updated; matrices stale | `bpy.context.view_layer.update()` + `evaluated_get(dg)` before measuring |
| F-6 | S1 | Long vertical smears on every wall | Single XY world projection | Triplanar |

## G. Unreal / pipeline (predecessor project)

| ID | Sev | Symptom | Root cause | Fix / rule |
|---|---|---|---|---|
| G-1 | S1 | 16-bit heightmap imported as 8-bit stair-steps | `RTF_RGBA8` silently ignores `rg_channel` | Requires `RTF_RGBA32F` |
| G-2 | S1 | Terrain-placed actors buried | Ray-cast landscape collision | Sample the heightmap |
| G-3 | S1 | Editor locked at 20 GB, force-killed twice | Unbounded loop over ~9,000 actors on the game thread | Bound every editor-side loop |
| G-4 | S1 | Landscape flattened to −256 m | RT sanity gate threw and was bypassed | Gates are unconditional; a gate that can be skipped is not a gate |
| G-5 | S1 | Constant-height test passed while 8-bit bug was live | Test used 50.0 m — low byte exactly 0, hiding the truncation | Test values must exercise the low byte (50.5) |

---

## Patterns — what keeps happening

Four root causes account for most of the S1 entries. Check these first:

1. **Cell-level reasoning against spanning pieces** (A-5, A-6, D-3, D-5) — five bugs.
2. **Offsets composed by hand instead of from the table** (A-1…A-4, A-7).
3. **A tolerance borrowed from a different purpose or axis** (B-1, A-6).
4. **A check that asks an adjacent, easier question than the real one** (A-5's origin-on-grid
   check; C-2's transitive connectivity) — the check passes, the building is wrong.

## Coverage confession

Of the S1 defects above, **the overwhelming majority were found by a human looking at a
render**, not by a check. Checks were added *after*. That ratio is the honest measure of the
validator's maturity, and improving it is the point of the Handbook.

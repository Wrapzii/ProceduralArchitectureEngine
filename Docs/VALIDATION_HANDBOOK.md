# Validation Handbook

**Read this before adding any piece, any placement rule, or any check.**

This is the directive for how PAE is tested and validated. It applies to everything — a new
tower type, a new solver, or a 4 cm coping strip on top of a parapet. There is no feature
too small to need a check, because the defects that have actually shipped in this project
were small: a railing 11 cm thick, a parapet on the wrong edge, a wall one cell over.

---

## 0. The premise

> **Validation is the product. The geometry is an implementation detail.**

Anyone can emit boxes. The engine's value is that it emits boxes *you can trust without
looking at them*. Every hour spent on a check buys back ten spent staring at renders.

Three facts from this project's history, which you should treat as laws:

1. **Every defect that shipped was found by a human looking at a render, never by a check.**
   Walls with 92 m gaps. A castle floating in a void. Parapets a full module outside the
   building. Balcony decks 4 m from the wall they serve. In each case the automated checks
   ran, passed, and were asking the wrong question.
2. **A check that has never failed is not evidence of correctness.** It is more likely
   evidence that it cannot fail. See §6.
3. **The bug is almost never in the geometry. It is in the reasoning about where geometry
   goes.** Cell arithmetic, rotation offsets, tolerance choice. See the Defect Ledger.

---

## 1. The taxonomy — nine ways a building is wrong

Every check in PAE answers exactly one of these questions. When you add a feature, walk the
list and ask which of these it can now violate. That is your check list.

| # | Class | The question | Existing checks |
|---|---|---|---|
| 1 | **Existence** | Did the thing that was asked for actually get placed? | `spiral_newel_exists`, entrance/ensemble existence, `building_doorway_exists`, `fortress_tower_capped`, `fortress_gate_exists`, `fortress_grand_approach` *(see §11b)* |
| 2 | **Dimension** | Does the piece match the grid contract? | `footprint_contract_errors`, `wall_height_span`, `gate_clear_height` |
| 3 | **Placement** | Is it in the cell/orientation it was meant to be? | `run_fit`, `buttress_outward` |
| 4 | **Connection** | Does it touch what it must touch? | `end_connectivity`, `collinear_gap`, `canopy_attachment`, `tower_hall_kiss`, `roof_valley_join`, `spire_freestanding`, `curtain_battlement_continuity`, `compound_range_doors` |
| 5 | **Support** | Is something underneath it? | `vertical_support` (parapet wall-head), `roof_bears_on_wall` |
| 6 | **Coherence** | Is it part of one building, or its own island? | `freestanding`, `spire_freestanding`, `structure_contiguous`, `structure_party_wall_open`, `structure_masses_reachable`, `structure_single_stair_core`, `compound_not_partitioned_as_buildings`, `building_in_building`, `footprint_overlap` |
| 7 | **Exclusion** | Does it avoid what it must avoid? | `interpenetration`, `roof_penetration` |
| 8 | **Containment** | Is the envelope sealed, floored, covered? | `enclosure`, `floor_coverage`, `roof_covers_enclosed`, `spiral_drum_enclosure` |
| 9 | **Use** | Can a person reach it, enter it, walk it, leave it? | `stair_reachability`, `stair_exit_clearance`, `stair_run_floor_clear`, `stair_landing_clear`, `stair_flight_stack`, `stair_typology_match`, `classroom_corridor`, `aperture_sanity`, `gate_passage_clear`, `approach_stair_height_mate`, `approach_stair_aligned_to_gate` |

A tenth class — **proportion** ("does it look right") — is *not* mechanically checkable and
must not be faked. See §9.

---

## 2. The seven questions

For **any** new piece family or placement rule, answer these seven in the PR description.
Each answer that is not "N/A" is a check you owe.

1. **What must it touch?** (Connection) — a railing touches a deck; a coping touches a
   parapet; a buttress touches a wall.
2. **What must be under it?** (Support)
3. **What must it NOT overlap?** (Exclusion)
4. **What must it not stick through?** (Exclusion)
5. **Can it exist in isolation?** If no → it must be caught by `freestanding`. If yes (a
   boundary fence, site paving) → it must be *explicitly exempted*, in code, with a comment
   saying why.
6. **Does a person interact with it?** (Use) — if you can stand on it, walk under it, or go
   through it, there is a clearance or reachability check owed.
7. **Is it requested by a spec?** (Existence) — if a spec field can ask for 3 of them, a
   check must assert 3 were placed.

### Worked example: adding a coping strip

Coping is a 12 cm capping course on top of a parapet. Trivially small. Here is what it owes:

| Q | Answer | Check |
|---|---|---|
| Touch | The parapet below it, along its whole length | `coping_attachment`: every coping AABB intersects a parapet AABB |
| Under | The parapet | covered by `vertical_support` — **but verify the tolerance**, see §4 |
| Not overlap | Other coping, roof pieces | `interpenetration` (already generic) |
| Not stick through | N/A (it is the topmost course) | — |
| Isolation | No | must be caught by `freestanding` — do **not** add an exemption |
| Interaction | No, decorative | — |
| Spec-requested | Yes, `coping: bool` per style | existence check: style asks for coping → coping placed on every parapet run |

That is **two new checks** and one tolerance verification, for a decorative strip. This is
the expected ratio. If a feature comes with no checks, it is not finished.

---

## 3. Registering a new kind — the completeness checklist

A half-registered kind is a silent hole: the piece exists, but the validator does not know
what rules apply to it, so it is checked by *nothing*. Every kind must appear in **all** of
these, or the PR is incomplete:

- [ ] `pae/primitives/<family>.py` — descriptor + `build_*_mesh`
- [ ] `pae/primitives/catalog.py` — `all_descriptors()` **and** the `build_mesh` dispatch
- [ ] `pae/primitives/measure.py` — a footprint rule branch. **Never let it fall to the
      `else` that raises "unknown kind"**, and never add it to an existing branch whose
      rules do not actually apply
- [ ] `pae/validate.py` — decide, explicitly, which of the nine classes apply
- [ ] `pae/blender_build.py` — a material colour, so it is distinguishable in a render
- [ ] `pae/export/manifest.py` — collision profile and LOD policy
- [ ] `Docs/PRIMITIVE_MEASUREMENTS.md` — regenerated

**Exemptions are code, not conventions.** If your kind is legitimately exempt from a check
(site surfaces are not part of the building; a boundary fence is *meant* to stand alone;
`light_anchor` markers are position-only UE spawn hints with no structural role),
add it to the named exemption set with a comment giving the reason:

```python
# light_anchor: position-only UE spawn markers — not structural envelope pieces.
ISLAND_EXEMPT_KINDS = frozenset({"surface", "light_anchor"})
ISLAND_EXEMPT_TAGS = frozenset({"site", "boundary", "light_anchor", "marker"})
```

An exemption that is not written down becomes a bug the next person has to rediscover.

**Outdoor tower crown / rampart decks (`tower_deck` / `tower_top`):** these are
open-air wall-walks under the crown (Phase 4.7), not enclosed habitable storeys.
`storey_egress` STOREY/VOLUME **must not** treat them as indoor floors that need a
stair arrival or a door/window volume — that is an explicit classification in
`validate._is_outdoor_tower_deck_floor` / `_check_storey_egress`, not a demotion of
the check. Indoor slabs stay fully covered. Deck presence is owned by
`tower_top_walkable` / rampart checks. Same family as the headroom outdoor-deck skip.

**`tower_entry` hall↔drum doors:** aperture cells must resolve to a walkable hall
bay (not the naive WALL_LINE neighbour) and a passable drum/stairwell cell.
Keep attach cells are often planned as `WALL_LINE` — that role is drum-passable for
`tower_entry` placement (the round shell owns the cell). `aperture_sanity` checks both
sides as a through-passage for `tower_entry` only — ordinary exterior doors still
require EXTERIOR/COURTYARD on the outside.

**Habitable keep drums (`TowerSpec.stair_kind=spiral`):** assemble places a helix +
newel in each such tower even when the hall `CirculationSpec` is switchback/straight.
Glazing and climb stop at hall-overlapping storeys; the outdoor `tower_deck` crown pad
is not an exit target (unopenable 1×1). After compound merge, helix quarters under a
neighbour roof AABB are stripped (headroom) rather than demoting the check.

**Worked example — `light_anchor` (S-068…S-070) is fully registered:**
`pae/primitives/anchors.py` + catalog `all_anchors` / `build_mesh` dispatch + measure
sub-bay branch + island exempt above + `blender_build` KIND colour + manifest
`NoCollision` stub and top-level `light_anchors` block + `Docs/PRIMITIVE_MEASUREMENTS.md`.

---

## 4. Tolerances — the most common source of false confidence

Three rules, each learned the hard way.

**4.1 Never reuse a tolerance across purposes.** `VERTICAL_SUPPORT_TOL_CM = 35` is a
*vertical* tolerance. It was also being used as the *horizontal overlap* threshold, which
meant any piece thinner than 35 cm could never be supported by anything: an 11 cm railing
standing squarely on a floor slab reported as floating.

**4.2 Scale tolerances to the piece under test, not to a constant.**

```python
def _support_overlap_tol(bb_min, bb_max, tol):
    smallest = min(bb_max[0] - bb_min[0], bb_max[1] - bb_min[1])
    return min(tol, max(0.0, smallest * 0.5))
```

A railing needs 5.5 cm of slab under it; a wall still needs the full 35.

**4.3 An inset must never exceed half the piece.** This is the single most expensive line in
the project's history:

```python
eps = MODULE_CM * 0.25          # WRONG — 100 cm, larger than a 60 cm wall
eps_x = min(MODULE_CM * 0.25, (mx[0] - mn[0]) * 0.5)   # right
```

The wrong version pushed a wall flush against cell 9's boundary into cell 10, inflating
every range by one cell, which put balcony decks 4 m from the wall they serve.

---

## 5. The five standing rules

These are not style preferences. Each one is a defect class that has already cost days.

**5.1 Never reason from `p.cell`. Always use `covered_cells(p)`.**
Floors, roofs and ground slabs are emitted as ONE spanning placement per wing, so `p.cell`
is only its origin. Reasoning per `p.cell` put parapets on a roof's corner bay and left the
other four bare, and made the site classify building interiors as courtyard. This has caused
**five separate bugs**. If you type `p.cell` in a check, justify it in a comment.

**5.2 Never hand-roll a placement offset. Use `pae/boundary.py`.**
Placing a piece on a cell edge means composing *two* offsets: yaw rotation compensation
(§2.2) and the boundary line (§2.3). `site.py` kept a private copy that did the second and
not the first, so every south/north fence — yawed 90° — landed a full module out, visible as
gates breaking at corners. There is one table. Use it.

**5.3 Never trust a declared size. Measure the mesh.** Monumental gate / cloister arches
(`gate_arch`, `gate_arch_grand`, `arcade_round`) use `head_bands ≥ 24` and band step
≤ 8 cm (`pae/primitives/measure.py` — `monumental_arch_mesh_smooth`). Descriptor opening
fractions are unchanged; only the curved-head mesh resolution improves.

**5.4 Never derive a face from cell neighbours when the piece's own position knows better.**
`_buttresses` chose a face by "this neighbour is not interior", which says nothing about
where the wall actually *sits* — a west buttress ended up braced against air next to a wall
standing on the cell's east boundary. Derive the face from the wall's AABB relative to its
cell bounds.

**5.5 All dimensions come from `pae/contract.py`.** CI greps for `400.0`, `350.0`, `60.0`,
`30.0`. Fractions of the contract are fine; literals are not.

**5.6 Never stack monumental stair flights in the same XY.** A `stair_switchback` or
`stair_wide` on level N+1 must be shifted by one stair width from level N. A 180° yaw
flip in the same 2×2 well is **not** a stair — it is a solid on the previous treads.
Multi-storey wells are 4×2 / 2×4; `stair_flight_stack` is **critical** (cells or AABB).
Exterior `steps_grand` / `steps_external` at L0 also fail when two approach pieces share
the same cell or XY AABB (causeway grid spam / double trim). See Defect Ledger D-23, D-29.

**5.7 Stairwell mesh punch must clear the full run.** Spanning upper decks keep a solid
AABB and open VOIDs in Blender via `slab_with_rect_holes`. Punch rectangles must be built
from every `covered_cells` bay of each `floor_hole` (merged into one opening per well) —
never from `h.cell` alone. Origin-only punch left stairs buried under half a floor slab
while `stair_exit_clearance` still passed (placements were correct). Gate:
`stair_run_floor_clear` (critical). See Defect Ledger D-24 / F-7.

**5.8 Stair landings must not be walled shut.** Solid walls (no door/gate/window/arcade)
must not block the top or bottom landing of a linear stair. Use `covered_cells` of the
stair plus the landing-pad cell beyond each end (Rule 5.1). Perimeter envelope walls past
the footprint are not landing blockers; interior exit edges with floor on the pad are.
Check: `stair_landing_clear` (**critical**, fail-closed — no warning demotion, no suppress
tags). Autofix in assemble/compound: strip blocking skins **only when every**
`covered_cells` bay lies inside the landing strip zone (pad + stair ends + ≤1 cell along
the run axis). Check: `stair_landing_strip_scope` (**critical**) — a blocker that spans
outside the zone must not be auto-stripped (prevents punching through the building).
Ledger D-18 / D-27 / D-30.

**5.9 Connected compound ranges are one circulation graph.** Touching ranges on one
compound/site must not be sealed by back-to-back exterior skins with no doorway. Detect
with `compound_not_partitioned_as_buildings` + `compound_range_doors` + `footprint_overlap`
(critical). **Connection policy** on each `RangeStyle` / `CompoundConnections` pair:

| Policy | Behaviour |
|--------|-----------|
| `separate` | Distinct buildings; sealed interfaces fail until a doorway is authored |
| `connect` | Strip back-to-back duplicate skins; punch ≥1 walkable link per interface |
| `merge` | Single inhabited mass — retag to shared `building:{campus_id}`, strip party walls |

Fortress bailey defaults: south curtain chain (`west_curtain` \| `gatehouse` \| `east_curtain`)
= **merge**; cloister ↔ curtain/keep = **connect**; all ranges declare
`structure:fortress_bailey` (one structure — Roadmap 10.1). Autofix
(`pae/compound_unify.unify_compound_assembly(assembly, connections=…)`): apply policies,
punch `compound_link` doors where needed. Building-in-building footprints →
`building_in_building` (critical) + tag merge. Every inhabited `building:*` needs ≥1 doorway
(`building_doorway_exists`). Ledger D-28.

**5.10 Declared height is not capped at two storeys.** Rooms / envelopes declare height via
`height_storeys` (float/int) or `HeightDecl` (`storeys` preferred; `height_cm` is a
Python override — BuildingSpec JSON still forbids `*_cm`). Convert with
`height_cm_from_storeys` / `STOREY_CM`. Monumental gate/arch leaves **span** the declared
envelope (`size_cm.z`, tag `wall_height_span`) rather than stacking one-MODULE stubs;
clear opening must be ≥ one storey (`gate_clear_height`). Checks: `wall_height_span`,
`gate_clear_height` (critical).

---

## 6. How to write the check — test-first, always

**Write the failing test before the check. Watch it fail. Then write the check.**

A check developed against only-correct input will happily be a no-op. This is not
hypothetical: the pre-existing checker verified that piece origins landed on grid multiples.
It passed while walls had 92 m gaps between them.

### The pattern

```python
def test_detached_island_is_reported():
    """A wall+floor pair 40 bays away is a separate building, not part of this one."""
    _, _, base, _ = run_through_assemble(m1_box_house_spec())
    stray = [_piece("floor", (40, 40)), _piece("wall_plain", (40, 40))]
    poisoned = Assembly(placements=list(base.placements) + stray, ...)
    _, report = validate(poisoned)
    islands = [f for f in report.critical if f.check == "freestanding"]
    assert islands, "detached group not reported"
    assert "2 piece" in islands[0].message
```

Three properties every check test must have:

1. **A deliberately broken fixture** containing the defect, built by hand.
2. **An assertion that the check FIRES** — not just that validation fails.
3. **An assertion on the message content** — a check that fires with a useless message
   costs the next person an hour.

### Every failure carries a coordinate

```python
Failure(
    check="coping_attachment",              # stable slug, greppable
    message="coping X sits 12.0 cm clear of the parapet below it",   # what + how much
    world_xyz=_centre(bb_min, bb_max),      # NON-NEGOTIABLE — click-to-frame needs it
    piece_id=p.piece_id,
    critical=True,
)
```

A failure without `world_xyz` cannot be located in the viewport, and "something is wrong
somewhere" is not a bug report.

### Critical vs warning

- **critical** — the building is physically wrong. Export refuses. Use this by default.
- **warning** — a designed condition that resembles a defect (tower arc quarters overlapping
  as an annulus), or **a new check whose hits you have not yet triaged**.

Shipping a new check as a warning is acceptable *once*, with a roadmap entry to triage and
promote it. `roof_penetration` was triaged (M7 / defect 0.3) and is now **critical**.
A warning that stays a warning for more than one milestone is decoration.

---

## 6b. Variation vs continuity

Style and kit **variation** (swap a window family, pitch a roof, restyle a door, pick a
stair kind) is allowed only inside kinds that still satisfy the building's continuity
contracts:

| Contract | Checks | What variation may not break |
|---|---|---|
| Connection | `end_connectivity`, `collinear_gap`, `tower_hall_kiss`, `canopy_attachment`, `roof_valley_join` | Wall runs stay jointed; tower drums still kiss the hall; roofs still meet the envelope |
| Support | `vertical_support` (parapet/battlement wall-head), `roof_bears_on_wall` | A restyled roof or parapet still bears on a wall head — posts alone are not enough |
| Exclusion | `interpenetration`, `roof_penetration` | Swapping a piece must not invent a new overlap class without a designed-pair exemption |
| Stair typology | `stair_typology_match` | Stair kind stays in the class allow-list; never place buttresses as stairs |

### Stair typology policy (`building_class`)

| Class | Default `stair_kind` | Allowed kinds | Placed assets |
|---|---|---|---|
| `house` / `cottage` | `straight` | `straight` only | `stair_straight`, `stair_half` (compact) |
| `industrial` | `wide` | `wide`, `switchback` | `stair_wide`, `stair_switchback` |
| `academy` | `switchback` | `wide`, `switchback` | same |
| `castle` | `switchback` | `wide`, `switchback`, `spiral` | monumental + spiral in towers |
| `tower` | `spiral` | `spiral` | `stair_spiral_quarter` |
| `generic` | `straight` | any continuity-safe supported kind | — |

Continuity-safe filter (`continuity_safe_stair_kinds` / `vary_spec`):
- `spiral` requires a tower volume
- `wide` / `switchback` require a 2×2 well (short footprint side ≥ 4)
- thin castle curtains may fall back to `straight` without a typology critical

**Buttresses are structural trim** (`pae/trim.py`) — never circulation stairs.
`stair_typology_match`: **critical** when a house gets `stair_wide`/`stair_switchback`
or a buttress is tagged `kind=stair`; **warning** when industrial/academy/castle
multi-storey keep only compact `stair_straight` while a 2×2 well is available.

If a variant cannot meet those checks, it is not a legal variant — fix the assemble path
or reject the style choice. Do **not** demote a critical check to green a restyle.

---

## 7. Known gaps in the method

Be honest about these rather than implying coverage:

- **Existence checks barely exist.** Nothing asserts "the spec asked for 3 side entrances
  and 3 were placed". This is the largest structural hole.
- **`stair_exit_clearance` is cell-based** and violates §5.1.
- **Proportion is unverified.** See §9.

---

## 8. Determinism

Same `(spec, seed, db_version)` → byte-identical assembly hash. Two rules:

- **Sort before emitting.** Any pass that builds a list from a set or dict must sort:
  `extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))`
- **Resolve shared resources once, globally.** A courtyard corner cell touches two ranges;
  claiming it per range gave it a duplicate deck and duplicate posts (20 decks for 16 cells).

---

## 9. What validation cannot do

The validator proves a building is **physically coherent**, not that it is **good**. These
pass every check and are still wrong:

- a barn-like roof pitch
- windows too small for their bay
- a cone floating above its drum
- four identical ranges that read as one asset copied four times

There is exactly one mitigation and it is not a check: **render it and look at it.** Golden-
image diffs at a 2 % threshold catch regressions; a human catches the rest. Every milestone
needs a render committed alongside its tests.

Do not add a check that claims to measure beauty. Add a render.

---

## 10. Review checklist

Before merging anything that places geometry:

- [ ] The seven questions (§2) answered in the PR description
- [ ] A deliberately broken fixture exists for each new check, and it failed first
- [ ] Every `Failure` has `world_xyz` and a stable `check` slug
- [ ] No `p.cell` in new reasoning without a justifying comment (§5.1)
- [ ] No hand-rolled offsets (§5.2)
- [ ] Tolerances scale with the piece (§4)
- [ ] New kind fully registered (§3 checklist)
- [ ] Exemptions written in code with reasons
- [ ] Determinism: sorted emission, globally-resolved shared cells
- [ ] Milestone render committed
- [ ] Defect Ledger updated if a bug was found (`Docs/DEFECT_LEDGER.md`)
- [ ] Change documented per `Docs/CHANGE_PROTOCOL.md`

---

## 11. Where to put things

| Concern | File |
|---|---|
| Grid contract, tolerances | `pae/contract.py` |
| Yaw + boundary offsets | `pae/boundary.py` |
| Footprint rules per kind | `pae/primitives/measure.py` |
| All checks | `pae/validate.py` |
| Fortress / bailey compound checks | `pae/fortress_validate.py` (wired from `validate`) |
| Additive placement passes | `pae/trim.py` |
| Site / multi-building | `pae/site.py`, `pae/compound.py` |
| Geometry only | `pae/assemble.py` + `pae/primitives/**` |

**Geometry is created in `assemble.py` and the primitive library. Nowhere else.**

---

## 11b. Fortress / castle compound checks (@CASTLE_FORTRESS_VALIDATE)

Phase 4 / Phase 6 — buildings only (flat-ground fortress / curtain bailey).
Implemented in `pae/fortress_validate.py`, registered by `validate._check_fortress_compound`.
Tests: `pae/tests/unit/test_fortress_validate.py` (broken fixtures first).

| Check | Sev | Class | Fires when | Question answered |
|---|---|---|---|---|
| `fortress_tower_capped` | **critical** | Existence | Fortress compound | ≥ N towers finished with `tower_cap` and/or spire |
| `fortress_gate_exists` | **critical** | Existence | Fortress compound | Gate leaf (`entrance_role_gate` or `wall_gate_arch`) |
| `curtain_battlement_continuity` | **warning** | Connection | Curtain-tagged walls | Wall-walk battlement coverage + gap stub |
| `buttress_outward` | **critical** | Placement | Any buttress present | Bears on a wall; `covered_cells` stay outside interior decks |
| `spire_freestanding` | **critical** | Connection | Any spire/finial | Meets tower_cap/crown/roof or attached spire chain |
| `fortress_grand_approach` | **critical** | Existence | Tag `grand_approach` | Exterior `steps_grand` / `steps_external` / ensemble steps at L0 |
| `gate_passage_clear` | **critical** | Use | Any gate leaf + approach steps | Step AABB must not plug the gate opening / exterior probe |
| `gate_opening_size` | **critical** | Dimension | Any gate leaf | Clear width/height ≥ 0.80 MODULE × 0.85 STOREY (`wall_gate_arch*`) |
| `approach_stair_height_mate` | **critical** | Dimension / Use | Exterior `steps_grand` / `steps_external` at L0 | Top tread Z ≤ gate sill / L0 floor top + TOL — never fixed 175 cm catalog rise |
| `approach_stair_aligned_to_gate` | **critical** | Placement | Gate + approach steps | One flanking pair per arch bay centre — no causeway grid spam |

### Fortress detection

An assembly is a fortress compound when **any** of:

- tag `fortress_compound` / `fortress:*` / `building:fortress*`
  (`build_fortress_compound` stamps `fortress_compound` on every piece via
  `_stamp_fortress_validate_tags`; approach steps also carry `grand_approach`)
- tag `fortress` on a **non-roofline** piece (kit `spire_conical` carries style tag
  `fortress` — that alone must **not** promote a keep)
- interim curtain compound: `west_curtain` **and** `east_curtain`
- massing: `north_curtain` + `gatehouse`

Ordinary houses / M3 keeps without those markers are untouched.

---

## 11c. Arcade / cloister / gallery checks (@ARCH_ARCADE_GALLERY)

Cloister walks and upper galleries overlooking an open court.
Implemented in `pae/arcade_validate.py`, registered by `validate._check_arcade_gallery`.
Tests: `pae/tests/unit/test_arch_arcade_gallery.py` (broken fixtures first).

| Check | Sev | Class | Fires when | Question answered |
|---|---|---|---|---|
| `arcade_pier_bearing` | **critical** | Support | Arcade/cloister trim at L0 | Arch or pier has floor/wall/deck under its footprint |
| `arcade_continuity` | **critical** | Connection | Court-facing arcade run | Adjacent bays touch or share a corner pier |
| `gallery_court_railing` | **critical** | Existence | Upper deck + open court edge | Balustrade on the court drop |

Fires only when the assembly carries `cloister` / `arcade` / `gallery` / `fortress_compound`
language or trim-tagged arcade pieces.

### Config

| Knob | How |
|---|---|
| Min capped towers | Tag `fortress_min_towers:N` (default **2**) |
| Grand approach required | Tag `grand_approach` (or `fortress_grand_approach`) |
| Future BaileySpec | `CastleBaileySpec` / `FortressBaileySpec` may mirror these via getattr |

### Standing rules applied

- Rule **5.1**: curtain / buttress cell sets use `covered_cells`. Tower *identity* for
  caps/spires that `rotates_about_center` uses the drum anchor cell (one tower per cell).
- Rule **5.4**: buttress orientation is measured (AABB bearing + interior exclusion), not
  inferred from neighbour emptiness alone.
- Do **not** demote `aperture_reachability` or `stair_flight_stack` / stair integrity to
  green a fortress restyle.

### Continuity stub honesty

`curtain_battlement_continuity` is a **warning** stub (coverage fraction + max gap in
bays). Full wall-walk circuit / moat-scale enclosure remains roadmap 4.1 open work —
promote to critical after triage against live fortress massing.

---

## 11d. Structure, stacked flights and roof edging (@STRUCTURE_MERGE, Roadmap 10)

Checks owed by Roadmap Phase 10. Defects in `DEFECT_LEDGER.md` §D3. Each needs the usual
`# WHY` comment naming the defect, and a poison test proving it can fire (§6).

| check | rule | defect it prevents |
|---|---|---|
| `structure_contiguous` | every mass tagged into a structure touches at least one other member, transitively | a declared structure whose parts do not actually meet |
| `structure_party_wall_open` | no two exterior walls stand back to back inside one structure | D3-2 — walls between rooms of what should be one building |
| `structure_masses_reachable` | every mass of a structure is walkable from every other | a "connected" building you cannot cross |
| `structure_single_stair_core` | a structure does not carry one stair core per mass | D3-1 — three staircases in one building |
| `flight_footprint_distinct` | no two flights of one core share a footprint on consecutive levels | D3-3 — flights stacked directly on top of each other |
| `roof_edging_exclusive` | no roof edge carries two edging styles | D3-4 — parapet and crenellation overlapping |
| `wall_face_exclusive` | no coplanar duplicate wall skin on one court bay when `wall_arcade` is present | D3-9 — cloister plain wall + arcade stacked on same face |
| `storey_datum_consistent` | headroom and stair rise measured against the **volume's own** datum, not `level * STOREY_CM` | Roadmap 10.6 — silently wrong once datums vary |

**Implemented (critical):** `stair_flight_stack` — `test_stair_flight_offset.py`. `roof_edging_exclusive` — `test_roof_edging_exclusive.py`. Structure identity (`structure_contiguous`, `structure_party_wall_open`, `structure_masses_reachable`, `structure_single_stair_core`) — `pae/structure_identity.py`, wired in `validate.py` via `_check_structure_identity`; green path `test_structure_identity.py::test_fortress_compound_green_path_structure_identity`. `freestanding` partition key prefers `structure:` when declared (T-102, same commit). `storey_datum_consistent` — `pae/storey_datum_validate.py` + `test_storey_datum_consistent.py`.

**Started (no behaviour change):** `contract.storey_datum_z_cm` + `placement_volume_offset_z_cm` — all production datum-Z routes through accessor; uniform grid unchanged until assemble stamps volume tags. Tests: `test_validate_contract.py::test_storey_datum_accessor_matches_legacy`.

**Missing (producer / spec):** assemble volume-aware floor placement (T-111), stair rise across two datums (T-112), mezzanine deck (T-113); feature smoke (Roadmap 10.7).

### The partition-key trap — read before touching `freestanding`

`_check_structural_islands` partitions on `structure:` when declared, else `building:`.
That was deliberate: without per-building partitioning a street of six houses reported five
freestanding groups and the check became noise. Fortress bailey declares one
`structure:fortress_bailey` for all ranges — freestanding then checks connectivity within
that structure, not per-range.

### The reachability gap this exposes

D3-3, D3-4 and D3-5 were all **correct code that never ran**: a mechanism gated to the wrong
stair kinds, a repair reached from one call site, two producers unaware of each other. Every
check in this handbook asks *"is the output right?"* — none asks *"did this feature run at
all?"*

That is a genuine hole in the method, and it is not fixed by adding more validators. The
cheapest cover is a **feature smoke test** per showcase build: assert that what the spec asked
for appears in the output at all. It is not validation and does not belong in `validate.py` —
put it beside the showcase tests. See Roadmap 10.7.

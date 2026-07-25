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
| 1 | **Existence** | Did the thing that was asked for actually get placed? | *(gap — see §7)* |
| 2 | **Dimension** | Does the piece match the grid contract? | `footprint_contract_errors` |
| 3 | **Placement** | Is it in the cell/orientation it was meant to be? | `run_fit` |
| 4 | **Connection** | Does it touch what it must touch? | `end_connectivity`, `collinear_gap`, `canopy_attachment` |
| 5 | **Support** | Is something underneath it? | `vertical_support` |
| 6 | **Coherence** | Is it part of one building, or its own island? | `freestanding` |
| 7 | **Exclusion** | Does it avoid what it must avoid? | `interpenetration`, `roof_penetration` |
| 8 | **Containment** | Is the envelope sealed, floored, covered? | `enclosure`, `floor_coverage` |
| 9 | **Use** | Can a person reach it, enter it, walk it, leave it? | `stair_reachability`, `stair_exit_clearance`, `classroom_corridor`, `aperture_sanity` |

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
(site surfaces are not part of the building; a boundary fence is *meant* to stand alone),
add it to the named exemption set with a comment giving the reason:

```python
ISLAND_EXEMPT_KINDS = frozenset({"surface"})
ISLAND_EXEMPT_TAGS = frozenset({"site", "boundary"})
```

An exemption that is not written down becomes a bug the next person has to rediscover.

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

**5.3 Never trust a declared size. Measure the mesh.**

**5.4 Never derive a face from cell neighbours when the piece's own position knows better.**
`_buttresses` chose a face by "this neighbour is not interior", which says nothing about
where the wall actually *sits* — a west buttress ended up braced against air next to a wall
standing on the cell's east boundary. Derive the face from the wall's AABB relative to its
cell bounds.

**5.5 All dimensions come from `pae/contract.py`.** CI greps for `400.0`, `350.0`, `60.0`,
`30.0`. Fractions of the contract are fine; literals are not.

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
promote it. `roof_penetration` is currently in this state. A warning that stays a warning
for more than one milestone is decoration.

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
| Additive placement passes | `pae/trim.py` |
| Site / multi-building | `pae/site.py`, `pae/compound.py` |
| Geometry only | `pae/assemble.py` + `pae/primitives/**` |

**Geometry is created in `assemble.py` and the primitive library. Nowhere else.**

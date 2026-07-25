# Change Protocol

**How every agent records what it changed, why, and what it learned.**

Multiple agents work this repo concurrently. Without a protocol the failure mode is not
merge conflicts — it is *silent divergence*: two agents fix the same bug differently, an
agent reverts work it did not know existed, or a defect is rediscovered from scratch three
weeks later. All three have already happened here.

---

## 0. Non-negotiables

1. **Commit only files you own or changed.** Never `git add -A` in a shared tree. Another
   agent's in-flight edits are not yours to commit, and checking out files you do not own
   destroys uncommitted work. *(This happened: a compound-layout rewrite was wiped and had
   to be redone from scratch.)*
2. **Claim before you edit.** Post a `>>> TRIGGER @TAG` line on `AGENT_SYNC.md` naming the
   files you will touch. If another lane already claims them, coordinate.
3. **Never leave the suite red without saying so.** If you leave a failing test, the commit
   message and the sync board must both say which test, why, and whether it is a true
   positive.
4. **Every bug you find goes in `Docs/DEFECT_LEDGER.md`.** Even if you fixed it in the same
   commit. Especially then.

---

### Exercise it through the add-on

A change is not verified until it has been run the way a user runs it: through an
add-on operator, with the Validate panel showing the result. Calling `pae.*` functions
directly from a console is fine while developing and **not** sufficient as evidence.

This is not ceremony. Two compound builders shipped for weeks ending in
`return sited, layout, Report.from_failures([])` — a hardcoded empty report — so they
announced "0 critical" regardless of what they built. Every agent working from those
reports believed the geometry was clean. Nobody caught it because nobody ran the path
the user runs. `validate()` on the same assemblies found 6 criticals and 517 warnings,
including walls with no floor beneath them and a structure owning three separate stair
cores — checks that already existed and whose output was being discarded.

If a change cannot be exercised through an operator, that is a finding about the
add-on. Add the operator; do not route around it.

## 1. The commit message

Commit messages are the primary record. They are read far more often than any doc.

```
<type>(<area>): <what changed, in plain words>

<WHY — the observable problem, not the code>

<WHAT WAS FOUND — each defect, root cause, fix>

<VERIFICATION — counts, test names, render path>
```

Types: `feat` · `fix` · `refactor` · `docs` · `test` · `chore`

### Rules that make them useful

- **Lead with the symptom as observed, not the code change.** "Balcony decks 4 m from the
  wall they serve" beats "adjust epsilon in covered_cells". The symptom is what the next
  person will search for.
- **State the root cause in one sentence.** If you cannot, you have not found it yet — you
  have found a change that makes the symptom go away.
- **Quote real numbers.** "20 decks for 16 cells", "3.8 rails per cell", "7 of 16 roofs
  touch nothing". Numbers are how the next person confirms a regression.
- **Credit the reporter.** `User: "it's too small by 1 entire unit"` — user observations are
  the highest-value signal in this project and should be traceable.
- **Say what you did NOT do**, and why.

### Example

```
fix(trim): covered_cells off-by-one inflated every range by a cell

User: "the west service floor is not connected to the west service wall ...
it's too small by 1 entire unit." Correct, and the cause was one line.

covered_cells inset each placement by a flat MODULE/4 = 100 cm before
rounding to cells. That is LARGER THAN A WALL (60 cm), so a wall flush
against the east boundary of cell 9 was inset past the boundary and
reported as occupying cell 10.

Consequences, none of which any check caught:
  * balcony decks landed one full bay (4 m) from the wall they serve
  * courtyard detection saw ranges as bigger than they are

Fix: inset is now min(MODULE/4, half the piece's extent) per axis.

Tests: covered_cells keeps a boundary-flush wall in its own cell; every
balcony deck in the compound touches a wall.
405 passed, 1 failing (detached random-spec tower, pre-existing).
```

---

## 2. The sync board (`AGENT_SYNC.md`)

The board is the *live* state. Commits are history; the board is now.

```
>>> TRIGGER @TAG — <scope>. Owns: <files>. <constraints>
>>> DONE @TAG — <what shipped>. <counts>. <gaps left>.
>>> BLOCKED @TAG — <what blocks it>. <who/what must move first>.
```

Rules:

- **`TRIGGER` before the first edit, `DONE` before handing off.** A lane with no `DONE` is
  assumed still live and its files are off-limits.
- **`DONE` must state what is NOT done.** "Pitched roof is a span AABB proxy, not per-bay
  gable mesh" saved a later agent from assuming coverage.
- **Report counts**: tests passed, placements, critical/warning totals.
- **If you touch a shared file** (`validate.py`, `contract.py`, `boundary.py`,
  `assemble.py`), say so explicitly — those are the collision-prone ones.

---

## 3. Docs that must be updated with the change

| If you… | Update |
|---|---|
| Add/change a check | `Docs/VALIDATION_HANDBOOK.md` §1 table |
| Find any bug | `Docs/DEFECT_LEDGER.md` |
| Add a piece or kind | `Docs/PRIMITIVE_MEASUREMENTS.md` (regenerate), §3 checklist |
| Change the grid contract or offsets | `Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md` §2 |
| Complete or discover roadmap work | `Docs/CASTLE_SCHOOL_ROADMAP.md` |
| Change the manifest schema | `Docs/UE_MANIFEST_CONSUMER.md` |

Regenerate the measurement table with:

```bash
python -c "from pae.primitives.catalog import all_descriptors; from pae.primitives.measure import measurement_table_markdown; from pathlib import Path; Path('Docs/PRIMITIVE_MEASUREMENTS.md').write_text(measurement_table_markdown(all_descriptors()), encoding='utf-8')"
```

---

## 4. Decision records

When you make a choice that a future agent might reasonably reverse, record it — in the
commit body if small, in the module docstring if structural.

Module docstrings in this repo carry a **`WHY THIS EXISTS`** section. That convention is
load-bearing: it is how `trim.py` explains that it is additive and lives outside
`assemble.py` deliberately, so nobody "tidies" it back in. Keep it.

Record: the choice, the alternative rejected, and the reason. Example, from `site.py`:

> Courtyard detection is a four-direction ray test, **not** a flood fill. A quad is four
> ranges with gaps at the corners, and a flood leaks straight out through them and reports
> no courtyard at all — which is exactly what the first version did.

---

## 5. Verification evidence

A change that places geometry is not done until there is a **render**. Structural checks
pass buildings that look wrong — that is the entire history of this project.

- Write renders to `Saved/Screenshots/<milestone>_<what>.png`
- Name the file in the commit message
- Re-render after *any* placement change, not only when you expect a visual difference

Measuring geometry in Blender: call `bpy.context.view_layer.update()` and use
`obj.evaluated_get(depsgraph)` before reading bounds. Stale matrices read 28× wrong and will
frame your camera at the wrong scale. (Ledger F-5.)

---

## 6. Handling a red suite

1. Determine whether it is a **true positive** (your new check found a real defect) or a
   **regression** (you broke something).
2. True positive you cannot fix in scope: leave it red, add a Ledger entry, add a roadmap
   defect, and say so in the commit **and** on the sync board. Never exempt a real defect to
   get green.
3. Regression: fix it or revert. Do not commit on top of it.
4. Failing tests owned by another lane: say so, do not "fix" their file.

Current standing exception: `test_random_specs_validate_ok` fails on a 26-piece detached
tower — a true positive, roadmap defect 0.1, Ledger C-5.

---

## 7. Session close-out

Before you stop, post to `AGENT_SYNC.md`:

- `DONE`/`BLOCKED` for every lane you opened
- Suite counts (`N passed, M failed`), naming any failure and its status
- Files left modified but uncommitted, and why
- Anything you learned that is not yet in the Ledger or Handbook

An agent that stops without a close-out has left the next one to reverse-engineer the state
from `git diff`.

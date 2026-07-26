# Design: the tower drum as a real enclosure

## Scalable shaft contract

`TowerSpec.radius_bays` is the physical outer radius/half-width in module units,
not the logical footprint-cell width. It accepts continuous values from `0.5`
(a four-metre-diameter stair turret) through `16`. The plan keeps one attachment
anchor cell; assembly resolves the actual centre so the scaled shell still kisses
the host wall.

`shape` selects `round` or `square`. `cap_style` selects `auto`, `flat`, `cone`,
or `square_spire`, and `spire_height_storeys` controls cap height independently
from the shaft storey count. Spiral tread width is clamped to the measured clear
bore. Radius-1.25+ towers receive supported landing/room bands around the core;
smaller shafts remain stair-only. Conical and square/pyramidal spires are roofs, not
battlement decks, so rampart-top validation does not invent an inaccessible
platform beneath them.

`stair_spiral_quarter.size_cm.x/y` controls the authored outer radius (the mesh
is centered), not a diameter. Every climb uses four quarters ordered from the
tower-entry yaw. The fixed-size newel is conditional: tight stairs that meet it
retain it; an open-well stair with a separated inner edge omits the pole.
`floor_hole` remains in the assembly as a validated deck cutter, but builders do
not instance its legacy frame mesh.

> Detail spec for Stage E of `Docs/MASTER_PLAN.md`.

**Status:** scalable shafts/interiors implemented; true curved door/window cuts
remain open. Foundations landed (`pae/drum.py`,
`pae/tests/unit/test_drum.py`). Implementation handed to the swarm.

**Lane:** `@DRUM_ENCLOSURE`

---

## 1. What is wrong, measured

From a render of `street_scene` (`gate_tower`), and reproduced numerically by
`scratchpad/diag3.py`:

| symptom | measured |
|---|---|
| rectangular perimeter walls running through the drum | **15 walls, 2 floors** |
| doorways into the drum | **1**, and it is incidental — not a designed entry |
| helix height vs drum height | reaches levels **0–1 of 0–3** |
| windows opening into the drum's interior | **6** |
| buttresses planted on the round face | 3 → **0** *(fixed, commit `5de4b0d`)* |

User's words: *"the spire is wrapping through the building… there's no entrances,
there's no exits. The staircase doesn't go the whole way up. There's windows placed in
a spot that they would be inside the spire."*

## 2. Root cause — one cause, five symptoms

**A tower cell is claimed by two enclosures at once.** The solver marks the cell as
belonging to a tower volume, and the assembler then emits *both*:

- the drum's own arcs (`kind="tower_arc"`), and
- the body's rectangular perimeter wall run, because `_emit_face_walls` in
  `pae/assemble.py` walks the footprint edge without asking whether a tower already
  encloses that cell.

Everything else follows. The straight wall stands inside the round tower. Window
selection runs over those perimeter walls, so it glazes bays that open into the drum.
The helix's exit check finds a wall/deck above it and refuses to build past level 1.

## 3. The trap — why the obvious fix broke seven tests

The one-line fix ("skip perimeter walls on tower cells") was tried and **reverted**. It
broke `test_school_academy` (×2), `test_export_manifest_cli` (×3) and
`test_validate_polish` (×2).

Reason: **not every tower is outboard.**

- **Outboard** — a turret bolted to a corner, its cells *outside* the body footprint.
  The drum is the entire enclosure. Suppressing the box wall is correct.
- **Inboard** — a stair tower swallowed by the plan, its cells *inside* the footprint.
  The perimeter wall there is still the building's outer skin. Suppressing it punches a
  hole in the elevation.

`school_academy_spec` and the m3 milestone both have inboard towers. **Always ask
`drum.outboard_drum_cells(assembly)`, never `drum.drum_cells(assembly)`, before
suppressing anything.** This is the single most important sentence in this document.

## 4. Foundations already provided

`pae/drum.py` — pure, no placement, safe to call from any stage:

| function | returns |
|---|---|
| `drum_cells(assembly)` | every cell occupied by a drum, any level |
| `body_cells(assembly)` | cells of the non-tower mass |
| `footprint_bbox(cells)` | `(x0,y0,x1,y1)` inclusive, or `None` |
| `outboard_drum_cells(assembly)` | **the safe suppression set** |
| `drum_levels(assembly)` | `cell -> [levels]` of the drum SHAFT (arcs only, not the cap) |
| `has_entry(assembly, cell)` | is there a `tower_entry`-tagged door serving this cell |

`pae/tests/unit/test_drum.py` locks the outboard/inboard distinction, including an
explicit regression test that the school's inboard tower yields **no** outboard cells.

## 5. Work items

### T-D1 — suppress the box wall on outboard drum cells
`pae/assemble.py`, the face-wall emitter. Skip a cell when it is in
`outboard_drum_cells`. Derive the set once per assembly, not per face.

*Caution:* the assembler builds placements incrementally, so `outboard_drum_cells`
(which reads a finished assembly) cannot be called mid-build. Compute the equivalent
from the floor plan: tower volume cells minus the body volume's footprint bbox. Keep
the predicate in `pae/drum.py` next to its sibling so the two cannot drift.

**Check owed:** no `kind="wall"` piece whose asset is not a drum arc may share a cell
with a `tower_arc` at the same level. Name it `drum_exclusivity`.

### T-D2 — a designed entry into the drum
Every drum with a stair needs a doorway from the body. `pae/tower_entry.py` already has
`place_tower_entry_doors` and `TOWER_ENTRY_TAG`; it is not reached for trim-added
helixes.

- ground level, on the arc facing the body
- tagged `TOWER_ENTRY_TAG` so `validate._check_tower_entry_door` is satisfied
- **this closes the live failure `test_showcase[library_tower]`**

**Check owed:** already exists — `_check_tower_entry_door`. Do not weaken it.

### T-D3 — no windows into the drum
Window selection must not glaze a bay whose exterior side is a drum cell. After T-D1
most of these disappear (the walls stop existing). Verify the remaining 6 reach zero.

**Check owed:** `aperture_faces_open_air` — an opening's exterior cell must not be
enclosed by another volume.

### T-D4 — helix climbs the full drum
`_tower_spiral_stairs` in `pae/trim.py` stops early because the exit check finds a
solid pad. Compare against `drum_levels(assembly)[cell]` and require the helix to reach
the top shaft level. Keep the three constraints already in the code — they were each
added after a real defect:
1. stop below the cap, or the top flight climbs into the roof
2. drop any quarter with less than `210 cm` under a roof slope
3. skip a level whose exit is a **1×1 pad** — mirrors `validate._is_module_solid_floor`

**Check owed:** `drum_stair_reaches_top` — for every drum with a stair, the helix's
maximum level equals `max(drum_levels[cell])`.

### T-D5 — hatch onto the top deck
The tower-top deck is a spanning slab with no opening. Punch a `floor_hole` at the
helix cells at `stair.level + 1` (the level `stair_exit_clearance` reads), then rail
the opening leaving the arrival edge free — `_stair_landing_edges` already does this
for straight runs.

### T-D6 — parapet ring on the top deck
The user asked for this earlier: *"at the top there needs to be adjustments to accept an
area to walk out on with circular rails."* Additive, lowest priority.

## 6. Acceptance — copy these numbers

Run `scratchpad/diag3.py`. Ship when:

```
PIECES INTERPENETRATING THE DRUM: {}          # from {'wall': 15, 'floor': 2}
DOORS touching a drum cell:       >= 1 tagged tower_entry per drum
HELIX COVERAGE:                   helix levels == drum levels, every drum
WINDOWS inside a drum cell:       0            # from 6
BUTTRESSES in a drum cell:        0            # already there
```

Plus: `test_showcase[library_tower]` green, and `test_school_academy`,
`test_export_manifest_cli`, `test_validate_polish` **still** green — those are the
canaries for the inboard case.

## 7. Do not

- Do not weaken `stair_exit_clearance`, `_check_tower_entry_door` or
  `_is_module_solid_floor` to get green. They are all currently reporting real defects.
- Do not make `trim` delete placements. Trim is additive by contract; wall suppression
  belongs in `assemble`.
- Do not treat `tower_cap` as shaft when computing height (see `drum_levels`).

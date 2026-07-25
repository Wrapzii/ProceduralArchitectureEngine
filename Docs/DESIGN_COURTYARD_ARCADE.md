# Design: the courtyard arcade — a walkable arched gallery

> Detail spec for Stage G/H of `Docs/MASTER_PLAN.md`.

**Status:** designed, not implemented. Nothing of this exists yet.

**Lane:** `@ARCADE`

Reference supplied by the user: an anime school interior — a long hall with a row of
tall arched openings down one side, light raking across a polished floor, the far end
closed by a doorcase. And an exterior: a quadrangle where the ranges facing the court
are arcaded at ground level.

> *"the first image is showing like a long hallway with arches … inside of my main goal
> building. I want stuff like that inside of the building facing the courtyard."*

---

## 1. What this is, precisely

An **arcade** is a *roofed, walkable circulation space* running along the inside face of
a range, open to a courtyard through a rhythm of arches.

It is **not** any of these, and confusing them is the main design risk:

| existing thing | what it actually is | why it is not this |
|---|---|---|
| `_colonnade` in `trim.py` | free-standing arches outside a courtyard face | no floor, no roof, not walkable, not enclosed |
| `wall_arcade` | a wall with an arch cut into it | a *wall*, solid at the ends — the boundary, not the space |
| `arch_freestanding` | two piers + arch, open both sides | the opening, not the gallery |

The arcade is a **room** whose courtyard-side wall happens to be a run of arches. That
framing is the whole design: build it as a space, not as decoration.

## 2. Anatomy

Per bay, from the court inward:

```
  courtyard
     │
     ├─ ARCH BAY        wall_arcade_round | wall_arcade_gothic   (the opening)
     ├─ WALK            floor deck, 1 bay deep, walkable         (the space)
     ├─ CEILING/VAULT   deck above, or the storey floor          (the cover)
     └─ INNER WALL      the range's real enclosing wall, with doors into rooms
```

Depth is **1 bay** by default (400 cm) — enough to walk two abreast, and it keeps the
arcade on the module grid so nothing needs special-casing.

## 3. Where it goes

Reuse, do not reinvent, the courtyard detector: `pae/site.py::_courtyard_cells` (a
four-direction ray test, deliberately not a flood fill — it must not leak out of an
open corner).

A range face qualifies when:
1. it is an **interior-facing** face — the neighbouring cell is courtyard, and
2. the range is at least 2 bays deep, so giving 1 bay to the walk leaves usable rooms.

`banding.band_faces_of` already derives which way each wall faces from its own
position; use it rather than deriving faces from cell neighbours, which is the mistake
that historically braced buttresses against thin air.

## 4. The spec object

Put this in a new `pae/arcade.py`. Follow `BandingSpec` / `TrimOptions` house style:
fractions and **bays**, never raw centimetres.

```python
@dataclass(frozen=True)
class ArcadeSpec:
    """A walkable arched gallery along courtyard-facing ranges."""

    depth_bays: int = 1                     # walk depth
    levels: Tuple[int, ...] = (0,)          # ground only by default
    arch_piece: str = "wall_arcade_round"   # or wall_arcade_gothic
    pier_piece: str = "pier_square"         # between bays, if the arch needs it
    deck_piece: str = "floor"
    vault: bool = False                     # ribbed ceiling over the walk (later)
    rhythm_bays: int = 1                    # 1 = every bay is an arch
    faces: Tuple[str, ...] = ()             # empty = every courtyard-facing run
    corner_pier: bool = True                # solid pier where two runs meet
```

Entry point, matching the shape of every other stage:

```python
def arcade(assembly, spec=None) -> Tuple[Assembly, Report]:
    """Additive pass. Returns a new assembly; the input is not mutated."""
```

Pipeline position: **after `trim`, before `banding`**. Trim must not put railings on
the arcade's court edge (the arches are the guarding), and banding must see the arcade's
arch wall so courses run across it correctly.

## 5. The corner problem — decide this before writing code

Where two arcade runs meet at a courtyard corner, the naive result is two arch bays
overlapping in one cell, each half-inside the other. Three options; **take the third**:

1. Leave the corner cell empty — reads as a gap, breaks the walk.
2. Let both runs claim it — interpenetration, and `validate` will say so.
3. **A solid corner pier.** The cell gets a pier, both runs stop one bay short of it,
   the walk turns around it. This is what real cloisters do, and it is the only one of
   the three that produces a continuous walkable loop.

`corner_pier=True` in the spec exists for this.

## 6. Checks owed

Per the Validation Handbook's seven questions. Each needs a `# WHY` comment naming the
defect it prevents, and a poison test proving it can fire.

| check | rule |
|---|---|
| `arcade_walkable` | the walk is continuous — every arcade cell reaches every other without leaving arcade or courtyard-adjacent deck |
| `arcade_covered` | every arcade cell has a deck or roof above within one storey. An uncovered "gallery" is a strip of pavement |
| `arcade_attached` | the arch run's back face is flush with the range's own wall line; the walk deck touches the range floor |
| `arcade_headroom` | ≥ 210 cm clear under the arch head and under the ceiling — same constant as `validate.HEADROOM_CLEARANCE_CM` |
| `arcade_no_double_claim` | no cell is both arcade walk and an interior room |
| `arcade_reaches_a_door` | the walk connects to at least one door into the range. A gallery serving nothing is scenery |

**Register the new kind.** Anything new must be considered by the existing checks:
decide explicitly whether arcade pieces participate in `vertical_support`,
`freestanding`, `enclosure` and `floor_coverage`, and write the decision **in code with
its reason** (as `banding.py` does for its `vertical_support` exemption). An arch run is
a wall and should participate normally; the walk deck is a floor and should participate
normally. Expect **no** exemptions here — if one seems necessary, that is a signal the
geometry is wrong, not the check.

## 7. Build order

1. `ArcadeSpec` + face selection, returning cells only. No placement. Test the geometry.
2. Arch run + walk deck on one straight range. One face, one level.
3. The corner pier, then the full loop around a quadrangle.
4. `arcade_walkable` + `arcade_covered` first — they catch the most.
5. Remaining checks, each with its poison test.
6. Vaulting (`vault=True`) last. It is the only part that is pure appearance.

## 8. Acceptance

Add an `arcade_court` entry to `pae/showcase.py`: a four-range quadrangle, arcaded on
all four inner faces, 0 critical. It should be possible to walk the full loop, in and
out of the ranges, without leaving the deck — which is exactly what `arcade_walkable`
asserts.

The interior reference (long hall, arches down one side) falls out of the same code
with `faces` restricted to a single run.

## 9. Related, deliberately out of scope

`Docs/CASTLE_SCHOOL_ROADMAP.md` §9.5 (T-023..T-028) covers a building that **spans** a
route — an archway over a street with rooms above. That needs a `passage` cell role and
role-aware exemptions in `enclosure` and `floor_coverage`. It shares vocabulary with the
arcade but is a different problem. Do not merge the two lanes.

# PAE — School / academy readiness (honest)

Target: a **giant multi-wing school** (courtyard, several storeys, many stairwells,
classrooms, UE walkable).

## Milestone spine (spec §11)

| Milestone | Status | School relevance |
|---|---|---|
| M1 box house | Done (pipeline + validate) | Spine only |
| M2 two storeys + stairs | Done (straight + floor_hole + exit clearance) | Core vertical circulation |
| M3 roofs + towers | Done (pitched + tower drum) | Hall / chapel / stair tower |
| M4 courtyard L/U | Done (multi-wing) | School plan shape |
| M5 dynamic assets | Demo seed done | Props / furniture later |
| M6 UE manifest | Dry-run + spawn/bind tables | **Not live PIE yet** |
| M7 school academy | Done (massing → interiors → trim → gallery) | Programmed academy shell |

## What landed (school expansion)

| Wave | Status | Notes |
|---|---|---|
| 1 Program massing | Done | `school_academy_spec()` / footprint `kind=school` → hall, classroom wings, admin, courtyard |
| 2 Switchback stairwells | Done | Solver emits 2×2 STAIR; assemble requires full 2×2; exit holes on upper decks |
| 3 Interiors | Done | `CORRIDOR` + `CLASSROOM` + partition doors; `classroom_corridor` validate |
| 4 Facade + trim | Done | Style tags → `wall_window_lancet` / gothic doors; `run_through_validate_trim` |
| 5 Campus proof | Done | Gallery `PAE_School`, export milestone `school`, headless dry-run |

## Stair kit

| Asset | Role |
|---|---|
| `stair_straight` | Corridor / hall run (2×1) |
| `stair_half` + `stair_landing` | Compose dog-legs |
| `stair_switchback` | Classic school stairwell (2×2 U) — **default for academy** |
| `stair_wide` | Monumental entrance (2×2) |
| `stair_spiral_quarter` | Helical tower stair (showcase / kit) |

Fail-closed: `stair_exit_clearance` refuses ceiling/wall-plugged tops.

## Still missing for a *finished* giant school

1. **UE PIE walkthrough** — M6 tables + school manifest dry-run exist; no verified walkable school in Unreal yet.
2. **Megascans / dress** — still greybox kit (intentional).
3. **Multi-stairwell egress sizing** — one switchback well is proven; campus-scale egress counts are not.

## Bottom line

**Ready to generate a validated gothic academy shell** with named volumes, switchback
stairwell, corridor classrooms, style-driven facade pieces, and trim.
**Not ready to claim a finished giant school in UE.** Next lever: live UE consumer + PIE.

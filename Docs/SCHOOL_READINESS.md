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

WP-1…WP-9 pipeline modules are in place. That is **not** the same as a finished school.

## Stair kit (this pass)

| Asset | Role |
|---|---|
| `stair_straight` | Corridor / hall run (2×1) |
| `stair_half` + `stair_landing` | Compose dog-legs |
| `stair_switchback` | Classic school stairwell (2×2 U) |
| `stair_wide` | Monumental entrance (2×2) |
| `stair_spiral_quarter` | Helical tower stair (4×/storey) |

Fail-closed: `stair_exit_clearance` refuses ceiling/wall-plugged tops.

## Still missing for a giant school

1. **Programmed massing** — classroom wings, gym, cafeteria, admin as named volumes (not just L/U boxes).
2. **Corridor graph** — double-loaded halls, fire egress, stairwell count vs occupancy.
3. **Switchback/wide plan cells** — assemble can emit the mesh, but the planner still defaults to a 2-cell straight run; need 2×2 STAIR/VOID blocks in `plan.py`.
4. **Interior partitions** — classrooms as enclosed rooms with doors (today: open wings).
5. **UE PIE proof** — M6 tables exist; no verified walkable school in Unreal yet.
6. **Visual bar** — still greybox kit; Megascans/dress is optional later.

## Bottom line

**Ready to generate large multi-wing greybox shells with real stair styles and validation.**
**Not ready to claim a finished giant school.** Next lever: school footprint factory + 2×2 stairwell planning + corridor rooms.

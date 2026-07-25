# Style & Detail Roadmap — wizarding school, medieval / anime-fantasy

Companion to `Docs/CASTLE_SCHOOL_ROADMAP.md`. That document covers **structure** — what the
engine must be able to build. This one covers **style and detail** — what makes it read as
a magic school rather than a shed with a lid.

**Target read:** steep pointed roofs, towers and spires, timber-framed and stone ranges,
grand halls with sweeping staircases, warm interior lamplight, weathered surfaces with
variation, a courtyard you want to walk into. Medieval bones, anime-fantasy legibility:
strong silhouette, clear panelling, exaggerated verticality.

**Answering the question directly: yes, angled roofs already work.** `roof_pitched_slope`
and `roof_gable_infill` are real geometry with proper gable ends, used by milestone M3. The
compound renders flat because its ranges *specify* `RoofSpec(kind="flat")`. That is a spec
default, not a limitation — see §B.

Every objective is numbered `S-nnn` for cross-reference from commits and the sync board.
Per `Docs/VALIDATION_HANDBOOK.md`, each carries the check it owes. Objectives marked
**[V]** need a new validator, **[R]** need a render as evidence, **[UE]** affect export.

---

## A. Style system — the thing that makes everything else adjustable

Currently a "style" is a small JSON with a roof pitch and a window tag. It needs to become
the switchboard for everything below.

| # | Objective | Check owed |
|---|---|---|
| S-001 | `StylePack` dataclass replacing loose JSON: geometry, proportion, material and detail sections | schema validation, unknown-key rejection |
| S-002 | Style resolution order: engine default → style pack → per-range override → per-piece override | resolution is deterministic and logged |
| S-003 | Every hard-coded fraction in `primitives/` becomes a style field with the current value as default | CI grep for bare fractions outside style packs |
| S-004 | Style packs: `wizard_academy`, `stone_keep`, `timber_wealden`, `cloister_abbey`, `dormitory_range` | each builds M1–M4 without critical defects **[R]** |
| S-005 | Style inheritance — `wizard_academy extends cloister_abbey` | cycle detection |
| S-006 | Per-range style in the compound so ranges differ by *style*, not just trim | ranges produce distinct silhouettes **[R]** |
| S-007 | Style-driven piece substitution tables (this style's "window" means `window_lancet`) | every referenced piece exists in the catalog |
| S-008 | Proportion profile per style: storey height, wall thickness, roof pitch, window ratio | proportion sanity **[V]** |
| S-009 | Style preview sheet — one render per style, same spec **[R]** | golden-image diff |
| S-010 | Seeded style variation: same style, different building, still recognisably that style | determinism per `(style, seed)` |

## B. Roofs — the single biggest silhouette lever

| # | Objective | Check owed |
|---|---|---|
| ~~S-011~~ | **DONE (RM_ROOF_ADV + RM_STYLE_ADV):** `RoofHints` / `resolve_roof_pitch` / `is_steep_silhouette_style`; `wizard_academy` steep pack; pitched + hip height from `spec.pitch ≥ 1.6`. Tests: `test_hip_roof.py`, `test_style_pack.py`. | pitch within style range ✓ |
| ~~S-012~~ | **DONE (RM_ROOF_ADV):** `roof_hip` four-slope mesh + per-wing `place_hip_roof`; validate `critical=[]` on milestones. Gaps: watertight envelope **[V]** (S-021). Tests: `test_hip_roof.py`. | watertight envelope **[V]** (stub) |
| S-013 | Half-hip / jerkinhead | " |
| S-014 | Mansard | " |
| S-015 | Gambrel | " |
| S-016 | Catslide / sweeping asymmetric roof to a lower eaves on one side | eaves height per side |
| S-017 | Conical roof over round towers, meeting the drum exactly | canopy attachment **[V]** |
| S-018 | Polygonal (octagonal) roof over polygonal towers | " |
| ~~S-019~~ | **DONE greybox (RM_ROOF_ADV):** `roof_valley` V-trough stubs on L/U wing abutments (pitched per-wing). Gaps: diagonal valley merge (S-021), ridge as real edge geom (S-020). Tests: `test_hip_roof.py`. | no roof interpenetration **[V]** (AABB-only) |
| S-020 | Hips and ridges as real geometry, not implied by adjacent slabs | ridge continuity **[V]** |
| S-021 | Roof over irregular (L/U/courtyard) plans as ONE resolved surface | watertight envelope |
| S-022 | Multiple roof heights per building — tall hall, lower service range | roof step attachment |
| S-023 | Tiled / slated / thatched / lead surface variants | material only |
| S-024 | Thatch profile with rolled ridge and deep eaves (the Wealden reference) **[R]** | eaves overhang range |
| S-025 | Roof lanterns and glazed ridge sections | aperture sanity on roof planes |
| S-026 | Bellcote / bell turret on a ridge | roofline attachment |
| S-027 | Weathervanes and finials on every apex | apex occupancy — no two at one apex |
| S-028 | Crow-stepped gables | gable infill continuity |
| S-029 | Barge boards and decorative verges | band attachment |
| S-030 | Snow guards / eaves detail as decorative bands | band attachment |
| S-031 | Roof pitch responds to span automatically within style limits | proportion sanity **[V]** |
| S-032 | Dormers placed by ROOM NEED (rooms that need light) rather than index rhythm | every attic room has a light source |

## C. Towers, spires, verticality

| # | Objective | Check owed |
|---|---|---|
| S-033 | Towers integrated into ranges rather than bolted on — **open defect, Ledger C-5** | freestanding **[V]** |
| S-034 | Tower heights driven by style, not fixed | proportion |
| S-035 | Tapered / battered tower shafts | — |
| S-036 | Square, round, octagonal, and D-shaped tower plans | footprint contract |
| S-037 | Stair turrets — a small tower containing only a spiral stair | stair reachability |
| S-038 | Machicolations under a tower crown | roofline attachment |
| S-039 | Multi-stage towers with string courses between stages | band attachment |
| S-040 | Clock stage / bell stage as a named tower level | — |
| S-041 | Spire lucarnes (little dormers on a spire) | roofline attachment |
| S-042 | Crockets along spire edges | decorative only |
| S-043 | Flying buttresses between a tower and a range | both ends attached **[V]** |
| S-044 | Pinnacles capping buttresses | apex occupancy |

## D. Grand entrances and ceremonial circulation

The showcase feature. See `CASTLE_SCHOOL_ROADMAP.md` Phase 1 for the entrance-role system.

| # | Objective | Check owed |
|---|---|---|
| S-045 | Great hall as a double-height volume | no intermediate floor; walls run two storeys **[V]** |
| S-046 | Twin sweeping staircases rising left and right from one entrance | both flights land on the same deck; both railed **[V]** |
| S-047 | Imperial staircase — one central flight splitting into two returns | landing continuity |
| S-048 | Grand square stair around an open well, all four sides | well guarded on every open edge |
| S-049 | Stair balustrades with newel posts at every turn | newel at each direction change |
| S-050 | Landings sized for ceremony, not minimum | proportion |
| S-051 | Entrance porch / portico with columns | column support |
| S-052 | Entrance steps from the walk up to the threshold | no step-up at the door **[V]** |
| S-053 | Tympanum / carved panel over a grand door | aperture sanity |
| S-054 | Double doors with a transom light above | aperture alignment |
| S-055 | Gallery overlooking the great hall from the upper storey | railed on every open edge **[V]** |
| S-056 | Screens passage behind the hall entrance (medieval plan convention) | corridor connectivity |
| S-057 | Processional axis: entrance → hall → dais aligned across the plan | axis alignment **[V]** |

## E. Attachable, functional openings

| # | Objective | Check owed |
|---|---|---|
| S-058 | Door LEAVES as separate meshes, hinged, not just an opening | leaf fits its opening within tolerance **[V]** |
| S-059 | Door leaf styles: plank-and-batten, panelled, iron-bound, glazed | — |
| S-060 | Double-leaf doors with a visible meeting stile | — |
| S-061 | Door hardware markers: hinge side, handle side, swing direction **[UE]** | swing arc unobstructed **[V]** |
| S-062 | Doors exported as interactive actors carrying their role **[UE]** | manifest schema |
| S-063 | Window leaves, mullion glazing, leaded lights | glazing fits its aperture |
| S-064 | Shutters, internal and external | swing arc unobstructed |
| S-065 | Portcullis and gate leaves for gatehouses | travel path clear |
| S-066 | Trapdoors and hatches for towers and cellars | floor hole present |
| S-067 | Every opening carries an `opening_id` linking geometry ↔ leaf ↔ actor **[UE]** | referential integrity **[V]** |

## F. Lighting — positions now, fixtures in Unreal

You asked for *at least the locations*. That is the right split: PAE emits anchors, Unreal
spawns lights.

| # | Objective | Check owed |
|---|---|---|
| S-068 | `LightAnchor` placement type — position, normal, kind, intended intensity **[UE]** | anchors lie on a surface, not in the void **[V]** |
| S-069 | Wall sconce anchors on a rhythm along corridors and halls | spacing within style range |
| S-070 | Chandelier anchors centred in halls, at a headroom-safe height | clearance below **[V]** |
| S-071 | Pendant / lantern anchors over stairs and landings | not intersecting stair volume |
| S-072 | Candle and torch anchors for the medieval read | — |
| S-073 | Exterior lamp anchors along walks and at entrances | on a surface, off the path centre |
| S-074 | Courtyard lamp posts as real geometry plus anchor | support **[V]** |
| S-075 | Window light-leak anchors so interiors read as occupied at night | one per glazed aperture |
| S-076 | Fire anchors: hearths, braziers, forge | anchored to a floor, under a flue |
| S-077 | Hearth ↔ chimney pairing — every hearth has a stack above it **[V]** | pairing check |
| S-078 | Magical light anchors (floating orbs, rune glow) for the wizarding read | — |
| S-079 | Light anchors exported with UE light-type hints **[UE]** | manifest schema |
| S-080 | Anchor density budget per room so UE does not choke | count per volume |

## G. Fixtures, fittings and props

| # | Objective | Check owed |
|---|---|---|
| S-081 | Picture / portrait anchors on interior walls at eye height | on a wall, correct normal **[V]** |
| S-082 | Banner and tapestry anchors, hanging from wall tops | attachment |
| S-083 | Bookcase runs along library walls | against a wall, not blocking doors **[V]** |
| S-084 | Refectory tables and benches, aligned to the room axis | clear of circulation **[V]** |
| S-085 | Dormitory beds on a bay rhythm | one per bay, clear of the door swing |
| S-086 | Lecterns, desks, blackboards for classrooms | — |
| S-087 | Altar / dais furniture for the chapel and hall | on the processional axis |
| S-088 | Cauldrons, apparatus, shelving for the alchemy range | — |
| S-089 | Staircase carpet runners and hall rugs | inside room bounds |
| S-090 | Courtyard well, fountain, planters | support, not on a walk |
| S-091 | Signage and heraldry over entrances | attachment |
| S-092 | Every prop declares clearance so nothing blocks a door or stair **[V]** | circulation clearance |

## H. Surface variation — breaking up repetition

You called this out specifically: physical texture and seeded variance, not just a texture
swap. This is where modular kits usually fail — 400 identical wall bays.

| # | Objective | Check owed |
|---|---|---|
| S-093 | Per-instance seed on every placement, deterministic from `(spec, seed, piece_id)` | determinism hash |
| S-094 | Seeded mesh variants: 3–5 physical variants per wall type, chosen by seed | all variants share the module contract **[V]** |
| S-095 | Micro-displacement on stone faces — real geometry, not normal maps | vertex budget per piece |
| S-096 | Seeded stone coursing so adjacent bays do not align into visible seams **[R]** | — |
| S-097 | Timber-frame panel infill variation: wattle, brick nogging, plaster (the reference photo shows all three) | — |
| S-098 | Edge wear and chipping on corners, seeded | — |
| S-099 | Weathering gradient — dirt and moss rising from the ground, streaking below sills | vertical gradient anchored to world Z |
| S-100 | Roof surface variation: displaced tiles, moss patches, sagging ridge lines | — |
| S-101 | Seeded slight rotation/offset jitter within tolerance so rows are not machine-perfect | jitter stays inside TOL so no gaps open **[V]** |
| S-102 | Material variation per instance (tint, roughness) driven by the same seed **[UE]** | — |
| S-103 | Vertex colour channels for masking dirt/moss/wear in UE **[UE]** | channels present on export |
| S-104 | Decal anchors: cracks, stains, posters, graffiti, scorch marks **[UE]** | on a surface, correct normal |
| S-105 | Trim-sheet UV layout so variation is cheap at runtime **[UE]** | UV bounds |
| S-106 | Seeded ivy / vine growth up walls and towers | attached to a wall face |
| S-107 | LOD-aware variation — variants collapse to one silhouette at distance **[UE]** | LOD chain |

## I. Interior architecture

| # | Objective | Check owed |
|---|---|---|
| S-108 | Ceilings distinct from the floor above — coffered, beamed, vaulted | headroom **[V]** |
| S-109 | Exposed timber trusses over halls | clearance below |
| S-110 | Ribbed vaulting for chapel and cloister | — |
| S-111 | Fan vaulting for the ceremonial stair | — |
| S-112 | Wainscoting and dado rails — banding applied INTERNALLY | band attachment (works today, needs interior faces) |
| S-113 | Interior arcades separating aisles from nave | column support |
| S-114 | Fireplaces and chimney breasts projecting into rooms | hearth ↔ chimney pairing **[V]** |
| S-115 | Window reveals and internal sills | aperture depth |
| S-116 | Floor patterning: flagstones, boards, tiles, aligned to room axis | — |
| S-117 | Cellars and undercrofts below ground level | support, access |

## J. Site and grounds

| # | Objective | Check owed |
|---|---|---|
| S-118 | Terrain conformance — buildings sit ON the landscape **[UE]** | no burying/floating **[V]** |
| S-119 | Retaining walls and terracing where ground falls | support |
| S-120 | Garden quadrants inside cloister courts | inside court bounds |
| S-121 | Tree and hedge anchors, seeded | not on walks, not inside buildings **[V]** |
| S-122 | Paths that connect DOORS to each other, not just ring the building | path connects every entrance **[V]** |
| S-123 | Bridges over water or ravines | both ends supported |
| S-124 | Boundary walls with gatehouses, replacing the picket fence at castle scale | enclosure |
| S-125 | Outbuildings: stables, forge, boathouse, greenhouse | freestanding exemption declared |
| S-126 | Clock tower / gate tower as a site landmark | — |
| S-127 | Night-time site render as a standing evidence shot **[R]** | — |

## K. Verification to match

| # | Objective | Check owed |
|---|---|---|
| S-128 | Existence checks — spec asks for N, N placed (largest current hole) | **[V]** |
| S-129 | Sweep every check off `p.cell` onto `covered_cells` — Handbook rule 5.1 | **[V]** |
| S-130 | Headroom check over all walkable surfaces | **[V]** |
| S-131 | Anchor validity — every light/prop/decal anchor on a real surface | **[V]** |
| S-132 | Clearance — nothing blocks a door swing, stair, or corridor | **[V]** |
| S-133 | Proportion sanity against style ranges | **[V]** |
| S-134 | Silhouette regression via golden images per style **[R]** | |
| S-135 | Instance and vertex budget per building and per site **[UE]** | |

---

## Suggested ordering

1. **S-001…S-010 (style system) first.** Everything else is a style field. Building the
   pointy roofs before the switchboard means hard-coding them twice.
2. **S-011…S-032 (roofs).** Biggest visual return per hour — the silhouette is what reads
   as "wizarding school" before any texture loads.
3. **S-045…S-057 + S-058…S-067 (grand entrance and real doors).** The showcase.
4. **S-093…S-107 (seeded variation).** The thing that stops 400 identical bays reading as a
   spreadsheet.
5. **S-068…S-092 (lighting and prop anchors).** Cheap to emit, transforms the UE result.
6. **S-108…S-127 (interiors and site).**
7. **S-128…S-135 (verification)** — *continuously*, not last. Every objective above ships
   with its check or it is not shipped.

## The standing caution

Everything in §H is where modular kits die. Variation must live **inside** the module
contract: a seeded variant that is 4 cm wider is not a variant, it is a gap. S-094 and
S-101 both carry contract checks for exactly this reason, and the arcade pillar that
measured 1.76 m in a 4 m module (Ledger C-7) is what happens without them.

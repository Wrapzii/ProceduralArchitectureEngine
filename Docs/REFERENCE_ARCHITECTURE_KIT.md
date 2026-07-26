# Reference architecture kit

Target reference: the user-provided mountain citadel image (2026-07-25).
The image is a style and composition target, not a fixed building preset.

## Composition grammar

The target is assembled from reusable systems:

| System | Required variants | Current engine status |
|---|---|---|
| Occupied ranges | house, office, academy, hall, lodging, service | Implemented structurally through `BuildingSpec` / `StructureSpec`, level programs, rooms, joined masses |
| Round towers | stair turret through landmark drum | Implemented with continuous `radius_bays=0.5..16`, independent storeys and cap height |
| Square towers | small stair turret, gate pier, landmark tower | Implemented; small and room-bearing variants validate |
| Tower roofs | cone, pyramid/square spire, flat crown | Implemented as scalable greybox geometry |
| Main roofs | pitched, hip, flat | Implemented; detailed slate, dormer, ridge and gable styling remains partial |
| Monumental gates | one/two-bay tall arch, flanking piers | Existing `wall_gate_arch_grand` / gatehouse path |
| Curtain walls | occupied wall ranges, battlements, buttresses | Existing castle/fortress compound path |
| Courtyard | open court with connected surrounding ranges | Implemented |
| Covered arcade | walk floor, rear wall, arch-and-pier court face, continuous cover | Implemented by `ArcadeSpec`; 16-bay proof validates |
| Vertical circulation | straight, wide, switchback, spiral | Implemented; tower spiral now reaches every requested shaft storey |
| Interior planning | rooms, full partitions, doors, upper floors | Implemented at structural greybox level |

## Scale families

`radius_bays` is a radius/half-width, not a diameter.

| Family | Suggested radius | Typical use |
|---|---:|---|
| Needle turret | `0.5` (4 m round diameter) | stair-only corner turret |
| Small square turret | `0.75` (6 m width) | stair, gate pier, roofline accent |
| Standard tower | `1.0` (8 m diameter/width) | stair plus landings |
| Room tower | `1.25..2.0` | offices, chambers, library stacks around a core |
| Landmark drum | `2.5+` | lighthouse, great stair, central tower |

Tower shaft storeys and `spire_height_storeys` are independent. The same tower
body can therefore carry a low cap, a steep reference-style cone, or no spire.

## Appearance work still owed

The engine can compose the major objects, but it does not yet reproduce the
reference finish. Do not mark the visual target complete until these exist:

1. True curved door and window cuts through round drums (flat inserts remain).
2. Pointed/lancet arcade option and thinner configurable pier rhythm.
3. Multi-stage tower shafts: string courses, bell/lantern stages, parapet-to-spire transitions.
4. Stepped gables, roof dormers, chimneys, finials, ridge cresting and slate/shingle courses.
5. Better gate ensembles: deep portal tunnel, archivolts, portcullis/recess and paired arch proportions.
6. Battered plinths, retaining walls, terraces and causeway/bridge composition.
7. Masonry coursing, quoins, trims and style-pack material variation.
8. Office/civic facade packs with regular glazing, service cores and larger room grids,
   while retaining the same mass/tower/courtyard grammar.

## Proof scenes

- `tiny_round_spire_spec`: compact 4×3, two-storey range with 4 m round turret.
- `small_square_spire_spec`: compact 4×3 range with 6 m square turret.
- `square_spire_tower_spec`: room-bearing 12 m square tower.
- `giant_lighthouse_spec`: 28 m round landmark drum.
- `m4_courtyard_spec` + `ArcadeSpec`: 16-bay covered courtyard walk.
- `build_fortress_compound`: validated 120×108 m structural reference campus;
  live Blender proof writes `fortress_live.png` and `reference_compound_close.png`.

Spiral proof contract: four 90° quarters per storey, ordered from the real
doorway landing. `floor_hole` placements are void/cutter metadata and are never
instanced as blue physical frames. The fixed 88 cm newel is emitted only where
the tread inner edge actually meets it; wider stairs remain unobstructed
open-well helices.

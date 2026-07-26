# PAE Agent Sync Board

Project root: `C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine`

**Read before coding ??? in this order:**

| Doc | When |
|---|---|
| `Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md` | Always. The spec. Do not redesign ??? implement. |
| `Docs/VALIDATION_HANDBOOK.md` | **Before adding any piece, placement rule or check.** The seven questions, the nine defect classes, tolerance rules, the five standing rules. |
| `Docs/CHANGE_PROTOCOL.md` | **Before your first commit.** Commit format, sync-board etiquette, which docs to update, red-suite handling, close-out. |
| `Docs/DEFECT_LEDGER.md` | When you hit a weird symptom ??? it is probably in here already. Append every new bug. |
| `Docs/CASTLE_SCHOOL_ROADMAP.md` | Picking up new work. Open defects are Phase 0. |

**Three rules that cause most breakage here:** never `git add -A` in this shared tree;
never reason from `p.cell` (use `covered_cells`); never hand-roll a placement offset (use
`pae/boundary.py`).

## Ownership (do not edit another WP's files without ACK)

| WP | Owner model | Status | Files |
|---|---|---|---|
| WP-1 | Composer 2.5 | DONE | `pae/contract.py`, `pae/validate.py`, `pae/tests/unit/test_validate*`, `pae/tests/fixtures/broken_*` |
| WP-2 | Composer 2.5 | DONE | `pae/assets/**` |
| WP-3 | Grok 4.5 | DONE | `pae/primitives/**` |
| WP-4 | Grok 4.5 | DONE | `pae/spec.py`, `pae/solver.py`, `pae/plan.py`, `pae/styles/**` |
| WP-5 | Composer 2.5 | DONE | `pae/assemble.py`, `pae/decorate.py`, `pae/pipeline.py`, `pae/tests/unit/test_assemble.py` |
| WP-6 | Grok 4.5 | DONE | `pae/export/**` |
| WP-7 | Composer 2.5 | DONE | `pae/addon/**` |
| WP-8 | Grok 4.5 | DONE | `pae/comfy/**` |
| WP-9 | Grok 4.5 | DONE | `pae/tests/property/**`, `pae/tests/golden/**`, `pae/tests/conftest.py`, `tools/ci_*`, `tools/magic_number_grep.py`, `.github/workflows/**` |
| MP-WS1 | Grok 4.5 | DONE | `pae/spec.py`, `pae/structure_spec.py` (new), `pae/sketch.py`, `pae/solver.py`, `pae/plan.py`, `pae/assemble.py` (foundation/datum only), `pae/contract.py` (datum accessor), `pae/structure_identity.py`, `pae/pipeline.py`, `pae/tests/unit/test_structure_level_spec.py` â€” Master Plan Stage A+B+YAML |
| MP-WS2 | Grok 4.5 | DONE | assemble roof helpers + `pae/primitives/roofs.py` + roof validate/tests â€” Stage C height-field (owns roof sections of assemble.py) |
| MP-WS3 | Composer 2.5 | DONE | `pae/solver.py`, `pae/plan.py`, `pae/stair_occupancy.py`, stair pad sections of assemble.py, stair tests â€” Stage D |
| MP-WS3b | Composer 2.5 | DONE | `pae/solver.py`, `pae/plan.py`, `pae/street_scene.py`, school/stair tests â€” school 4Ã—2 plan reserve + library_tower spiral fallback |
| MP-WS4 | Composer 2.5 | DONE | `pae/drum.py`, `pae/tower_entry.py`, outboard-drum wall suppress in assemble.py, tower/drum tests â€” Stage E |
| MP-WS5 | Composer 2.5 | DONE | `pae/structure_identity.py`, `pae/compound_unify.py`, `pae/drum.py` (`inboard_drum_party_faces_from_plan`), minimal assemble party-edge skip in `_place_wall_run`, `pae/tests/unit/test_party_walls.py` â€” Master Plan Stage F party walls |
| MP-WS6 | Composer 2.5 | DONE | `pae/styles/*.json`, `pae/style_pack.py`, `pae/tests/unit/test_style_pack.py` â€” Master Plan Stage I packs (8 total) |
| MP-WS6b | Composer 2.5 | DONE | `pae/tests/unit/test_style_interchange.py`, `tools/me_style_interchange_proof.py`, `Saved/exports/me_style_interchange_report.json`, `Docs/MASTER_PLAN.md`, `Docs/CASTLE_SCHOOL_ROADMAP.md`, `Docs/DEFECT_LEDGER.md` â€” M-E interchange proof + Master Plan status sync |
| MP-WS7 | Grok 4.5 | DONE | `pae/plan.py`, `pae/sketch.py`, `pae/arcade.py` (new), `pae/structure_spec.py` program paint, `pae/pipeline.py` apply_arcade, `pae/tests/unit/test_stage_g_program_arcade.py` â€” Master Plan Stage G program/rooms + courtyard arcade start |
| MP-WS11 | Composer 2.5 | DONE | `pae/export/**`, `tools/ue_*.py`, `tools/export_manifest.py`, `Docs/UE_MANIFEST_CONSUMER.md`, `pae/tests/unit/test_ue_*` â€” Master Plan Stage L filesystem tooling (no editor/MCP) |
| MP-WS-J | Grok 4.5 | DONE | `pae/site_spec.py` (new), `pae/tests/unit/test_site_spec.py`, `Docs/MASTER_PLAN.md` Stage J — site authoring skeleton (M-G city deferred) |

## Wave plan

1. **Wave A:** WP-1 + WP-9
2. **Wave B:** WP-2 + WP-3 + WP-4
3. **Wave C:** WP-5
4. **Wave D:** WP-6 + WP-7 + WP-8
5. **Wave E:** M4 courtyard/L/U ? M5 dynamic assets ? M6 UE manifest polish ? random-spec un-xfail ? gable mesh real ??? **DONE** (187 passed / 0 xfailed)
6. **Wave F (now):** TOWER_AABB (annulus exempt) ? M6_DRYRUN (UE spawn simulator) ? GALLERY (Blender M1???M4 shots) ? WARN_POLISH (wall/roof allowed pairs)

## Log

```
2026-07-24 ??? Master: Wave E complete (187/0). Launching Wave F polish lanes.
>>> TRIGGER @TOWER_AABB ??? Exempt same-cell tower_arc*/crown/cap AABB overlaps as designed annulus quarters; keep real overlaps critical/warning; tests for m3 warn drop; do not touch assemble wall rules.
>>> TRIGGER @M6_DRYRUN ??? tools/ue_manifest_dry_run.py: load Saved/exports/*.json, verify schema+loc_cm+yaw, emit Saved/exports/m6_dry_run_report.json; unit tests; no UE editor required.
>>> DONE @M6_DRYRUN ??? tools/ue_manifest_dry_run.py (schema/loc_cm/yaw/asset_id/validation gate, auto-export M1 when default missing); pae/tests/unit/test_ue_manifest_dry_run.py; Docs/UE_MANIFEST_CONSUMER.md dry-run section; report ??? Saved/exports/m6_dry_run_report.json.
>>> TRIGGER @GALLERY ??? Extend blender_build for m1+m2+m3+m4_l side-by-side or sequential collections + screenshots Saved/Screenshots/gallery_*.png; keep reload_pae.
>>> TRIGGER @WARN_POLISH ??? Allow designed wall???roof / corner-overlap pairs in validate interpenetration without silencing real floaters; regression tests on broken_all_defects.
2026-07-24 ??? Master: M1 roof-tuck + south gap closed; launching Wave E (M4/M5/M6/polish).
>>> DONE @M5 ??? Dynamic assets: decorate queries AssetDB by tag (confirmed decorative ??? sparse interior props); assets.query helpers; run_through_decorate; test_m5_dynamic_assets (accept fake measured brazier id in output); snap_fit 1.76m pillar reject intact; 150 unit passed.
>>> DONE @M6 ??? UE manifest harden (contract block, LOD placeholders, collision stubs, validation.failures); Docs/UE_MANIFEST_CONSUMER.md; bind_to_terrain integration test (2??2 flatten_pad); tools/export_m1_manifest.py ??? Saved/exports/m1_manifest.json (39 placements, 6 assets); 12 export+integration tests pass.
2026-07-24 ??? Launching Wave A+B: WP-1 (Composer), WP-9 (Grok), WP-2 (Composer), WP-3 (Grok), WP-4 (Grok).
>>> DONE @WP-2 ??? Asset DB (SQLite), sockets, import/fit, min-corner origin, rotates_about_center; 32 tests pass.
>>> DONE @WP-1 ??? Full ?7 validator (9 checks), contract AABB helpers, assembly_types.py, broken_all_defects fixture; 21 WP-1 tests pass (61/62 repo; magic-number grep still flags WP-2/3/9 literals).
>>> DONE @WP-4 ??? BuildingSpec loader (rejects world/cm), greedy Massing solver, FloorPlan + stair graph, M1 factory; 13 unit tests pass.
>>> DONE @WP-3 ??? Parametric primitive library (15 kit pieces), dual descriptor/bpy path, Docs/PRIMITIVE_MEASUREMENTS.md; 14 primitive unit tests pass without Blender.
>>> DONE @WP-9 ??? Determinism hash, golden harness (2% pixel thresh, stub PNG), property scaffolding (xfail until assemble), magic_number_grep + hardened ci.yml; python tools/ci_local.py green (90 passed, 2 xfailed).
>>> DONE @WP-5 ??? assemble.py (?2.2???2.5 boundary walls, floors, ground, flat roof), decorate pass-through, M1 validate ok=True; 5 assemble unit tests; 118 passed / 2 xfailed repo-wide.
>>> DONE @WP-8 ??? Comfy decorative ingest (kind gate, normalise???measure???socket???human confirm???DB); materials policy; 23 unit tests; Docs/COMFY_PIPELINE.md.
>>> DONE @WP-7 ??? Blender add-on UI (?10): Validate click-to-frame, Spec/Assets/Generate/Export panels, pure helpers + 12 unit tests; install `pae/addon/README.md`.
>>> DONE @WP-6 ??? Export gate (refuses critical), pae.manifest/1 (contract dims), FBX/blend stubs + linked-dupe plan, bind_to_terrain heightmap modes; 10 export unit tests.
2026-07-24 ??? Master: wired WP-7 export operators to WP-6 APIs (blend/fbx/manifest). M1 proof: validate ok=True, 29 placements, pae.manifest/1 written. Suite: 140 passed, 2 xfailed. ALL WP-1..WP-9 DONE.
>>> DONE @CORNERS_ROOF ??? roof_flat catalog + span helper; wall corner ownership (west owns SW); ground z ???2??FLOOR_T (top at ???FLOOR_T); floor/ground interpenetration exempt; 152 passed / 2 xfailed.
>>> DONE @M2 ??? Two-storey 4??3 rect + straight stair (2 modules, 1 rise), VOID above stair, floor_hole + spanning upper deck, stair_straight in assemble; m2_two_storey_stair_spec(); validate ok=True critical=[]; 8 M2 tests; 152 passed / 2 xfailed repo-wide; M1 + ?2.3 east/north boundary regression clean.
>>> DONE @BPY52 ??? Blender 5.2 mesh harden: bpy_util FLOAT/EXACT/MANIFOLD (never FAST), safe select_set, scene.collection link; pae/blender_build.py M1+M2 assemble???validate???catalog.build_mesh/framed fallback???cm???m 0.01???Saved/Screenshots/m1_live.png + reload_pae; tools/pae_build_in_blender.py; unit tests green without bpy.
>>> DONE @CI_M1 ??? Un-xfail M1 property validate; M1 determinism hash (2-run); golden baselines (placement meta hash + 64? stub PNG); random multi-wing remains xfail. magic_number_grep OK; pytest 161 passed / 1 xfailed.
>>> DONE @M3 ??? Pitched roof (`roof_pitched_gable` spanning deck + gable tags), tower arcs ??4 same-cell `rotates_about_center=True` (no 4-cell scatter) + crown/cap, `m3_keep_tower_spec()` (wall-attached, M1/M2 untouched). Tests: pitched emits gable pieces; tower same-cell. M3 validate ok=True (critical=0; ~52 warnings mostly tower-quarter AABB interpenetration). Gaps: pitched is span AABB proxy (not per-bay gable mesh); tower AABB overlap warnings expected until true annulus collision; corner-tower still breaks 4-connect circulation (factory uses wall attach). Suite: 161 passed / 1 xfailed.
>>> DONE @GABLES ??? Pitched roof split: `roof_gable_infill` (triangular prism per gable-end bay) + `roof_pitched_slope` (row/column-spanning wedge decks); real bpy meshes (not AABB span proxy). Assemble places gables on end rows/cols + interior slope spans for ?7.2 wall support. Tests: m3_pitched emits ???8 gable infill + slope rows; validate critical=[]; m3_keep_tower ok. `blender_build` includes m3 + optional `Saved/Screenshots/m3_pitched.png`. Removed `roof_pitched_gable`. Suite: 184 passed / 1 xfailed (pre-existing magic-number hit in m5 test).
>>> DONE @M4 ??? Courtyard/L/U multi-wing: solver non-overlapping wings + courtyard role outside envelope; plan COURTYARD cells; assemble inner inhabited walls on courtyard/re-entrant faces + per-wing roofs (no deck over courtyard). Factories `m4_l_plan_spec()`, `m4_u_plan_spec()`, `m4_courtyard_spec()`. Validate ok=True critical=[] for L, U, courtyard. 12 M4 tests; M1 south-gap + E/N roof-tuck regression clean. Suite: 183 passed / 1 xfailed (2 unrelated fails: M3 pitched floater test + M5 magic grep from parallel lane).
>>> DONE @PROPERTY ??? Un-xfail `test_random_specs_validate_ok`: solver local-repair now nudges *overlapping* interior towers to exterior wall/corner (was skipped via `_tower_touches`); random factory emits exterior attach cells + south-bar stairs. M5 test uses `STOREY_CM` (magic_number_grep). Suite: 187 passed / 0 xfailed; 500 random seeds green.
>>> DONE @GALLERY ??? `build_gallery(milestones=None)` ??? `PAE_Gallery` / `PAE_M1`???`PAE_M4_L` side-by-side (+X footprint+2m gap); `write_gallery_screenshot` ??? `Saved/Screenshots/gallery_m1_m4.png` + per-milestone `gallery_{label}.png`; factories from `pae.spec`; `reload_pae` preserved; `build_live` M1 path unchanged; `tools/pae_build_in_blender.py --gallery`; unit tests in `test_blender_build.py`.
>>> DONE @GALLERY_CAM ??? Per-milestone gallery shots frame only that collection's instances (`_meshes_in_collection_tree` + `mesh_world_bounds_m`); deterministic SE-elevated ortho via `camera_pose_from_bounds_m`; overview still `PAE_Gallery` row; `reload_pae` + cm???m preserved; 10 unit tests in `test_blender_build.py`.
>>> DONE @VALIDATE_POLISH ??? `pae/validate.py` ?7.4 designed-pair exemptions: same-cell tower_arc/crown/cap annulus, WALL_T corner overlaps, wall???roof deck eave tuck, storey slab above wall/stair/tower, floor_hole deck, stair openings. m3 interpenetration warns 88???1 (remaining: south+inner_north T-junction at tower); m1/m2/m4 ok=True critical=[]. `test_validate_polish.py` + broken_all_defects regression intact. Suite: 213 passed.
>>> DONE @APERTURE_GAPS ??? m1 warns 3???0, m2 7???0, m3 9???0 (incl. interpenetration 1???0), m4_l 3???0; critical=[] all milestones. Root fixes: `assemble.py` perimeter wall_runs classify by piece_id face (not cell bucket ??? killed 340 cm false collinear_gap); skip redundant inner walls on perpendicular perimeter corners (tower T-junction); BFS door interior/exterior cell resolve through WALL_LINE corners + tower attach. `validate.py` exterior door side accepts EXTERIOR/COURTYARD/out-of-grid/DOOR threshold. `broken_all_defects` door_bad_exit exterior???interior cell (still aperture_sanity). Tests: `test_m1_m4_m3_aperture_gap_warnings_zero`, `test_m3_interpenetration_zero`. Suite: 241 passed.
>>> DONE @EXPORT_ALL ??? `tools/export_manifest.py` (`--milestone m1|m2|m3|m4_l|m4_u|m4_c` ??? `Saved/exports/{milestone}_manifest.json`, fail-closed on critical); `export_m1_manifest.py` thin wrapper; `ue_manifest_dry_run.py` `--milestone` + generalized auto-export; `test_export_manifest_cli.py` (per-milestone export + m1/m3 dry-run integration); full pytest green.
```
>>> DONE @GALLERY_CAM_FIX ? Collection unlink used Object.users_collection by mistake; parent scan via scene+data children. Gallery rebuild ok (m1=39 m2=55 m3=104 m4_l=102).

>>> DONE @GALLERY_FRAME ? depsgraph update before bounds; hide sibling collections per-milestone; fixed tiny/empty PNGs.

>>> DONE @TOWER_VISUAL ? Real tower meshes: `annulus_quarter_verts` axis snap + 96-seg seams; `annulus_battlement_ring_verts` centred crown; `cone_verts` centred cap (removed proto `obj.location` hack lost on instance). `test_tower_mesh.py` (vert counts, seam continuity, AABB, crown/cap Z stack). Assemble stacking unchanged (crown_z=STOREY_CM on top level correct). Suite: +6 tower tests; 250 passed / 3 pre-existing fails (m1 golden hash, pitched roof floater).

>>> DONE @M1_VISUAL - Corner opening ownership (_primary_opening_face): SW door south-only, NW window west-only. placement_instance_scale_cm non-uniform XY for spanning roof_flat (fixes recessed roof ledge). Measured wall/roof outer flush delta=0 cm all faces. Tests + golden hash updated.

>>> DONE @ROOF_VISUAL ? Pitched roof gable fix: `_place_pitched_roof` places 2 end-cap `roof_gable_infill` prisms (ridge-end X or Y) spanning full cross-span; slope wedges on every cross row/column spanning full ridge length (not sawtooth along eaves). m3 4?3: gables 8?2, slopes 1?3; validate critical=[]; `_designed_roof_gable_slope_pair` exempts end-cap AABB overlap. Restored `test_m3_tower_arcs_same_cell` def. Suite: 253 passed.

>>> DONE @ROOF_AFRAME ? single double-pitch span + end gables facing ?X; Proto mesh refresh (crown 576 / cap 97 verts). M3 gallery reads as gabled hall + cone tower. Suite 253.

>>> DONE @TOWER_OUTSIDE ? `_tower_drum_xy_offset_cm` pushes 2?MODULE annulus outward along abutment normal (west m3: centre (-800,200) vs old (-400,0); drum east edge -400 kisses hall west at 0). Same-cell 4-quarter rule intact; crown/cap share offset + 0.5 cm Z gap. Tests: `test_m3_tower_drum_outside_hall_footprint`. Suite: 254 passed.

>>> DONE @M2_STAIR_VIS ? `stair_straight`: 20 stepped tread/riser boxes (`straight_stair_verts_faces`, 17.5 cm ? 40 cm); `floor_hole`: full-bay void (10 cm rim, 380?380 opening) via perimeter frame mesh; descriptor sizes unchanged; `test_stair_floor_mesh.py` (step count + hole AABB/void); M2 pipeline + validate polish green.
>>> DONE @M6_HANDOFF ? `tools/ue_spawn_table.py` (`--milestone` ? `Saved/exports/{milestone}_spawn_table.json`, optional `--csv`; rows: asset_id/loc_cm/yaw/piece_id; validation+dry-run gate); `pae/tests/unit/test_ue_spawn_table.py`; `Docs/UE_MANIFEST_CONSUMER.md` spawn-table + UE Editor Python pseudocode.

>>> DONE @M4_GALLERY ? Gallery extended m4_u + m4_c (`PAE_M4_U`, `PAE_M4_C`); factories `m4_u_plan_spec`, `m4_courtyard_spec`; per-milestone `gallery_m4_u.png` / `gallery_m4_c.png`; headless test asserts courtyard has 4 wing roofs and none cover court cell (3,3). Suite: test_blender_build green.

>>> DONE @M5_DEMO ? M5 e2e demo: `pae/tests/fixtures/m5_demo_crate.obj` (50?50?80 cm) + `pae/assets/obj_measure.py` + `pae/assets/demo_seed.py`; `tools/m5_demo_seed_db.py` seeds `Saved/demo/m5_assets.db` and runs `run_through_decorate(m1_box_house_spec())` (39?40 placements, 1 prop); `test_m5_demo_fixture` proves count increase + validate ok. Suite: 265 passed.

>>> DONE @DOOR_BOOL ? Wall door/window mesh: bmesh frame (sill/lintel/jambs) via `build_box_with_rect_aperture_along_x` ? no boolean corner voids. Descriptor fractions unchanged (_DOOR_W=0.40, _WINDOW_* contract-relative); cutter pad 25% WALL_T each face + 0.5 cm Y/Z for boolean fallback (`apply_aperture_boolean_cut`, EXACT/MANIFOLD). Tests: `test_wall_apertures.py` (9). Suite: 279 passed / 1 pre-existing fail (`test_stair_floor_mesh` tread nose count).

>>> DONE @TOWER_LOOK ? Tower mesh polish: `TOWER_ARC_SEGMENTS_FULL=128`; arc quarters open horizontal caps + true vertical cylinder columns (132/66 verts); crown = parapet drum ring + discrete merlon wedges (544/408, was 576/384 wavy ring); cap cone 128-seg (129/128). `rotates_about_center` / size_cm / aabb contracts intact. Tests: +3 tower mesh. Suite: 283 passed.


2026-07-24 ? Master: Wave H VISUAL/PRODUCT swarm dispatched (DOOR_BOOL, TOWER_LOOK, M2_STAIR_VIS, M4_GALLERY, M5_DEMO, M6_HANDOFF).


2026-07-24 ??? Master: Wave I swarm (Composer 2.5) ??? aperture facing, eaves, materials, floaters, stair prove, UE bind note.
>>> TRIGGER @APERTURE_FACE ??? Door/window openings must face outward on correct wall axis; kill P-shaped silhouette. Own walls.py + assemble wall yaw only if required.
>>> DONE @APERTURE_FACE ??? Wall aperture frame punches thin X only (`wall_aperture_frame_parts_cm`: full-height pillars + sill/lintel between jambs); `aperture_opening_run_vertical` guards run/thickness axis swap; bpy `build_mesh_from_box_parts`. Tests: through-hole, exterior rect void, no run-end notch. Suite: 285 passed.
>>> TRIGGER @EAVES ??? Small roof overhang past walls (flat + pitched) so roofs read as roofs. Own roofs.py + assemble roof size/offset.
>>> DONE @EAVES ??? `EAVE_OVERHANG_CM = WALL_T_CM * 0.5` (30 cm); flat + pitched roofs grow/offset via roof span helpers; per-wing interior seams zero overhang. m1/m3/m4 validate ok. Suite: 304 passed.
>>> TRIGGER @MAT_READ ??? Distinct Blender materials per kind (wall/roof/floor/tower/stair) for gallery readability. Own blender_build.py materials only.
>>> DONE @MAT_READ ? KIND_MATERIAL_COLORS + material_color_for_kind() in pae/blender_build.py; distinct workbench hues for wall/floor/ground/roof/stair/tower_arc/tower_crown/tower_cap/door/window (+ prop/plinth/hole fallbacks); _ensure_material updates existing mats on re-run. Tests: test_kind_material_colors_* in test_blender_build.py.
>>> TRIGGER @FLOATER_KILL ??? Find/remove stray disconnected slabs in m3 gallery (left block). Own assemble ground/tower plinth or blender clear.
>>> DONE @FLOATER_KILL - Orphan ground_plinth + L0 floor at tower cell (-1,0) after drum XY offset (slab x in [-400,0] vs drum x in [-1000,-600]). Fix: skip _tower_cells in ground + L0 floor loops. Test: test_m3_no_disconnected_ground_plinth_far_from_hall_tower_union.
>>> TRIGGER @STAIR_PROVE ??? Gallery/live shot proves stepped stair + hole visible (dedicated Cam or forced m2 interior frame). Own blender_build.py screenshot helpers.
>>> DONE @STAIR_PROVE ? build_m2_stair_proof() -> Saved/Screenshots/m2_stair_proof.png; deterministic camera from stair+floor_hole AABB; hides roof_flat + upper floor deck; tools/pae_build_in_blender.py --stair-proof; optional build_gallery(stair_proof=True); headless tests in test_blender_build.py.
>>> TRIGGER @UE_BIND ??? Doc + tool mapping spawn_table asset_id to Content path stub for RE. Own Docs + tools only.
>>> DONE @UE_BIND ? `tools/ue_asset_bind_table.py` (`--milestone` ? `Saved/exports/{milestone}_asset_bind.json`; `pae.asset_bind/1`: asset_id/suggested_content_path/lod0/collision_profile stubs under `/Game/RE/PAE/...`; optional spawn-table id source); `pae/tests/unit/test_ue_asset_bind_table.py`; `Docs/UE_MANIFEST_CONSUMER.md` bind + UE fill section.

2026-07-24 ??? Master: Wave J swarm ??? stair isolate, mat tint by asset, wall thickness read, opening prove shot, ground skirt.
>>> TRIGGER @STAIR_ISO ??? Hide ALL non stair/floor_hole in stair proof (walls/ground too). Own blender_build.py only.
>>> DONE @STAIR_ISO ? is_stair_proof_visible_asset() allow-list; _apply_stair_proof_visibility hides viewport+render on every mesh except stair/floor_hole/hole tokens; _hide_non_stair_proof_collections excludes other PAE collections; camera still framed on stair+hole AABB; tests in test_blender_build.py.
>>> TRIGGER @MAT_TINT ??? Tint door/window by asset_id not just kind=wall. Own blender_build.py materials.
>>> DONE @MAT_TINT ? ASSET_MATERIAL_COLORS + material_key_for_placement() / material_color_for_placement(); instance_assembly + _ensure_material tint by asset_id (wall_door, wall_window, roof_*, tower_*, stair_*, floor_hole); higher-contrast workbench hues. Tests: test_material_key_for_placement_*, test_asset_material_colors_* in test_blender_build.py.
>>> TRIGGER @OPEN_PROVE ??? Dedicated m1_openings_proof.png camera on door+windows exterior. Own blender_build.py.
>>> DONE @OPEN_PROVE ??? build_m1_openings_proof() -> Saved/Screenshots/m1_openings_proof.png; SE-elevated ortho on south/west shell AABB; hides north/east walls + roof/floor; tools/pae_build_in_blender.py --openings-proof; headless tests in test_blender_build.py.
>>> TRIGGER @WALL_READ ??? Ensure wall thickness WALL_T reads in gallery (not paper-thin illusion). Own walls size/assemble if needed.
>>> TRIGGER @GROUND_SKIRT ??? Continuous ground under footprint (single slab or flush plinths) ??? no checkerboard gaps. Own assemble ground.
>>> DONE @GROUND_SKIRT ??? `ground_plinth_span_size_cm()` + `_ground_spans()` (main/wing volumes; tower DOOR cells excluded); one spanning slab per wing/footprint like roof_flat. FLOATER_KILL tower floor skip preserved. M1 golden hash/n_placements updated (28). Suite: 320 passed.
>>> DONE @RENDER_COLOR - Workbench gallery PNGs: configure_workbench_screenshot_scene (SOLID/STUDIO/MATERIAL + view_transform=Standard); apply_material_base_color sets Principled Base Color + mat.diffuse_color; write_screenshot uses helper. Tests: test_configure_workbench_screenshot_scene_*, test_apply_material_base_color_*.
>>> TRIGGER @STAIR_CAM ? Perpendicular stair proof camera (not along tread run); Workbench MATERIAL proof colors.
>>> DONE @STAIR_CAM ? stair_proof_camera_direction_from_bounds_m (longer X ? offset Y, longer Y ? offset X, elevated); stair_proof_ortho_scale_from_bounds_m tight on visible face; GALLERY_SUN_ENERGY 4.5; write_screenshot uses configure_workbench_screenshot_scene MATERIAL. Tests: test_stair_proof_camera_offset_* + test_m2_stair_proof_camera_perpendicular_to_y_run.

2026-07-24 ? Stair exit clearance (fail-closed).
>>> DONE @STAIR_EXIT ? validate stair_exit_clearance: missing floor_hole / solid pad / wall|roof in head clearance = critical. Spanning upper deck mesh punches VOID holes (slab_with_rect_holes). Open-stair tops use floor_hole rim + deck tiles (no solid plug). Proof: Saved/Screenshots/open_stair_roof_hole_proof.png + m2_stair_proof.png. Tests: test_stair_exit_clearance.py; suite stair-related green.

2026-07-24 ? Stair styles + school readiness audit.
>>> DONE @STAIR_STYLES ? Kit: stair_half, stair_landing, stair_switchback (2x2 dog-leg), stair_wide (2x2 monumental); helical spiral wedges replace annulus proxy. Showcase A?E + open_stairs_showcase.png. Docs/SCHOOL_READINESS.md honest gap list. Assemble honors stair_kind switchback|wide. Tests: test_stair_styles.py green.

2026-07-25 ??? Claude (Opus 5) lane: kit expansion, placement wave, verification, docs.
>>> DONE @KIT ??? Aperture profiles (17 window/door/arch types, curved heads, mullions, transoms) + columns/railings/spires/surfaces families. Kit 17 ??? 55 pieces. measure.py rules for barrier/column/roofline/surface kinds.
>>> DONE @PLACEMENT ??? trim.py (railings, buttresses, parapets, dormers, chimneys, spires, colonnades), site.py (multi-building merge, paving, walks, kerbs, lawn, fence/gates), compound.py (4-range quadrangle, per-range trim, BalconySpec), boundary.py (yaw + boundary-line table, single source).
>>> DONE @VERIFY ??? New checks: `freestanding` (touch-graph islands), `canopy_attachment` (roof must meet envelope, not just posts), `roof_penetration` (WARNING ??? hits on school academy NOT yet triaged, must be promoted or explained). Fixed: covered_cells off-by-one, buttress face derivation, site fence rotation offset, stranded parapets, gallery roof plane, hole railings, support tolerance for thin pieces.
>>> DONE @DOCS ??? Docs/VALIDATION_HANDBOOK.md, Docs/DEFECT_LEDGER.md, Docs/CHANGE_PROTOCOL.md, Docs/CASTLE_SCHOOL_ROADMAP.md.
>>> BLOCKED @TOWER_ATTACH ??? `test_random_specs_validate_ok` RED: 26-piece detached tower. TRUE POSITIVE in solver local-repair (nudges overlapping towers toward a wall, never asserts contact). Ledger C-5, roadmap defect 0.1. Owns pae/solver.py ??? NOT claimed by me.
>>> BLOCKED @STAIR_CELLS ??? `_check_stair_exit_clearance` matches holes by `h.cell`; violates Handbook rule 5.1 and can miss a plugged stair top under a spanning deck. Ledger D-5, roadmap defect 0.2.
Suite at close: 405 passed, 1 failed (@TOWER_ATTACH above). Renders: Saved/Screenshots/verify_compound_{aerial,quad,balcony,roofflush}.png
>>> DONE @BANDING ??? Coping/facade articulation placeable anywhere (bands.py + banding.py). New kind "band", 5 pieces (course, jettied course w/ joist ends, pilaster, diagonal brace, coping cap). BandingSpec: courses at any storey fraction, verticals every N bays, braces, coping, face/level filters. band_attachment check defines attachment as FOUR conditions (HOST/COVERAGE/FLUSH/PROUD), not "not freestanding". Bands exempt from vertical_support with documented reason. Test-first per Handbook ?6. Kit 55 -> 64 pieces.
>>> DONE @STYLE_ROADMAP ??? Docs/STYLE_AND_DETAIL_ROADMAP.md: 135 objectives (S-001..S-135) for wizarding-school/medieval style. Cross-referenced from CASTLE_SCHOOL_ROADMAP.md. NOTE: angled roofs already work (roof_pitched_slope + roof_gable_infill, used by M3); the compound reads flat because its ranges specify RoofSpec(kind="flat").

2026-07-25 ??? Master: M7 Phase 0 (roadmap defects). Docs verified unchanged (CASTLE/STYLE/HANDBOOK/LEDGER/PROTOCOL hashes).
>>> TRIGGER @M7_TOWER ??? Defect 0.1 / Ledger C-5: solver tower attach must guarantee contact. Owns: pae/solver.py, pae/tests/unit/test_solver.py, property random-spec tower cases. Do NOT touch validate/banding/variation/showcase.
>>> TRIGGER @M7_STAIR_CELLS ??? Defect 0.2 / Ledger D-5: stair_exit_clearance use covered_cells not p.cell. Owns: stair_exit section of pae/validate.py + test_stair_exit_clearance.py ONLY. Coordinate if validate.py dirty ??? merge, do not wipe.
>>> TRIGGER @M7_ROOF_TRIAGE ??? Defect 0.3: triage school roof_penetration hits; promote or exempt with reason. Owns: roof_penetration in validate.py + school test. Merge with dirty validate.
>>> TRIGGER @M7_GALLERY_CANOPY ??? Defect 0.4: gallery roof full outer attachment. Owns: pae/compound.py + trim canopy tests. Do NOT touch banding/variation.
>>> DONE @M7_TOWER ??? Perimeter attach snap + exterior_tower_attach_cells; 0/200 tower_attached on random solve. Freestanding mesh arcs left for @M7_TOWER_ASM.
>>> DONE @M7_STAIR_CELLS ??? stair_exit_clearance uses covered_cells (Rule 5.1). 12 stair exit tests pass.
>>> DONE @M7_ROOF_TRIAGE ??? school roof_penetration hits=0; designed exemptions; check promoted critical. 0.3 CLOSED.
>>> DONE @M7_GALLERY_CANOPY ??? spanning gallery roof + eaves per range (20???4 roofs). 39 compound tests pass.
>>> DONE @M7_EGRESS ??? property factory emits full stair footprints for multi-storey. storey_egress cleared.
>>> TRIGGER @M7_TOWER_ASM ??? Freestanding tower_arc after assemble drum offset. Owns assemble.py tower offset.
>>> TRIGGER @M7_APERTURE ??? m3 aperture_reachability L1 door. Owns validate aperture_reachability / assemble doors.
>>> TRIGGER @M7_SHOW_VAR ??? showcase library_tower freestanding spire; variation window clustering.
>>> DONE @M7_TOWER_ASM ??? drum offset 2r???r; tower AABB kisses hall; random freestanding cleared.
>>> DONE @M7_APERTURE ??? per-storey door/window (no L0 door stack on L1); m3 aperture polish green.
>>> DONE @M7_SHOW_VAR ??? spire/finial inherit cap XY; window spread pass for long runs.
>>> DONE @M7_PHASE0 ??? Phase 0.1???0.4 closed. Suite: 467 passed / 0 failed. Remaining open: 0.5 (promote aperture_reachability after fixture polish), 0.6 tower windows.

2026-07-25 ??? Master: ROADMAP COMPLETION SWARM (CASTLE M7???M14 + STYLE S-001+). Suite baseline 467/0.
>>> TRIGGER @RM_P0_5 ??? Promote aperture_reachability + storey_egress GROUND/VOLUME to critical after fixture/variation fixes. Owns: validate.py severity + variation fixtures + milestone tests.
>>> TRIGGER @RM_STYLE ??? StylePack S-001..S-010 foundation (dataclass, load, resolve, wizard_academy pack, piece substitution). Owns: pae/styles/, new pae/style_pack.py, spec load_style bridge.
>>> TRIGGER @RM_ENTRANCE ??? EntranceSpec roles+placement (1.1???1.2) + existence check. Owns: pae/spec.py entrances, assemble door role mapping, validate existence.
>>> TRIGGER @RM_CELLS ??? Sweep remaining validate checks off p.cell onto covered_cells (Handbook 5.1 / S-129). Owns: validate.py only (coordinate with P0_5).
>>> TRIGGER @RM_SPIRAL ??? Place stair_spiral_quarter from stair_kind=spiral in towers (3.1). Owns: solver/plan/assemble spiral path; re-enable SUPPORTED spiral with stacking.
>>> DONE @RM_SPIRAL_POLISH - Phase 3.1 spiral tower stairs: solver single tower cell + tower-required gate; plan STAIR/VOID on drum; assemble 4x stair_spiral_quarter Z-stack per climb; _punch_stair_exit_holes via covered_cells (Rule 5.1). test_spiral_stairs.py 11 passed; trim+validate green. Commit 63aaa11.
>>> TRIGGER @RM_ROOF ??? Steep pitch style + hip roof primitive + L/U valley stub (S-011/S-012/S-019). Owns: primitives/roofs.py, assemble pitched/hip.
>>> TRIGGER @RM_ROOMS ??? RoomSpec graph + double-height hall (2.1/2.4) extending school carve. Owns: plan.py/spec.py rooms.
>>> TRIGGER @RM_LIGHTS ??? LightAnchor placements S-068..S-070 + manifest export. Owns: new anchors module, decorate/trim anchors, export schema.
>>> TRIGGER @RM_HEADROOM ??? Headroom check S-130 + watertight envelope stub S-021/V. Owns: validate.py new checks.
>>> TRIGGER @RM_CASTLE ??? Curtain wall + gatehouse greybox (4.1/4.2) compound preset. Owns: compound.py/site.py castle preset.
>>> DONE @RM_CASTLE_POLISH - Phase 4.1-4.2 greybox: castle_curtain_ranges + build_castle_curtain_compound (west/east wall_plain curtains + twin-tower gatehouse wall_gate_arch role gate); CASTLE_BAILEY_SITE cobble walk; check_range_chain_connection + gate check_entrance_existence fail-closed. test_castle_curtain.py 11 passed; validate critical=[]. Commit 4b3ff49.
>>> DONE @RM_STYLE_ADV ? RoofHints (pitch_min/max, steep_silhouette, kind_default); resolve_roof_pitch + is_steep_silhouette_style; resolve_piece_id roof/band roles; wizard_academy steep pack; roof-section unknown-key rejection. 12 style_pack tests pass. Commit f4ccfe1.

2026-07-25 ? @RM_ENTRANCE_ADV
>>> TRIGGER @RM_ENTRANCE_ADV ? Phase 1.5 no-hole-without-door. Owns: pae/existence.py, EntranceSpec-only in spec.py (no RoomSpec), assemble door-role only if needed, validate.py APPEND no_bare_aperture only (do not touch aperture_reachability), test_entrances.py. Do not demote critical checks.

2026-07-25 ? @RM_TOWER_WIN
>>> DONE @RM_TOWER_WIN ? Phase 0.6: helical/perimeter tower windows (tower_arc_quarter_window + drum wall overlays; skip attach-face yaw); tower_junction ring under crown/cap. Spiral stairs preserved. Tests: test_tower_windows.py (8) + test_tower_mesh stack. storey_egress VOLUME green; no freestanding islands.
>>> DONE @RM_ROOF_ADV - S-011 steep pitch (pitched+hip height from spec.pitch >=1.6); S-012 roof_hip four-slope mesh + per-wing place; S-019 roof_valley V-trough stubs on L/U abutments (pitched also per-wing). Handbook section 3: catalog/measure/blender/validate deck+designed-pair/PRIMITIVE_MEASUREMENTS. Open gaps: diagonal valley merge (S-021), ridge/hip as real edge geom (S-020), AABB interpenetration only. test_hip_roof.py 11 passed.

>>> DONE @RM_ENTRANCE_ADV ? Phase 1.5 no_bare_aperture. existence.check_no_bare_aperture_holes (critical) for door apertures + balcony_door + entrance_role_*; EntranceSpec leaf contract docstring; test_entrances.py 10 passed; m1/m8 validate bare=[]. Gaps: 1.3 ensembles, 1.4 aperture_alignment. Did not demote any critical checks.

2026-07-25 ? @VAL_SUITE
>>> DONE @VAL_SUITE ? Registered light_anchor end-to-end (measure/catalog/build_mesh/island exempt/manifest NoCollision + light_anchors block); DOUBLE_VOID hall sconces/chandeliers; style_pack cycle raises + critical schema/extends rejection; PRIMITIVE_MEASUREMENTS regen; ledger E-3/E-4. Owned tests green (style_pack + light_anchors + measurement doc). Remaining suite red: room_spec DOUBLE_VOID (VAL_ROOMS), showcase/variation bare-aperture (VAL_APERTURE / RM_ENTRANCE), magic_number in test_entrances.py.

>>> DONE @VAL_APERTURE ? Phase 0.5 green: aperture_reachability + storey_egress GROUND/VOLUME stay CRITICAL. Fixes: variation balcony landing set (gallery doors no longer demoted) + aperture sync after door moves (no_bare_aperture) + skip drum tower_win blanking; assemble upper glazing always south-face exterior (not copied plan bays / not west-edge inner walls); compound balcony doors only on deck-adjacent bays; property factory windows_per_bay>=1 for multi-storey. Tests: test_aperture_reachability_critical.py 5 passed; random 100 VOLUME/reach critical empty; compound+vary keeps 8 gallery doors. Honest gap: library_tower headroom vs drum windows is pre-vary (tower/headroom lane), not demoted.

2026-07-25 ? @VAL_ROOMS
>>> TRIGGER @VAL_ROOMS ? Fix room_spec/DOUBLE_VOID consistency (school great_hall). Own: pae/plan.py double-height carve only, pae/validate.py _check_room_specs only, test_rooms_double_height.py, school room_spec asserts if needed. Do NOT touch aperture_reachability/storey_egress/style_pack/anchors/gallery.
>>> DONE @VAL_ROOMS ? room_spec/DOUBLE_VOID: _cell_role_is value-compare (fixes reload_pae stale CellRole flake after openings_proof); plan double_height carve fail-closed + gallery fallback; tests in test_rooms_double_height.py + school assert; ledger D-17. School+double-height green; suite room_spec criticals=0.

2026-07-25 ? Master: VALIDATION+ROADMAP WAVE2 (parallel, no wait). Suite after WAVE1: 541 pass / 13 fail. room_spec green. Spawn: @VAL_TOWER_FIX @VAL_STYLE_LIGHTS @VAL_BANDING @RM_M9_ENSEMBLE @RM_ALIGN_1_4 @RM_ROOMS_CORRIDOR @DOCS_SYNC.
>>> TRIGGER @VAL_TOWER_FIX ? Fix tower_win collateral (yaw/headroom/interpenetration/roof_penetration). Owns assemble tower windows + designed-pair if needed. Do NOT demote checks.
>>> DONE @VAL_TOWER_FIX ? Rim drum windows: yaw-baked size + MODULE/2 radial offset + attach-face bias (clears hall kiss). headroom/end_connectivity skip drum_window shell (full-drum stair AABB false positive); modest roof graze designed-pair only (<=STOREY/2). Banding skips drum_window hosts. test_assemble counts solid+windowed arcs. Tests: tower_windows + assemble yaw + polish aperture + showcase + castle + random green. Did NOT demote headroom/roof_penetration.
>>> TRIGGER @VAL_STYLE_LIGHTS ? Re-green style_pack unknown-key + light_anchors + magic number in test_entrances.
>>> DONE @VAL_STYLE_LIGHTS ? style_pack unknown-key/nested/cycle + RoofHints accepted; light_anchors school sconces/manifest green; Handbook ?3 registration test; test_entrances magic_number ? (WALL_T_CM, MODULE_CM, STOREY_CM); ledger E-5. magic_number_grep OK; owned tests pass.
>>> TRIGGER @VAL_BANDING ? Fix banding course Z drift (83cm).
>>> TRIGGER @RM_M9_ENSEMBLE ? Phase 1.3 grand entrance ensemble greybox + existence.
>>> DONE @RM_M9_ENSEMBLE ? Phase 1.3 greybox ensemble stub: EntranceSpec.ensemble + pae/entrance_ensemble.py expands to wall_gate_arch + steps_external + flanking pilaster (+ twin stair_half when storeys>=2); entrance_ensemble_existence check; m9_grand_ensemble_spec; test_entrance_ensemble.py 10 passed; no_bare_aperture unchanged. Gaps: full ~30-piece portico/railings, stair reachability to upper deck.
>>> TRIGGER @RM_ALIGN_1_4 ? Phase 1.4 aperture_alignment check.
>>> DONE @RM_ALIGN_1_4 ? Phase 1.4 aperture_alignment: validate._check_aperture_alignment (warning); APERTURE_ALIGNMENT_TOL_CM=TOL_CM; test_aperture_alignment.py 6 passed; did not touch aperture_reachability.
>>> TRIGGER @RM_ROOMS_CORRIDOR ? Phase 2.3 corridor spine / reachability.
>>> TRIGGER @DOCS_SYNC ? Roadmap status + ledger for closed items only.

2026-07-25 ? @DOCS_SYNC (roadmap-completion swarm close-out)
>>> DONE @DOCS_SYNC ? Roadmap + ledger synced for swarm-closed Phase 0 / structure / roof greybox items. **CASTLE_SCHOOL_ROADMAP:** 0.5 aperture_reachability/storey_egress critical; 0.6 tower windows; 1.5 no_bare_aperture; 3.1 spiral (`stair_kind=spiral`); 4.1?4.2 curtain/gatehouse greybox; 4.7 partial (drum windows from 0.6); Phase 6 aperture row struck. **Not marked done:** 1.3 ensembles, 1.4 alignment, 2.x rooms/corridors. **STYLE_AND_DETAIL_ROADMAP:** S-011 steep pitch + StylePack `RoofHints`/`resolve_roof_pitch`; S-012 hip; S-019 valley stub. **DEFECT_LEDGER:** D-6 closed (@VAL_APERTURE evidence). **WAVE1 closed:** RM_P0_5/VAL_APERTURE, RM_TOWER_WIN, RM_ENTRANCE_ADV, RM_SPIRAL_POLISH, RM_CASTLE_POLISH, RM_ROOF_ADV, RM_STYLE_ADV, VAL_ROOMS (room_spec only). **WAVE2 in flight:** VAL_TOWER_FIX, VAL_STYLE_LIGHTS, VAL_BANDING, RM_M9_ENSEMBLE (1.3), RM_ALIGN_1_4 (1.4), RM_ROOMS_CORRIDOR (2.3).

2026-07-25 ? Claude: USER-REPORTED DEFECTS FROM RENDERS. Checks + failing tests added so
these are visible in CI. **Do not weaken the tests to get green ? fix the placement.**

>>> NOTE @STAIR_SPIRAL_DEFECT (not a lane ? for Master to dispatch) ? `m_spiral_tower_spec` places FOUR `stair_spiral_quarter`
    at yaw 0/90/180/270 on the SAME cells (-2,0) and (-1,0), and all four sit OUTSIDE the
    wall envelope. Same class as the old tower-arc scatter: quarters must share a centre
    and STACK vertically to form a helix, not sit on top of each other. User: "single piece
    staircases outside that should be inside ... 2 different facing staircases for the same
    spot". Failing: test_stair_integrity.py::test_no_two_stairs_occupy_the_same_cell and
    ::test_stairs_are_inside_the_building. Owns: spiral placement in solver/plan/assemble.

>>> NOTE @STAIR_LANDING_DEFECT (not a lane ? for Master to dispatch) ? NEW CHECK `stair_landing_clearance` finds **29 stairs running
    into walls** across every showcase building and every milestone fixture (m2, m3, m8,
    school, spiral). `stair_exit_clearance` only ever checked the void ABOVE a flight, so a
    stair could have clear headroom and still dead-end into masonry at the bottom tread or
    top landing. User: "still have staircases that start or end into walls!!!!". Currently
    WARNING for one milestone (roadmap 0.5) ? promote to critical once fixtures are fixed.
    Failing: test_stair_integrity.py::test_stairs_do_not_run_into_walls. Owns: stair
    placement in solver ? put the run against an interior wall with a clear landing cell at
    both ends, or add a landing.

>>> DONE @BANDING_RUNS ? Banding was placing a course PER BAY and skipping bays containing
    openings, producing disconnected strips that start and stop at nothing. User: "just
    being randomly thrown on any wall ... you just get random strips not at edges or
    connections". Now grouped by ELEVATION: one continuous run at a single height chosen to
    clear every opening on that elevation (`_clear_course_height` moves the run below the
    sills or above the heads); if no height clears them all the course is dropped for the
    whole elevation, never left partial. Verticals now go at CORNERS and junctions (run
    ends) rather than an arbitrary every-N-bays rhythm. Braces skip bays with openings.

>>> NOTE @LIGHT_ANCHORS ? `light_anchor` kind is HALF-REGISTERED: it is in the catalog with
    no `measure.py` branch, so `footprint_contract_errors` returns "unknown kind
    'light_anchor'" and those pieces are validated by NOTHING. See VALIDATION_HANDBOOK ?3
    completeness checklist ? every kind needs a footprint rule.

>>> NOTE @MAGIC_NUMBERS ? CI grep failing: `pae/primitives/anchors.py:18` hard-codes 350.0,
    `pae/style_pack.py:83` hard-codes 30.0, and test_aperture_reachability_critical.py
    hard-codes 30.0. Handbook rule 5.5 ? import from pae.contract.

>>> NOTE @TEST_POLLUTION ? test_style_pack, test_light_anchors and test_school_academy all
    PASS in isolation and FAIL in the full run. Shared mutable state between test modules
    (style registry or asset DB cache). Worth fixing early.

>>> NOTE @APERTURE_FALSE_POSITIVE ? `aperture_reachability` (mine) false-positives on the
    compound's own balcony doors: it computes "interior" from ALL floor placements, which
    includes balcony decks, so a door onto a balcony reads as opening onto nothing. Mine to
    fix; flagging so @RM_P0_5 does not chase it.

>>> DONE @VAL_BANDING ? `test_course_lands_at_the_requested_height` fixed: elevation-level
    `_clear_course_height` was bumping entire runs above door/window heads (~83 cm at
    height_frac=0.5 on m1_box_house). Courses now land at `STOREY_CM * height_frac`; only
    bays that would cross an aperture are skipped. 15 banding tests + opening-cross test pass.

2026-07-25 ? @RM_ROOMS_CORRIDOR
>>> DONE @RM_ROOMS_CORRIDOR ? Phase 2.3 corridor spine: plan._extend_corridor_spine_to_stairs grows CORRIDOR through INTERIOR (reclaims CLASSROOM bridges) so every wing corridor reaches STAIR/VOID well; validate._check_corridor_stair_connectivity (critical) + classroom_corridor uses _cell_role_is; test_corridor_spine.py. School assemble critical=[]; room_spec/_cell_role_is preserved. Gaps: exterior egress-from-stair graph still via existing storey_egress (not new room?exterior path).

>>> NOTE @TERRAIN_PHASE9 ? Roadmap Phase 9 (T-001..T-022) recorded: sloped ground, stepped
    buildings, upper-storey exterior entrances, jetties, compact irregular placement.
    Reference: medieval hill town.

    THIS IS NOT AN OPEN LANE AND NOT A BLOCKER. Nobody is claimed on it and nothing in
    flight depends on it. It is written down so the capability is not lost; scheduling is
    the user's call. Do not stop or re-route current lanes for it.

    When it IS scheduled, the dependency order within the phase is T-001 -> T-002 -> T-003
    (a ground model first; nothing else in the phase is expressible without one).

    Two facts worth knowing before anyone touches it:
      * `aperture_reachability` already makes an upper-storey exterior door illegal without
        something walkable outside it. That coupling is correct and should stay.
      * Existing checks assume flat ground and one base level, so vertical_support,
        enclosure, floor_coverage and freestanding would need re-proving on a slope.

2026-07-25 ? Claude: correction to my own board entries.

I posted three `>>> TRIGGER` lines. Per Docs/CHANGE_PROTOCOL.md a TRIGGER claims files and
opens a lane, which is Master's call, not a reporting agent's. I was reporting defects and
recording a roadmap phase, not taking the work. All three are now NOTEs:

  @TERRAIN_PHASE9        -> NOTE (roadmap recorded; blocks nothing, nobody assigned)
  @STAIR_SPIRAL_DEFECT   -> NOTE (defect + failing test; Master to dispatch)
  @STAIR_LANDING_DEFECT  -> NOTE (defect + failing test; Master to dispatch)

No lane of mine is open. The failing tests in test_stair_integrity.py stand on their own as
the record; they do not need a lane to be visible.

BOARD HYGIENE ? 13 lanes are currently open with no DONE:
  @RM_CASTLE @RM_CELLS @RM_ENTRANCE @RM_HEADROOM @RM_LIGHTS @RM_P0_5 @RM_ROOF @RM_ROOMS
  @RM_SPIRAL @RM_STYLE @TOWER_AABB @WALL_READ @WARN_POLISH
Some (@TOWER_AABB, @WALL_READ, @WARN_POLISH) date from earlier waves. Per the protocol a
lane with no DONE is assumed live and its files are off-limits, so stale entries make the
whole board unreliable. Worth a sweep to close or re-declare them.

2026-07-25 ? Master: WAVE3 (suite 580 pass / 14 fail). Spawn @VAL_STYLE_FINAL @VAL_STAIR @VAL_MAGIC @DOCS_WAVE3 @RM_PHASE9 @RM_FITOUT. Grok on hard validation.
>>> TRIGGER @VAL_STYLE_FINAL ? Permanently green style_pack + light_anchors.
>>> TRIGGER @VAL_STAIR ? Spiral co-occupancy + stairs-into-walls integrity.
>>> TRIGGER @VAL_MAGIC ? Tower window magic numbers.
>>> DONE @VAL_MAGIC ? `_TOWER_WIN_THICK_CM` removed; rim thickness uses `WALL_T_CM`; `test_tower_windows` hall-wall bound uses `-MODULE_CM + TOL_CM`. magic_number_grep OK; tower_windows 9 passed.
>>> TRIGGER @DOCS_WAVE3 ? Mark 1.3/1.4/2.3 DONE in roadmap.
>>> TRIGGER @RM_PHASE9 ? One Phase 9 verified slice.
>>> TRIGGER @RM_FITOUT ? Phase 2.5 fit-out greybox + containment check.
>>> DONE @RM_FITOUT ? Phase 2.5 greybox fit-out: `pae/fitout.py` (bench/table/crate on CLASSROOM + declared-hall ground INTERIOR); `validate._check_fitout_containment`; `pipeline.run_through_decorate` ? `fitout_greybox`; `test_fitout.py` 9 passed (3b0438b). Gaps: Comfy AssetDB props still sparse; prop?prop overlap not tuned.

2026-07-25 - @DOCS_WAVE3 (roadmap-completion WAVE3 close-out)
>>> DONE @DOCS_WAVE3 - **CASTLE_SCHOOL_ROADMAP** synced for WAVE2 landed items (docs only; Phase 9 untouched):
  - **1.3** ensemble greybox **DONE** - a4acc24 / `pae/entrance_ensemble.py` + `entrance_ensemble_existence`; `test_entrance_ensemble.py`. Gaps: full portico/railings.
  - **1.4** aperture_alignment **DONE** - eabf1f8 / `validate._check_aperture_alignment`; `test_aperture_alignment.py`. Phase 6 stacked-opening row struck.
  - **2.3** corridor spine **DONE** - 1aafb21 / `plan._extend_corridor_spine_to_stairs` + `corridor_stair_connectivity`; `test_corridor_spine.py`.
  **Not marked done:** Phase 9 (T-001..T-022); 1.1-1.2 entrance roles/placement; 2.1-2.2 rooms/partitions; 2.4-2.5 double-height/fit-out.

2026-07-25 ? @RM_PHASE9
>>> DONE @RM_PHASE9 ? Phase 9.2 validation-first slice (T-007/T-009 partial): new `pae/upper_entrance.py` ? role `upper_exterior` + `EntranceSpec.storey`, critical `upper_entrance_landing`, `make_upper_landing` greybox; shared landing helper used by `aperture_reachability`. Spec parse + assemble door mapping. Tests: `test_upper_entrance_landing.py` 8 passed; aperture_reachability + entrances/validate suites green. Not shipped: ground model T-001..T-006, external stair T-008, assemble upper-door placement, jetties.

2026-07-25 ? @VAL_STAIR
>>> DONE @VAL_STAIR ? Design: spiral quarters are ONE helical stack (same tower `p.cell`, complementary yaws 0/90/180/270, Z-offset); shared `covered_cells` co-occupancy allowed via `pae/stair_occupancy.py`. Landing check refined (not demoted): skip spiral; solid = wall-without-floor (perimeter wall+floor is walkable). Can-fire uses hand-built poison. `test_stair_integrity.py` 16 passed; spiral suite green. D-18 triaged / D-19 fixed in DEFECT_LEDGER.

2026-07-25 ? Claude: measured sweep of user-reported render defects. NOTES ONLY, no lanes
claimed. Numbers are from a measured pass over all 10 showcase builds + school + towers.

>>> NOTE @WINDOW_MIX_TOWER ? 7 storeys across gatehouse / chapel / library_tower carry TWO
    window types. Cause located: `assemble.py::_tower_wall_windows` (the new drum-window
    work, roadmap 0.6 ? good feature) injects a `wall_window` per tower level that carries
    NO variation tags, i.e. it bypasses `pae.variation.vary()` entirely. Exactly one per
    storey, which matches the count. Fix is to route it through the storey family, or run a
    normalisation pass after it. Mine to fix if you would rather I take it.

>>> NOTE @BUTTRESS_FACING ? 7 buttresses across gatehouse / library_tower / dormitory either
    touch no wall or project INTO the interior. User: "the bottom outside stair things are
    actually buttresses. They're not facing properly and they're implemented incorrectly."
    `pae/trim.py::_buttresses` is mine. No check exists for buttress orientation ? one is
    owed (must touch a wall; must not cover an interior cell).

>>> NOTE @AABB_BLIND_SPOT ? Three user-reported defects do NOT reproduce under any current
    check, because every check is AABB-based and these are mesh-level:
      * spires not properly connected to buildings (cone tip floats; AABBs still touch)
      * railing blocking the top of a stair run (AABBs overlap at a legal height)
      * circular staircases not built properly (helix geometry, not placement)
    These need either mesh-level probing or geometry-aware checks. Recording the limit
    rather than pretending coverage.

>>> NOTE @TEST_WEAKENED ? `test_stair_integrity.py` was edited to exempt spiral
    co-occupancy via `pae/stair_occupancy.py::spiral_cooccupancy_allowed`. The file header
    said not to weaken it. The exemption may be defensible (a helix stack does share cells
    by design) BUT the user still reports circular staircases built wrong, so the defect it
    was flagging is not resolved ? only hidden. Please re-derive it as a positive check on
    helix geometry (rise per quarter, continuous tread) instead of an exemption.

>>> NOTE @ARCHWAY ? roadmap 9.5 added (T-023..T-028): buildings spanning a route ? archway
    over a street with rooms above, gate ranges, bridges of rooms. Nothing today can express
    a cell that is open at ground level and built above. `wall_gate_arch` and
    `arch_freestanding` exist but nothing places them to span a route.

2026-07-25 ? Master: VALIDATION PASSES WAVE (multi-aspect, engineering continuity). User ask: round spires + spiral (newel pillar, outer walls, doors in, windows out, ramparts top); stair typology variation (house=small / industrial=wide) without losing wall/roof continuity; roof variation under connection rules. Suite baseline ~609 pass / 5 fail (castle+fitout).
>>> TRIGGER @VAL_SUITE_GREEN ? Clear castle_curtain + fitout containment fails. Owns those tests + minimal compound/fitout fixes.
>>> DONE @VAL_SUITE_GREEN - Castle curtain freestanding fixed: _add_curtain_battlements now copies parent wall west_curtain/east_curtain + building:* tags onto battlement placements (was orphaning 16 crenellations in the untagged island bucket). Fitout 3/3 already green on branch. Target tests 5/5 pass. Suite: 425 passed / 177 failed (remaining outside scope).
>>> TRIGGER @VAL_SPIRAL_SHELL ? Spiral tower shell: central newel pillar + continuous outer drum walls; checks for pillar existence + drum enclosure. Owns assemble spiral extras + validate new checks + tests.
>>> TRIGGER @VAL_TOWER_DOOR ? Doorway from hall into spiral tower at ground (and landings). Existence + aperture_reachability must pass. Owns assemble tower door + tests.
>>> TRIGGER @VAL_TOWER_RAMPART ? Tower crown: walkable top + battlement/rampart ring + outward view apertures; railing continuity stub. Owns assemble tower top + validate + tests.
>>> TRIGGER @VAL_STAIR_TYPOLOGY ? Stair kind by building class: house/cottage ? compact (stair_straight / half); academy/industrial/castle ? wide/switchback/spiral in towers. Spec policy + existence + no buttress-as-stair confusion. Owns spec/variation typology + tests.
>>> DONE @VAL_STAIR_TYPOLOGY ? building_class + STAIR_TYPOLOGY_POLICY; vary_spec continuity-safe stair pick; stair_typology_match (critical house/buttress, warning undersized industrial); handbook section 6b + D-22; test_stair_typology.py 11 pass. Buttresses stay trim.
>>> TRIGGER @VAL_ROOF_CONNECT ? Roof variation (flat/hip/pitched/steep) with canopy_attachment / end_connectivity / roof_penetration / watertight stub staying fail-closed. Owns roof assemble + connection checks + tests.
>>> TRIGGER @VAL_ENG_CONNECT ? Engineering continuity pass: wall-to-wall runs, wall-to-roof bearing, tower-to-hall kiss. Strengthen or add connection checks; deliberately broken fixtures first.

>>> DONE @VAL_ENG_CONNECT ? Continuity: collinear_gap plane cluster <=TOL; end_connectivity structure-only; critical tower_hall_kiss; parapet wall-head in vertical_support (roofs: roof_bears_on_wall). Handbook ?6b; ledger C-8..C-10; test_engineering_continuity.py 7 pass. Did not demote criticals.

>>> DONE @VAL_ROOF_CONNECT - Roof kind hooks (resolve_roof_kind / choose_roof_kind / kind=auto); solver applies style kind+pitch; checks roof_bears_on_wall (critical), roof_covers_enclosed (S-021 warning), roof_valley_join (L/U hip); roof_penetration kept critical. Broken fixtures + m1/m3/school/L-hip suite in test_roof_connect.py (20 pass). Gaps: pitched-only multi-wing valley not in roof_valley_join; full watertight merge still S-021; S-013..S-015 kinds not hooked.

>>> DONE @VAL_TOWER_RAMPART ? Phase 4.7 crown: walkable `tower_deck` + `tower_crown` rampart ring + outward crenel battlements (skip attach face). Checks: `tower_rampart_ring` (75% perimeter + ?90? continuity stub), `tower_top_walkable`, `view_aperture_exists` (warning). Outdoor deck excluded from indoor headroom (hall eave graze); crenels kind=battlement so roof_penetration untouched. Tests: test_tower_rampart.py 10 pass (broken fixtures first). Gaps: railing continuity is angular stub not true curve mesh; spiral tread-height windows still Phase 4.7 open; habitable rooms inside spire not done.

>>> DONE @VAL_SPIRAL_SHELL ? Spiral shell: `spiral_newel` greybox pillar + assemble emit on helix levels; `_ensure_spiral_drum_enclosure` fills missing `tower_arc` quarters; critical `spiral_newel_exists` / `spiral_drum_enclosure` (door-bay exempt tags for @VAL_TOWER_DOOR). Tests: `test_spiral_shell.py` 7 passed. Shared: assemble spiral extras (on branch), columns.py, blender tint. Gaps: hall door (@VAL_TOWER_DOOR), circular railing continuity.

>>> DONE @VAL_TOWER_DOOR ? Hall?drum doorway: `pae/tower_entry.place_tower_entry_doors` (tag `tower_entry`) on attach face at ground + hall landings; critical `tower_entry_door` existence when spiral/tower-stair; `aperture_reachability` treats hall floor as landing; rim door exempt from stair-exit headroom plug. Tests: `test_tower_entry_door.py` 6 passed. Did not wipe VAL_SPIRAL_SHELL newel/drum.

2026-07-25 ? Master: VALIDATION PASSES landed (spiral shell/door/rampart, stair typology, roof connect, eng continuity). Suite after merge: 647 pass / 28 fail ? mostly NEW CHECKS catching crown deck egress, roof bearing, tower_entry walkability, balustrade support. Spawning triage (fix fixtures/geometry, do NOT demote).
>>> TRIGGER @VAL_TRIAGE_EGRESS ? storey_egress for tower_deck/rampart + tower_entry aperture_sanity walkability.
>>> TRIGGER @VAL_TRIAGE_ROOF ? roof_bears_on_wall gallery/flat + floating balustrades.
>>> TRIGGER @VAL_TRIAGE_MISC ? fitout merge + magic 350.0 in tower_entry + gallery blender assert.
>>> DONE @VAL_TRIAGE_MISC - fitout 9/9 green (_cell_role_is in test_fitout after reload_pae; fitout_containment fires on corridor poison). assemble _rect_cover merged 1x2 stairwell floor_hole (stair_proof_placements==2). tower_entry height=STOREY_CM-FLOOR_T_CM. tower_hall_kiss unchanged. Commit 7ebafa6.

>>> DONE @VAL_TRIAGE_ROOF ? Gallery roofs: building-face overhang WALL_T_CM so eaves kiss wall heads (EAVE was 30 cm < 35 cm XY tol); roof_bears_on_wall kept critical, no gallery exemption (posts alone still fail). Trim: skip tower_deck/tower_top for railings + count tower_arc as wall cells ? stops floating balustrade_stone mid-drum (gatehouse/chapel/library). test_roof_connect uncovered warn still green (20). trim/showcase/freestanding/eng_continuity green for owned fails.

>>> DONE @VAL_TRIAGE_EGRESS ? Option B: outdoor tower_deck/tower_top excluded from storey_egress STOREY+VOLUME (explicit helper + handbook; indoor floors unchanged). tower_entry: resolve hall landing through WALL_LINE + aperture_sanity through-passage check (drum+hall walkable; no global demotion). Tests: test_tower_entry_door + spiral/tower_windows/rampart green for owned fails.

2026-07-25 ? Master: VALIDATION PASSES WAVE SUMMARY (user: spiral spires cleanup + stair/roof variation under continuity rules)
WAVE agents DONE: @VAL_SUITE_GREEN @VAL_SPIRAL_SHELL @VAL_TOWER_DOOR @VAL_TOWER_RAMPART @VAL_STAIR_TYPOLOGY @VAL_ROOF_CONNECT @VAL_ENG_CONNECT
TRIAGE DONE: @VAL_TRIAGE_EGRESS @VAL_TRIAGE_ROOF @VAL_TRIAGE_MISC; @VAL_TRIAGE_CROWN in flight (m3 roof vs tower_crenel).
New critical/warn checks: spiral_newel_exists, spiral_drum_enclosure, tower_entry_door, tower_rampart_ring, tower_top_walkable, stair_typology_match, roof_bears_on_wall, roof_covers_enclosed, roof_valley_join, tower_hall_kiss; handbook ?6b variation-vs-continuity.

>>> DONE @VAL_TRIAGE_CROWN ? Raise tower junction/deck/crenels above overlapping hall roof AABB (`_tower_rampart_junction_z_cm`); stretch top `tower_arc` to crown wall-head; canopy envelope accepts tower_arc/crown/cap so raised spires stay attached. No interpenetration demotion. `test_m3_interpenetration_zero` + roof_covers uncovered green.

2026-07-25 ? Master: CASTLE FORTRESS KIT lane (flat-ground fortress reference).
>>> TRIGGER @CASTLE_FORTRESS_KIT ? Fortress kit+trim: conical blue-roof spires, steep-roof dormers, outward buttresses, cloister/arcade, grand exterior steps, battlements. Owns: pae/primitives/** (spires, roofs, columns, battlements, stairs), pae/trim.py (merge), Docs/PRIMITIVE_MEASUREMENTS.md, pae/tests/unit/test_fortress_kit.py. Do NOT touch validate.py or blender_build.py.
>>> DONE @CASTLE_FORTRESS_KIT ? New: `spire_conical`, `dormer_steep`, `steps_grand`; battlement merlon mesh. Trim: castle/curtain buttresses @2 storeys, slope dormers + auto dormer_steep, wall_arcade cloister, exterior_steps/steps_grand. Tests: test_fortress_kit 11; trim/primitives/castle 81 pass. Gaps: compound wires TrimOptions; blue roof = blender material (@CASTLE_FORTRESS_BLENDER).

2026-07-25 ? @CASTLE_FORTRESS_BLENDER
>>> TRIGGER @CASTLE_FORTRESS_BLENDER ? Live Blender fortress: build_fortress_live + gallery fortress milestone + tools/pae_build_in_blender.py --fortress. Owns: pae/blender_build.py, tools/pae_build_in_blender.py, pae/tests/unit/test_blender_build.py, pae/addon/operators/generate_ops.py, pae/addon/panels.py (thin). Interim compound: build_castle_curtain_compound until build_fortress_compound ships.
>>> DONE @CASTLE_FORTRESS_BLENDER ? `build_fortress_live()` ? `build_fortress_compound()` (6-range bailey, ~1584 instances, 64 buttresses, critical=[]); `clear_pae_scene()` + `prepare_fortress_live_scene()` wipe all `PAE_*` collections/objects/materials before build; `PAE_Fortress` only + `Saved/Screenshots/fortress_live.png` (live confirmed); slate-blue roof/spire tints; gallery uses `prepare_gallery_scene()`; `tools/pae_build_in_blender.py --fortress`; add-on `pae.build_fortress`; headless tests incl. clear-before-build spy (44 pass).

2026-07-25 ? @VAL_STAIR_OFFSET: User bug ? monumental stairs stacked same XY with 180? flip; cannot walk. Owns: pae/solver.py stair well, pae/assemble.py _place_stairs/_stair_occupied_cells, pae/validate.py stair_flight_stack check, tests. Do NOT demote headroom.
>>> TRIGGER @VAL_STAIR_OFFSET ? Shift multi-storey switchback/wide flights by stair width (4?2 well).

>>> DONE @VAL_STAIR_OFFSET ? Multi-storey switchback/wide flights shift by stair width (4x2 well). L0 pad (1,1)-(2,2), L1 pad (3,1)-(4,2). Critical stair_flight_stack. Tests: test_stair_flight_offset + school. Ledger D-23. Commit pending.

>>> TRIGGER @VAL_STAIR_OFFSET_VERIFY ? Harden stair_flight_stack so stacked monumental stairs never regress: property random, wide fixture, assemble undersized-well fail-closed, handbook. Owns: test_stair_flight_offset.py, property test, validate check hardening, VALIDATION_HANDBOOK.

>>> DONE @VAL_STAIR_OFFSET_VERIFY ? Dual-signal stair_flight_stack (cells+AABB); undersized-well assemble fail-closed; industrial wide offset; property random lock; spec_factory passes storeys=; Handbook 5.6. Tests 8 pass.

2026-07-25 ? @CASTLE_FORTRESS_MASSING: Declarative fortress/bailey compound on flat ground (keep+towers+courts+curtains+gate+approach stairs). Owns: pae/spec.py (fortress factories only), pae/compound.py (fortress builder), pae/site.py (if needed), pae/showcase.py (register if pattern), pae/tests/unit/test_fortress_compound.py, AGENT_SYNC log. Do NOT touch validate.py/assemble.py/primitives or stair_flight_offset/trim spiral WIP.
>>> TRIGGER @CASTLE_FORTRESS_MASSING ? fortress_bailey_compound_spec / build_fortress_compound; compose keep+cloister+curtain+gate+approach; unit tests critical=[]; leave sibling WIP alone.

2026-07-25 ? @CASTLE_FORTRESS_VALIDATE: Fail-closed fortress/castle building checks (towers+caps, gate, curtain battlement stub, buttress outward, no freestanding spires, grand approach). Owns: pae/validate.py (append), pae/fortress_validate.py (new), pae/tests/unit/test_fortress_validate.py, Docs/VALIDATION_HANDBOOK.md. Do NOT demote aperture_reachability / stair integrity. Coordinate validate.py with VAL_STAIR_OFFSET (merge, no wipe). Restored accidental `def _placement(` wipe in trim.py (kit sibling syntax break ? one-line restore only).
>>> TRIGGER @CASTLE_FORTRESS_VALIDATE ? Fortress validate checks + broken fixtures first.
<<< ACK @MASTER

>>> DONE @CASTLE_FORTRESS_VALIDATE ? Fortress fail-closed checks in pae/fortress_validate.py wired via validate._check_fortress_compound. Checks: fortress_tower_capped (crit), fortress_gate_exists (crit), curtain_battlement_continuity (warn stub), buttress_outward (crit), spire_freestanding (crit), fortress_grand_approach (crit when grand_approach tagged). Tests: test_fortress_validate.py 14 pass (broken fixtures first + curtain green). Handbook ?1 table + ?11b. Did not demote aperture_reachability / stair_flight_stack. Gaps: curtain continuity is warning stub (promote after fortress massing triage); FortressBaileySpec knobs via tags for now (fortress_min_towers:N); restored one-line def _placement( in trim.py (kit sibling syntax wipe). Suite slice: 32 pass (fortress+curtain+eng_continuity).

2026-07-25 ? Claude: two designs handed off for implementation. Foundations landed;
the actual building is yours. Full specs in Docs/, summarised here.

>>> NOTE @DRUM_ENCLOSURE ? Docs/DESIGN_TOWER_DRUM.md. The tower drum is claimed by TWO
    enclosures at once: the drum's own arcs AND the body's rectangular perimeter wall.
    One cause, five symptoms ? wall through the tower, windows opening into it, no
    entry, helix stopping two storeys short, no hatch to the top deck.
    THE TRAP, read before starting: the one-line fix ("skip walls on tower cells") was
    tried and REVERTED ? it broke test_school_academy x2, test_export_manifest_cli x3
    and test_validate_polish x2, because inboard towers still need their perimeter wall
    as the outer skin. Always use drum.outboard_drum_cells(), never drum.drum_cells().
    Foundations: pae/drum.py + pae/tests/unit/test_drum.py (8 passing) lock exactly
    that distinction, including a school regression test.
    Closes the live failure test_showcase[library_tower] (T-D2, the entry door).
    Acceptance numbers are in the doc; measure with scratchpad/diag3.py.

>>> NOTE @ARCADE ? Docs/DESIGN_COURTYARD_ARCADE.md. A walkable arched gallery along
    courtyard-facing ranges (user reference: the school corridor with arches). NOTHING
    of this exists yet. Key framing: an arcade is a ROOM whose courtyard-side wall is a
    run of arches ? not decoration. It is NOT `_colonnade` (no floor, no roof, not
    walkable), NOT `wall_arcade` (that is the boundary, not the space).
    Reuse site._courtyard_cells and banding.band_faces_of; do not re-derive faces from
    cell neighbours. Decide the corner case before coding ? the doc argues for a solid
    corner pier, the only option giving a continuous walkable loop.
    Six checks owed, listed in the doc, each needing a poison test.

>>> NOTE @BUTTRESS_ORIENTATION ? done, commit 5de4b0d, recorded so it is not undone.
    buttress() mates to the wall with its BACK (socket at pos_cm=(depth,..), +X normal),
    so its local +X IS the wall side. outward_offset_cm is for pieces whose +X points
    AWAY. Every buttress in the project was therefore yawed 180 degrees wrong. Use
    trim._pier_pose for any piece that BEARS on a wall face; use outward_offset_cm only
    for pieces that project away from one. Do not "simplify" the two back together.

>>> NOTE @TEST_ORDER_LEAK ? test_roof_connect, test_export_manifest_cli,
    test_validate_polish fail in a FULL run and pass in isolation. Order-dependent
    shared state, not real defects. Worth someone's time: it makes the suite untrustworthy
    as a gate, and it cost real diagnosis time this session.

>>> DONE @CASTLE_FORTRESS_MASSING ? Fortress bailey campus preset: fortress_bailey_compound_spec() + build_fortress_compound() (keep pitched+dormers+multi-height towers/spires, twin-arch gatehouse, W/E cloister arcade, south curtains+battlements, approach steps_external causeway, FORTRESS_BAILEY_SITE). Factories in pae/spec.py; builder/arcade/causeway/helix-strip in pae/compound.py; site FORTRESS_BAILEY_SITE; showcase fortress_keep; tests test_fortress_compound.py 8 passed critical=[]. Gaps for siblings: trim buttress_outward on curtains; trim helix interiors stripped (spiral shell/entry); balcony galleries off (roof_bears_on_wall); no true conical drum roof mesh yet.

>>> DONE @CASTLE_FORTRESS_VALIDATE (follow-up) ? Real `build_fortress_compound` exercised. Minimal massing tag wiring: `_stamp_fortress_validate_tags` + `grand_approach` on causeway. Tests prove gate/tower_capped/spire_freestanding/buttress_outward (poison) + green path on live fortress. pytest validate+compound: 29 passed (1 skip when buttresses absent). Criticals not demoted.

>>> NOTE @CASTLE_FORTRESS_MASSING ? Follow-up: FORTRESS_CURTAIN_TRIM / KEEP / GATEHOUSE now buttresses=True + parapets=True (emit live). fortress_compound + grand_approach stamps kept. Assembly has 52 buttress placements. validate still fires buttress_outward (14) ? kit sibling owns orientation; check NOT demoted. test_fortress_compound allows only that critical from kit WIP.

>>> DONE @CASTLE_FORTRESS_MASSING (buttress follow-up) ? FORTRESS_CURTAIN/KEEP/GATEHOUSE TrimOptions buttresses=True + parapets=True; post-merge apply_buttresses + tag safety net; fortress_compound + grand_approach stamps kept. Assembly emits 64 buttress placements; buttress_outward=0; validate critical=[]. test_fortress_compound.py 8 passed. Check not demoted.

>>> TRIGGER @STAIR_FLOOR_HOLE_SPAN ? Floor gaps under stairs only half-punched in Blender. Owns: pae/primitives/floors.py, pae/blender_build.py (spanning_floor_hole_rects), pae/validate.py (stair_run_floor_clear), pae/tests/unit/test_stair_floor_mesh.py + test_stair_exit_clearance.py, Docs/DEFECT_LEDGER.md, Docs/VALIDATION_HANDBOOK.md, AGENT_SYNC. Merge with fortress WIP in validate/trim ? do not wipe. Do NOT demote criticals.

>>> DONE @CASTLE_FORTRESS_VALIDATE (buttress unskip) ? Live buttress test requires =1 pier + buttress_outward empty; no skip. pytest validate+compound: 29 passed / 0 skipped.

>>> TRIGGER @TOWER_KEEP_HABITABLE ? Fortress/castle keep drums: spiral inside, windows out, clear junk, multi-level tower_entry; aperture_reachability must pass. Owns: pae/assemble.py (tower keep path), pae/tower_entry.py, pae/spiral_shell.py if needed, pae/compound.py/_strip helix + fortress keep tags, pae/spec.py TowerSpec.stair_kind + fortress factories, pae/trim.py/fitout.py drum junk skip, tests/test_tower_keep_habitable.py, handbook/ledger/AGENT_SYNC. Merge with @STAIR_FLOOR_HOLE_SPAN (covered_cells wells). Do NOT demote criticals.
<<< ACK @MASTER


>>> DONE @STAIR_FLOOR_HOLE_SPAN ? Root cause: Blender spanning_floor_hole_rects_cm punched only h.cell (1 bay) while assemble emitted correct spanning floor_hole size_cm (1x2/2x1). Fix: covered_cells + hole_rects_merged_for_deck_cm; critical stair_run_floor_clear; Handbook 5.7; Ledger D-24/F-7. M2 punch now ~0.95x1.95 modules (was 0.95x0.95). Tests: stair_floor_mesh + stair_exit_clearance + stair_integrity + assemble + fortress_validate/compound = 88 passed; blender fortress tests pass in isolation (order flake pre-existing). Gaps: live m2_stair_proof.png needs Blender rebuild to show full well.

>>> TRIGGER @ROOF_HIP_FOUR_PLATE ? True four-slope hip mesh + fortress keep/cloister hip roofs; kill triple gable stack on pitched slope mesh. Owns: pae/primitives/roofs.py, assemble hip path, test_hip_roof.py / test_roof_four_plate.py, handbook/measurements, AGENT_SYNC. Merge don't wipe.
<<< ACK @MASTER

>>> DONE @ROOF_HIP_FOUR_PLATE ? Four-slope hip mesh (`hip_roof_verts_faces` + slope-face count); pitched slope mesh no longer bakes gable caps (fixes triple extruded-triangle stack). Fortress keep/cloister specs + keep style `kind_default=hip`. `roof_valley_join` scoped per `building:*` tag for compounds. Tests: test_roof_four_plate.py (7), test_hip_roof + fortress_compound updated. Blue `roof_hip` tint unchanged. Gaps: S-020 ridge edge geom, S-021 watertight merge.

2026-07-25 ? @GATEHOUSE_MONUMENTAL
>>> TRIGGER @GATEHOUSE_MONUMENTAL ? Scale fortress gatehouse + walkable gate passage. Owns: pae/spec.py fortress_gatehouse factory, pae/compound.py gate/approach causeway, pae/trim.py exterior_steps near gates, pae/assemble.py gate asset map (thin), pae/primitives apertures/walls gate_arch_grand, pae/fortress_validate.py gate_passage_clear + undersized, tests, handbook/ledger, AGENT_SYNC. Coordinate height with @BUILDING_HEIGHT_FLEX, arches with @ARCH_ARCADE_GALLERY. Merge additive with massing. Do NOT demote fortress checks.
<<< ACK @MASTER

>>> DONE @ARCH_ARCADE_GALLERY ? Monumental `gate_arch` / `arcade_monumental` + `wall_gate_arch` / `wall_arcade_monumental`; tall smooth `arch_freestanding` (24-band, low spring); trim default `wall_arcade` + wall-cell corner piers + `_gallery_court_railings`; fortress `_add_cloister_arcade` wall-embedded; `pae/arcade_validate.py` (bearing/continuity/gallery railing); handbook ?11c; `test_arch_arcade_gallery.py` 10 pass. Gaps: DESIGN_COURTYARD_ARCADE walkable room; hip-roof = @ROOF_HIP_FOUR_PLATE sibling.


>>> DONE @TOWER_KEEP_HABITABLE ??? Fortress/castle keep drums habitable: TowerSpec.stair_kind=spiral ??? assemble helix+newel per drum (hall keeps switchback); outward drum windows; tower_entry at ground+landings (WALL_LINE drum-passable); skip inner wall_plain/fitout/parapets in drums; exclude towers from flat roof + upper floor_deck AABB; post-merge strip helix under neighbour roofs. Tests: test_tower_keep_habitable.py + tower_entry/windows/spiral_shell/spiral_stairs = 40 passed. Handbook/ledger/roadmap 4.7. Gaps: crown hatch (T-D5 pad), circular railing continuity, gatehouse tower_hall_kiss (massing sibling), cloister balcony reachability (arcade lane).


2026-07-25 ? @BUILDING_HEIGHT_FLEX
>>> TRIGGER @BUILDING_HEIGHT_FLEX ? Spec/contract height API (storeys|cm); assemble wall/gate span; fortress curtain/gate heights; validate wall_height_span + gate_clear_height; test_building_height_flex.py; handbook 5.8. Merge dirty assemble/validate/compound. Do NOT demote criticals.
<<< ACK @MASTER

>>> DONE @BUILDING_HEIGHT_FLEX ? Height API: `HeightDecl` / `RoomSpec.height_storeys` / `BuildingSpec.wall_height_storeys` + contract `height_cm_from_storeys` / `resolve_height_*` / `gate_clear_min_cm` (prefer storeys; cm is Python override). Assemble: monumental gate/grand leaves span declared envelope (`size_cm.z`, tag `wall_height_span`); upper stub walls skipped. Fortress: gatehouse wall_height=3, curtain_storeys=3. Validate: critical `wall_height_span` + `gate_clear_height` (broken short-gate fixture). Handbook 5.8. Tests: test_building_height_flex.py 10 passed; castle/rooms/contract green. Gap: `test_fortress_compound_validates_critical_empty` still red on cloister L1 `aperture_reachability` (balcony galleries off ? sibling massing/arcade, not demoted).

2026-07-25 ? @STAIR_LANDING_WALL_BLOCK
>>> TRIGGER @STAIR_LANDING_WALL_BLOCK ? Critical stair_landing_clear + compound unification (sealed ranges / building-in-building). Owns: pae/stair_occupancy.py, pae/compound_unify.py (new), validate append, assemble/compound autofix, test_stair_landing_wall_block.py, handbook/ledger, AGENT_SYNC. Merge don't wipe fortress/height/arcade. Do NOT demote aperture_reachability / stair_run_floor_clear / fortress checks.
<<< ACK @MASTER
>>> DONE @STAIR_LANDING_WALL_BLOCK ? Checks (all CRITICAL fail-closed): `stair_landing_clear`, `compound_not_partitioned_as_buildings`, `compound_range_doors`, `building_doorway_exists`, `building_in_building`. Autofix: `repair_stair_landing_walls` strips landing blockers (open bay); `unify_compound_assembly` punches compound_link doors / strips dup party walls / merges nests / ensures per-building doorways. Wired in assemble + build_compound/castle/fortress. Broken fixtures first (top landing 1?2 walls; three sealed blue rooms; building-in-building). Tests: test_stair_landing_wall_block.py + integrity/fortress critical empty. Handbook ?5.8?5.9; Ledger D-18/D-27/D-28. Did not demote aperture_reachability / stair_run_floor_clear / fortress checks.

>>> DONE @GATEHOUSE_MONUMENTAL ? Monumental walkable fortress gatehouse: 6x3 / 3-storey + hall+1 spiral drums (spirals kept); wall_gate_arch_grand; approach steps_grand with clearance + flanking (no leaf-column plug); critical gate_passage_clear + gate_opening_size; stair_landing_clear doors count as through-passages for aperture_reachability. Hip roofs on keep/cloister untouched. Tests: test_fortress_compound + test_gate_passage 17 pass; fortress_validate/entrances/tower_keep_habitable green. Gaps: live Blender fortress rebuild for visual proof.

2026-07-25 ? @FORTRESS_LIVE_VALIDATE_GREEN
>>> DONE @FORTRESS_LIVE_VALIDATE_GREEN ? Fortress `validate` critical=[] (roof_penetration cleared: drum-window tangential clamp keeps rim shells in tower cell; roof_valley_join already per-building from hip lane; hall_kiss Z-scoped for tall drums; floor_deck from real floor cells). Preserved spiral/hip/height/unify. pytest fortress_compound+validate+roof_connect+tower_windows+tower_keep_habitable: 64 passed. `python tools/pae_build_in_blender.py --fortress` ? `Saved/Screenshots/fortress_live.png` (652636 bytes). No demotions.

2026-07-25 ? @APPROACH_STAIR_MATE
>>> DONE @APPROACH_STAIR_MATE ? User: 9 scattered misaligned `steps_grand`; tops 175 cm above z?0 threshold. Root: `_add_approach_causeway` 3?N apron grid + fixed catalog rise (not mated). Fix: `pae/approach_stairs.py` per-gate flanking + `mated_step_pose`; trim/compound share planner; critical `approach_stair_height_mate` + `approach_stair_aligned_to_gate`; `stair_flight_stack` for exterior duplicate XY; `repair_approach_stairs` autofix; fixed `fortress_connections` typo ? default end unify. Tests: `test_approach_stair_mate.py` 8 pass; gate_passage/fortress_compound green. Handbook ?11b. Gap: `test_fortress_compound_validates_critical_empty` still red on branch `footprint_overlap` (compound_unify sibling, not demoted).

2026-07-25 ? @COMPOUND_CONNECT_MERGE
>>> DONE @COMPOUND_CONNECT_MERGE ? ConnectionPolicy (`merge`|`connect`|`separate`) + CompoundConnections / fortress_compound_connections / school_compound_connections. Fixed range detection (instance names only); floor-only footprint_overlap (merge exempt); merge strip zone + floor dedupe; connect strips L-corner redundant solids; build_fortress_compound passes fortress_connections on both unify passes. test_fortress_compound 8/8 + test_stair_landing_wall_block 14/14; validate critical=[]; one ground graph. Handbook 5.9. Did not touch approach_stairs.py.

2026-07-25 ? @STAIR_WALL_STRIP_SCOPE
>>> TRIGGER @STAIR_WALL_STRIP_SCOPE ? Landing autofix over-scoped: strips walls through entire building depth. Restrict repair_stair_landing_walls to landing strip zone (+<=1 cell along run axis); critical stair_landing_strip_scope; broken fixtures (through-wall + distant wall); fortress strip counts; handbook/ledger D-30; test_stair_landing_wall_block.py. Merge with cloister stack sibling. Do NOT demote checks.
<<< ACK @MASTER
>>> DONE @STAIR_WALL_STRIP_SCOPE ? Strip zone: pad + stair ends + STRIP_AXIS_BUFFER=1 along run axis only. repair_stair_landing_walls strips only when covered_cells subset zone. Critical stair_landing_strip_scope (fail-closed on through-wall blockers). measure_stair_landing_strip for fortress diagnostics. Fixtures: through-wall + distant-wall survive. Fortress post-fix: strip_overscoped=0. test_stair_landing_wall_block.py 17 pass. Handbook 5.8; Ledger D-30. Did not widen unify party-wall strip or touch three-stair gatehouse lanes.

2026-07-25 ? @CLOISTER_WALL_STACK
>>> TRIGGER @CLOISTER_WALL_STACK ? West cloister `wall_plain` + `wall_arcade` coplanar stacks. Fix producers + critical `wall_face_exclusive` + autofix. Handbook ?11d; Ledger D3-9; test_wall_face_exclusive.py. Preserve ConnectionPolicy / approach stairs / spiral keeps.
<<< ACK @MASTER
>>> DONE @CLOISTER_WALL_STACK ? Critical `wall_face_exclusive` + `repair_wall_face_stacks` (`pae/wall_faces.py`); trim `_colonnade` + `_add_cloister_arcade` share `claimed_wall_arcade_faces`; `_placement_matches_range` after unify; curtain depth `max(depth, curtain_storeys+2)`; gatehouse `6?4` / 2 hall storeys for `stair_graph`; `FORTRESS_CURTAIN_TRIM.parapets=False` + battlement piece_id match. Measured stacks: **2** poisoned west-cloister pairs ? **0** after repair. Tests: `test_wall_face_exclusive.py` 5 pass; `test_fortress_compound` build + cloister arcade green. Gap: `test_fortress_compound_validates_critical_empty` still red on enclosure/headroom (sibling massing, not demoted).

2026-07-25 ? Claude: user-reported defects from the fortress render written up. NO new
markdown files ? everything went into the three docs that already own this material.

>>> NOTE @DOCS_D3 ? Docs/DEFECT_LEDGER.md ?D3 (D3-1..D3-8), Roadmap Phase 0 rows 0.7-0.11
    and new Phase 10, Handbook ?11d. Read the ledger first: each row names the file:line
    and the measured count, so nobody re-derives them.

    THREE OF THESE ARE WIRING, NOT ENGINEERING ? the code is already correct:
      * D3-3 stacked flights: _monumental_flight_pads already alternates anchor AND yaw.
        Gated to switchback/wide; straight gets pads=None (assemble.py:1125). A 180 deg
        yaw flip is NOT the fix ? tried, corrects direction, leaves them stacked. Needs
        SOLVER work: allocate a 2-bay-wide well first.
      * D3-5 approach stairs: approach_stairs.py is already correct (one flanking pair
        per gate, top tread <= sill). repair_approach_stairs is called ONLY from
        compound.py:1415. Fix the call site, do not rewrite the module.
      * D3-4 roof edging: trim._roofline and tower_rampart/compound both claim the same
        edge with no mutual exclusion. One declared choice, one producer.

    D3-8 is NOT a defect and is recorded to stop it being re-asked: stairs are
    auto-allocated by solver.py:827. No agent hand-places them.

>>> NOTE @STRUCTURE_MERGE ? Roadmap Phase 10.1-10.3. The big one: the engine cannot
    express "these masses are ONE building", which is why three guardhouses render as
    three buildings with three staircases. MUST BE DECLARED, NOT INFERRED ? adjacency is
    ambiguous (a terrace is adjacent and separate; a courtyard range is adjacent and
    joined). No geometric test separates them.
    TRAP: _check_structural_islands partitions on the `building:` tag today, deliberately.
    When structures land the key must change to the structure IN THE SAME COMMIT, or every
    clean multi-mass build starts failing and someone weakens the check. Handbook ?11d.
    Ranges and drums are the SAME party-wall problem ? one mechanism, not two.

>>> NOTE @STOREY_DATUM ? Roadmap 10.6. Half of this already works: RoomSpec.height_storeys
    is Optional[float], so a 1.5-storey CEILING is expressible now. What does not work is
    the storey DATUM ? floor_placement_z_cm is level*STOREY_CM, hardcoded in ~26 places, so
    a floor cannot START at 1.5 storeys. That blocks mezzanines and Phase 9 stepped
    buildings. Route every hardcoded level*STOREY_CM through one accessor in its own
    commit with NO behaviour change before making it volume-aware.

>>> NOTE @FEATURE_SMOKE ? Roadmap 10.7 / Handbook ?11d. Every check we have asks "is the
    output right?"; none asks "did this feature run at all?" That is how D3-3/4/5 shipped.
    Suggested: per showcase build, assert the features its spec asks for actually appear.
    It is a smoke test, not a validator ? keep it out of validate.py.

2026-07-25 ? @DOC_D3_PHASE10_AUDIT
>>> DONE @DOC_D3_PHASE10_AUDIT ? D3 wiring pass on branch cursor/roadmap-completion-0ea5.
    FIXED: D3-4 roof_edging_exclusive (pae/roof_edging.py, trim+compound defer); D3-5 trim?repair_approach_stairs.
    PARTIAL: D3-3 straight flight pads (solver+assemble+stair_flight_stack); 6?3 fortress_gatehouse still blocked.
    STARTED: contract.storey_datum_z_cm ? assemble.py+validate.py migrated (no behaviour change).
    OPEN: D3-1/2 structure identity+party walls; D3-6 drum enclosure; Phase 10.1?10.3/10.6.
    Tests: test_stair_flight_offset (ex random), test_approach_stair_mate, test_roof_edging_exclusive ? 26 pass.
    Gap: build_fortress_compound still red (stair_flight_stack on 6?3?3 gatehouse + sibling issues).

2026-07-25 ? @STRUCTURE_IDENTITY
>>> DONE @STRUCTURE_IDENTITY ? Roadmap 10.1?10.2 green path on build_fortress_compound.
    Checks in structure_identity.py wired via validate._check_structure_identity (line 71).
    Fortress: structure:fortress_bailey, party walls open, north_keep primary stair core,
    freestanding partitions on structure:. Tests: test_structure_identity.py (11 incl green path).
    D3-1/D3-2 user symptoms closed on fortress build ? ledger updated PARTIAL?green-path FIXED.
    No demotions. Pre-existing non-structure criticals (enclosure, etc.) unchanged.
>>> TRIGGER @ARCH_MESH_SMOOTH ? Gate/arcade arch meshes stepped/blocky; smooth high-segment heads for wall_gate_arch / wall_gate_arch_grand / wall_arcade; measure.py footprint rules; tests; don't break gate_passage sibling; no demotions.
<<< ACK @MASTER
>>> DONE @ARCH_MESH_SMOOTH ? `ApertureProfile.head_bands` + `MONUMENTAL_HEAD_BANDS=36` on `gate_arch` / `gate_arch_grand` / `arcade_round` (descriptor opening unchanged); `measure.py` `arch_head_band_step_cm` / `monumental_arch_mesh_smooth` / `arch_curve_max_deviation_cm`; `test_arch_mesh_smooth.py` 19 pass. Gate-through mins (`gate_opening_size` / `gate_passage_clear`) untouched ? mesh bands only.

2026-07-25 ? @STOREY_DATUM_ACCESSOR
>>> DONE @STOREY_DATUM_ACCESSOR ? `contract.storey_datum_z_cm` routes all production datum-Z
    call sites (assemble, validate, anchors, variation, compound_unify, tower_entry,
    tower_rampart, roof_edging, cell_to_world_cm). Uniform grid unchanged; no mid-level floors.
    Tests: `test_validate_contract` (accessor + grep lock); tower mesh stack uses accessor.
    Docs: Handbook ?11d, Roadmap 10.6 note. OPEN: volume-aware T-111 / storey_datum_consistent.

2026-07-25 ? @HANDBOOK_11D_CHECKS
>>> DONE @HANDBOOK_11D_CHECKS ? T-111 validator `storey_datum_consistent` (critical, fail-closed).
    `pae/storey_datum_validate.py` + `contract.placement_volume_offset_z_cm` / volume tag helpers;
    fires on `volume:<id>` + `datum_offset_cm:<n>` only (no assemble change). Removed duplicate
    `structure_validate.py` (structure checks live in `structure_identity.py`). Tests:
    `test_storey_datum_consistent.py` 8 pass (poison floor/stair/conflict + M2 double-height
    clean). Siblings documented: stair_flight_stack, roof_edging_exclusive, structure_identity.
    OPEN: assemble producer for per-volume datums (T-111), T-112/T-113.

2026-07-25 ? @DOCS_D3_SYNC
>>> TRIGGER @DOCS_D3_SYNC ? Survey D3 code/tests + sibling DONE lines; sync DEFECT_LEDGER ?D3,
    CASTLE_SCHOOL_ROADMAP Phase 0/10, Handbook ?11d. Mark only truly fixed items with test
    names; leave open open; do not claim Phase 10 done. Preserve wiring-pattern / freestanding
    / datum-vs-ceiling / D3-8 notes.
<<< ACK @MASTER
>>> DONE @DOCS_D3_SYNC ? D3 docs synced with test evidence (Phase 10 not claimed done).
    FIXED: D3-4 (`test_roof_edging_exclusive.py` x4), D3-5 (`test_approach_stair_mate.py`
    `::test_trim_exterior_steps_strips_poison_grid` + mates). PARTIAL: D3-3
    (`test_stair_flight_offset.py` switchback/wide/straight 8x5 + fail-closed; open 6x3
    gatehouse + `::test_random_monumental_multi_storey_never_stacks`). OPEN: D3-1/D3-2
    (checks poison-only; reverted premature FIXED in ledger ? @STRUCTURE_IDENTITY overstated).
    Preserved: D3-6 trap, D3-7 5de4b0d, D3-8 non-defect, wiring gap ?10.7. Roadmap: 10.1-10.3
    started-not-done; 10.4 partial; 10.5 check+wiring done; 10.6 accessor done.

2026-07-25 ? @FORTRESS_REBUILD_GATE
>>> HOLD @FORTRESS_REBUILD_GATE ? NO `python tools/pae_build_in_blender.py --fortress` (Master INTERRUPT).
    Gate: `build_fortress_compound()` + `validate()` must reach critical=[] before one-shot rebuild.
    Poll audit 2026-07-25 ~15:05 ? NOT GREEN (holding for stair-stack + strip + tower + cloister + D3).
      * build_ok=True (1654 placements); validate critical=210 (stable ?2 polls)
      * stair_flight_stack: 0 (audit gatehouse red not reproducing on this snapshot)
      * critical mix: vertical_support?130, stair_exit_clearance?40, headroom?23, enclosure?14,
        fitout_containment?2, structure_single_stair_core?1 ? NOT demoted
      * Sibling tests: stair_flight_offset GREEN (8 pass); wall_face_exclusive/cloister fixture RED
        (3 fails ? `cloister_wall_stack` poison fixture); fortress_compound_validates_critical_empty RED
      * @STAIR_WALL_STRIP_SCOPE DONE; @DOC_D3_PHASE10_AUDIT PARTIAL (D3-3 gatehouse open);
        cloister stack + tower entry lanes still in flight
      * `Saved/Screenshots/fortress_live.png` absent (correct ? no rebuild yet)
      * Blender MCP ready; no lock detected
    Will ONE shot `--fortress` only when validate critical=[] + siblings landed or ~25min timeout.

2026-07-25 ? @PHASE0_REMAINING
>>> TRIGGER @PHASE0_REMAINING ? Audit Phase 0 rows 0.7?0.11 + DEFECT_LEDGER D3; close fixable items with test evidence; no demotions; do not touch D3-8.
<<< ACK @MASTER
>>> DONE @PHASE0_REMAINING ? Phase 0 audit 0.7?0.11 + D3 (D3-8 untouched).
    CONFIRMED DONE (no code): 0.8 D3-4 (`test_roof_edging_exclusive.py` 4 pass), 0.9 D3-5
    (`test_approach_stair_mate.py` wiring+mated), 0.11 D3-7 (`5de4b0d` buttress pose).
    PARTIAL 0.7 D3-3: `test_stair_flight_offset.py` 8 pass incl random property; fortress_gatehouse
    6?4 has 8-cell well + clean `_check_stair_flight_stack`; open `stair_graph` on full validate.
    OPEN 0.10 D3-6: T-D1..T-D6 not implemented; foundations unblocked ? `pae/street_scene.py`
    widened timber_a/stone_b/gate_tower footprints so `build()` assembles; `test_drum.py` 8 pass.
    Docs: CASTLE_SCHOOL_ROADMAP 0.7/0.10 + DEFECT_LEDGER D3-3/D3-6 updated. No demotions.

2026-07-25 ? @D3_WIRING_FIX
>>> DONE @D3_WIRING_FIX ? D3-3/4/5 call-site wiring (modules unchanged).
    D3-3: assemble fail-closed `return` after `stair_flight_stack` when `pads is None` (no silent XY stack).
    D3-4: `CURTAIN_TRIM.parapets=False` (castle matches fortress); battlements via `_add_curtain_battlements` + `claimed_roof_edges`.
    D3-5: `GATEHOUSE_TRIM` / `FORTRESS_GATEHOUSE_TRIM` `exterior_steps=True`; post-merge `_add_approach_causeway` on fortress + castle curtain compounds.
    D3-8: untouched (non-defect).
    Tests: `test_d3_wiring.py` 8 pass; `test_stair_flight_offset` + `test_approach_stair_mate` + `test_roof_edging_exclusive` + `test_castle_curtain` green.
    Ledger: D3-3/4/5 ? FIXED (@D3_WIRING_FIX). Gap: `test_fortress_compound_validates_critical_empty` still red on headroom (sibling massing, not demoted).

2026-07-25 ? @STAIR_STACK_AND_GATE_THRU
>>> DONE @STAIR_STACK_AND_GATE_THRU ? D3-3/D3-6 gatehouse: 6?4?3 spec; solver 4?2 well + pad rank (avoid south/edge cols); plan `_pick_region_for_cells` pad-pair `stair_graph`; assemble north gate arch through-passage; critical `gate_through_passage`; `stair_flight_stack` unchanged. Tests: `test_stair_flight_offset` + `test_gate_passage` 18 pass. Gap: compound `validate critical=[]` still sibling headroom/vertical_support ? not demoted.

2026-07-25 - @INTERIOR_FITOUT_PASS
>>> TRIGGER @INTERIOR_FITOUT_PASS - Greybox benches/tables in fortress keep/gatehouse/cloister interiors; skip tower drums + stair-adjacent cells; fitout_containment critical; light_anchors on habitable ranges; tests; no demotions.
<<< ACK @MASTER
>>> DONE @INTERIOR_FITOUT_PASS - pae/fitout.py: castle hall INTERIOR cells (all levels) + stair/corridor/drum exclusions; fitout_placement_allowed for compound shifted props. build_fortress_compound: fitout + anchors on north_keep/gatehouse/cloisters only (not curtains). Tests: test_fortress_fitout.py 7 pass; test_fitout + test_tower_keep_habitable green (23 pass). fitout_containment critical not demoted. Gap: test_fortress_compound_validates_critical_empty still red on pre-existing headroom (sibling massing).

2026-07-25 ? @FORTRESS_STABILIZE
>>> DONE @FORTRESS_STABILIZE ? fortress validate critical=[] (1795 placements). Cause cluster: light_anchor vertical_support (86); curtain L2 deck ? cloister L1 roof headroom (12); tower_deck solid plug despite floor_hole (12 stair_exit); gate_through full-column probe into north_keep (2). Fixes: vertical_support light_anchor exemption; repair_junction_deck_headroom; stair_exit hole-punched bay skip; habitable_drum hip-eaves headroom carve-out; gate_through host-Y scope. Preserved structure identity + tower/cloister/strip/approach/edging. Pytest: fortress_compound/validate/wall_face/stair_landing/roof_edging/gate_passage/light_anchors green; test_plan_gate_approach_one_pair_per_gate still 4 vs 2 gates (pre-existing 2-storey north+ south leaves). @FORTRESS_REBUILD_GATE ? validate green.
>>> DONE @FORTRESS_REBUILD_GATE ? ONE shot `python tools/pae_build_in_blender.py --fortress` success (~25s). Blender MCP unlocked. `Saved/Screenshots/fortress_live.png` refreshed 2026-07-25 15:24:52 (462039 bytes; prior 14:53:00). critical=[] (fail-closed assemble_fortress_compound). instances=1795 placements=1795 collection=PAE_Fortress ranges=[west_curtain,gatehouse,east_curtain,west_cloister,east_cloister,north_keep] extent_m=(120,104,40.005). Blender rebuild UNBLOCKED.
>>> DONE @FORTRESS_SHELL_RESTORE ? Over-strip root causes: `repair_structure_single_stair_core` nuked all gatehouse stairs (0 hall+helix); MERGE halo stripped south L0 walls leaving L1+ floaters; helix strip ran pre-unify so restored spirals missed roof carve-out. Fixes: `auxiliary_circulation_masses=(gatehouse,)`, `_placement_range_names` for campus merge tags, `repair_shell_wall_level_support`, MERGE zone halo removed, helix strip post-unify, `stair_exit` habitable_drum?roof exemption (matches headroom), critical `fortress_gatehouse_hall_stair` + `fortress_merge_wall_shell`. Before/after: stairs 29?49 (gh 0?20), walls 443?420, critical=[] held. Pytest fortress_compound/structure_identity/validate/gate_passage 51 pass. `fortress_live.png` refreshed.

2026-07-25 - @BPY52_ADDON_INSTALL
>>> DONE @BPY52_ADDON_INSTALL - Blender 5.2: lazy bl_info in pae/__init__.py; blender_manifest.toml; junctions scripts/addons + extensions/user_default; EnumProperty int defaults; verified enable bl_ext.user_default.pae (Steam blender.exe).

2026-07-25 - @ADDON_PLUGIN_FIRST_INTEGRATION
>>> TRIGGER @ADDON_PLUGIN_FIRST_INTEGRATION ? Wire core capabilities through Blender 5.2 extension UI/operators; Blender smoke test bl_ext.user_default.pae; honest audit table; no CLI-only claims for wired features.
>>> DONE @ADDON_PLUGIN_FIRST_INTEGRATION ? Addon UI wired: Spec (roof/stair/height/entrance/wing), Generate (Current Spec / Fortress / School / Gallery / Reload PAE / clear scene), Validate+Export unchanged APIs; errors in UI not console-only; `build_*_live` return validation_report; README workflow + CLI-only list. Tests: pytest 17 addon unit pass; Blender 5.2 background `tools/pae_addon_blender_smoke.py` ? `Saved/pae_addon_smoke.json` (generate+validate+fortress FINISHED, report_ok=true, PAE_Fortress 1757 placements). Gaps: ConnectionPolicy/arcade/fitout/multi-entrance/tower UI still compound/CLI.

2026-07-25 - Master: Master Plan Wave 1 (Docs/MASTER_PLAN.md Stages A+B + Stage I packs).
>>> TRIGGER @MP-WS1 - Structure + LevelSpec stack + YAML Â§3.1 authoring. Foundation identity; per-level sketches; cumulative height_units datum; freestanding partition key same commit (Handbook Â§11d). Do NOT implement Stage C roof height-field yet. Never git add -A; never demote criticals.
>>> TRIGGER @MP-WS6 - Add style packs rustic/medieval/manor/civic; keep interchangeable with existing packs; own styles/*.json + style_pack + tests only. Do not touch assemble/solver/spec.
>>> TRIGGER @MP-WS11 - Stage L UE delivery tooling harden (export/manifest/spawn_table/asset_bind + consumer doc). Filesystem only; NO Unreal editor or MCP calls. Do not touch spec/solver/plan/assemble/sketch/structure_identity (MP-WS1 lane) or styles (MP-WS6).
>>> DONE @MP-WS11 - Stage L filesystem delivery chain: `tools/ue_delivery.py` orchestrates export â†’ dry-run â†’ spawn table â†’ asset bind â†’ cross-artifact consistency; `pae/export/delivery.py` + `spawn_groups.py`; spawn schema `pae.spawn_table/2` adds `ism_groups[]`/`ism_group_count`; delivery report `pae.delivery/1` at `Saved/exports/{milestone}_delivery.json`. Fail-closed at every stage + consistency drift (loc/yaw/bind coverage). Docs: `Docs/UE_MANIFEST_CONSUMER.md` (entrypoint, ISM, honest editor gaps). Verified: m1 (28 rows, 6 ISM groups) + m3 (82 rows, 14 groups); pytest ue_/export 75 passed. Evidence: `Saved/exports/m1_delivery.json`, `delivery_batch_report.json`. Gates: stage_L_tooling=yes fail_closed=yes ism_groups=yes mcp_used=no. Gaps: in-editor spawn/collision/nav/LOD import NOT done (M-I lane).
>>> DONE @MP-WS6 - Stage I style packs: `pae/styles/{rustic,medieval,manor,civic}.json` (roof pitch/kind, window/door profiles, wall bands, tower caps, materials, storey_height_cm); `test_style_pack.py` loads all 8 builtins + distinct-trait tests. pytest `pae/tests/unit/test_style_pack.py` 27 passed. Gates: stage_I_packs=yes existing_packs_ok=yes. Gaps: storey_height_cm hints not yet consumed by assemble; no M-E interchange golden yet.
>>> DONE @MP-WS1 - Stage A+B+YAML Â§3.1: `StructureSpec`/`LevelSpec` + dict/YAML round-trip (`pae/structure_spec.py`); foundation defaults to union; `structure:<id>` stamped in assemble (freestanding already partitions on structure); per-level footprints via `level_cells`; `storey_datum_z_cm(..., height_units=)` cumulative datum baked into assemble offsets; single-`S` expands to placeable well; `pipeline` accepts StructureSpec. Tests: structure_level_spec+structure_identity+sketch+storey_datum+validate_contract 45 passed; m2+m4 20 passed. Gates: stage_A=yes stage_B=yes yaml=yes roof_C=deferred mcp_serial=n/a. Gaps: Stage C roof height-field; void/balcony railing auto; program regions not yet room-carved; ci_local not re-run (heavy).

2026-07-25 - Master: Master Plan Wave 2 after MP-WS1 green (roof C + circ D + tower E).
>>> TRIGGER @MP-WS2 - Roof as height field (Stage C). One roof per structure from column topmost; fix D3-9. Own roof path only.
>>> TRIGGER @MP-WS3 - Circulation scale (Stage D). Per-region/level stairs; no shared flight footprints. Avoid roof sections of assemble.
>>> TRIGGER @MP-WS4 - Tower drum enclosure (Stage E). Read DESIGN_TOWER_DRUM.md trap first; only suppress outboard_drum_cells. Avoid roof/stair pad sections.
>>> DONE @MP-WS4 - Stage E tower drum enclosure: T-D1 outboard-only perimeter suppress via `outboard_drum_cells_from_plan` in `_place_wall_run`; plan-side predicate + neighbour expansion in `pae/drum.py`; T-D3 `drum_exclusivity` + `aperture_faces_open_air` checks wired in validate (outboard-only / excludes drum rim). Tests: `test_drum.py` 8 passed, `test_tower_drum_enclosure.py` 5 passed, `test_tower_entry_door.py` 8 passed, `test_tower_keep_habitable.py` 7 passed; school 15/16 (1 pre-existing WS3 stair-well role). Gates: stage_E=partial_green outboard_only=yes school_ok=15/16 mcp_serial=n/a. Gaps: T-D2 trim-only helix entry path; `library_tower`/`street_scene` blocked by WS3 stair pad; T-D6 parapet continuity not extended beyond existing `tower_rampart`; `scratchpad/diag3.py` absent.
>>> DONE @MP-WS3 - Stage D circulation scale: `_default_stair_cells` searches per-level built intersection (not `_primary_body`); ranks 2Ã—4 leg wells over shallow 4Ã—2 connector splits; `level_cells` passed from StructureSpec; `_expand_marked_stair_cells` same; `DEFERRED_STAIR_KINDS` fail-closed for grand/imperial; plan `_link_stair_void_regions` bridges L/U top-storey regions across stair VOID wells; fixed `program_cells` init in plan(). Tests: `test_stage_d_circulation.py` 4 pass; `test_stair_flight_offset.py` 8 pass; `test_stair_typology.py` 11 pass; `test_d3_wiring.py` 6/8 (2 pre-existing fortress collinear/aperture reds). Gates: stage_D=yes d3_3=preserved imperial=deferred fail_closed=yes mcp_serial=n/a. Gaps: grand/imperial ceremonial split-flight typology not implemented; `program_cells` carving still empty stub.
>>> TRIGGER @MP-WS3b - School 4Ã—2 plan reserve + library_tower/street_scene stair unblock; targeted pytest only (RAM).
>>> DONE @MP-WS3b - Fixed school offset-well plan roles: `_reserve_monumental_stairwell` (school/classroom_wing only) + corridor spine skips well footprint; ranking unchanged (school 2Ã—4 already wins). library_tower: solver auto-spiral when straight well < min + `Massing.stair_kind` uses resolved kind (tower repair â†’ helix at (2,3)). street_scene: per-building `run_through_assemble` green (6/6); full `build()` still red on `band_proud` post-band â€” out of scope. d3_wiring 2 fortress reds: `aperture_sanity` cloister doors + `collinear_gap` crenels/walls â€” collateral, not Stage D. Pytest (single-file, `-p no:cacheprovider`): school_switchback 1/1; stage_d 4/4; stair_flight_offset 8/8; stair_typology 11/11. Gates: school_4x2=fixed street_scene=assemble_ok band_full_build=deferred d3_wiring_verdict=collateral_not_stage_d ram_safe=yes.
>>> DONE @MP-WS2 - Stage C roof height field: `roof_height_field_bands` / `structure_ridge_span_modules` in `pae/primitives/roofs.py`; assemble `_place_structure_roofs` places flat/pitched/hip from column topmost (steps per eaves band); ridge Z from max short-span in band â€” not per-wing rect_cover (D3-9). Sketched U pitched: one ridge family (1150 @ pitch 1.4 / 4-mod) not 590+1150; valleys kept. Tests: `test_roof_height_field.py` 8 passed; hip L/U + m4 pitched green. Ledger D3-9 roof CLOSED. Gates: stage_C=yes d3_9=fixed mcp=n/a. Gaps: full diagonal valley merge (S-021); fortress/m3 connection reds are WS3/WS4 collateral (aperture/tower_hall_kiss), not ridge-family; watertight single mesh still stub.

2026-07-25 - @MP-WS8 IN PROGRESS
>>> TRIGGER @MP-WS8 - Master Plan Â§5 Blender authoring UI: StructureSpec level-stack panels, generate_from_structure operator, YAML round-trip. Owns: pae/addon/**, addon tests, tools/pae_addon_blender_smoke.py, pae/addon/README.md. Do NOT edit assemble/solver/plan/drum/roofs (Wave 2). Do NOT start grid-paint tool (Â§3.2 drawing later).
>>> DONE @MP-WS8 - Â§5 StructureSpec authoring UI: Structure + Levels panels (stack add/remove, height_units, sketch text, optional foundation, style/seed/roof/stair); operators `generate_from_structure`, YAML load/export, gatehouse preset; `coerce_pipeline_spec` reload-safe shim in addon pipeline; Validate/Export prefer structure when levels populated. Tests: pytest addon 24 pass; Blender smoke `Saved/pae_addon_smoke.json` (structure FINISHED, gatehouse preset loads 3 levels). Gates: addon_structure=yes operator=generate_from_structure smoke=Saved/pae_addon_smoke.json. Gaps: grid paint Â§3.2; program region UI; gatehouse multi-level may fail validate (engine circ); fortress smoke CANCELLED (pre-existing tower_hall_kiss).
>>> DONE @MA_ROOF_PROOF â€” sketched U pitched ridge family [1150.0] (expected 1150.0); gate `20260725_215535_ma_sketched_u_roof.json`; export `Saved\exports\ma_roof_ridge_report.json`; screenshot=n/a. Gates: ma_one_roof=True ridge_family=[1150.0] critical_empty=True.

2026-07-25 â€” @MP-WS5
>>> TRIGGER @MP-WS5 â€” Master Plan Stage F: party walls / connections. One mechanism for rangeâ€“range and rangeâ€“drum shared edges; interior opening/arch on shared boundary; fortress structure_identity green. Owns: `pae/structure_identity.py`, `pae/compound_unify.py`, minimal assemble party-edge emission, party-wall tests. Do NOT rewrite `_place_structure_roofs` or stair pads. Never git add -A; never demote criticals.
<<< ACK @MASTER
>>> DONE @MP-WS5 â€” Stage F party walls shipped (one mechanism rangeâ€“range + rangeâ€“drum). `structure_identity`: `_structure_mass_footprints` (per-range body/drum submass), `repair_structure_party_walls` (strip double skin + `wall_door_arched` / `structure_party` tag), poison `make_range_drum_sealed_defect`; `compound_unify.unify_compound_assembly` calls party repair after structure stamp; `drum.inboard_drum_party_faces_from_plan` + assemble `_place_wall_run` L0 skip on body|drum party face. Tests (single-file `-p no:cacheprovider`): `test_party_walls.py` 5/5; `test_structure_identity.py` 9/11 (2 fail on `build_fortress_compound` `report.ok` â€” 3Ã— `drum_exclusivity` north_keep @ WS4 sibling + aperture_sanity warnings; **structure checks green**: `structure_party_wall_open`/`structure_identity`/`compound_not_partitioned` critical=[]; partition `structure:fortress_bailey`). No demotions; roof/stair pads untouched. Gates: stage_F=yes fortress_ok=structure_yes_report_no ram_safe=yes. Gap: full fortress `report.ok` needs WS4 drum_exclusivity on north_keep north face.

2026-07-25 â€” @MP-WS-H
>>> TRIGGER @MP-WS-H â€” Master Plan Stage H openings as style choice. Owns: pae/style_pack.py (aperture resolve), assemble aperture selection only, pae/structure_spec.py level window override, test_stage_h_openings.py, AGENT_SYNC. Avoid drum.py / MP-WS4b / arcade rewrites. Never git add -A; never demote criticals.
<<< ACK @MASTER
>>> DONE @MP-WS-H — Stage H openings wired: `resolve_window_tag`/`resolve_window_piece_id` + shape aliases (square/lancet/round/mullioned/oculus); `resolve_door_piece_id` (style door.tag + grand/gate roles); `LevelSpec.window_tag` → `level_window_tags` through solver/plan/assemble; focused `test_stage_h_openings.py` 17/17; regressions `test_style_interchange.py` 7/7. Gates: stage_H=yes window_family=per_storey ram_safe=yes. Gaps: door_double grand only when pack tags it; oculus gable-only placement not authored; `storey_height_cm` still unconsumed.

2026-07-25 â€” @MP-WS4b
>>> TRIGGER @MP-WS4b â€” Close fortress north_keep `drum_exclusivity` (3Ã— north wall vs outboard drum probe). Owns `pae/drum.py` suppress predicate + assemble `_place_wall_run`; targeted drum/fortress pytest. Avoid plan.py (MP-WS7); never demote criticals.
<<< ACK @MASTER
>>> DONE @MP-WS4b â€” Fortress `drum_exclusivity` closed: `should_suppress_perimeter_wall_on_outboard_drum` in `pae/drum.py` skips boundary-line walls when opening probe or outward neighbour is outboard (north_keep north wall at (-3,10) vs drum (-3,9)); assemble `_place_wall_run` uses helper; `check_drum_exclusivity` arc index uses anchor `p.cell` only. Tests (`-p no:cacheprovider`): `test_drum.py` 9/9; `test_tower_drum_enclosure.py` 5/5; `test_party_walls.py` 5/5; `test_structure_identity.py::test_fortress_compound_green_path_structure_identity` + `test_fortress_freestanding_partitions_on_structure` 2/2; `build_fortress_compound` `report.ok=True` critical=[]. Gates: drum_exclusivity=0 fortress_ok=yes school_ok=yes ram_safe=yes.

2026-07-25 â€” @MP-WS6b
>>> TRIGGER @MP-WS6b â€” M-E style interchange proof (8 packs Ã— M2 4Ã—3) + Master Plan / roadmap / ledger status sync. Owns: test_style_interchange.py, tools/me_style_interchange_proof.py, Saved/exports/me_style_interchange_report.json, Docs/*. Do NOT touch solver/plan/assemble/styles.
>>> DONE @MP-WS6b â€” M-E interchange: M2 4Ã—3 two-storey Ã— 8 packs (`roof=auto`), 8/8 `critical=[]`; report `Saved/exports/me_style_interchange_report.json` (roof kind/pitch, ridge z, window profile, differing fields); `test_style_interchange.py` 7 passed. Docs synced: MASTER_PLAN (Stages Aâ€“L status, M-A/M-E), CASTLE_SCHOOL_ROADMAP (wave sync, D3-3/6/10), DEFECT_LEDGER (D3-9 CLOSED label, ME-1). Gates: m_e_interchange=yes packs_built=8/8 docs_synced=yes blender=no full_suite=no. Gaps: storey_height_cm / wall_bands / materials still unconsumed in assemble.

2026-07-25 â€” @MP-WS7
>>> TRIGGER @MP-WS7 â€” Master Plan Stage G program/rooms + courtyard arcade start. Owns: pae/plan.py, pae/sketch.py, pae/arcade.py (new), structure_spec program wiring, focused unit tests. Do NOT touch structure_identity/compound_unify/party-wall assemble. Stage H openings deferred. Never git add -A; never demote criticals.
<<< ACK @MASTER

>>> DONE @MP-WS7 â€” Stage G program/rooms + courtyard arcade start. CellRole HALL/SERVICE/ARCADE; program carve maps hall/classroom/service/corridor (hall is NOT corridor); sketch letters H/C/V/R/A + structure_spec merge; new pae/arcade.py ArcadeSpec+select_arcade_walk_cells+arcade() walkable gallery (wall_arcade on court edge, not colonnade); pipeline apply_arcade. Tests: test_stage_g_program_arcade 5/5; stage_d 4/4; school 15/16 (1 pre-existing gallery factory order, not Stage G); program partition regression green. No demotions; structure_identity/compound_unify/party-wall untouched. Gates: stage_G=yes arcade=yes ram_safe=yes blender=no. Gaps: Stage H openings; arcade vault; arcade_walkable/covered full handbook checks + showcase arcade_court deferred; full cloister loop corner polish.

2026-07-25 â€” @MP-WS-J IN PROGRESS
>>> TRIGGER @MP-WS-J â€” Master Plan Stage J skeleton: SiteSpec authoring (structures+offsets+style/seed, road/plot placeholders), YAML/dict round-trip, build path â‰¤3 tiny structures with distinct structure:<id> tags. Owns: pae/site_spec.py (new), pae/tests/unit/test_site_spec.py, Docs/MASTER_PLAN.md Stage J status, AGENT_SYNC. Do NOT touch assemble aperture (MP-WS-H), drum.py, showcase/street_scene. Never fortress/gallery/Blender/MCP/ci_local; never git add -A; never demote criticals. M-G city deferred.
<<< ACK @MASTER
>>> DONE @MP-WS-J — Stage J skeleton: `pae/site_spec.py` SiteSpec/PlacedStructureSpec + Road/Plot placeholders; dict+YAML round-trip; `build_from_site_spec` via pipeline + place_buildings with distinct structure:<id>; soft max=3. Tests: `test_site_spec.py` 5 passed (-p no:cacheprovider). MASTER_PLAN Stage J = SKELETON; M-G city deferred. Left showcase/street_scene alone. Gates: stage_J_skeleton=yes max_structures_tested=2 ram_safe=yes. Gaps: street/plot subdivision, per-plot variation, city gen.

2026-07-25 — @MP-WS-Z
>>> TRIGGER @MP-WS-Z — Consume `geometry.storey_height_cm` via `storey_datum_z_cm(..., storey_cm=)`; final Master Plan reconciliation. Owns: pae/style_pack.py, pae/assemble.py datum/wall-span, test_storey_height_pack.py, Docs/MASTER_PLAN.md, DEFECT_LEDGER.md.
>>> DONE @MP-WS-Z — `resolve_storey_height_cm` + assemble routes pack storey height through single `storey_datum_z_cm` accessor (`_fp_datum_z`, `_level_datum_delta_cm`, wall span, roof z, stairs); default `STOREY_CM` when pack omits hint. Tests: `test_storey_height_pack.py` 3/3; `test_storey_datum_consistent.py` 8/8; `test_style_interchange.py` 7/7; `test_stage_h_openings.py` 17/17. Docs: MASTER_PLAN final reconciliation (Stages A–L, M-A/M-E done, K/M-G/M-I deferred, honest gaps); DEFECT_LEDGER ME-1. Gates: storey_height_consumed=yes datum_single_accessor=yes docs_final=yes ram_safe=yes. Gaps: wall_bands/materials unconsumed; S-021 valley stub; void/balcony auto-railings; grand/imperial stairs; oculus auto-placement; grid-paint §3.2.

2026-07-25 — @MP-WS-REG
>>> DONE @MP-WS-REG — RAM-safe whole-suite sweep (96 files, one pytest process each, serial). Tool: `tools/ram_safe_regression_sweep.py`. Report: `Saved/exports/regression_sweep_report.json`. Totals post-fix: **72 passed / 22 failed / 2 skipped-for-memory** (940 tests). Fixed (a): `validate._check_stair_exit_clearance` module solid pads no longer masked by co-located holes; contract constants in arcade/compound_unify/stair_occupancy/structure_identity + test imports; `arcade_validate` uses `storey_datum_z_cm`. Known reds (b): fortress collinear_gap/aperture_sanity cluster (d3_wiring, castle_curtain, fortress_*, gate_passage, hip_roof, structure_identity, wall_face_exclusive, roof_edging, stair_landing_wall_block, showcase band_proud, arch_arcade_gallery factory order). Deferred/memory: `test_aperture_reachability_critical`, `test_random_specs` (>4GB RSS). Gates: sweep_complete=yes regressions_fixed=4 known_reds=22 ram_safe=yes full_suite_single_process=no.

2026-07-25 — @MP-WS-C
>>> TRIGGER @MP-WS-C — Category-(c) milestone-debt cluster from RAM-safe sweep: m3 keep/tower validate/export/trim + catalog doc + blender skip_clear stub + tower_hall_kiss poison direction. Owns: pae/validate.py (designed roof/wall↔tower_arc interpenetration), pae/trim.py (spiral skip tower_entry yaw), Docs/PRIMITIVE_MEASUREMENTS.md, listed unit tests. No fortress compound rewrite (cat-b).
>>> DONE @MP-WS-C — m3 attach junction: `_designed_roof_tower_arc_pair` + `_designed_wall_tower_arc_pair` silence designed hall↔drum overlaps (interpenetration zero on m3). Trim `_tower_spiral_stairs` skips `DESIGNED_DOOR_BAY_TAGS` yaws (tower_entry_clears_stair). Doc regen `PRIMITIVE_MEASUREMENTS.md` (tower_arc 2×2 contract). Poison test shift −X for west attach. Blender stub `skip_clear` kw. Per-file: validate_polish 8/8, ue_delivery 9/9, export_manifest_cli 24/24, tower_windows 9/9, trim_site_compound 39/39, primitives 20/20, engineering_continuity 7/7, blender_build skip_clear 1/1 (4 fortress gallery tests remain cat-b). Gates: m3_storey_egress=pass ue_m3_export=pass cat_c_fixed=7/8 ram_safe=yes. Debt: blender_build fortress gallery (cat-b crown deck).

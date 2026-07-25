# PAE Agent Sync Board

Project root: `C:\Users\WhiteWidow\Documents\GitHub\ProceduralArchitectureEngine`

**Read `Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md` before coding. Do not redesign — implement.**

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

## Wave plan

1. **Wave A:** WP-1 + WP-9
2. **Wave B:** WP-2 + WP-3 + WP-4
3. **Wave C:** WP-5
4. **Wave D:** WP-6 + WP-7 + WP-8
5. **Wave E:** M4 courtyard/L/U · M5 dynamic assets · M6 UE manifest polish · random-spec un-xfail · gable mesh real — **DONE** (187 passed / 0 xfailed)
6. **Wave F (now):** TOWER_AABB (annulus exempt) · M6_DRYRUN (UE spawn simulator) · GALLERY (Blender M1–M4 shots) · WARN_POLISH (wall/roof allowed pairs)

## Log

```
2026-07-24 — Master: Wave E complete (187/0). Launching Wave F polish lanes.
>>> TRIGGER @TOWER_AABB — Exempt same-cell tower_arc*/crown/cap AABB overlaps as designed annulus quarters; keep real overlaps critical/warning; tests for m3 warn drop; do not touch assemble wall rules.
>>> TRIGGER @M6_DRYRUN — tools/ue_manifest_dry_run.py: load Saved/exports/*.json, verify schema+loc_cm+yaw, emit Saved/exports/m6_dry_run_report.json; unit tests; no UE editor required.
>>> DONE @M6_DRYRUN — tools/ue_manifest_dry_run.py (schema/loc_cm/yaw/asset_id/validation gate, auto-export M1 when default missing); pae/tests/unit/test_ue_manifest_dry_run.py; Docs/UE_MANIFEST_CONSUMER.md dry-run section; report → Saved/exports/m6_dry_run_report.json.
>>> TRIGGER @GALLERY — Extend blender_build for m1+m2+m3+m4_l side-by-side or sequential collections + screenshots Saved/Screenshots/gallery_*.png; keep reload_pae.
>>> TRIGGER @WARN_POLISH — Allow designed wall↔roof / corner-overlap pairs in validate interpenetration without silencing real floaters; regression tests on broken_all_defects.
2026-07-24 — Master: M1 roof-tuck + south gap closed; launching Wave E (M4/M5/M6/polish).
>>> DONE @M5 — Dynamic assets: decorate queries AssetDB by tag (confirmed decorative → sparse interior props); assets.query helpers; run_through_decorate; test_m5_dynamic_assets (accept fake measured brazier id in output); snap_fit 1.76m pillar reject intact; 150 unit passed.
>>> DONE @M6 — UE manifest harden (contract block, LOD placeholders, collision stubs, validation.failures); Docs/UE_MANIFEST_CONSUMER.md; bind_to_terrain integration test (2×2 flatten_pad); tools/export_m1_manifest.py → Saved/exports/m1_manifest.json (39 placements, 6 assets); 12 export+integration tests pass.
2026-07-24 — Launching Wave A+B: WP-1 (Composer), WP-9 (Grok), WP-2 (Composer), WP-3 (Grok), WP-4 (Grok).
>>> DONE @WP-2 — Asset DB (SQLite), sockets, import/fit, min-corner origin, rotates_about_center; 32 tests pass.
>>> DONE @WP-1 — Full §7 validator (9 checks), contract AABB helpers, assembly_types.py, broken_all_defects fixture; 21 WP-1 tests pass (61/62 repo; magic-number grep still flags WP-2/3/9 literals).
>>> DONE @WP-4 — BuildingSpec loader (rejects world/cm), greedy Massing solver, FloorPlan + stair graph, M1 factory; 13 unit tests pass.
>>> DONE @WP-3 — Parametric primitive library (15 kit pieces), dual descriptor/bpy path, Docs/PRIMITIVE_MEASUREMENTS.md; 14 primitive unit tests pass without Blender.
>>> DONE @WP-9 — Determinism hash, golden harness (2% pixel thresh, stub PNG), property scaffolding (xfail until assemble), magic_number_grep + hardened ci.yml; python tools/ci_local.py green (90 passed, 2 xfailed).
>>> DONE @WP-5 — assemble.py (§2.2–2.5 boundary walls, floors, ground, flat roof), decorate pass-through, M1 validate ok=True; 5 assemble unit tests; 118 passed / 2 xfailed repo-wide.
>>> DONE @WP-8 — Comfy decorative ingest (kind gate, normalise→measure→socket→human confirm→DB); materials policy; 23 unit tests; Docs/COMFY_PIPELINE.md.
>>> DONE @WP-7 — Blender add-on UI (§10): Validate click-to-frame, Spec/Assets/Generate/Export panels, pure helpers + 12 unit tests; install `pae/addon/README.md`.
>>> DONE @WP-6 — Export gate (refuses critical), pae.manifest/1 (contract dims), FBX/blend stubs + linked-dupe plan, bind_to_terrain heightmap modes; 10 export unit tests.
2026-07-24 — Master: wired WP-7 export operators to WP-6 APIs (blend/fbx/manifest). M1 proof: validate ok=True, 29 placements, pae.manifest/1 written. Suite: 140 passed, 2 xfailed. ALL WP-1..WP-9 DONE.
>>> DONE @CORNERS_ROOF — roof_flat catalog + span helper; wall corner ownership (west owns SW); ground z −2×FLOOR_T (top at −FLOOR_T); floor/ground interpenetration exempt; 152 passed / 2 xfailed.
>>> DONE @M2 — Two-storey 4×3 rect + straight stair (2 modules, 1 rise), VOID above stair, floor_hole + spanning upper deck, stair_straight in assemble; m2_two_storey_stair_spec(); validate ok=True critical=[]; 8 M2 tests; 152 passed / 2 xfailed repo-wide; M1 + §2.3 east/north boundary regression clean.
>>> DONE @BPY52 — Blender 5.2 mesh harden: bpy_util FLOAT/EXACT/MANIFOLD (never FAST), safe select_set, scene.collection link; pae/blender_build.py M1+M2 assemble→validate→catalog.build_mesh/framed fallback→cm→m 0.01→Saved/Screenshots/m1_live.png + reload_pae; tools/pae_build_in_blender.py; unit tests green without bpy.
>>> DONE @CI_M1 — Un-xfail M1 property validate; M1 determinism hash (2-run); golden baselines (placement meta hash + 64² stub PNG); random multi-wing remains xfail. magic_number_grep OK; pytest 161 passed / 1 xfailed.
>>> DONE @M3 — Pitched roof (`roof_pitched_gable` spanning deck + gable tags), tower arcs ×4 same-cell `rotates_about_center=True` (no 4-cell scatter) + crown/cap, `m3_keep_tower_spec()` (wall-attached, M1/M2 untouched). Tests: pitched emits gable pieces; tower same-cell. M3 validate ok=True (critical=0; ~52 warnings mostly tower-quarter AABB interpenetration). Gaps: pitched is span AABB proxy (not per-bay gable mesh); tower AABB overlap warnings expected until true annulus collision; corner-tower still breaks 4-connect circulation (factory uses wall attach). Suite: 161 passed / 1 xfailed.
>>> DONE @GABLES — Pitched roof split: `roof_gable_infill` (triangular prism per gable-end bay) + `roof_pitched_slope` (row/column-spanning wedge decks); real bpy meshes (not AABB span proxy). Assemble places gables on end rows/cols + interior slope spans for §7.2 wall support. Tests: m3_pitched emits ≥8 gable infill + slope rows; validate critical=[]; m3_keep_tower ok. `blender_build` includes m3 + optional `Saved/Screenshots/m3_pitched.png`. Removed `roof_pitched_gable`. Suite: 184 passed / 1 xfailed (pre-existing magic-number hit in m5 test).
>>> DONE @M4 — Courtyard/L/U multi-wing: solver non-overlapping wings + courtyard role outside envelope; plan COURTYARD cells; assemble inner inhabited walls on courtyard/re-entrant faces + per-wing roofs (no deck over courtyard). Factories `m4_l_plan_spec()`, `m4_u_plan_spec()`, `m4_courtyard_spec()`. Validate ok=True critical=[] for L, U, courtyard. 12 M4 tests; M1 south-gap + E/N roof-tuck regression clean. Suite: 183 passed / 1 xfailed (2 unrelated fails: M3 pitched floater test + M5 magic grep from parallel lane).
>>> DONE @PROPERTY — Un-xfail `test_random_specs_validate_ok`: solver local-repair now nudges *overlapping* interior towers to exterior wall/corner (was skipped via `_tower_touches`); random factory emits exterior attach cells + south-bar stairs. M5 test uses `STOREY_CM` (magic_number_grep). Suite: 187 passed / 0 xfailed; 500 random seeds green.
>>> DONE @GALLERY — `build_gallery(milestones=None)` → `PAE_Gallery` / `PAE_M1`…`PAE_M4_L` side-by-side (+X footprint+2m gap); `write_gallery_screenshot` → `Saved/Screenshots/gallery_m1_m4.png` + per-milestone `gallery_{label}.png`; factories from `pae.spec`; `reload_pae` preserved; `build_live` M1 path unchanged; `tools/pae_build_in_blender.py --gallery`; unit tests in `test_blender_build.py`.
>>> DONE @GALLERY_CAM — Per-milestone gallery shots frame only that collection's instances (`_meshes_in_collection_tree` + `mesh_world_bounds_m`); deterministic SE-elevated ortho via `camera_pose_from_bounds_m`; overview still `PAE_Gallery` row; `reload_pae` + cm→m preserved; 10 unit tests in `test_blender_build.py`.
>>> DONE @VALIDATE_POLISH — `pae/validate.py` §7.4 designed-pair exemptions: same-cell tower_arc/crown/cap annulus, WALL_T corner overlaps, wall↔roof deck eave tuck, storey slab above wall/stair/tower, floor_hole deck, stair openings. m3 interpenetration warns 88→1 (remaining: south+inner_north T-junction at tower); m1/m2/m4 ok=True critical=[]. `test_validate_polish.py` + broken_all_defects regression intact. Suite: 213 passed.
>>> DONE @APERTURE_GAPS — m1 warns 3→0, m2 7→0, m3 9→0 (incl. interpenetration 1→0), m4_l 3→0; critical=[] all milestones. Root fixes: `assemble.py` perimeter wall_runs classify by piece_id face (not cell bucket — killed 340 cm false collinear_gap); skip redundant inner walls on perpendicular perimeter corners (tower T-junction); BFS door interior/exterior cell resolve through WALL_LINE corners + tower attach. `validate.py` exterior door side accepts EXTERIOR/COURTYARD/out-of-grid/DOOR threshold. `broken_all_defects` door_bad_exit exterior→interior cell (still aperture_sanity). Tests: `test_m1_m4_m3_aperture_gap_warnings_zero`, `test_m3_interpenetration_zero`. Suite: 241 passed.
>>> DONE @EXPORT_ALL — `tools/export_manifest.py` (`--milestone m1|m2|m3|m4_l|m4_u|m4_c` → `Saved/exports/{milestone}_manifest.json`, fail-closed on critical); `export_m1_manifest.py` thin wrapper; `ue_manifest_dry_run.py` `--milestone` + generalized auto-export; `test_export_manifest_cli.py` (per-milestone export + m1/m3 dry-run integration); full pytest green.
```
>>> DONE @GALLERY_CAM_FIX � Collection unlink used Object.users_collection by mistake; parent scan via scene+data children. Gallery rebuild ok (m1=39 m2=55 m3=104 m4_l=102).

>>> DONE @GALLERY_FRAME � depsgraph update before bounds; hide sibling collections per-milestone; fixed tiny/empty PNGs.

>>> DONE @TOWER_VISUAL � Real tower meshes: `annulus_quarter_verts` axis snap + 96-seg seams; `annulus_battlement_ring_verts` centred crown; `cone_verts` centred cap (removed proto `obj.location` hack lost on instance). `test_tower_mesh.py` (vert counts, seam continuity, AABB, crown/cap Z stack). Assemble stacking unchanged (crown_z=STOREY_CM on top level correct). Suite: +6 tower tests; 250 passed / 3 pre-existing fails (m1 golden hash, pitched roof floater).

>>> DONE @M1_VISUAL - Corner opening ownership (_primary_opening_face): SW door south-only, NW window west-only. placement_instance_scale_cm non-uniform XY for spanning roof_flat (fixes recessed roof ledge). Measured wall/roof outer flush delta=0 cm all faces. Tests + golden hash updated.

>>> DONE @ROOF_VISUAL ? Pitched roof gable fix: `_place_pitched_roof` places 2 end-cap `roof_gable_infill` prisms (ridge-end X or Y) spanning full cross-span; slope wedges on every cross row/column spanning full ridge length (not sawtooth along eaves). m3 4�3: gables 8?2, slopes 1?3; validate critical=[]; `_designed_roof_gable_slope_pair` exempts end-cap AABB overlap. Restored `test_m3_tower_arcs_same_cell` def. Suite: 253 passed.

>>> DONE @ROOF_AFRAME � single double-pitch span + end gables facing �X; Proto mesh refresh (crown 576 / cap 97 verts). M3 gallery reads as gabled hall + cone tower. Suite 253.

>>> DONE @TOWER_OUTSIDE � `_tower_drum_xy_offset_cm` pushes 2�MODULE annulus outward along abutment normal (west m3: centre (-800,200) vs old (-400,0); drum east edge -400 kisses hall west at 0). Same-cell 4-quarter rule intact; crown/cap share offset + 0.5 cm Z gap. Tests: `test_m3_tower_drum_outside_hall_footprint`. Suite: 254 passed.

>>> DONE @M2_STAIR_VIS � `stair_straight`: 20 stepped tread/riser boxes (`straight_stair_verts_faces`, 17.5 cm � 40 cm); `floor_hole`: full-bay void (10 cm rim, 380�380 opening) via perimeter frame mesh; descriptor sizes unchanged; `test_stair_floor_mesh.py` (step count + hole AABB/void); M2 pipeline + validate polish green.
>>> DONE @M6_HANDOFF � `tools/ue_spawn_table.py` (`--milestone` ? `Saved/exports/{milestone}_spawn_table.json`, optional `--csv`; rows: asset_id/loc_cm/yaw/piece_id; validation+dry-run gate); `pae/tests/unit/test_ue_spawn_table.py`; `Docs/UE_MANIFEST_CONSUMER.md` spawn-table + UE Editor Python pseudocode.

>>> DONE @M4_GALLERY � Gallery extended m4_u + m4_c (`PAE_M4_U`, `PAE_M4_C`); factories `m4_u_plan_spec`, `m4_courtyard_spec`; per-milestone `gallery_m4_u.png` / `gallery_m4_c.png`; headless test asserts courtyard has 4 wing roofs and none cover court cell (3,3). Suite: test_blender_build green.

>>> DONE @M5_DEMO � M5 e2e demo: `pae/tests/fixtures/m5_demo_crate.obj` (50�50�80 cm) + `pae/assets/obj_measure.py` + `pae/assets/demo_seed.py`; `tools/m5_demo_seed_db.py` seeds `Saved/demo/m5_assets.db` and runs `run_through_decorate(m1_box_house_spec())` (39?40 placements, 1 prop); `test_m5_demo_fixture` proves count increase + validate ok. Suite: 265 passed.

>>> DONE @DOOR_BOOL � Wall door/window mesh: bmesh frame (sill/lintel/jambs) via `build_box_with_rect_aperture_along_x` ? no boolean corner voids. Descriptor fractions unchanged (_DOOR_W=0.40, _WINDOW_* contract-relative); cutter pad 25% WALL_T each face + 0.5 cm Y/Z for boolean fallback (`apply_aperture_boolean_cut`, EXACT/MANIFOLD). Tests: `test_wall_apertures.py` (9). Suite: 279 passed / 1 pre-existing fail (`test_stair_floor_mesh` tread nose count).

>>> DONE @TOWER_LOOK � Tower mesh polish: `TOWER_ARC_SEGMENTS_FULL=128`; arc quarters open horizontal caps + true vertical cylinder columns (132/66 verts); crown = parapet drum ring + discrete merlon wedges (544/408, was 576/384 wavy ring); cap cone 128-seg (129/128). `rotates_about_center` / size_cm / aabb contracts intact. Tests: +3 tower mesh. Suite: 283 passed.


2026-07-24 � Master: Wave H VISUAL/PRODUCT swarm dispatched (DOOR_BOOL, TOWER_LOOK, M2_STAIR_VIS, M4_GALLERY, M5_DEMO, M6_HANDOFF).


2026-07-24 — Master: Wave I swarm (Composer 2.5) — aperture facing, eaves, materials, floaters, stair prove, UE bind note.
>>> TRIGGER @APERTURE_FACE — Door/window openings must face outward on correct wall axis; kill P-shaped silhouette. Own walls.py + assemble wall yaw only if required.
>>> DONE @APERTURE_FACE — Wall aperture frame punches thin X only (`wall_aperture_frame_parts_cm`: full-height pillars + sill/lintel between jambs); `aperture_opening_run_vertical` guards run/thickness axis swap; bpy `build_mesh_from_box_parts`. Tests: through-hole, exterior rect void, no run-end notch. Suite: 285 passed.
>>> TRIGGER @EAVES — Small roof overhang past walls (flat + pitched) so roofs read as roofs. Own roofs.py + assemble roof size/offset.
>>> DONE @EAVES — `EAVE_OVERHANG_CM = WALL_T_CM * 0.5` (30 cm); flat + pitched roofs grow/offset via roof span helpers; per-wing interior seams zero overhang. m1/m3/m4 validate ok. Suite: 304 passed.
>>> TRIGGER @MAT_READ — Distinct Blender materials per kind (wall/roof/floor/tower/stair) for gallery readability. Own blender_build.py materials only.
>>> DONE @MAT_READ � KIND_MATERIAL_COLORS + material_color_for_kind() in pae/blender_build.py; distinct workbench hues for wall/floor/ground/roof/stair/tower_arc/tower_crown/tower_cap/door/window (+ prop/plinth/hole fallbacks); _ensure_material updates existing mats on re-run. Tests: test_kind_material_colors_* in test_blender_build.py.
>>> TRIGGER @FLOATER_KILL — Find/remove stray disconnected slabs in m3 gallery (left block). Own assemble ground/tower plinth or blender clear.
>>> DONE @FLOATER_KILL - Orphan ground_plinth + L0 floor at tower cell (-1,0) after drum XY offset (slab x in [-400,0] vs drum x in [-1000,-600]). Fix: skip _tower_cells in ground + L0 floor loops. Test: test_m3_no_disconnected_ground_plinth_far_from_hall_tower_union.
>>> TRIGGER @STAIR_PROVE — Gallery/live shot proves stepped stair + hole visible (dedicated Cam or forced m2 interior frame). Own blender_build.py screenshot helpers.
>>> DONE @STAIR_PROVE � build_m2_stair_proof() -> Saved/Screenshots/m2_stair_proof.png; deterministic camera from stair+floor_hole AABB; hides roof_flat + upper floor deck; tools/pae_build_in_blender.py --stair-proof; optional build_gallery(stair_proof=True); headless tests in test_blender_build.py.
>>> TRIGGER @UE_BIND — Doc + tool mapping spawn_table asset_id to Content path stub for RE. Own Docs + tools only.
>>> DONE @UE_BIND � `tools/ue_asset_bind_table.py` (`--milestone` ? `Saved/exports/{milestone}_asset_bind.json`; `pae.asset_bind/1`: asset_id/suggested_content_path/lod0/collision_profile stubs under `/Game/RE/PAE/...`; optional spawn-table id source); `pae/tests/unit/test_ue_asset_bind_table.py`; `Docs/UE_MANIFEST_CONSUMER.md` bind + UE fill section.

2026-07-24 — Master: Wave J swarm — stair isolate, mat tint by asset, wall thickness read, opening prove shot, ground skirt.
>>> TRIGGER @STAIR_ISO — Hide ALL non stair/floor_hole in stair proof (walls/ground too). Own blender_build.py only.
>>> DONE @STAIR_ISO � is_stair_proof_visible_asset() allow-list; _apply_stair_proof_visibility hides viewport+render on every mesh except stair/floor_hole/hole tokens; _hide_non_stair_proof_collections excludes other PAE collections; camera still framed on stair+hole AABB; tests in test_blender_build.py.
>>> TRIGGER @MAT_TINT — Tint door/window by asset_id not just kind=wall. Own blender_build.py materials.
>>> DONE @MAT_TINT � ASSET_MATERIAL_COLORS + material_key_for_placement() / material_color_for_placement(); instance_assembly + _ensure_material tint by asset_id (wall_door, wall_window, roof_*, tower_*, stair_*, floor_hole); higher-contrast workbench hues. Tests: test_material_key_for_placement_*, test_asset_material_colors_* in test_blender_build.py.
>>> TRIGGER @OPEN_PROVE — Dedicated m1_openings_proof.png camera on door+windows exterior. Own blender_build.py.
>>> DONE @OPEN_PROVE — build_m1_openings_proof() -> Saved/Screenshots/m1_openings_proof.png; SE-elevated ortho on south/west shell AABB; hides north/east walls + roof/floor; tools/pae_build_in_blender.py --openings-proof; headless tests in test_blender_build.py.
>>> TRIGGER @WALL_READ — Ensure wall thickness WALL_T reads in gallery (not paper-thin illusion). Own walls size/assemble if needed.
>>> TRIGGER @GROUND_SKIRT — Continuous ground under footprint (single slab or flush plinths) — no checkerboard gaps. Own assemble ground.
>>> DONE @GROUND_SKIRT — `ground_plinth_span_size_cm()` + `_ground_spans()` (main/wing volumes; tower DOOR cells excluded); one spanning slab per wing/footprint like roof_flat. FLOATER_KILL tower floor skip preserved. M1 golden hash/n_placements updated (28). Suite: 320 passed.
>>> DONE @RENDER_COLOR - Workbench gallery PNGs: configure_workbench_screenshot_scene (SOLID/STUDIO/MATERIAL + view_transform=Standard); apply_material_base_color sets Principled Base Color + mat.diffuse_color; write_screenshot uses helper. Tests: test_configure_workbench_screenshot_scene_*, test_apply_material_base_color_*.
>>> TRIGGER @STAIR_CAM ? Perpendicular stair proof camera (not along tread run); Workbench MATERIAL proof colors.
>>> DONE @STAIR_CAM ? stair_proof_camera_direction_from_bounds_m (longer X ? offset Y, longer Y ? offset X, elevated); stair_proof_ortho_scale_from_bounds_m tight on visible face; GALLERY_SUN_ENERGY 4.5; write_screenshot uses configure_workbench_screenshot_scene MATERIAL. Tests: test_stair_proof_camera_offset_* + test_m2_stair_proof_camera_perpendicular_to_y_run.

2026-07-24 � Stair exit clearance (fail-closed).
>>> DONE @STAIR_EXIT � validate stair_exit_clearance: missing floor_hole / solid pad / wall|roof in head clearance = critical. Spanning upper deck mesh punches VOID holes (slab_with_rect_holes). Open-stair tops use floor_hole rim + deck tiles (no solid plug). Proof: Saved/Screenshots/open_stair_roof_hole_proof.png + m2_stair_proof.png. Tests: test_stair_exit_clearance.py; suite stair-related green.

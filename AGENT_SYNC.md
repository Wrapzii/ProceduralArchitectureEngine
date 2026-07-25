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
5. **Wave E (now):** M4 courtyard/L/U · M5 dynamic assets · M6 UE manifest polish · random-spec un-xfail · gable mesh real

## Log

```
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
```

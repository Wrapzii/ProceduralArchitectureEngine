"""M5 — Dynamic decorative assets: Comfy ingest → AssetDB → decorate (§11 M5, §9)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pae.assets.db import AssetDB
from pae.assets.demo_seed import (
    M5_DEMO_CRATE_ID,
    M5_DEMO_CRATE_XY_CM,
    M5_DEMO_CRATE_Z_CM,
    m5_demo_fixture_path,
    seed_m5_demo_assets,
)
from pae.assets.fit import snap_fit
from pae.assets.import_ import MeasuredAABB, import_asset_measured
from pae.assets.obj_measure import measure_obj_aabb
from pae.assets.query import list_decorative_for_generator
from pae.comfy import confirm_decorative, ingest_decorative
from pae.contract import STOREY_CM
from pae.decorate import decorate, pick_prop_assets
from pae.pipeline import run_through_assemble, run_through_decorate
from pae.spec import m1_box_house_spec
from pae.validate import validate


# Measured decorative sizes — intentionally off-grid (precision irrelevant for props).
_BRAZIER_XY = 55.0
_BRAZIER_Z = 95.0
_ASSET_ID = "m5_brazier_measured"


def _brazier_aabb() -> MeasuredAABB:
    return MeasuredAABB(
        min_corner=(0.0, 0.0, 0.0),
        max_corner=(_BRAZIER_XY, _BRAZIER_XY, _BRAZIER_Z),
    )


class TestM5SnapFitUntouched:
    def test_structural_176cm_pillar_still_rejects(self):
        """Do not break §4.3 structural snap_fit reject for 1.76 m pillars."""
        decision, _ = snap_fit(176.0)
        assert decision == "reject"

        result = import_asset_measured(
            "pillar_176",
            "/kit/pillar.glb",
            "prop",
            MeasuredAABB(
                min_corner=(0.0, 0.0, 0.0),
                max_corner=(176.0, 176.0, STOREY_CM),
            ),
        )
        assert result.asset is None
        assert result.fit_decision == "reject"
        assert any(f.check == "snap_fit" for f in result.report.critical)


class TestM5DecorateFromDb:
    def test_query_picks_confirmed_decorative_without_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                pending = ingest_decorative(
                    _ASSET_ID,
                    "/gen/brazier.glb",
                    "brazier",
                    measured=_brazier_aabb(),
                    human_confirmed=False,
                    tags={"indoor", "m5"},
                )
                assert pending.artifact is not None
                assert db.get_asset(_ASSET_ID) is None

                confirmed = confirm_decorative(pending.artifact, db)
                assert confirmed.report.ok
                assert confirmed.artifact is not None
                assert confirmed.artifact.written_to_db

                # Generator query API — new tagged asset appears with no code edit.
                found = list_decorative_for_generator(db, tags={"decorative", "m5"})
                assert any(a.id == _ASSET_ID for a in found)
                picked = pick_prop_assets(db, tags={"decorative", "human_confirmed", "m5"})
                assert [a.id for a in picked] == [_ASSET_ID]
            finally:
                db.close()

    def test_decorate_places_asset_id_on_interior_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                result = ingest_decorative(
                    _ASSET_ID,
                    "/gen/brazier.glb",
                    "brazier",
                    measured=_brazier_aabb(),
                    human_confirmed=True,
                    db=db,
                    tags={"indoor", "m5"},
                )
                assert result.artifact is not None
                assert result.artifact.written_to_db

                _, _, assembly, dreport = run_through_decorate(
                    m1_box_house_spec(seed=42),
                    asset_db=db,
                    seed=42,
                    tags={"decorative", "human_confirmed", "m5"},
                )
                assert dreport.ok
                prop_ids = [
                    p.asset_id for p in assembly.placements if p.kind == "prop"
                ]
                assert _ASSET_ID in prop_ids
                assert any(p.piece_id.startswith("prop_") for p in assembly.placements)
            finally:
                db.close()

    def test_decorate_seed_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                ingest_decorative(
                    _ASSET_ID,
                    "/gen/brazier.glb",
                    "brazier",
                    measured=_brazier_aabb(),
                    human_confirmed=True,
                    db=db,
                )
                _, _, a1, _ = run_through_decorate(
                    m1_box_house_spec(seed=7), asset_db=db, seed=7
                )
                _, _, a2, _ = run_through_decorate(
                    m1_box_house_spec(seed=7), asset_db=db, seed=7
                )
                props1 = [
                    (p.piece_id, p.cell, p.asset_id)
                    for p in a1.placements
                    if p.kind == "prop"
                ]
                props2 = [
                    (p.piece_id, p.cell, p.asset_id)
                    for p in a2.placements
                    if p.kind == "prop"
                ]
                assert props1 == props2
                assert props1  # at least one prop with density default
            finally:
                db.close()

    def test_pass_through_without_db(self):
        from pae.pipeline import run_through_assemble

        _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
        decorated, report = decorate(assembly, None)
        assert report.ok
        assert decorated.placements == assembly.placements
        assert not any(p.kind == "prop" for p in decorated.placements)

    def test_unconfirmed_not_placed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                # Pending ingest never writes DB — decorate must not invent props.
                ingest_decorative(
                    "pending_statue",
                    "/gen/statue.glb",
                    "statue",
                    measured=MeasuredAABB(
                        min_corner=(0.0, 0.0, 0.0),
                        max_corner=(80.0, 80.0, 160.0),
                    ),
                    human_confirmed=False,
                    db=db,
                )
                assert db.get_asset("pending_statue") is None
                _, _, assembly, dreport = run_through_decorate(
                    m1_box_house_spec(), asset_db=db, seed=1
                )
                assert dreport.ok  # warning only
                assert not any(p.kind == "prop" for p in assembly.placements)
            finally:
                db.close()


class TestM5DemoFixture:
    def test_obj_fixture_measured_size(self):
        measured = measure_obj_aabb(m5_demo_fixture_path())
        assert measured.size_cm == (
            M5_DEMO_CRATE_XY_CM,
            M5_DEMO_CRATE_XY_CM,
            M5_DEMO_CRATE_Z_CM,
        )

    def test_seed_db_places_props_and_increases_placement_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "m5_demo.db")
            try:
                ingested = seed_m5_demo_assets(db)
                assert ingested.artifact is not None
                assert ingested.artifact.written_to_db
                stored = db.get_asset(M5_DEMO_CRATE_ID)
                assert stored is not None
                assert stored.size_cm == (
                    M5_DEMO_CRATE_XY_CM,
                    M5_DEMO_CRATE_XY_CM,
                    M5_DEMO_CRATE_Z_CM,
                )
                assert "human_confirmed" in stored.tags
                assert "m5_demo" in stored.tags
                assert any(s.name == "base" for s in stored.sockets)

                _, _, bare, _ = run_through_assemble(m1_box_house_spec(seed=11))
                _, _, decorated, dreport = run_through_decorate(
                    m1_box_house_spec(seed=11),
                    asset_db=db,
                    seed=11,
                )
                assert dreport.ok
                assert len(decorated.placements) > len(bare.placements)
                assert any(
                    p.kind == "prop" and p.asset_id == M5_DEMO_CRATE_ID
                    for p in decorated.placements
                )
                _, vreport = validate(decorated)
                assert vreport.ok
                assert not any(f.critical for f in vreport.failures)
            finally:
                db.close()


def test_m5_e2e_fake_measured_asset_id_in_decorate_output():
    """Acceptance: insert fake measured decorative asset → pipeline → id in output."""
    with tempfile.TemporaryDirectory() as tmp:
        db = AssetDB(Path(tmp) / "m5.db")
        try:
            ingested = ingest_decorative(
                _ASSET_ID,
                "/gen/fake_brazier.glb",
                "brazier",
                measured=_brazier_aabb(),
                human_confirmed=True,
                db=db,
                tags={"m5_acceptance"},
            )
            assert ingested.artifact is not None
            assert ingested.artifact.written_to_db
            stored = db.get_asset(_ASSET_ID)
            assert stored is not None
            assert stored.size_cm == (_BRAZIER_XY, _BRAZIER_XY, _BRAZIER_Z)
            assert "human_confirmed" in stored.tags

            _, _, assembly, report = run_through_decorate(
                m1_box_house_spec(seed=99),
                asset_db=db,
                seed=99,
                tags={"decorative", "human_confirmed", "m5_acceptance"},
            )
            assert report.ok
            assert any(
                p.asset_id == _ASSET_ID and p.kind == "prop"
                for p in assembly.placements
            )
        finally:
            db.close()

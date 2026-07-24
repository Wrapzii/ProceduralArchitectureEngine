"""Unit tests for asset import pipeline."""

import tempfile
from pathlib import Path

import pytest

from pae.assets.db import AssetDB
from pae.assets.fit import snap_fit
from pae.assets.import_ import (
    MeasuredAABB,
    center_origin_offset,
    import_asset,
    import_asset_measured,
    min_corner_origin_offset,
    normalize_to_min_corner,
    size_cm_from_aabb,
)
from pae.contract import MODULE_CM, WALL_T_CM


class TestOriginHelpers:
    def test_min_corner_normalization(self):
        new_min, new_max = normalize_to_min_corner((10.0, 20.0, 5.0), (70.0, 420.0, 355.0))
        assert new_min == (0.0, 0.0, 0.0)
        assert new_max == (60.0, 400.0, 350.0)

    def test_min_corner_offset(self):
        assert min_corner_origin_offset((10.0, 20.0, 5.0)) == (-10.0, -20.0, -5.0)

    def test_center_offset(self):
        assert center_origin_offset((0.0, 0.0, 0.0), (400.0, 400.0, 350.0)) == (
            -200.0,
            -200.0,
            -175.0,
        )

    def test_size_from_aabb(self):
        assert size_cm_from_aabb((0.0, 0.0, 0.0), (60.0, 400.0, 350.0)) == (
            60.0,
            400.0,
            350.0,
        )


class TestImportAsset:
    def test_nominal_wall_imports(self):
        result = import_asset(
            "wall_test",
            "/meshes/wall.fbx",
            "wall",
            min_corner=(0.0, 0.0, 0.0),
            max_corner=(WALL_T_CM, MODULE_CM, 350.0),
            tags={"exterior"},
        )
        assert result.asset is not None
        assert result.fit_decision == "ok"
        assert result.report.ok
        assert {s.name for s in result.proposed_sockets} == {"end_a", "end_b"}

    def test_176cm_footprint_rejects_not_silent(self):
        """§4.3 / WP-2 acceptance — fake measured 1.76 m pillar in 4 m module."""
        decision, _ = snap_fit(176.0)
        assert decision == "reject"

        result = import_asset(
            "bad_pillar",
            "/meshes/pillar.fbx",
            "prop",
            measured_aabb=MeasuredAABB(
                min_corner=(0.0, 0.0, 0.0),
                max_corner=(176.0, 176.0, 350.0),
            ),
        )
        assert result.asset is None
        assert result.fit_decision == "reject"
        assert not result.report.ok
        assert any(f.check == "snap_fit" for f in result.report.critical)

    def test_176cm_with_scale_disabled_rejects(self):
        result = import_asset(
            "bad_pillar",
            "/meshes/pillar.fbx",
            "prop",
            min_corner=(0.0, 0.0, 0.0),
            max_corner=(176.0, MODULE_CM, 350.0),
            allow_scale=False,
        )
        assert result.asset is None
        assert result.fit_decision in ("reject", "scale")

    def test_declared_size_without_measure_fails(self):
        result = import_asset("no_measure", "/x.fbx", "wall")
        assert result.asset is None
        assert not result.report.ok

    def test_persists_to_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "assets.db"
            with AssetDB(db_path) as db:
                result = import_asset_measured(
                    "wall_db",
                    "/meshes/wall.fbx",
                    "wall",
                    MeasuredAABB((0.0, 0.0, 0.0), (WALL_T_CM, MODULE_CM, 350.0)),
                    db=db,
                )
                loaded = db.get_asset("wall_db")

            assert result.asset is not None
            assert loaded is not None
            assert loaded.size_cm == (WALL_T_CM, MODULE_CM, 350.0)

    def test_rotates_about_center_flag(self):
        result = import_asset(
            "arc_q1",
            "/meshes/arc.fbx",
            "tower_arc",
            min_corner=(0.0, 0.0, 0.0),
            max_corner=(MODULE_CM, MODULE_CM, 350.0),
            rotates_about_center=True,
        )
        assert result.asset is not None
        assert result.asset.rotates_about_center is True
        assert result.asset.origin == "center"

    def test_stretch_within_ceiling_warns_not_critical(self):
        slightly_off = MODULE_CM - 15.0
        result = import_asset(
            "floor_off",
            "/meshes/floor.fbx",
            "floor",
            min_corner=(0.0, 0.0, 0.0),
            max_corner=(slightly_off, MODULE_CM, 30.0),
        )
        assert result.asset is not None
        assert result.fit_decision == "scale"
        assert result.report.ok
        assert result.report.warnings

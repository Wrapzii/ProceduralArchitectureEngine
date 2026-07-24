"""WP-8 Comfy decorative pipeline — decorative accept + structural reject."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pae.assets.db import AssetDB
from pae.assets.import_ import MeasuredAABB
from pae.comfy import (
    DECORATIVE_KINDS,
    STRUCTURAL_KINDS,
    GlbMetadata,
    confirm_decorative,
    ingest_decorative,
    is_decorative,
    is_structural,
    normalize_glb_metadata,
)
from pae.comfy.materials import DEFAULT_MATERIAL_POLICY
from pae.contract import MODULE_CM, STOREY_CM


# Decorative fixture sizes — not grid contract literals.
_STATUE_XY = 85.0
_STATUE_Z = 180.0
_BRAZIER_XY = 55.0
_BRAZIER_Z = 95.0


def _statue_aabb() -> MeasuredAABB:
    return MeasuredAABB(
        min_corner=(12.0, -4.0, 3.0),
        max_corner=(12.0 + _STATUE_XY, -4.0 + _STATUE_XY, 3.0 + _STATUE_Z),
    )


class TestKindGates:
    def test_decorative_kinds_listed(self):
        for k in ("statue", "banner", "brazier", "furniture", "gargoyle", "fountain"):
            assert k in DECORATIVE_KINDS
            assert is_decorative(k)

    def test_structural_kinds_listed(self):
        for k in ("wall", "floor", "stair", "roof", "tower_arc", "plinth"):
            assert k in STRUCTURAL_KINDS
            assert is_structural(k)

    def test_no_overlap(self):
        assert DECORATIVE_KINDS.isdisjoint(STRUCTURAL_KINDS)


class TestStructuralReject:
    @pytest.mark.parametrize("kind", sorted(STRUCTURAL_KINDS))
    def test_structural_ingest_fails(self, kind: str):
        result = ingest_decorative(
            f"bad_{kind}",
            f"/gen/{kind}.glb",
            kind,
            measured=MeasuredAABB(
                min_corner=(0.0, 0.0, 0.0),
                max_corner=(MODULE_CM, MODULE_CM, STOREY_CM),
            ),
            human_confirmed=True,
        )
        assert result.artifact is None
        assert not result.report.ok
        assert any(f.check == "comfy_structural_reject" for f in result.report.critical)

    def test_wall_never_written_even_with_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                result = ingest_decorative(
                    "wall_from_comfy",
                    "/gen/wall.glb",
                    "wall",
                    measured=_statue_aabb(),
                    human_confirmed=True,
                    db=db,
                )
                assert result.artifact is None
                assert db.get_asset("wall_from_comfy") is None
            finally:
                db.close()


class TestDecorativeAccept:
    def test_statue_normalise_measure_socket(self):
        result = ingest_decorative(
            "statue_iron",
            "/gen/statue.glb",
            "statue",
            measured=_statue_aabb(),
            human_confirmed=False,
        )
        assert result.report.ok  # pending confirm is a warning, not critical
        assert result.artifact is not None
        assert result.artifact.kind == "statue"
        assert result.artifact.measured_size_cm == (_STATUE_XY, _STATUE_XY, _STATUE_Z)
        assert result.artifact.normalize is not None
        assert result.artifact.normalize.min_corner == (0.0, 0.0, 0.0)
        assert any(s.name == "base" for s in result.artifact.proposed_sockets)
        assert not result.artifact.written_to_db
        assert "needs_human_confirm" in result.artifact.asset.tags

    def test_glb_metadata_path_without_comfy(self):
        meta = GlbMetadata(
            path="/gen/brazier.glb",
            measured=MeasuredAABB(
                min_corner=(0.0, 0.0, 0.0),
                max_corner=(_BRAZIER_XY, _BRAZIER_XY, _BRAZIER_Z),
            ),
            prompt_height_m=1.0,
            forward_axis="+Y",
            texture_path="/gen/brazier_paint.png",
            tri_count=8000,
        )
        norm = normalize_glb_metadata(meta)
        assert norm.size_cm == (_BRAZIER_XY, _BRAZIER_XY, _BRAZIER_Z)

        result = ingest_decorative(
            "brazier_01",
            meta.path,
            "brazier",
            glb=meta,
            human_confirmed=False,
        )
        assert result.artifact is not None
        assert result.report.ok
        assert result.artifact.material_policy.generated_texture_is_guide_only
        assert result.artifact.material_policy.texture_guide is not None
        assert result.artifact.material_policy.texture_guide.path == meta.texture_path

    def test_human_confirm_writes_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                pending = ingest_decorative(
                    "gargoyle_ne",
                    "/gen/gargoyle.glb",
                    "gargoyle",
                    measured=MeasuredAABB(
                        min_corner=(0.0, 0.0, 0.0),
                        max_corner=(70.0, 40.0, 55.0),
                    ),
                    human_confirmed=False,
                )
                assert pending.artifact is not None
                assert db.get_asset("gargoyle_ne") is None

                confirmed = confirm_decorative(pending.artifact, db)
                assert confirmed.report.ok
                assert confirmed.artifact is not None
                assert confirmed.artifact.written_to_db
                stored = db.get_asset("gargoyle_ne")
                assert stored is not None
                assert stored.kind == "gargoyle"
                assert "human_confirmed" in stored.tags
                assert "needs_human_confirm" not in stored.tags
                assert any(s.name == "base" for s in stored.sockets)
            finally:
                db.close()

    def test_ingest_with_confirm_and_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AssetDB(Path(tmp) / "assets.db")
            try:
                result = ingest_decorative(
                    "furniture_bench",
                    "/gen/bench.glb",
                    "furniture",
                    measured=MeasuredAABB(
                        min_corner=(0.0, 0.0, 0.0),
                        max_corner=(120.0, 45.0, 50.0),
                    ),
                    human_confirmed=True,
                    db=db,
                    tags={"outdoor"},
                )
                assert result.artifact is not None
                assert result.artifact.written_to_db
                assert result.report.ok
                stored = db.get_asset("furniture_bench")
                assert stored is not None
                assert "outdoor" in stored.tags
                assert "comfy" in stored.tags
            finally:
                db.close()

    def test_unknown_kind_rejected(self):
        result = ingest_decorative(
            "weird",
            "/gen/x.glb",
            "spaceship",
            measured=_statue_aabb(),
        )
        assert result.artifact is None
        assert not result.report.ok

    def test_missing_measure_rejected(self):
        result = ingest_decorative("no_mesh", "/gen/x.glb", "statue")
        assert result.artifact is None
        assert any(f.check == "measure" for f in result.report.critical)

    def test_material_policy_default(self):
        assert DEFAULT_MATERIAL_POLICY.engine_authored
        assert DEFAULT_MATERIAL_POLICY.generated_texture_is_guide_only
        assert "colour guide" in DEFAULT_MATERIAL_POLICY.summary().lower() or (
            "color guide" in DEFAULT_MATERIAL_POLICY.summary().lower()
            or "guide" in DEFAULT_MATERIAL_POLICY.summary().lower()
        )

"""Unit tests for SQLite AssetDB."""

import tempfile
from pathlib import Path

from pae.assets.db import Asset, AssetDB, Socket


def _sample_wall() -> Asset:
    return Asset(
        id="wall_plain",
        path="/meshes/wall_plain.fbx",
        kind="wall",
        footprint_modules=(1, 1),
        height_storeys=1.0,
        size_cm=(60.0, 400.0, 350.0),
        sockets=[
            Socket("end_a", (0.0, 200.0, 175.0), (-1.0, 0.0, 0.0), "wall_end", {"module_400"}),
            Socket("end_b", (60.0, 200.0, 175.0), (1.0, 0.0, 0.0), "wall_end", {"module_400"}),
        ],
        tags={"exterior", "stone"},
    )


def test_upsert_and_get_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        with AssetDB(db_path) as db:
            wall = _sample_wall()
            db.upsert_asset(wall)
            loaded = db.get_asset("wall_plain")

        assert loaded is not None
        assert loaded.id == wall.id
        assert loaded.size_cm == wall.size_cm
        assert loaded.footprint_modules == (1, 1)
        assert len(loaded.sockets) == 2
        assert loaded.sockets[0].name == "end_a"
        assert loaded.tags == {"exterior", "stone"}


def test_list_and_filter():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        with AssetDB(db_path) as db:
            db.upsert_asset(_sample_wall())
            db.upsert_asset(
                Asset(
                    id="floor_slab",
                    path="/meshes/floor.fbx",
                    kind="floor",
                    footprint_modules=(2, 2),
                    height_storeys=0.09,
                    size_cm=(800.0, 800.0, 30.0),
                    tags={"interior"},
                )
            )
            walls = db.list_assets(kind="wall")
            tagged = db.list_assets(tags={"exterior"})

        assert [a.id for a in walls] == ["wall_plain"]
        assert [a.id for a in tagged] == ["wall_plain"]


def test_delete_asset():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        with AssetDB(db_path) as db:
            db.upsert_asset(_sample_wall())
            assert db.delete_asset("wall_plain")
            assert db.get_asset("wall_plain") is None


def test_rotates_about_center_persisted():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        arc = Asset(
            id="tower_arc_q1",
            path="/meshes/arc.fbx",
            kind="tower_arc",
            footprint_modules=(1, 1),
            height_storeys=1.0,
            size_cm=(400.0, 400.0, 350.0),
            origin="center",
            rotates_about_center=True,
        )
        with AssetDB(db_path) as db:
            db.upsert_asset(arc)
            loaded = db.get_asset("tower_arc_q1")

        assert loaded is not None
        assert loaded.rotates_about_center is True
        assert loaded.origin == "center"

"""SQLite asset DB (§4) — WP-2."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple


@dataclass
class Socket:
    name: str
    pos_cm: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    type: str
    tags: Set[str] = field(default_factory=set)


@dataclass
class Asset:
    id: str
    path: str
    kind: str
    footprint_modules: Tuple[int, int]
    height_storeys: float
    size_cm: Tuple[float, float, float]
    origin: str = "min_corner"
    rotates_about_center: bool = False
    sockets: List[Socket] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    lod: Optional[dict] = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    footprint_modules_x INTEGER NOT NULL,
    footprint_modules_y INTEGER NOT NULL,
    height_storeys REAL NOT NULL,
    size_x REAL NOT NULL,
    size_y REAL NOT NULL,
    size_z REAL NOT NULL,
    origin TEXT NOT NULL DEFAULT 'min_corner',
    rotates_about_center INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    lod TEXT
);

CREATE TABLE IF NOT EXISTS sockets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    pos_x REAL NOT NULL,
    pos_y REAL NOT NULL,
    pos_z REAL NOT NULL,
    normal_x REAL NOT NULL,
    normal_y REAL NOT NULL,
    normal_z REAL NOT NULL,
    type TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    UNIQUE(asset_id, name),
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
"""


def _json_set(values: Set[str]) -> str:
    return json.dumps(sorted(values))


def _parse_set(raw: str) -> Set[str]:
    return set(json.loads(raw))


class AssetDB:
    """SQLite-backed asset database (§4.1)."""

    def __init__(self, path: str | Path = "assets.db") -> None:
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "AssetDB":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def upsert_asset(self, asset: Asset) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO assets (
                id, path, kind,
                footprint_modules_x, footprint_modules_y,
                height_storeys, size_x, size_y, size_z,
                origin, rotates_about_center, tags, lod
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                path=excluded.path,
                kind=excluded.kind,
                footprint_modules_x=excluded.footprint_modules_x,
                footprint_modules_y=excluded.footprint_modules_y,
                height_storeys=excluded.height_storeys,
                size_x=excluded.size_x,
                size_y=excluded.size_y,
                size_z=excluded.size_z,
                origin=excluded.origin,
                rotates_about_center=excluded.rotates_about_center,
                tags=excluded.tags,
                lod=excluded.lod
            """,
            (
                asset.id,
                asset.path,
                asset.kind,
                asset.footprint_modules[0],
                asset.footprint_modules[1],
                asset.height_storeys,
                asset.size_cm[0],
                asset.size_cm[1],
                asset.size_cm[2],
                asset.origin,
                1 if asset.rotates_about_center else 0,
                _json_set(asset.tags),
                json.dumps(asset.lod) if asset.lod is not None else None,
            ),
        )
        conn.execute("DELETE FROM sockets WHERE asset_id = ?", (asset.id,))
        for sock in asset.sockets:
            conn.execute(
                """
                INSERT INTO sockets (
                    asset_id, name,
                    pos_x, pos_y, pos_z,
                    normal_x, normal_y, normal_z,
                    type, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.id,
                    sock.name,
                    sock.pos_cm[0],
                    sock.pos_cm[1],
                    sock.pos_cm[2],
                    sock.normal[0],
                    sock.normal[1],
                    sock.normal[2],
                    sock.type,
                    _json_set(sock.tags),
                ),
            )
        conn.commit()

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        conn = self.connect()
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            return None
        sockets = self._load_sockets(asset_id)
        return self._row_to_asset(row, sockets)

    def list_assets(
        self,
        kind: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[Asset]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM assets ORDER BY id").fetchall()
        assets = [self._row_to_asset(r, self._load_sockets(r["id"])) for r in rows]
        if kind is not None:
            assets = [a for a in assets if a.kind == kind]
        if tags:
            assets = [a for a in assets if tags <= a.tags]
        return assets

    def delete_asset(self, asset_id: str) -> bool:
        conn = self.connect()
        cur = conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        conn.commit()
        return cur.rowcount > 0

    def iter_assets(self) -> Iterator[Asset]:
        yield from self.list_assets()

    def _load_sockets(self, asset_id: str) -> List[Socket]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM sockets WHERE asset_id = ? ORDER BY name",
            (asset_id,),
        ).fetchall()
        return [self._row_to_socket(r) for r in rows]

    @staticmethod
    def _row_to_socket(row: sqlite3.Row) -> Socket:
        return Socket(
            name=row["name"],
            pos_cm=(row["pos_x"], row["pos_y"], row["pos_z"]),
            normal=(row["normal_x"], row["normal_y"], row["normal_z"]),
            type=row["type"],
            tags=_parse_set(row["tags"]),
        )

    @staticmethod
    def _row_to_asset(row: sqlite3.Row, sockets: List[Socket]) -> Asset:
        lod_raw = row["lod"]
        return Asset(
            id=row["id"],
            path=row["path"],
            kind=row["kind"],
            footprint_modules=(row["footprint_modules_x"], row["footprint_modules_y"]),
            height_storeys=row["height_storeys"],
            size_cm=(row["size_x"], row["size_y"], row["size_z"]),
            origin=row["origin"],
            rotates_about_center=bool(row["rotates_about_center"]),
            sockets=sockets,
            tags=_parse_set(row["tags"]),
            lod=json.loads(lod_raw) if lod_raw else None,
        )

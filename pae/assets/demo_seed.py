"""Seed measured decorative assets for the M5 end-to-end demo."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from pae.assets.db import AssetDB
from pae.assets.obj_measure import measure_obj_aabb
from pae.comfy.pipeline import ComfyIngestResult, ingest_decorative

# Fixture crate dimensions (cm) — must match m5_demo_crate.obj vertices.
M5_DEMO_CRATE_XY_CM = 50.0
M5_DEMO_CRATE_Z_CM = 80.0
M5_DEMO_CRATE_ID = "m5_demo_crate"
M5_DEMO_FIXTURE_REL = Path("pae/tests/fixtures/m5_demo_crate.obj")
DEFAULT_M5_DEMO_DB = Path("Saved/demo/m5_assets.db")


def project_root(start: Optional[Path] = None) -> Path:
    """PAE repo root (parent of ``pae/``)."""
    if start is not None:
        return start
    return Path(__file__).resolve().parents[2]


def m5_demo_fixture_path(root: Optional[Path] = None) -> Path:
    return project_root(root) / M5_DEMO_FIXTURE_REL


def seed_m5_demo_assets(
    db: AssetDB,
    *,
    root: Optional[Path] = None,
    human_confirmed: bool = True,
    extra_tags: Optional[Set[str]] = None,
) -> ComfyIngestResult:
    """Measure the OBJ fixture and upsert one confirmed decorative prop."""
    fixture = m5_demo_fixture_path(root)
    measured = measure_obj_aabb(fixture)
    tags: Set[str] = {"m5_demo", "indoor"}
    if extra_tags:
        tags |= set(extra_tags)
    return ingest_decorative(
        M5_DEMO_CRATE_ID,
        str(fixture),
        "prop",
        measured=measured,
        human_confirmed=human_confirmed,
        db=db,
        tags=tags,
    )


__all__ = [
    "DEFAULT_M5_DEMO_DB",
    "M5_DEMO_CRATE_ID",
    "M5_DEMO_CRATE_XY_CM",
    "M5_DEMO_CRATE_Z_CM",
    "M5_DEMO_FIXTURE_REL",
    "m5_demo_fixture_path",
    "project_root",
    "seed_m5_demo_assets",
]

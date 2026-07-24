"""Property tests over random specs (§10.2) — scaffolding until WP-4/WP-5 land."""

from __future__ import annotations

import random

import pytest

from pae.tests.property.determinism import hash_assembly
from pae.tests.property.spec_factory import random_building_spec


def test_hash_assembly_is_order_independent(sample_placements):
    """Placement list order must not change the digest."""
    a = hash_assembly(sample_placements, asset_db_version="1", seed=7)
    b = hash_assembly(list(reversed(sample_placements)), asset_db_version="1", seed=7)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_hash_assembly_stable_across_calls(sample_placements):
    h1 = hash_assembly(sample_placements, asset_db_version="v0", seed=1)
    h2 = hash_assembly(sample_placements, asset_db_version="v0", seed=1)
    assert h1 == h2


def test_hash_assembly_changes_with_seed(sample_placements):
    h1 = hash_assembly(sample_placements, seed=1)
    h2 = hash_assembly(sample_placements, seed=2)
    assert h1 != h2


def test_hash_assembly_accepts_dict_placements():
    rows = [
        {
            "asset_id": "wall_plain",
            "cell": (0, 0),
            "level": 0,
            "yaw": 0,
            "offset_cm": (0.0, 0.0, 0.0),
        },
        {
            "asset_id": "floor_slab",
            "cell": (1, 0),
            "level": 0,
            "yaw": 0,
            "offset_cm": (0.0, 0.0, 0.0),
        },
    ]
    assert hash_assembly(rows) == hash_assembly(list(reversed(rows)))


def test_random_spec_factory_stays_in_bay_space():
    rng = random.Random(12345)
    for _ in range(20):
        spec = random_building_spec(rng)
        assert spec.footprint.bays_x >= 2
        assert spec.footprint.bays_y >= 2
        assert spec.storeys >= 1
        assert len(spec.storey_use) == spec.storeys
        # No world-coordinate fields on the public dataclass surface
        assert not hasattr(spec, "origin_cm")
        assert not hasattr(spec, "world_xyz")


@pytest.mark.xfail(
    reason="WP-5: M1 passes; non-rect footprints / multi-wing validation still open",
    strict=False,
)
def test_random_specs_validate_ok():
    """For random specs within sane bounds, validator must pass (§10.2).

    Any failing assembly is a solver bug, not a bad spec.
    """
    from pae.assemble import assemble
    from pae.plan import plan as plan_floor
    from pae.solver import solve
    from pae.validate import validate

    rng = random.Random(99)
    for _ in range(5):
        spec = random_building_spec(rng)
        # Pipeline stubs until WP-4/WP-5 — raise NotImplementedError → xfail
        massing, _ = solve(spec)
        floor_plan, _ = plan_floor(massing)
        assembly, _ = assemble(floor_plan, asset_db=None, style=None)
        _, report = validate(assembly)
        assert report.ok, report.critical

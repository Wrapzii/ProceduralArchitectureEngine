"""Property tests over random specs (§10.2) — L/U/rect/courtyard within M1–M3."""

from __future__ import annotations

import random

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


def _pipeline_validate(spec):
    from pae.assemble import assemble
    from pae.plan import plan as plan_floor
    from pae.solver import solve
    from pae.spec import load_style
    from pae.validate import validate

    massing, _ = solve(spec)
    assert massing is not None, "solver returned no massing"
    floor_plan, _ = plan_floor(massing)
    style, _ = load_style(spec.style)
    assembly, _ = assemble(floor_plan, asset_db=None, style=style)
    _, report = validate(assembly)
    return assembly, report


def test_m1_box_house_validate_ok():
    """M1 box house — assemble + validate must pass (no longer xfail)."""
    from pae.spec import m1_box_house_spec

    _, report = _pipeline_validate(m1_box_house_spec())
    assert report.ok, report.critical


def test_m1_assembly_hash_stable_across_two_runs():
    """Same M1 spec → identical placement hash across two full pipeline runs."""
    from pae.spec import m1_box_house_spec

    spec = m1_box_house_spec()
    a1, r1 = _pipeline_validate(spec)
    a2, r2 = _pipeline_validate(spec)
    assert r1.ok and r2.ok
    h1 = hash_assembly(a1.placements, asset_db_version="0", seed=spec.seed)
    h2 = hash_assembly(a2.placements, asset_db_version="0", seed=spec.seed)
    assert h1 == h2
    assert len(h1) == 64


def test_random_specs_validate_ok():
    """For random specs within sane bounds, validator must pass (§10.2).

    Any failing assembly is a solver/assemble bug, not a bad spec.
    Generator draws rect/L/U/courtyard with exterior tower attach cells;
    solver local-repair also nudges interior/overlapping towers outside.
    """
    rng = random.Random(99)
    for _ in range(20):
        spec = random_building_spec(rng)
        _, report = _pipeline_validate(spec)
        assert report.ok, report.critical


def test_random_specs_never_stack_monumental_stair_flights():
    """Regression lock for Handbook §5.6 / D-23 — no same-XY monumental stacks."""
    from pae.validate import _check_stair_flight_stack

    rng = random.Random(4242)
    for _ in range(30):
        spec = random_building_spec(rng)
        assembly, report = _pipeline_validate(spec)
        stack = [
            f
            for f in report.failures + report.critical
            if f.check == "stair_flight_stack"
        ]
        direct = _check_stair_flight_stack(assembly)
        assert not stack and not direct, (
            f"seed={spec.seed} storeys={spec.storeys} "
            f"stair={spec.circulation.stair_kind}: {stack or direct}"
        )

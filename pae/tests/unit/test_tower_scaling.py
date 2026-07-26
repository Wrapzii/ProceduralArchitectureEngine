from pae.contract import STOREY_CM
from pae.assemble import _tower_radius_cm
from pae.pipeline import run_through_assemble
from pae.solver import Volume
from pae.spec import (
    giant_lighthouse_spec,
    habitable_round_tower_spec,
    small_square_spire_spec,
    square_spire_tower_spec,
    tiny_round_spire_spec,
)
from pae.validate import validate


def _validated(factory):
    _massing, _plan, assembly, report = run_through_assemble(factory())
    assert report.ok, [f.message for f in report.critical]
    assembly, report = validate(assembly)
    assert report.ok, [f.message for f in report.critical]
    return assembly


def test_tower_radius_is_continuous_not_integer_only():
    tower = Volume(
        id="scaled",
        x0=0,
        y0=0,
        x1=0,
        y1=0,
        storeys=2,
        role="tower",
        tower_radius_bays=1.375,
    )
    assert _tower_radius_cm(tower) == 550.0


def test_tiny_round_spire_stair_fits_clear_bore():
    assembly = _validated(tiny_round_spire_spec)
    stairs = [
        p
        for p in assembly.placements
        if p.asset_id == "stair_spiral_quarter" and "habitable_drum" in p.tags
    ]
    assert stairs
    # Radius 200 - two 80 cm wall leaves a 240 cm clear diameter. The diagonal
    # stair footprint is clamped further so it cannot clip the curved masonry.
    assert max(p.size_cm[0] for p in stairs) < 280.0
    assert len(stairs) % 4 == 0
    assert {p.yaw for p in stairs} == {0, 90, 180, 270}
    assert any(p.asset_id == "spiral_newel" for p in assembly.placements)


def test_square_spire_has_supported_upper_rooms_and_pyramidal_cap():
    assembly = _validated(square_spire_tower_spec)
    assert any("square_tower" in p.tags for p in assembly.placements)
    caps = [p for p in assembly.placements if p.asset_id == "tower_cap_square"]
    assert len(caps) == 1
    assert caps[0].size_cm[2] == 3.0 * STOREY_CM
    assert any(
        p.level >= 1 and "tower_room_floor" in p.tags
        for p in assembly.placements
    )


def test_small_square_spire_is_a_stair_turret_not_a_room_tower():
    assembly = _validated(small_square_spire_spec)
    assert any("square_tower" in p.tags for p in assembly.placements)
    assert any(p.asset_id == "tower_cap_square" for p in assembly.placements)
    assert not any("tower_room_floor" in p.tags for p in assembly.placements)
    stairs = [p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"]
    assert stairs
    assert max(p.size_cm[0] for p in stairs) <= 480.0
    assert len(stairs) % 4 == 0
    assert {p.yaw for p in stairs} == {0, 90, 180, 270}
    assert not any(p.asset_id == "spiral_newel" for p in assembly.placements)
    entries = [p for p in assembly.placements if "tower_entry" in p.tags]
    for entry in entries:
        landing_treads = [
            p
            for p in stairs
            if p.level == entry.level and p.yaw == entry.yaw
        ]
        assert landing_treads
        assert min(p.offset_cm[2] for p in landing_treads) == 0.0


def test_lighthouse_and_habitable_round_tower_validate_at_large_scale():
    for factory in (habitable_round_tower_spec, giant_lighthouse_spec):
        assembly = _validated(factory)
        assert any("tower_room_floor" in p.tags for p in assembly.placements)
        assert any(p.level >= 2 for p in assembly.placements if p.kind == "stair")
    lighthouse = _validated(giant_lighthouse_spec)
    assert any(p.level >= 5 for p in lighthouse.placements if p.kind == "stair")

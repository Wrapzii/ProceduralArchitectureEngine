"""Phase 0.5 — aperture_reachability and storey_egress GROUND/VOLUME are critical."""

from __future__ import annotations

import random

from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_compound
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, WALL_T_CM, rotation_offset_cm
from pae.pipeline import run_through_assemble
from pae.tests.property.spec_factory import random_building_spec
from pae.validate import validate
from pae.variation import VariationSpec, vary


def _upper_door(level=1) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    return SolidPlacement(
        piece_id=f"door_l{level}",
        asset_id="wall_door",
        kind="wall",
        cell=(2, 0),
        level=level,
        yaw=180,
        offset_cm=rotation_offset_cm(180, sx, sy) + (0.0,),
        size_cm=(sx, sy, sz),
        tags=frozenset({"wall"}),
    )


def test_unreachable_upper_door_is_critical():
    assembly = Assembly(
        placements=[_upper_door()],
        storeys=2,
    )
    _, report = validate(assembly)
    hits = [f for f in report.failures if f.check == "aperture_reachability"]
    assert hits
    assert all(f.critical for f in hits)


def test_no_ground_door_is_critical():
    assembly = Assembly(
        placements=[
            SolidPlacement(
                piece_id="w",
                asset_id="wall_plain",
                kind="wall",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            ),
            SolidPlacement(
                piece_id="floor0",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            ),
        ],
        storeys=1,
    )
    _, report = validate(assembly)
    ground = [
        f
        for f in report.failures
        if f.check == "storey_egress" and "GROUND" in f.message
    ]
    assert ground
    assert all(f.critical for f in ground)


def test_enclosed_storey_without_aperture_is_critical():
    assembly = Assembly(
        placements=[
            SolidPlacement(
                piece_id="w",
                asset_id="wall_plain",
                kind="wall",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            ),
            SolidPlacement(
                piece_id="floor0",
                asset_id="floor",
                kind="floor",
                cell=(0, 0),
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            ),
        ],
        storeys=1,
    )
    _, report = validate(assembly)
    volume = [
        f
        for f in report.failures
        if f.check == "storey_egress" and "VOLUME" in f.message
    ]
    assert volume
    assert all(f.critical for f in volume)


def test_compound_gallery_doors_survive_vary():
    """Balcony decks are floors — variation must not demote gallery doors."""
    asm, _, _ = build_compound()
    before = [
        p
        for p in asm.placements
        if p.kind == "wall" and "balcony_door" in p.tags and p.level > 0
    ]
    assert before, "compound fixture must place upper balcony doors"
    varied, _ = vary(asm, VariationSpec(seed=42))
    after = [
        p
        for p in varied.placements
        if p.kind == "wall"
        and ("door" in p.asset_id or "gate" in p.asset_id)
        and p.level > 0
        and "door_demoted" not in p.tags
    ]
    assert after, "vary demoted every gallery door (balcony landing bug)"
    _, report = validate(varied)
    reach = [f for f in report.failures if f.check == "aperture_reachability"]
    assert not reach, reach


def test_random_specs_have_no_volume_critical(seed_count: int = 40):
    """Property factory + assemble must glaze every storey with floor area."""
    volume_hits = []
    for i in range(seed_count):
        sp = random_building_spec(random.Random(i))
        _m, _p, asm, stage = run_through_assemble(sp)
        if not asm.placements:
            continue
        _, report = validate(asm)
        for f in report.failures:
            if (
                f.critical
                and f.check == "storey_egress"
                and "VOLUME" in f.message
            ):
                volume_hits.append((i, sp.name, sp.storeys, f.message))
    assert not volume_hits, volume_hits[:8]

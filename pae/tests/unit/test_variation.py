"""Seeded variation and aperture legality."""

from __future__ import annotations

import pytest

from pae.pipeline import run_through_assemble
from pae.showcase import builds
from pae.validate import validate
from pae.variation import VariationSpec, vary, vary_spec


def _asm(key="dormitory"):
    b = [x for x in builds() if x.key == key][0]
    _, _, a, r = run_through_assemble(b.spec)
    assert r.ok
    return a


def _doors(a):
    return sorted(
        (p.level, p.cell, p.asset_id)
        for p in a.placements
        if p.kind == "wall" and ("door" in p.asset_id or "gate" in p.asset_id)
    )


def test_unreachable_upper_doors_are_not_stacked_by_assembler():
    """Ground doors must not stamp the same bay on every upper storey."""
    a = _asm()
    upper = [
        (p.level, p.cell, p.asset_id)
        for p in a.placements
        if p.kind == "wall" and ("door" in p.asset_id or "gate" in p.asset_id)
        and p.level > 0
    ]
    assert not upper, f"assembler still stacks doors above ground: {upper}"


def test_variation_removes_every_doorway_to_nothing():
    varied, _ = vary(_asm(), VariationSpec(seed=1))
    _, report = validate(varied)
    assert not [f for f in report.failures if f.check == "aperture_reachability"]


def test_doors_move_off_the_corner():
    a = _asm()
    before = _doors(a)
    varied, _ = vary(a, VariationSpec(seed=1))
    after = _doors(varied)
    assert before != after
    assert all(lvl == 0 for lvl, _c, _p in after), after


def test_same_seed_is_identical_different_seed_differs():
    a = _asm()
    one, _ = vary(a, VariationSpec(seed=7))
    two, _ = vary(a, VariationSpec(seed=7))
    three, _ = vary(a, VariationSpec(seed=8))
    sig = lambda x: [(p.piece_id, p.asset_id) for p in x.placements]
    assert sig(one) == sig(two)
    assert sig(one) != sig(three)


def test_storeys_are_not_identical():
    """Every floor looking the same from outside was the complaint."""
    varied, _ = vary(_asm(), VariationSpec(seed=3))
    by_level = {}
    for p in varied.placements:
        if p.kind == "wall":
            by_level.setdefault(p.level, []).append(p.asset_id)
    sigs = {lvl: tuple(sorted(v)) for lvl, v in by_level.items()}
    assert len(set(sigs.values())) > 1, "all storeys still identical"


def test_variation_never_changes_piece_count():
    a = _asm()
    varied, _ = vary(a, VariationSpec(seed=2))
    assert len(varied.placements) == len(a.placements)


def test_every_elevation_keeps_a_minimum_of_lights():
    varied, _ = vary(_asm(), VariationSpec(seed=5, blank_chance=0.95,
                                           min_lights_per_elevation=1))
    lights = [p for p in varied.placements
              if p.kind == "wall" and "window" in p.asset_id]
    assert lights, "blanked every window despite a minimum"


def test_vary_spec_keeps_pitch_buildable():
    b = [x for x in builds() if x.key == "great_hall"][0]
    for seed in range(6):
        s = vary_spec(b.spec, seed)
        assert 0.8 <= s.roof.pitch <= 2.1


def test_varied_showcase_still_validates():
    for key in ("dormitory", "library_tower", "storefront"):
        varied, _ = vary(_asm(key), VariationSpec(seed=11))
        _, report = validate(varied)
        assert report.ok, [f.message for f in report.critical]


def test_banding_does_not_cross_an_opening():
    from pae.banding import BandingSpec, CourseSpec, band
    from pae.primitives.catalog import catalog_by_id

    varied, _ = vary(_asm(), VariationSpec(seed=4))
    banded, _ = band(varied, BandingSpec(courses=(CourseSpec("sill", 0.30),),
                                         verticals_every_bays=0, braces=False))
    cat = catalog_by_id()
    hosts = {p.piece_id: p for p in banded.placements if p.kind == "wall"}
    for p in banded.placements:
        if p.kind != "band":
            continue
        for hid, host in hosts.items():
            if hid in p.piece_id:
                ap = cat[host.asset_id].aperture
                if ap is None:
                    continue
                z0 = p.offset_cm[2]
                z1 = z0 + p.size_cm[2]
                assert not (z1 > ap.min_cm[2] + 6.0 and z0 < ap.max_cm[2] - 6.0), p.piece_id


# --- composition rules (user-reported: variation looked random, not designed) ---


def _by_storey_window_types(a):
    out = {}
    for p in a.placements:
        if p.kind == "wall" and "window" in p.asset_id:
            out.setdefault(p.level, set()).add(p.asset_id)
    return out


@pytest.mark.parametrize("key", ["storefront", "dormitory", "library_tower"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_one_window_family_per_storey(key, seed):
    """Four window shapes scattered at random across one elevation reads as a bug."""
    varied, _ = vary(_asm(key), VariationSpec(seed=seed))
    for level, types in _by_storey_window_types(varied).items():
        assert len(types) == 1, f"storey {level} mixes {types}"


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_one_door_style_per_building(seed):
    """An arched entrance beside a square-headed one reads as two buildings."""
    varied, _ = vary(_asm("storefront"), VariationSpec(seed=seed))
    styles = {p.asset_id for p in varied.placements
              if p.kind == "wall" and "door" in p.asset_id}
    assert len(styles) <= 1, styles


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_doors_are_never_adjacent(seed):
    """Two entrances side by side was the reported defect."""
    spec = VariationSpec(seed=seed, door_min_separation_bays=3)
    varied, _ = vary(_asm("dormitory"), spec)
    doors = [p for p in varied.placements
             if p.kind == "wall" and "door" in p.asset_id]
    for i, a in enumerate(doors):
        for b in doors[i + 1:]:
            if a.level != b.level or a.yaw != b.yaw:
                continue
            axis = 1 if a.yaw in (0, 180) else 0
            assert abs(a.cell[axis] - b.cell[axis]) >= spec.door_min_separation_bays, (
                a.piece_id, b.piece_id
            )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_windows_are_distributed_not_clustered(seed):
    """Independent per-bay coin flips put every window on one corner."""
    varied, _ = vary(_asm("dormitory"), VariationSpec(seed=seed))
    per_elev = {}
    for p in varied.placements:
        if p.kind != "wall":
            continue
        axis = 1 if p.yaw in (0, 180) else 0
        key = (p.level, axis, p.cell[1 - axis])
        per_elev.setdefault(key, []).append(("window" in p.asset_id, p.cell[axis]))
    # Judge only elevations long enough for clustering to be meaningful. A 3-bay wall
    # under a "two glazed, one blank" rhythm legitimately spans 2 — that is rhythm, not
    # clustering. The defect was every window on ONE END of a long run.
    long_runs = [v for v in per_elev.values() if len(v) >= 6 and any(g for g, _ in v)]
    assert long_runs, "no elevation long enough to judge"
    for run in long_runs:
        bays = sorted(b for g, b in run if g)
        all_bays = sorted(b for _g, b in run)
        span = max(bays) - min(bays) + 1
        full = max(all_bays) - min(all_bays) + 1
        assert span >= full * 0.5, (
            f"windows occupy only {span} of {full} bays — clustered at one end"
        )

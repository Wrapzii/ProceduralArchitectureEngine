"""Unit tests — Phase 1.3 grand entrance ensemble + existence."""

from __future__ import annotations

from pae.assemble import assemble
from pae.entrance_ensemble import (
    ENSEMBLE_ARCH_TAG,
    ENSEMBLE_COLUMN_TAG,
    ENSEMBLE_STAIR_TAG,
    ENSEMBLE_STEPS_TAG,
    ENSEMBLE_TAG,
    check_entrance_ensemble_existence,
    expand_entrance_ensembles,
    placed_ensemble_parts,
)
from pae.existence import check_no_bare_aperture_holes, entrance_role_tag
from pae.plan import plan
from pae.solver import solve
from pae.spec import (
    BuildingSpec,
    CirculationSpec,
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    load_spec,
    m8_entrances_spec,
    m9_grand_ensemble_spec,
)


def _assemble_spec(spec: BuildingSpec):
    massing, mreport = solve(spec)
    assert mreport.ok, [f.message for f in mreport.failures]
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures]
    from pae.spec import load_style

    style, _ = load_style(spec.style)
    assembly, areport = assemble(floor_plan, None, style)
    return assembly, areport, floor_plan, massing


def test_m9_factory_sets_ensemble_flag():
    spec = m9_grand_ensemble_spec()
    assert spec.name == "m9_grand_ensemble"
    assert spec.entrances[0].role == "grand"
    assert spec.entrances[0].ensemble is True
    assert spec.entrances[1].role == "service"
    assert spec.entrances[1].ensemble is False


def test_loader_parses_ensemble_flag():
    data = {
        "name": "parsed_ensemble",
        "style": "keep",
        "footprint": {"kind": "rect", "bays_x": 6, "bays_y": 5},
        "storeys": 2,
        "storey_use": ["hall", "hall"],
        "entrances": [
            {"role": "grand", "facade": "south", "ensemble": True},
            {"role": "service", "facade": "north"},
        ],
    }
    spec, report = load_spec(data)
    assert report.ok
    assert spec is not None
    assert spec.entrances[0].ensemble is True
    assert spec.entrances[1].ensemble is False


def test_m9_places_ensemble_arch_steps_columns():
    assembly, areport, _, _ = _assemble_spec(m9_grand_ensemble_spec())
    assert areport.ok, [f.message for f in areport.failures]

    parts = placed_ensemble_parts(assembly, "grand")
    assert parts[ENSEMBLE_ARCH_TAG] >= 1
    assert parts[ENSEMBLE_STEPS_TAG] >= 1
    assert parts[ENSEMBLE_COLUMN_TAG] >= 2

    arch = [
        p
        for p in assembly.placements
        if ENSEMBLE_ARCH_TAG in p.tags and entrance_role_tag("grand") in p.tags
    ]
    assert arch
    assert "gate" in arch[0].asset_id or "door" in arch[0].asset_id

    steps = [p for p in assembly.placements if ENSEMBLE_STEPS_TAG in p.tags]
    assert steps and steps[0].asset_id == "steps_external"

    cols = [p for p in assembly.placements if ENSEMBLE_COLUMN_TAG in p.tags]
    assert len(cols) >= 2
    assert all(p.asset_id == "pilaster" for p in cols)


def test_m9_twin_stairs_when_feasible():
    """Two-storey hall with free interior flanks → twin stair_half stubs."""
    assembly, areport, _, _ = _assemble_spec(m9_grand_ensemble_spec())
    assert areport.ok, [f.message for f in areport.failures]
    parts = placed_ensemble_parts(assembly, "grand")
    # Feasible on the default 8×6 two-storey footprint.
    assert parts[ENSEMBLE_STAIR_TAG] >= 2
    stairs = [p for p in assembly.placements if ENSEMBLE_STAIR_TAG in p.tags]
    assert all(p.asset_id == "stair_half" for p in stairs)


def test_ensemble_existence_passes_m9():
    assembly, areport, _, massing = _assemble_spec(m9_grand_ensemble_spec())
    assert areport.ok
    failures = check_entrance_ensemble_existence(massing.entrances, assembly)
    assert failures == []


def test_ensemble_existence_fails_when_steps_stripped():
    assembly, areport, _, massing = _assemble_spec(m9_grand_ensemble_spec())
    assert areport.ok
    stripped = [
        p for p in assembly.placements if ENSEMBLE_STEPS_TAG not in p.tags
    ]
    from pae.assembly_types import Assembly

    broken = Assembly(
        placements=stripped,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=list(assembly.apertures),
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    failures = check_entrance_ensemble_existence(massing.entrances, broken)
    assert failures
    assert failures[0].check == "entrance_ensemble_existence"
    assert "steps" in failures[0].message


def test_ensemble_does_not_weaken_no_bare_aperture():
    """Ensemble pieces must not stamp entrance_role_* on non-door assets."""
    assembly, areport, _, _ = _assemble_spec(m9_grand_ensemble_spec())
    assert areport.ok
    bare = check_no_bare_aperture_holes(assembly)
    assert bare == [], [f.message for f in bare]

    for p in assembly.placements:
        if ENSEMBLE_TAG in p.tags and ENSEMBLE_ARCH_TAG not in p.tags:
            assert not any(t.startswith("entrance_role_") for t in p.tags), (
                f"non-arch ensemble piece {p.piece_id} carries entrance_role_* "
                f"(would trip no_bare_aperture): {sorted(p.tags)}"
            )


def test_m8_without_ensemble_flag_emits_no_ensemble_pieces():
    assembly, areport, _, _ = _assemble_spec(m8_entrances_spec())
    assert areport.ok
    assert placed_ensemble_parts(assembly) == {
        ENSEMBLE_ARCH_TAG: 0,
        ENSEMBLE_STEPS_TAG: 0,
        ENSEMBLE_COLUMN_TAG: 0,
        ENSEMBLE_STAIR_TAG: 0,
    }


def test_expand_skips_when_no_ensemble_requested():
    assembly, areport, _, massing = _assemble_spec(m8_entrances_spec())
    assert areport.ok
    out, failures = expand_entrance_ensembles(assembly, massing.entrances, storeys=2)
    assert failures == []
    assert len(out.placements) == len(assembly.placements)


def test_single_storey_ensemble_uses_columns_not_stairs():
    spec = BuildingSpec(
        name="ensemble_1storey",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=6, bays_y=5),
        storeys=1,
        storey_use=["hall"],
        roof=RoofSpec(kind="pitched", pitch=0.9),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(
            windows_per_bay=1,
            doors_ground=0,
            skip_ground_windows=True,
        ),
        entrances=[EntranceSpec(role="grand", facade="south", ensemble=True)],
        seed=91,
        ground_slab=True,
    )
    assembly, areport, _, _ = _assemble_spec(spec)
    assert areport.ok, [f.message for f in areport.failures]
    parts = placed_ensemble_parts(assembly, "grand")
    assert parts[ENSEMBLE_STEPS_TAG] >= 1
    assert parts[ENSEMBLE_COLUMN_TAG] >= 2
    assert parts[ENSEMBLE_STAIR_TAG] == 0
    assert check_entrance_ensemble_existence(spec.entrances, assembly) == []

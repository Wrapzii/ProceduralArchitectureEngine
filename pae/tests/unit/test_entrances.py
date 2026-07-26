"""Unit tests — entrance roles, asset mapping, and existence (§1.1–1.2)."""

from __future__ import annotations

from pae.assemble import _door_asset_for_role, assemble
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.existence import (
    check_entrance_existence,
    check_no_bare_aperture_holes,
    entrance_role_tag,
    is_door_or_gate_asset,
    placed_entrance_roles,
)
from pae.plan import plan
from pae.solver import solve
from pae.spec import (
    BuildingSpec,
    EntranceSpec,
    FootprintSpec,
    OpeningPolicy,
    RoofSpec,
    CirculationSpec,
    load_spec,
    m8_entrances_spec,
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


def test_door_asset_for_role_mapping():
    assert _door_asset_for_role("grand", None) == "wall_gate_arch"
    assert _door_asset_for_role("gate", None) == "wall_gate_arch_grand"
    assert _door_asset_for_role("main", None) == "wall_door"
    assert _door_asset_for_role("side", None) == "wall_door"
    assert _door_asset_for_role("service", None) == "wall_door_plain"
    assert _door_asset_for_role("postern", None) == "wall_door_plain"

    gothic_style = {"window": {"tag": "window_gothic"}}
    assert _door_asset_for_role("grand", gothic_style) == "wall_door_gothic"
    assert _door_asset_for_role("main", gothic_style) == "wall_door_gothic"


def test_m8_entrances_spec_factory():
    spec = m8_entrances_spec()
    assert spec.name == "m8_entrances"
    assert len(spec.entrances) == 2
    assert spec.entrances[0].role == "grand"
    assert spec.entrances[0].facade == "south"
    assert spec.entrances[1].role == "service"
    assert spec.entrances[1].facade == "north"


def test_m8_entrances_places_role_tagged_doors():
    assembly, areport, floor_plan, _ = _assemble_spec(m8_entrances_spec())
    assert areport.ok, [f.message for f in areport.failures]
    roles = placed_entrance_roles(assembly)
    assert "grand" in roles
    assert "service" in roles

    door_assets = {
        p.asset_id
        for p in assembly.placements
        if entrance_role_tag("grand") in p.tags
    }
    service_assets = {
        p.asset_id
        for p in assembly.placements
        if entrance_role_tag("service") in p.tags
    }
    assert door_assets == {"wall_gate_arch"}
    assert service_assets == {"wall_door_plain"}

    assert len(floor_plan.door_cells) == 2
    assert floor_plan.entrance_by_cell[floor_plan.door_cells[0]] == "grand"
    assert floor_plan.entrance_by_cell[floor_plan.door_cells[1]] == "service"


def test_entrance_existence_fails_when_role_missing():
    spec = BuildingSpec(
        name="missing_grand",
        style="keep",
        footprint=FootprintSpec(kind="rect", bays_x=4, bays_y=3),
        storeys=1,
        storey_use=["hall"],
        entrances=[EntranceSpec(role="grand", facade="south")],
        openings=OpeningPolicy(doors_ground=0, skip_ground_windows=True),
    )
    assembly, _, floor_plan, _ = _assemble_spec(spec)
    assert any(
        entrance_role_tag("grand") in p.tags for p in assembly.placements
    )

    stripped = [
        p
        for p in assembly.placements
        if entrance_role_tag("grand") not in p.tags
    ]
    from pae.assembly_types import Assembly

    failures = check_entrance_existence(spec.entrances, Assembly(placements=stripped))
    assert failures
    assert failures[0].check == "entrance_existence"
    assert "grand" in failures[0].message
    assert len(floor_plan.door_cells) == 1


def test_loader_parses_entrances():
    data = {
        "name": "parsed",
        "style": "keep",
        "footprint": {"kind": "rect", "bays_x": 4, "bays_y": 3},
        "storeys": 1,
        "storey_use": ["hall"],
        "entrances": [
            {"role": "main", "facade": "south", "bay": 1},
            {"role": "service", "facade": "north"},
        ],
    }
    spec, report = load_spec(data)
    assert report.ok
    assert spec is not None
    assert len(spec.entrances) == 2
    assert spec.entrances[0].role == "main"
    assert spec.entrances[0].bay == 1


def test_legacy_openings_when_entrances_empty():
    from pae.spec import m1_box_house_spec

    spec = m1_box_house_spec()
    assert not spec.entrances
    assembly, areport, floor_plan, _ = _assemble_spec(spec)
    assert areport.ok
    assert len(floor_plan.door_cells) == 1
    assert not floor_plan.entrance_by_cell
    assert not placed_entrance_roles(assembly)


def test_is_door_or_gate_asset():
    assert is_door_or_gate_asset("wall_door")
    assert is_door_or_gate_asset("wall_door_plain")
    assert is_door_or_gate_asset("wall_gate_arch")
    assert is_door_or_gate_asset("wall_door_gothic")
    assert not is_door_or_gate_asset("wall_plain")
    assert not is_door_or_gate_asset("wall_window")
    assert not is_door_or_gate_asset("wall_arcade")


def test_no_bare_aperture_passes_m8_and_m1():
    """Healthy assemblies never leave a passage breach without a leaf."""
    from pae.spec import m1_box_house_spec
    from pae.validate import validate

    for factory in (m8_entrances_spec, m1_box_house_spec):
        assembly, areport, _, _ = _assemble_spec(factory())
        assert areport.ok, [f.message for f in areport.failures]
        bare = check_no_bare_aperture_holes(assembly)
        assert bare == []
        _, vreport = validate(assembly)
        assert not any(f.check == "no_bare_aperture" for f in vreport.failures)


def test_no_bare_aperture_fails_when_door_host_is_plain_wall():
    """Deliberately broken: door aperture hosted by wall_plain (bare hole)."""
    from pae.assembly_types import Assembly, Aperture, SolidPlacement
    from pae.validate import validate

    assembly, _, _, _ = _assemble_spec(m8_entrances_spec())
    door_aps = [a for a in assembly.apertures if a.kind == "door"]
    assert door_aps
    victim_id = door_aps[0].wall_piece_id

    mutated: list = []
    for p in assembly.placements:
        if p.piece_id == victim_id:
            mutated.append(
                SolidPlacement(
                    piece_id=p.piece_id,
                    asset_id="wall_plain",
                    kind=p.kind,
                    cell=p.cell,
                    level=p.level,
                    yaw=p.yaw,
                    offset_cm=p.offset_cm,
                    size_cm=p.size_cm,
                    rotates_about_center=p.rotates_about_center,
                    tags=frozenset({"wall", "plain"}),
                )
            )
        else:
            mutated.append(p)

    broken = Assembly(
        placements=mutated,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=list(assembly.apertures),
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
    )
    failures = check_no_bare_aperture_holes(broken)
    assert failures
    assert failures[0].check == "no_bare_aperture"
    assert "bare hole" in failures[0].message
    assert failures[0].critical is True

    _, vreport = validate(broken)
    assert any(f.check == "no_bare_aperture" and f.critical for f in vreport.critical)


def test_no_bare_aperture_fails_on_balcony_door_without_leaf():
    from pae.assembly_types import Assembly, SolidPlacement

    bare = SolidPlacement(
        piece_id="wall_fake_balcony_door",
        asset_id="wall_plain",
        kind="wall",
        cell=(0, 0),
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"wall", "balcony", "balcony_door"}),
    )
    failures = check_no_bare_aperture_holes(Assembly(placements=[bare]))
    assert len(failures) == 1
    assert failures[0].check == "no_bare_aperture"
    assert "balcony_door" in failures[0].message

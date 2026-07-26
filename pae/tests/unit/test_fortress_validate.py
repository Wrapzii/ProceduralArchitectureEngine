"""Fortress / castle compound validation — broken fixtures first (Handbook §6).

Each check must fire on a hand-built poison before we assert green paths.
Does not demote ``aperture_reachability`` or stair integrity checks.
"""

from __future__ import annotations

from dataclasses import replace

from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_castle_curtain_compound, build_fortress_compound
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    rotation_offset_cm,
)
from pae.existence import entrance_role_tag
from pae.fortress_validate import (
    DEFAULT_MIN_CAPPED_TOWERS,
    FORTRESS_COMPOUND_TAG,
    FORTRESS_MIN_TOWERS_TAG_PREFIX,
    GRAND_APPROACH_TAG,
    assembly_is_fortress,
    assembly_requires_grand_approach,
    check_buttress_outward,
    check_curtain_battlement_continuity,
    check_fortress_gate_exists,
    check_fortress_grand_approach,
    check_fortress_tower_capped,
    check_spire_freestanding,
)
from pae.pipeline import run_through_assemble
from pae.spec import fortress_bailey_compound_spec, m1_box_house_spec, m3_keep_tower_spec
from pae.trim import covered_cells
from pae.validate import validate


def _wall(
    pid: str,
    cell: tuple[int, int],
    yaw: int = 0,
    *,
    tags: frozenset[str] | None = None,
    level: int = 0,
) -> SolidPlacement:
    sx, sy, sz = WALL_T_CM, MODULE_CM, STOREY_CM
    rx, ry = rotation_offset_cm(yaw, sx, sy)
    return SolidPlacement(
        piece_id=pid,
        asset_id="wall_plain",
        kind="wall",
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=(rx, ry, 0.0),
        size_cm=(sx, sy, sz),
        tags=tags or frozenset({"wall"}),
    )


def _floor(pid: str, cell: tuple[int, int]) -> SolidPlacement:
    return SolidPlacement(
        piece_id=pid,
        asset_id="floor_wood",
        kind="floor",
        cell=cell,
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
        tags=frozenset({"floor"}),
    )


def _tower_cap(pid: str, cell: tuple[int, int]) -> SolidPlacement:
    return SolidPlacement(
        piece_id=pid,
        asset_id="tower_cap",
        kind="tower_cap",
        cell=cell,
        level=1,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM * 0.5),
        rotates_about_center=True,
        tags=frozenset({"tower", "cap"}),
    )


def _spire(pid: str, cell: tuple[int, int], *, attached: bool = True) -> SolidPlacement:
    # Attached: sit on tower cell. Detached: far offset so AABB misses envelope.
    ox = 0.0 if attached else MODULE_CM * 40.0
    return SolidPlacement(
        piece_id=pid,
        asset_id="spire_conical",
        kind="roofline",
        cell=cell,
        level=2,
        yaw=0,
        offset_cm=(ox, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM * 2.0),
        rotates_about_center=True,
        tags=frozenset({"spire", "conical", "fortress", "tower"}),
    )


def _buttress(
    pid: str,
    cell: tuple[int, int],
    *,
    offset_cm: tuple[float, float, float],
    yaw: int = 0,
) -> SolidPlacement:
    return SolidPlacement(
        piece_id=pid,
        asset_id="buttress",
        kind="column",
        cell=cell,
        level=0,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=(WALL_T_CM * 2.0, MODULE_CM * 0.4, STOREY_CM),
        tags=frozenset({"buttress", "column", "structural"}),
    )


def _battlement(pid: str, cell: tuple[int, int], level: int = 1) -> SolidPlacement:
    return SolidPlacement(
        piece_id=pid,
        asset_id="battlement",
        kind="battlement",
        cell=cell,
        level=level,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM * 0.25),
        tags=frozenset({"battlement", "curtain", "trim"}),
    )


def _tag_fortress(assembly: Assembly) -> Assembly:
    """Stamp compound marker on first wall (spire ``fortress`` style tag is ignored)."""
    placements = []
    stamped = False
    for p in assembly.placements:
        if not stamped and p.kind == "wall":
            placements.append(
                replace(p, tags=p.tags | frozenset({FORTRESS_COMPOUND_TAG}))
            )
            stamped = True
        else:
            placements.append(p)
    if not stamped and assembly.placements:
        p0 = assembly.placements[0]
        placements = [
            replace(p0, tags=p0.tags | frozenset({FORTRESS_COMPOUND_TAG}))
        ] + list(assembly.placements[1:])
    return Assembly(
        placements=placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        building_class=assembly.building_class,
        stair_kind=assembly.stair_kind,
        wide_stair_well_available=assembly.wide_stair_well_available,
    )


# --- Broken fixtures first -------------------------------------------------


def test_broken_too_few_capped_towers_fires():
    """Fortress with one tower_cap fails fortress_tower_capped."""
    wall = _wall("w0", (0, 0), tags=frozenset({"wall", FORTRESS_COMPOUND_TAG}))
    cap = _tower_cap("cap0", (0, 0))
    asm = Assembly(placements=[wall, cap], storeys=2)
    assert assembly_is_fortress(asm)
    fails = check_fortress_tower_capped(asm)
    assert fails, "single capped tower must fail when min is 2"
    assert fails[0].check == "fortress_tower_capped"
    assert fails[0].critical
    assert fails[0].world_xyz is not None
    assert str(DEFAULT_MIN_CAPPED_TOWERS) in fails[0].message


def test_broken_missing_gate_fires():
    """Fortress with towers but no gate fails fortress_gate_exists."""
    wall = _wall("w0", (0, 0), tags=frozenset({"wall", FORTRESS_COMPOUND_TAG}))
    caps = [_tower_cap(f"cap{i}", (i, 0)) for i in range(2)]
    asm = Assembly(placements=[wall, *caps], storeys=2)
    fails = check_fortress_gate_exists(asm)
    assert fails, "missing gate must fail fortress_gate_exists"
    assert fails[0].check == "fortress_gate_exists"
    assert fails[0].critical
    assert "gate" in fails[0].message.lower()


def test_broken_curtain_without_battlements_fires_continuity_stub():
    """Curtain walls with zero battlements warn on continuity stub."""
    walls = [
        _wall(
            f"cw{i}",
            (i, 0),
            90,
            tags=frozenset({"wall", "curtain", "west_curtain"}),
            level=1,
        )
        for i in range(4)
    ]
    asm = Assembly(placements=walls, storeys=2)
    fails = check_curtain_battlement_continuity(asm)
    assert fails, "bare curtain must warn curtain_battlement_continuity"
    assert all(f.check == "curtain_battlement_continuity" for f in fails)
    assert all(not f.critical for f in fails)
    assert any(f.world_xyz is not None for f in fails)


def test_broken_inward_buttress_fires():
    """Buttress planted on an interior floor cell fails buttress_outward."""
    wall = _wall("w0", (0, 0), yaw=0)
    floor = _floor("f0", (0, 0))
    # Offset into the cell interior (not outward of the wall face).
    butt = _buttress(
        "bad_butt",
        (0, 0),
        offset_cm=(MODULE_CM * 0.4, MODULE_CM * 0.4, 0.0),
        yaw=0,
    )
    asm = Assembly(placements=[wall, floor, butt], storeys=1)
    fails = check_buttress_outward(asm)
    assert fails, "inward buttress must fail buttress_outward"
    assert fails[0].check == "buttress_outward"
    assert fails[0].critical
    assert fails[0].world_xyz is not None
    assert "interior" in fails[0].message or "inward" in fails[0].message


def test_broken_detached_spire_fires():
    """Spire shifted 40 modules away fails spire_freestanding."""
    wall = _wall("w0", (0, 0))
    cap = _tower_cap("cap0", (0, 0))
    spire = _spire("island_spire", (0, 0), attached=False)
    asm = Assembly(placements=[wall, cap, spire], storeys=2)
    fails = check_spire_freestanding(asm)
    assert fails, "detached spire must fail spire_freestanding"
    assert fails[0].check == "spire_freestanding"
    assert fails[0].critical
    assert fails[0].piece_id == "island_spire"
    assert fails[0].world_xyz is not None


def test_broken_grand_approach_without_steps_fires():
    """grand_approach tag without exterior steps fails fortress_grand_approach."""
    wall = _wall(
        "w0",
        (0, 0),
        tags=frozenset({"wall", FORTRESS_COMPOUND_TAG, GRAND_APPROACH_TAG}),
    )
    gate = replace(
        _wall("gate0", (1, 0), tags=frozenset({"wall", "gate"})),
        asset_id="wall_gate_arch",
        tags=frozenset({"wall", "gate", entrance_role_tag("gate")}),
    )
    caps = [_tower_cap(f"cap{i}", (i, 0)) for i in range(2)]
    asm = Assembly(placements=[wall, gate, *caps], storeys=2)
    fails = check_fortress_grand_approach(asm)
    assert fails, "tagged grand approach without steps must fail"
    assert fails[0].check == "fortress_grand_approach"
    assert fails[0].critical
    assert "steps" in fails[0].message.lower()


# --- Positive / green paths -------------------------------------------------


def test_min_towers_tag_override():
    """fortress_min_towers:1 allows a single capped tower."""
    wall = _wall(
        "w0",
        (0, 0),
        tags=frozenset(
            {
                "wall",
                FORTRESS_COMPOUND_TAG,
                f"{FORTRESS_MIN_TOWERS_TAG_PREFIX}1",
            }
        ),
    )
    cap = _tower_cap("cap0", (0, 0))
    gate = SolidPlacement(
        piece_id="g0",
        asset_id="wall_gate_arch",
        kind="wall",
        cell=(1, 0),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
        tags=frozenset({"wall", "gate", entrance_role_tag("gate")}),
    )
    asm = Assembly(placements=[wall, cap, gate], storeys=2)
    assert check_fortress_tower_capped(asm) == []


def test_house_is_not_fortress():
    """Ordinary M1 house must not trigger fortress existence checks."""
    _, _, assembly, _ = run_through_assemble(m1_box_house_spec())
    assert not assembly_is_fortress(assembly)
    _, report = validate(assembly)
    fortress_checks = {
        "fortress_tower_capped",
        "fortress_gate_exists",
        "fortress_grand_approach",
    }
    hits = [f for f in report.failures if f.check in fortress_checks]
    assert hits == [], [f.message for f in hits]


def test_castle_curtain_compound_passes_fortress_criticals():
    """Interim fortress (curtain compound) satisfies tower + gate criticals."""
    assembly, _, creport = build_castle_curtain_compound()
    assert creport.ok, [f.message for f in creport.failures]
    assert assembly_is_fortress(assembly)
    assert check_fortress_tower_capped(assembly) == []
    assert check_fortress_gate_exists(assembly) == []
    _, report = validate(assembly)
    crit = [
        f
        for f in report.critical
        if f.check
        in (
            "fortress_tower_capped",
            "fortress_gate_exists",
            "spire_freestanding",
            "buttress_outward",
            "fortress_grand_approach",
        )
    ]
    assert crit == [], [f.message for f in crit]


def test_attached_spire_on_m3_cap_passes():
    """Spire on the same drum cell as tower_cap is not freestanding."""
    _, _, base, _ = run_through_assemble(m3_keep_tower_spec())
    caps = [p for p in base.placements if p.kind == "tower_cap"]
    assert caps
    cell = caps[0].cell
    spire = _spire("ok_spire", cell, attached=True)
    # Match cap XY offset so AABB kisses the cone seat.
    spire = replace(
        spire,
        offset_cm=(caps[0].offset_cm[0], caps[0].offset_cm[1], STOREY_CM),
        level=caps[0].level,
    )
    asm = Assembly(
        placements=list(base.placements) + [spire],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
        aperture_policy=base.aperture_policy,
        building_class=base.building_class,
    )
    fails = check_spire_freestanding(asm)
    assert fails == [], [f.message for f in fails]


def test_grand_approach_with_steps_grand_passes():
    wall = _wall(
        "w0",
        (0, 0),
        tags=frozenset({"wall", FORTRESS_COMPOUND_TAG, GRAND_APPROACH_TAG}),
    )
    steps = SolidPlacement(
        piece_id="steps0",
        asset_id="steps_grand",
        kind="surface",
        cell=(0, -1),
        level=0,
        yaw=0,
        offset_cm=(0.0, 0.0, 0.0),
        size_cm=(MODULE_CM, MODULE_CM, STOREY_CM * 0.3),
        tags=frozenset({"steps", "grand", "fortress", "path"}),
    )
    asm = Assembly(placements=[wall, steps], storeys=1)
    assert check_fortress_grand_approach(asm) == []


def test_curtain_with_battlements_passes_coverage():
    walls = [
        _wall(
            f"cw{i}",
            (i, 0),
            90,
            tags=frozenset({"wall", "curtain", "west_curtain"}),
            level=1,
        )
        for i in range(4)
    ]
    batts = [_battlement(f"b{i}", (i, 0), level=1) for i in range(4)]
    asm = Assembly(placements=walls + batts, storeys=2)
    fails = check_curtain_battlement_continuity(asm)
    assert fails == [], [f.message for f in fails]


def test_poisoned_curtain_compound_missing_caps_fails_via_validate():
    """Strip tower_caps from curtain compound — fortress_tower_capped critical."""
    assembly, _, _ = build_castle_curtain_compound()
    broken = Assembly(
        placements=[p for p in assembly.placements if p.kind != "tower_cap"],
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        building_class=getattr(assembly, "building_class", "castle"),
    )
    # Also strip spires so finishes cannot rescue the count.
    broken = Assembly(
        placements=[
            p
            for p in broken.placements
            if not (p.asset_id or "").startswith("spire_")
        ],
        floor_plan=broken.floor_plan,
        circulation=broken.circulation,
        wall_runs=broken.wall_runs,
        apertures=broken.apertures,
        storeys=broken.storeys,
        aperture_policy=broken.aperture_policy,
        building_class=broken.building_class,
    )
    assert assembly_is_fortress(broken)
    fails = check_fortress_tower_capped(broken)
    assert fails
    _, report = validate(broken)
    hits = [f for f in report.critical if f.check == "fortress_tower_capped"]
    assert hits, "validate pipeline must register fortress_tower_capped"


def test_spire_style_tag_alone_does_not_mark_fortress():
    """spire_conical carries tag fortress — must not promote M3 to fortress compound."""
    _, _, base, _ = run_through_assemble(m3_keep_tower_spec())
    caps = [p for p in base.placements if p.kind == "tower_cap"]
    spire = _spire("style_spire", caps[0].cell if caps else (0, 0), attached=True)
    asm = Assembly(
        placements=list(base.placements) + [spire],
        floor_plan=base.floor_plan,
        circulation=base.circulation,
        wall_runs=base.wall_runs,
        apertures=base.apertures,
        storeys=base.storeys,
        aperture_policy=base.aperture_policy,
    )
    assert not assembly_is_fortress(asm)


# --- Real fortress compound (build_fortress_compound) -----------------------


def _copy_asm(assembly: Assembly, placements: list[SolidPlacement]) -> Assembly:
    return Assembly(
        placements=placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        building_class=getattr(assembly, "building_class", "castle"),
        stair_kind=getattr(assembly, "stair_kind", "switchback"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def test_real_fortress_has_validate_tags():
    """Massing stamps fortress_compound + grand_approach for existence checks."""
    assembly, layout, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    assert "north_keep" in layout.ranges
    tags = set()
    for p in assembly.placements:
        tags |= set(p.tags)
    assert FORTRESS_COMPOUND_TAG in tags, (
        "build_fortress_compound must stamp fortress_compound "
        "(minimal tag wiring for fortress_validate)"
    )
    assert GRAND_APPROACH_TAG in tags, (
        "approach causeway must carry grand_approach "
        f"(bailey.approach_rows={fortress_bailey_compound_spec().approach_rows})"
    )
    assert assembly_is_fortress(assembly)
    assert assembly_requires_grand_approach(assembly)


def test_real_fortress_passes_fortress_criticals():
    """Live fortress output clears tower/gate/spire/approach/buttress criticals."""
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]

    assert check_fortress_tower_capped(assembly) == []
    assert check_fortress_gate_exists(assembly) == []
    assert check_spire_freestanding(assembly) == []
    assert check_fortress_grand_approach(assembly) == []
    assert check_buttress_outward(assembly) == []

    _, vreport = validate(assembly)
    fortress_crit = [
        f
        for f in vreport.critical
        if f.check
        in (
            "fortress_tower_capped",
            "fortress_gate_exists",
            "fortress_grand_approach",
            "spire_freestanding",
            "buttress_outward",
        )
    ]
    assert fortress_crit == [], [f"{f.check}: {f.message}" for f in fortress_crit]


def test_real_fortress_poison_strips_gate_fires():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    stripped = [
        p
        for p in assembly.placements
        if "gate" not in (p.asset_id or "").lower()
        and entrance_role_tag("gate") not in p.tags
    ]
    broken = _copy_asm(assembly, stripped)
    fails = check_fortress_gate_exists(broken)
    assert fails, "stripping gate leaves must fire fortress_gate_exists"
    assert fails[0].critical
    _, vreport = validate(broken)
    assert any(f.check == "fortress_gate_exists" for f in vreport.critical)


def test_real_fortress_poison_strips_caps_and_spires_fires():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    stripped = [
        p
        for p in assembly.placements
        if p.kind != "tower_cap"
        and not (p.asset_id or "").startswith("spire_")
    ]
    broken = _copy_asm(assembly, stripped)
    fails = check_fortress_tower_capped(broken)
    assert fails, "no caps/spires must fire fortress_tower_capped"
    assert fails[0].critical
    assert "need" in fails[0].message


def test_real_fortress_poison_detached_spire_fires():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    spires = [
        p
        for p in assembly.placements
        if (p.asset_id or "").startswith("spire_")
    ]
    assert spires, "fortress massing must place spires for this poison"
    target = spires[0]
    ox, oy, oz = target.offset_cm
    poisoned = []
    for p in assembly.placements:
        if p.piece_id == target.piece_id:
            poisoned.append(
                replace(p, offset_cm=(ox + MODULE_CM * 40.0, oy, oz))
            )
        else:
            poisoned.append(p)
    broken = _copy_asm(assembly, poisoned)
    fails = check_spire_freestanding(broken)
    assert fails, "shifted spire must fire spire_freestanding"
    assert any(f.piece_id == target.piece_id for f in fails)
    assert all(f.critical for f in fails)


def test_real_fortress_poison_inward_buttress_fires():
    """Inject an interior pier on live fortress — buttress_outward must fire."""
    assembly, _, report = build_fortress_compound()
    assert report.ok
    wall = next(
        p
        for p in assembly.placements
        if p.kind == "wall" and p.level == 0 and "north_keep" in p.tags
    )
    # Prefer a floor whose covered_cells include the wall anchor (Rule 5.1).
    floor = next(
        (
            p
            for p in assembly.placements
            if p.kind == "floor"
            and p.level == 0
            and wall.cell in covered_cells(p)
        ),
        None,
    )
    assert floor is not None or any(
        p.kind == "floor" for p in assembly.placements
    ), "fortress keep needs a floor deck for interior-cell poison"
    butt = _buttress(
        "poison_inward_butt",
        wall.cell,
        offset_cm=(MODULE_CM * 0.4, MODULE_CM * 0.4, 0.0),
        yaw=0,
    )
    broken = _copy_asm(assembly, list(assembly.placements) + [butt])
    fails = check_buttress_outward(broken)
    assert fails, "inward buttress on real fortress must fire buttress_outward"
    assert any(f.piece_id == "poison_inward_butt" for f in fails)
    assert all(f.critical for f in fails)


def test_real_fortress_live_buttresses_pass_outward():
    """Live fortress buttresses must bear outward (massing enabled 64 piers)."""
    assembly, _, report = build_fortress_compound()
    assert report.ok
    butts = [
        p
        for p in assembly.placements
        if p.asset_id == "buttress" or "buttress" in p.tags
    ]
    assert len(butts) >= 1, "fortress massing must place live buttresses"
    fails = check_buttress_outward(assembly)
    assert fails == [], [f.message for f in fails]
    _, vreport = validate(assembly)
    assert not any(
        f.check == "buttress_outward" for f in vreport.critical
    ), [f.message for f in vreport.critical if f.check == "buttress_outward"]

"""Master Plan Stage G — program regions + walkable courtyard arcade (small fixtures)."""

from __future__ import annotations

from pae.arcade import ArcadeSpec, arcade, select_arcade_walk_cells
from pae.plan import CellRole, plan
from pae.pipeline import run_through_assemble
from pae.sketch import PROGRAM_SKETCH_ROLES, SKETCH_LEGEND, parse_sketch
from pae.solver import solve
from pae.spec import m4_courtyard_spec
from pae.structure_spec import LevelSpec, StructureSpec, structure_to_building_spec


def test_sketch_legend_has_arcade_and_stage_g_program_letters():
    assert SKETCH_LEGEND["a"] == "arcade"
    assert SKETCH_LEGEND["h"] == "hall"
    assert SKETCH_LEGEND["c"] == "classroom"
    assert SKETCH_LEGEND["v"] == "service"
    assert SKETCH_LEGEND["r"] == "corridor"
    assert PROGRAM_SKETCH_ROLES == {
        "hall",
        "classroom",
        "service",
        "corridor",
        "arcade",
    }
    marks = parse_sketch("HHCC\nVVRR\nAAAA\n")
    assert marks["hall"]
    assert marks["classroom"]
    assert marks["service"]
    assert marks["corridor"]
    assert marks["arcade"]


def test_program_regions_hall_classroom_service_corridor_affect_plan():
    """Tiny rect — program paint must carve Stage G roles + partitions/doors."""
    sketch = (
        "########\n"
        "########\n"
        "########\n"
        "########\n"
        "########\n"
        "########\n"
    )
    structure = StructureSpec(
        name="stage_g_program",
        style="townhouse",
        seed=3,
        roof_kind="flat",
        levels=[
            LevelSpec(
                sketch=sketch,
                program={
                    "hall": [(1, 1, 2, 4)],
                    "classroom": [(3, 1, 4, 4)],
                    "service": [(5, 1, 6, 2)],
                    "corridor": [(5, 3, 6, 4)],
                },
            )
        ],
    )
    massing, floor_plan, assembly, report = run_through_assemble(structure)
    assert report.ok, [f.message for f in report.failures[:8]]
    assert floor_plan is not None
    labels = {p[3] for p in floor_plan.program_cells}
    assert labels >= {"hall", "classroom", "service", "corridor"}

    grid = floor_plan.storeys[0]
    hall_cells = [
        (x, y) for x, y, level, name in floor_plan.program_cells if name == "hall"
    ]
    assert hall_cells
    assert all(grid.get(*c) == CellRole.HALL for c in hall_cells)

    class_cells = [
        (x, y)
        for x, y, level, name in floor_plan.program_cells
        if name == "classroom"
    ]
    assert class_cells
    assert all(grid.get(*c) == CellRole.CLASSROOM for c in class_cells)

    service_cells = [
        (x, y)
        for x, y, level, name in floor_plan.program_cells
        if name == "service"
    ]
    assert service_cells
    assert all(grid.get(*c) == CellRole.SERVICE for c in service_cells)

    corr_cells = [
        (x, y)
        for x, y, level, name in floor_plan.program_cells
        if name == "corridor"
    ]
    assert corr_cells
    assert all(grid.get(*c) == CellRole.CORRIDOR for c in corr_cells)

    assert floor_plan.interior_partitions
    doors = [p for p in floor_plan.interior_partitions if p[4]]
    assert doors, "expected at least one door between unlike program regions"
    partition_pieces = [p for p in assembly.placements if "partition" in set(p.tags)]
    assert partition_pieces


def test_sketch_program_letters_merge_into_structure_program():
    structure = StructureSpec(
        name="sketch_paint",
        style="townhouse",
        seed=1,
        roof_kind="flat",
        levels=[
            LevelSpec(
                sketch=(
                    "HHHHCCCC\n"
                    "HHHHCCCC\n"
                    "HHHHCCCC\n"
                    "VVVVRRRR\n"
                    "VVVVRRRR\n"
                    "VVVVRRRR\n"
                )
            )
        ],
    )
    painted = structure.levels[0].program_from_sketch()
    assert set(painted) >= {"hall", "classroom", "service", "corridor"}
    building = structure_to_building_spec(structure)
    assert building.level_programs is not None
    l0 = building.level_programs[0]
    assert "hall" in l0 and "classroom" in l0
    massing, mreport = solve(building)
    assert mreport.ok
    floor_plan, preport = plan(massing)
    assert preport.ok, [f.message for f in preport.failures[:6]]
    roles = {floor_plan.storeys[0].get(x, y) for x, y, _, _ in floor_plan.program_cells}
    assert CellRole.HALL in roles
    assert CellRole.CLASSROOM in roles
    assert CellRole.SERVICE in roles
    assert CellRole.CORRIDOR in roles


def test_small_courtyard_arcade_is_walkable_gallery_room():
    """m4 courtyard (8×8, wing_depth=2) — Stage G arcade room, not colonnade."""
    _, _, assembly, report = run_through_assemble(m4_courtyard_spec(seed=6))
    assert report.ok, [f.message for f in report.failures[:5]]

    walk = select_arcade_walk_cells(assembly, ArcadeSpec(depth_bays=1, levels=(0,)))
    assert 0 in walk and len(walk[0]) >= 4, walk

    gallery, greport = arcade(assembly, ArcadeSpec(depth_bays=1, levels=(0,)))
    assert greport.ok, [f.message for f in greport.failures]

    layer = gallery.floor_plan[0]
    arcade_cells = []
    ox, oy = layer.origin_cell
    for ly in range(layer.height):
        for lx in range(layer.width):
            if layer.cells[ly][lx] == CellRole.ARCADE:
                arcade_cells.append((ox + lx, oy + ly))
    assert arcade_cells, "expected ARCADE room cells on the courtyard walk"

    arches = [
        p
        for p in gallery.placements
        if "arcade_gallery" in p.tags and p.asset_id.startswith("wall_arcade")
    ]
    assert arches, "expected wall_arcade leaves tagged arcade_gallery (the room edge)"

    # Must not be the free-standing colonnade path.
    freestanding = [
        p for p in gallery.placements if p.asset_id == "arch_freestanding"
    ]
    assert not freestanding

    # Walk cells must have floor coverage (existing deck or arcade deck).
    from pae.trim import covered_cells

    floored: set = set()
    for p in gallery.placements:
        if p.kind == "floor" and "hole" not in (p.asset_id or ""):
            floored |= covered_cells(p)
    assert all(c in floored for c in arcade_cells)


def test_arcade_face_filter_limits_to_one_run():
    _, _, assembly, _ = run_through_assemble(m4_courtyard_spec(seed=6))
    south_only = select_arcade_walk_cells(
        assembly, ArcadeSpec(depth_bays=1, levels=(0,), faces=("south",))
    )
    all_faces = select_arcade_walk_cells(
        assembly, ArcadeSpec(depth_bays=1, levels=(0,))
    )
    assert south_only.get(0)
    assert len(south_only[0]) < len(all_faces[0])

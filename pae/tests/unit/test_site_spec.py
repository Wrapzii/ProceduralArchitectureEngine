"""Master Plan Stage J skeleton — SiteSpec load/build (≤3 tiny structures, RAM-safe)."""

from __future__ import annotations

from pae.site_spec import (
    SKELETON_MAX_STRUCTURES,
    PlacedStructureSpec,
    PlotPlaceholder,
    RoadPlaceholder,
    SiteSpec,
    build_from_site_spec,
    load_site,
    load_site_yaml,
)
from pae.structure_identity import structure_ids_on, structure_tag
from pae.trim import covered_cells

# Two 3×2 boxes — keep assemble count tiny (never fortress / street_scene).
_TINY_SKETCH = "###\n##\n"


def _two_shed_site() -> SiteSpec:
    return SiteSpec(
        name="two_sheds",
        style="townhouse",
        seed=3,
        structures=[
            PlacedStructureSpec(
                structure_id="shed_a",
                cell_offset=(0, 0),
                sketch=_TINY_SKETCH,
            ),
            PlacedStructureSpec(
                structure_id="shed_b",
                cell_offset=(6, 0),
                sketch=_TINY_SKETCH,
            ),
        ],
        roads=[RoadPlaceholder(name="lane", path_cells=((3, 0), (4, 0)))],
        plots=[PlotPlaceholder(name="plot_west", origin=(0, 0), bays_x=3, bays_y=2)],
    )


def test_dict_yaml_round_trip():
    site = _two_shed_site()
    again, report = load_site(site.to_dict())
    assert report.ok, [f.message for f in report.failures]
    assert again is not None
    assert again.name == "two_sheds"
    assert again.seed == 3
    assert len(again.structures) == 2
    assert again.structures[0].structure_id == "shed_a"
    assert again.structures[1].cell_offset == (6, 0)
    assert again.roads[0].name == "lane"
    assert again.plots[0].bays_x == 3

    yaml_text = site.to_yaml()
    third, yreport = load_site_yaml(yaml_text)
    assert yreport.ok, [f.message for f in yreport.failures]
    assert third is not None
    assert third.name == site.name
    assert [p.structure_id for p in third.structures] == ["shed_a", "shed_b"]
    assert third.structures[1].cell_offset == (6, 0)
    assert third.roads[0].path_cells == ((3, 0), (4, 0))


def test_yaml_sketch_load():
    text = """
name: yard
style: townhouse
seed: 1
structures:
  - structure_id: a
    cell_offset: [0, 0]
    sketch: |
      ###
      ##
  - structure_id: b
    cell_offset: [5, 0]
    sketch: |
      ###
      ##
roads:
  - name: stub
plots:
  - name: p0
    origin: [0, 0]
    bays_x: 3
    bays_y: 2
"""
    site, report = load_site_yaml(text)
    assert report.ok, [f.message for f in report.failures]
    assert site is not None
    assert len(site.structures) == 2
    assert "###" in (site.structures[0].sketch or "")


def test_build_two_tiny_structures_distinct_tags():
    assert SKELETON_MAX_STRUCTURES == 3
    site = _two_shed_site()
    assert len(site.structures) <= 3

    merged, report = build_from_site_spec(site)
    assert report.ok, [f.message for f in report.failures]
    assert merged.placements

    tags_a = structure_tag("shed_a")
    tags_b = structure_tag("shed_b")
    has_a = any(tags_a in p.tags for p in merged.placements)
    has_b = any(tags_b in p.tags for p in merged.placements)
    assert has_a and has_b

    # Offsets applied: shed_b cells shifted by +6 in X vs shed_a local footprint.
    cells_a = set()
    cells_b = set()
    for p in merged.placements:
        ids = structure_ids_on(p)
        if tags_a in ids:
            cells_a |= covered_cells(p)
        if tags_b in ids:
            cells_b |= covered_cells(p)
    assert cells_a and cells_b
    assert max(c[0] for c in cells_a) < min(c[0] for c in cells_b)


def test_resolve_accepts_building_spec_in_memory():
    """BuildingSpec is a valid resolve() payload (dict/YAML still Structure/sketch)."""
    from pae.spec import BuildingSpec, CirculationSpec, FootprintSpec, OpeningPolicy, RoofSpec

    tiny = BuildingSpec(
        name="tiny_box",
        style="townhouse",
        footprint=FootprintSpec(kind="rect", bays_x=3, bays_y=2),
        storeys=1,
        storey_use=["hall"],
        towers=[],
        roof=RoofSpec(kind="flat", pitch=1.0),
        circulation=CirculationSpec(stair_kind="straight", stair_cells=[]),
        openings=OpeningPolicy(windows_per_bay=1, doors_ground=1, windows_ground=1),
        seed=1,
        ground_slab=True,
    )
    site = SiteSpec(name="mem", structures=[])
    placed = PlacedStructureSpec(
        structure_id="box_a",
        cell_offset=(0, 0),
        building=tiny,
    )
    assert placed.resolve(site) is tiny


def test_skeleton_rejects_more_than_max_structures():
    structures = [
        PlacedStructureSpec(
            structure_id=f"s{i}",
            cell_offset=(i * 4, 0),
            sketch=_TINY_SKETCH,
        )
        for i in range(4)
    ]
    site = SiteSpec(name="too_many", structures=structures)
    merged, report = build_from_site_spec(site)
    assert not report.ok
    assert any(f.check == "site_too_many_structures" for f in report.failures)
    assert merged.placements == []

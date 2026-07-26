"""Fortress keep / gatehouse / cloister interior greybox fit-out."""

from __future__ import annotations

from pae.anchors import anchor_kind_from_tags, apply_light_anchors
from pae.compound import build_fortress_compound
from pae.drum import drum_cells
from pae.fitout import (
    GREYBOX_FITOUT_PROPS,
    fitout_candidate_cells,
    fitout_greybox,
    is_fitout_cell,
)
from pae.pipeline import run_through_assemble
from pae.plan import CellRole
from pae.spec import (
    fortress_cloister_range_spec,
    fortress_gatehouse_spec,
    fortress_keep_spec,
)
from pae.validate import _cell_role_is, validate


def _fitout_props(assembly):
    return [p for p in assembly.placements if "fitout_greybox" in p.tags]


def _light_anchors(assembly):
    return [p for p in assembly.placements if p.kind == "light_anchor"]


def test_fortress_keep_has_interior_fitout_candidates():
    _, _, assembly, report = run_through_assemble(fortress_keep_spec())
    assert report.ok
    candidates = fitout_candidate_cells(assembly)
    assert len(candidates) >= 8, "keep hall should expose many interior bays"
    drums = drum_cells(assembly)
    for level, cell in candidates:
        assert cell not in drums
        assert is_fitout_cell(
            assembly.floor_plan,
            level,
            cell,
            castle_fitout=True,
            drum_cells=drums,
        )
        role = assembly.floor_plan[level].role_at(cell[0], cell[1])
        assert _cell_role_is(role, CellRole.INTERIOR)


def test_fortress_keep_fitout_places_props_and_passes_containment():
    _, _, assembly, _ = run_through_assemble(fortress_keep_spec())
    fitted, freport = fitout_greybox(assembly, seed=11, density=0.2, max_props=10)
    assert freport.ok
    props = _fitout_props(fitted)
    assert len(props) >= 3
    assert {p.asset_id for p in props} <= {aid for aid, _ in GREYBOX_FITOUT_PROPS}
    _, vreport = validate(fitted)
    fitout_crit = [f for f in vreport.critical if f.check == "fitout_containment"]
    assert not fitout_crit, [f.message for f in fitout_crit]


def test_fortress_keep_fitout_skips_drum_and_stair_adjacent_cells():
    _, _, assembly, _ = run_through_assemble(fortress_keep_spec())
    fitted, _ = fitout_greybox(assembly, seed=3, density=0.25, max_props=12)
    drums = drum_cells(fitted)
    for p in _fitout_props(fitted):
        assert p.cell not in drums
        layer = fitted.floor_plan[p.level]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr = layer.role_at(p.cell[0] + dx, p.cell[1] + dy)
            assert not _cell_role_is(nr, CellRole.STAIR), (
                f"{p.piece_id} blocks stair at {p.cell}"
            )


def test_fortress_gatehouse_and_cloister_fitout_candidates():
    _, _, gate, _ = run_through_assemble(fortress_gatehouse_spec())
    _, _, cloister, _ = run_through_assemble(
        fortress_cloister_range_spec("west_cloister", 3, 5)
    )
    assert fitout_candidate_cells(gate), "gatehouse hall needs fit-out cells"
    assert fitout_candidate_cells(cloister), "cloister range needs fit-out cells"


def test_fortress_compound_fitout_and_anchors():
    assembly, _, report = build_fortress_compound()
    assert report.ok, [f.message for f in report.failures]
    props = _fitout_props(assembly)
    anchors = _light_anchors(assembly)
    assert len(props) >= 4, "compound keep/gate/cloister should receive greybox props"
    assert anchors, "compound interiors should receive light anchors"
    kinds = {anchor_kind_from_tags(p.tags) for p in anchors}
    assert "sconce" in kinds

    drums = drum_cells(assembly)
    for p in props:
        assert p.cell not in drums, f"fitout {p.piece_id} landed in tower drum"
        tags = set(p.tags)
        assert any(
            t in tags or t.startswith("building:")
            for t in (
                "north_keep",
                "gatehouse",
                "west_cloister",
                "east_cloister",
            )
        ), f"fitout {p.piece_id} outside keep/gate/cloister ranges"

    _, vreport = validate(assembly)
    fitout_crit = [f for f in vreport.critical if f.check == "fitout_containment"]
    assert not fitout_crit, [f.message for f in fitout_crit]


def test_fortress_compound_no_curtain_fitout():
    assembly, _, report = build_fortress_compound()
    assert report.ok
    curtain_props = [
        p
        for p in _fitout_props(assembly)
        if "west_curtain" in p.tags
        or "east_curtain" in p.tags
        or "building:west_curtain" in p.tags
        or "building:east_curtain" in p.tags
    ]
    assert not curtain_props, "curtain walls must not receive interior fit-out props"


def test_fortress_keep_anchors_after_assemble():
    _, _, assembly, _ = run_through_assemble(fortress_keep_spec())
    anchored, areport = apply_light_anchors(assembly)
    assert areport.ok, [f.message for f in areport.failures]
    assert _light_anchors(anchored), "keep hall should receive sconce anchors"

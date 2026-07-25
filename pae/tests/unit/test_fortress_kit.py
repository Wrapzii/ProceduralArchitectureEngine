"""Fortress kit — spires, dormers, buttresses, cloister arcade, grand steps, battlements."""

from __future__ import annotations

import pytest

from pae.compound import build_castle_curtain_compound
from pae.contract import MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM, placement_world_aabb
from pae.pipeline import run_through_assemble
from pae.primitives import all_descriptors, footprint_contract_errors, get
from pae.primitives.catalog import catalog_by_id
from pae.spec import castle_curtain_wall_spec, castle_gatehouse_spec, m3_keep_tower_spec
from pae.trim import TrimOptions, covered_cells, trim
from pae.validate import validate


def _assemble(spec):
    _, _, assembly, report = run_through_assemble(spec)
    assert report.ok, [f.message for f in report.failures]
    return assembly


def _aabb(p):
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


# --- descriptors -------------------------------------------------------------


def test_fortress_pieces_registered_and_measured():
  ids = {"spire_conical", "steps_grand", "dormer_steep"}
  catalog = {d.id for d in all_descriptors()}
  missing = ids - catalog
  assert not missing, f"missing fortress pieces: {missing}"
  for pid in ids:
    errs = footprint_contract_errors(get(pid), tol_cm=TOL_CM)
    assert errs == [], "\n".join(errs)


def test_spire_conical_is_centred_tall_cone():
  desc = get("spire_conical")
  assert desc.rotates_about_center
  assert desc.kind == "roofline"
  assert "fortress" in desc.tags
  assert desc.size_cm[2] == pytest.approx(STOREY_CM * 2.0, rel=0.01)


def test_steps_grand_taller_than_external():
  ext = get("steps_external")
  grand = get("steps_grand")
  assert grand.size_cm[2] > ext.size_cm[2]
  assert "grand" in grand.tags


def test_dormer_steep_taller_than_gabled():
  g = get("dormer_gabled")
  s = get("dormer_steep")
  assert s.size_cm[2] > g.size_cm[2]
  assert "steep" in s.tags


# --- trim: conical spires on towers ------------------------------------------


def test_m3_tower_can_use_conical_spire():
  base = _assemble(m3_keep_tower_spec())
  opts = TrimOptions(spire_piece="spire_conical")
  trimmed, report = trim(base, opts)
  assert report.ok
  assert any(p.asset_id == "spire_conical" for p in trimmed.placements)


def test_gatehouse_trim_conical_spire_on_caps():
  base = _assemble(castle_gatehouse_spec())
  opts = TrimOptions(
    railings=False,
    buttresses=False,
    roofline=True,
    colonnade=False,
    parapets=False,
    spire_piece="spire_conical",
  )
  trimmed, report = trim(base, opts)
  assert report.ok
  spires = [p for p in trimmed.placements if p.asset_id == "spire_conical"]
  assert len(spires) >= 2, "twin gatehouse towers need conical spires"
  caps = [p for p in base.placements if p.kind == "tower_cap"]
  for sp in spires:
    cap_xy = next(
      (c.offset_cm[0], c.offset_cm[1])
      for c in caps
      if c.cell == sp.cell
    )
    assert sp.offset_cm[0] == pytest.approx(cap_xy[0], abs=1.0)
    assert sp.offset_cm[1] == pytest.approx(cap_xy[1], abs=1.0)


# --- trim: castle curtain buttresses -----------------------------------------


def test_castle_curtain_gets_outward_buttresses():
  base = _assemble(castle_curtain_wall_spec("west_curtain", 6, storeys=2))
  base.building_class = "castle"
  for p in base.placements:
    if p.kind == "wall":
      p.tags = p.tags | frozenset({"west_curtain", "curtain"})
  opts = TrimOptions(
    railings=False,
    roofline=False,
    colonnade=False,
    parapets=False,
    buttresses=True,
  )
  trimmed, report = trim(base, opts)
  assert report.ok
  butts = [p for p in trimmed.placements if p.asset_id == "buttress"]
  assert butts, "2-storey castle curtain should carry buttresses"
  interior = set()
  for p in trimmed.placements:
    if p.kind in ("floor", "plinth", "ground"):
      interior |= covered_cells(p)
  for b in butts:
    assert not (covered_cells(b) & interior), "buttress must project outward"


# --- trim: cloister wall arcade ----------------------------------------------


def test_courtyard_can_use_wall_arcade_cloister():
  from pae.spec import m4_courtyard_spec

  base = _assemble(m4_courtyard_spec())
  opts = TrimOptions(
    colonnade=True,
    arcade_piece="wall_arcade",
    buttresses=False,
    roofline=False,
    railings=False,
    parapets=False,
  )
  trimmed, report = trim(base, opts)
  assert report.ok
  arcs = [p for p in trimmed.placements if p.asset_id == "wall_arcade"]
  assert arcs, "cloister walk should place wall_arcade on courtyard faces"


# --- trim: grand exterior steps ----------------------------------------------


def test_exterior_steps_at_ground_doors():
  base = _assemble(castle_gatehouse_spec())
  opts = TrimOptions(
    exterior_steps=True,
    steps_piece="steps_grand",
    railings=False,
    buttresses=False,
    roofline=False,
    colonnade=False,
    parapets=False,
  )
  trimmed, report = trim(base, opts)
  assert report.ok
  steps = [p for p in trimmed.placements if p.asset_id == "steps_grand"]
  assert steps, "fortress entrance should get grand exterior steps"
  for s in steps:
    assert s.level == 0


def test_steep_roof_auto_selects_dormer_steep():
  from pae.spec import m3_keep_tower_spec

  base = _assemble(m3_keep_tower_spec())
  pitched = [
    p
    for p in base.placements
    if p.kind == "roof" and "flat" not in p.asset_id and "gable" not in p.asset_id
  ]
  if not pitched:
    pytest.skip("no pitched slope planes in m3")
  opts = TrimOptions(
    dormer_piece="dormer_gabled",
    railings=False,
    buttresses=False,
    colonnade=False,
    parapets=False,
  )
  trimmed, report = trim(base, opts)
  assert report.ok
  dormers = [p for p in trimmed.placements if p.asset_id == "dormer_steep"]
  assert dormers, "steep roof should auto-upgrade to dormer_steep"


# --- castle compound integration (read-only) ---------------------------------


def test_castle_compound_still_validates():
  assembly, _, report = build_castle_curtain_compound()
  assert report.ok, [f.message for f in report.failures]
  _, vreport = validate(assembly)
  assert vreport.ok, [f.message for f in vreport.critical]

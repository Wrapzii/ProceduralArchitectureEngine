"""Spiral tower shell — newel pillar + drum enclosure (Handbook §6 test-first).

@VAL_SPIRAL_SHELL: poisoned fixtures must fire before the healthy spiral passes.
Does not demote existing stair checks.
"""

from __future__ import annotations

from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.primitives.catalog import get as get_primitive
from pae.primitives.measure import footprint_contract_errors
from pae.spec import m_spiral_tower_spec
from pae.spiral_shell import (
    SPIRAL_NEWEL_ASSET,
    check_spiral_drum_enclosure,
    check_spiral_newel_exists,
    check_spiral_shell,
    make_spiral_drum_bay_gap_defect,
    make_spiral_drum_door_exempt_ok,
    make_spiral_missing_newel_defect,
)
from pae.validate import validate


def test_spiral_newel_primitive_registered():
    desc = get_primitive(SPIRAL_NEWEL_ASSET)
    assert desc.kind == "column"
    assert "newel" in desc.tags
    assert desc.rotates_about_center
    assert not footprint_contract_errors(desc)


def test_missing_newel_poison_fires():
    """Handbook §6: deliberately broken fixture must trip spiral_newel_exists."""
    poisoned = make_spiral_missing_newel_defect()
    hits = check_spiral_newel_exists(poisoned)
    assert hits, "spiral_newel_exists never fires — may have become a no-op"
    assert all(f.check == "spiral_newel_exists" for f in hits)
    assert all(f.critical for f in hits)
    assert "newel" in hits[0].message.lower()
    assert hits[0].world_xyz is not None

    _, vreport = validate(poisoned)
    assert any(f.check == "spiral_newel_exists" for f in vreport.critical)


def test_drum_bay_gap_poison_fires():
    """Handbook §6: missing tower_arc yaw must trip spiral_drum_enclosure."""
    poisoned = make_spiral_drum_bay_gap_defect()
    hits = check_spiral_drum_enclosure(poisoned)
    assert hits, "spiral_drum_enclosure never fires — may have become a no-op"
    assert all(f.check == "spiral_drum_enclosure" for f in hits)
    assert all(f.critical for f in hits)
    assert "270" in hits[0].message
    assert "missing" in hits[0].message
    assert hits[0].world_xyz is not None

    _, vreport = validate(poisoned)
    assert any(f.check == "spiral_drum_enclosure" for f in vreport.critical)


def test_designed_door_bay_exempts_drum_gap():
    """@VAL_TOWER_DOOR hook: tagged door bay may omit one tower_arc quarter."""
    ok = make_spiral_drum_door_exempt_ok()
    assert not check_spiral_drum_enclosure(ok)
    assert not check_spiral_newel_exists(ok)
    assert not check_spiral_shell(ok)


def test_healthy_open_well_spiral_omits_disconnected_newel_and_closes_drum():
    _, _, assembly, areport = run_through_assemble(m_spiral_tower_spec())
    assert areport.ok, [f.message for f in areport.failures]

    newels = [p for p in assembly.placements if p.asset_id == SPIRAL_NEWEL_ASSET]
    spirals = [p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"]
    assert spirals, "expected spiral quarters"
    # The standard stair's inner edge is well outside the fixed-size pole.
    # A disconnected pole would only obstruct the open well.
    assert not newels

    shell_hits = check_spiral_shell(assembly)
    assert not shell_hits, [f.message for f in shell_hits]


def test_healthy_spiral_shell_checks_pass_validate():
    _, _, assembly, _ = run_through_assemble(m_spiral_tower_spec())
    _, vreport = validate(assembly)
    shell = [
        f
        for f in vreport.failures
        if f.check in ("spiral_newel_exists", "spiral_drum_enclosure")
    ]
    assert not shell, [f.message for f in shell]


def test_spiral_trim_still_green_with_shell():
    """Shell checks stay clean on the trim path (do not assert unrelated criticals)."""
    _, _, assembly, stage_report = run_through_validate_trim(m_spiral_tower_spec())
    shell = [
        f
        for f in stage_report.failures
        if f.check in ("spiral_newel_exists", "spiral_drum_enclosure")
    ]
    assert not shell, [f.message for f in shell]
    # Trim must not re-introduce a disconnected pole into the open well.
    assert not any(p.asset_id == SPIRAL_NEWEL_ASSET for p in assembly.placements)

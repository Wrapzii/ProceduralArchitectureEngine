"""Phase 0.6 / 4.7 — circular tower helical windows + roof junction."""

from __future__ import annotations

from pae.contract import STOREY_CM
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.primitives.catalog import get as get_primitive
from pae.spec import m3_keep_tower_spec, m_spiral_tower_spec
from pae.validate import validate, _check_storey_egress


def _tower_cell(assembly, massing=None):
    if massing is not None:
        tower = next(v for v in massing.volumes if v.role == "tower")
        return (tower.x0, tower.y0)
    wins = [p for p in assembly.placements if "drum_window" in p.tags]
    assert wins
    return wins[0].cell


def test_tower_arc_quarter_window_has_aperture_contract():
    win = get_primitive("tower_arc_quarter_window")
    solid = get_primitive("tower_arc_quarter")
    assert win.aperture is not None
    assert win.aperture.kind == "window"
    assert win.size_cm == solid.size_cm
    assert "window" in win.tags


def test_tower_junction_descriptor_between_drum_and_crown():
    j = get_primitive("tower_junction")
    assert j.size_cm[2] > 0.0
    assert j.size_cm[2] < STOREY_CM * 0.2
    assert "junction" in j.tags


def test_m3_tower_has_perimeter_windows_and_apertures():
    _, _, assembly, areport = run_through_assemble(m3_keep_tower_spec())
    assert areport.ok, [f.message for f in areport.failures]
    drum_wins = [
        p
        for p in assembly.placements
        if p.kind == "wall" and "drum_window" in p.tags
    ]
    win_arcs = [
        p
        for p in assembly.placements
        if p.asset_id == "tower_arc_quarter_window"
    ]
    assert drum_wins, "expected perimeter drum window wall pieces"
    assert win_arcs, "expected windowed arc quarters"
    tower_aps = [
        a
        for a in assembly.apertures
        if a.kind == "window" and a.wall_piece_id.startswith("tower_win_")
    ]
    assert len(tower_aps) == len(drum_wins)
    # One windowed quarter per storey (non-helical), attach face skipped.
    assert len(drum_wins) >= 2


def test_spiral_tower_helical_windows_at_tread_heights():
    from pae.solver import solve

    spec = m_spiral_tower_spec()
    massing, mreport = solve(spec)
    assert mreport.ok
    _, _, assembly, areport = run_through_assemble(spec)
    assert areport.ok, [f.message for f in areport.failures]

    tower = next(v for v in massing.volumes if v.role == "tower")
    cell = (tower.x0, tower.y0)
    quarter_rise = get_primitive("stair_spiral_quarter").size_cm[2]
    drum_wins = [
        p
        for p in assembly.placements
        if p.kind == "wall"
        and "drum_window" in p.tags
        and p.cell == cell
    ]
    assert drum_wins
    # Helical: several per storey at quarter-rise z offsets (attach yaw skipped).
    z_offs = sorted({round(p.offset_cm[2], 3) for p in drum_wins if p.level == 0})
    assert any(abs(z - quarter_rise) < 1.0 for z in z_offs) or len(z_offs) >= 2
    assert max(z_offs) <= STOREY_CM + 1.0

    # Spiral stairs still present — do not wipe Phase 3.1 placement.
    spirals = [p for p in assembly.placements if p.asset_id == "stair_spiral_quarter"]
    assert len(spirals) >= 4


def test_tower_windows_no_freestanding_islands():
    for spec in (m3_keep_tower_spec(), m_spiral_tower_spec()):
        _, _, assembly, _ = run_through_assemble(spec)
        _, vreport = validate(assembly)
        islands = [f for f in vreport.critical if f.check == "freestanding"]
        assert islands == [], [f.message for f in islands]


def test_tower_storey_egress_volume_passes():
    for spec in (m3_keep_tower_spec(), m_spiral_tower_spec()):
        _, _, assembly, _ = run_through_assemble(spec)
        eg = _check_storey_egress(assembly)
        volume = [f for f in eg if "VOLUME" in f.message]
        assert volume == [], [f.message for f in volume]


def test_tower_junction_present_in_assembly():
    _, _, assembly, _ = run_through_assemble(m3_keep_tower_spec())
    junctions = [p for p in assembly.placements if p.asset_id == "tower_junction"]
    assert len(junctions) == 1


def test_spiral_trim_still_validates_with_tower_windows():
    _, _, _, stage_report = run_through_validate_trim(m_spiral_tower_spec())
    assert stage_report.ok, [f.message for f in stage_report.critical]

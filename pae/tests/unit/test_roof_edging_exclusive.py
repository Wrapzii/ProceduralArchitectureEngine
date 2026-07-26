"""Roof edging exclusivity — D3-4 / Handbook §11d (broken fixtures first)."""

from __future__ import annotations

from dataclasses import replace

from pae.assembly_types import Assembly, SolidPlacement
from pae.compound import build_castle_curtain_compound
from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM, rotation_offset_cm
from pae.roof_edging import CHECK_ROOF_EDGING_EXCLUSIVE, check_roof_edging_exclusive
from pae.validate import validate


def _parapet(pid: str, cell: tuple[int, int], *, face: str = "south") -> SolidPlacement:
    from pae.boundary import FACE_YAW

    yaw = FACE_YAW[face]
    sx, sy, sz = WALL_T_CM, MODULE_CM, WALL_T_CM
    ox, oy = rotation_offset_cm(yaw, sx, sy)
    return SolidPlacement(
        piece_id=pid,
        asset_id="parapet_solid",
        kind="railing",
        cell=cell,
        level=1,
        yaw=yaw,
        offset_cm=(ox, oy, STOREY_CM),
        size_cm=(sx, sy, sz),
        tags=frozenset({"parapet", "trim"}),
    )


def _battlement(pid: str, cell: tuple[int, int], *, face: str = "south") -> SolidPlacement:
    from pae.boundary import FACE_YAW

    yaw = FACE_YAW[face]
    sx, sy, sz = MODULE_CM, WALL_T_CM, 80.0
    ox, oy = rotation_offset_cm(yaw, sx, sy)
    return SolidPlacement(
        piece_id=pid,
        asset_id="battlement",
        kind="battlement",
        cell=cell,
        level=1,
        yaw=yaw,
        offset_cm=(ox, oy, STOREY_CM),
        size_cm=(sx, sy, sz),
        tags=frozenset({"battlement", "trim", "curtain"}),
    )


def test_double_edging_on_same_edge_fires_roof_edging_exclusive():
    cell = (2, 0)
    asm = Assembly(
        placements=[
            _parapet("parapet_a", cell, face="south"),
            _battlement("batt_a", cell, face="south"),
        ]
    )
    hits = check_roof_edging_exclusive(asm)
    assert hits, "parapet + battlement on same edge must fail"
    assert all(f.check == CHECK_ROOF_EDGING_EXCLUSIVE and f.critical for f in hits)
    assert "multiple edging" in hits[0].message


def test_single_edging_style_passes():
    asm = Assembly(placements=[_parapet("parapet_a", (1, 1), face="west")])
    assert check_roof_edging_exclusive(asm) == []


def test_castle_curtain_compound_has_no_double_edging():
    assembly, _layout, report = build_castle_curtain_compound()
    assert report.ok, [f.message for f in report.failures]
    hits = check_roof_edging_exclusive(assembly)
    assert hits == [], [f.message for f in hits]
    _, vreport = validate(assembly)
    assert not any(f.check == CHECK_ROOF_EDGING_EXCLUSIVE for f in vreport.critical)


def test_validate_surfaces_roof_edging_exclusive():
    asm = Assembly(
        placements=[
            _parapet("parapet_a", (0, 0), face="east"),
            _battlement("batt_a", (0, 0), face="east"),
        ]
    )
    _, report = validate(asm)
    assert any(
        f.check == CHECK_ROOF_EDGING_EXCLUSIVE and f.critical for f in report.critical
    )

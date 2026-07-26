"""S-012 four-plate hip mesh topology + pitched slope must not bake gable caps."""

from __future__ import annotations

import pytest

from pae.contract import MODULE_CM
from pae.pipeline import run_through_assemble
from pae.primitives.roofs import (
    _double_pitch_verts_faces,
    _double_pitch_verts_faces_ridge_y,
    hip_roof_slope_face_count,
    hip_roof_verts_faces,
)
from pae.spec import fortress_keep_spec, m11_hip_roof_spec
from pae.validate import validate


def _sloped_face_count(verts, faces) -> int:
    return hip_roof_slope_face_count(verts, faces)


def test_hip_square_has_four_slope_plates():
    sx = sy = MODULE_CM
    sz = 240.0
    verts, faces = hip_roof_verts_faces(sx, sy, sz)
    assert len(verts) == 5
    assert _sloped_face_count(verts, faces) == 4
    apex = verts[4]
    assert apex[2] == pytest.approx(sz)
    eave_z = {verts[i][2] for i in (0, 1, 2, 3)}
    assert eave_z == {0.0}


def test_hip_rectangle_has_four_slope_plates():
    sx, sy, sz = MODULE_CM * 2, MODULE_CM, 200.0
    verts, faces = hip_roof_verts_faces(sx, sy, sz)
    assert len(verts) == 6
    assert _sloped_face_count(verts, faces) == 4
    ridge_z = {verts[4][2], verts[5][2]}
    assert all(z == pytest.approx(sz) for z in ridge_z)


def test_hip_tall_rectangle_ridge_along_y():
    sx, sy, sz = MODULE_CM, MODULE_CM * 2, 200.0
    verts, faces = hip_roof_verts_faces(sx, sy, sz)
    assert len(verts) == 6
    assert _sloped_face_count(verts, faces) == 4


def test_pitched_slope_mesh_has_no_baked_gable_caps():
    """Slope deck is two planes only; gable ends are separate placements."""
    sx, sy, sz = MODULE_CM * 4, MODULE_CM * 3, 260.0
    verts, faces = _double_pitch_verts_faces(sx, sy, sz)
    assert _sloped_face_count(verts, faces) == 2
    verts_y, faces_y = _double_pitch_verts_faces_ridge_y(sy, sx, sz)
    assert _sloped_face_count(verts_y, faces_y) == 2


def _assembly_from_spec(spec):
    _, _, assembly, stage_report = run_through_assemble(spec)
    assert stage_report.ok is True, [f.message for f in stage_report.failures]
    return assembly


def test_fortress_keep_uses_single_hip_not_gable_stack():
    assembly = _assembly_from_spec(fortress_keep_spec())
    hips = [p for p in assembly.placements if p.asset_id == "roof_hip"]
    gables = [p for p in assembly.placements if p.asset_id == "roof_gable_infill"]
    slopes = [p for p in assembly.placements if p.asset_id == "roof_pitched_slope"]
    assert len(hips) == 1
    assert gables == []
    assert slopes == []


def test_m11_hip_visual_contract_validates():
    assembly = _assembly_from_spec(m11_hip_roof_spec())
    _, report = validate(assembly)
    assert report.critical == [], [f.message for f in report.critical]
    assert report.ok is True

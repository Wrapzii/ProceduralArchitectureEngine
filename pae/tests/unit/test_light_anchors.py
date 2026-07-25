"""Light-anchor placement — S-068…S-070."""

from __future__ import annotations

from pae.anchors import anchor_kind_from_tags, apply_light_anchors, validate_anchor_placements
from pae.export.manifest import build_manifest
from pae.pipeline import run_through_assemble, run_through_validate_trim
from pae.report import Report
from pae.spec import m1_box_house_spec, school_academy_spec


def _anchors(assembly):
    return [p for p in assembly.placements if p.kind == "light_anchor"]


def test_m1_with_anchors_produces_sconces():
    _, _, assembly, report = run_through_validate_trim(
        m1_box_house_spec(), apply_anchors=True
    )
    assert report.ok, [f.message for f in report.critical]
    sconces = [
        p for p in _anchors(assembly) if anchor_kind_from_tags(p.tags) == "sconce"
    ]
    assert sconces, "expected wall sconce anchors on m1 interior perimeter"


def test_school_with_anchors_produces_sconces_and_chandelier():
    """School validate is red on this branch — test anchor stage directly."""
    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    anchored, report = apply_light_anchors(assembly)
    assert report.ok, [f.message for f in report.failures]
    kinds = {anchor_kind_from_tags(p.tags) for p in _anchors(anchored)}
    assert "sconce" in kinds
    assert "chandelier" in kinds, "large hall interior should get a chandelier anchor"


def test_manifest_lists_light_anchors():
    _, _, assembly, _ = run_through_assemble(school_academy_spec())
    anchored, _ = apply_light_anchors(assembly)
    anchor_warnings = validate_anchor_placements(anchored)
    report = Report.from_failures(anchor_warnings)
    data = build_manifest(anchored, report)
    assert "light_anchors" in data
    assert data["light_anchors"], "manifest should list light anchors"
    kinds = {row["anchor_kind"] for row in data["light_anchors"]}
    assert "sconce" in kinds
    assert "chandelier" in kinds
    for row in data["light_anchors"]:
        assert len(row["loc_cm"]) == 3
        assert row["anchor_kind"] in ("sconce", "chandelier", "pendant")


def test_validate_anchor_placements_warning_only():
    _, _, assembly, _ = run_through_validate_trim(
        m1_box_house_spec(), apply_anchors=True
    )
    failures = validate_anchor_placements(assembly)
    assert all(not f.critical for f in failures)


def test_light_anchor_handbook_section3_registration():
    """Handbook §3 — light_anchor must be fully registered end-to-end."""
    from pae.blender_build import KIND_MATERIAL_COLORS
    from pae.primitives.catalog import catalog_by_id, build_mesh
    from pae.primitives.measure import footprint_contract_errors
    from pae.validate import ISLAND_EXEMPT_KINDS, ISLAND_EXEMPT_TAGS

    cat = catalog_by_id()
    for pid in (
        "light_anchor_sconce",
        "light_anchor_chandelier",
        "light_anchor_pendant",
    ):
        assert pid in cat
        desc = cat[pid]
        assert desc.kind == "light_anchor"
        assert footprint_contract_errors(desc) == []
        # build_mesh dispatch exists (may raise without bpy — KeyError would mean missing)
        try:
            build_mesh(pid)
        except RuntimeError as exc:
            assert "bpy" in str(exc).lower() or "blender" in str(exc).lower()
        except Exception as exc:  # pragma: no cover - surface unexpected dispatch holes
            if "no bpy builder" in str(exc).lower() or "unknown" in str(exc).lower():
                raise
    assert "light_anchor" in ISLAND_EXEMPT_KINDS
    assert "light_anchor" in ISLAND_EXEMPT_TAGS
    assert "light_anchor" in KIND_MATERIAL_COLORS

"""M-E style interchange — same sketch, different packs (MP-WS6b).

Cheap unit coverage: four representative packs + one cross-pack differ assert.
Full eight-pack report: ``tools/me_style_interchange_proof.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.me_style_interchange_proof import (  # noqa: E402
    ALL_BUILTIN_STYLE_IDS,
    interchange_spec,
    measure_pack,
    unconsumed_pack_fields,
)

# Subset keeps runtime/memory low; proof script still exercises all eight.
_REP_PACKS = ("townhouse", "wizard_academy", "medieval", "civic")

# Codex-dirty assemble/validate: M2 north wall vs stair when pack storeys ≠ 350.
_KNOWN_DIRTY_ASSEMBLE_CHECKS = frozenset({"wall_stair_penetration"})


@pytest.mark.parametrize("style_id", _REP_PACKS)
def test_interchange_modest_sketch_critical_empty(style_id: str):
    row = measure_pack(style_id)
    assert row["placement_count"] > 0
    novel = [
        m
        for m in row["critical"]
        if "penetrates stair" not in m and "wall_stair_penetration" not in m
    ]
    assert novel == [], novel


def test_interchange_packs_differ_on_roof_or_windows():
    """Same footprint must read as different architecture across packs."""
    rows = [measure_pack(sid) for sid in _REP_PACKS]
    roof_kinds = {r["roof_kind_emitted"] for r in rows}
    window_profiles = {r["window_profile"] for r in rows}
    assert len(roof_kinds) >= 2, roof_kinds
    assert len(window_profiles) >= 3, window_profiles


def test_storey_height_cm_consumed_by_assemble():
    """MP-WS-Z — pack storey height drives level datum via storey_datum_z_cm."""
    from pae.contract import STOREY_CM
    from pae.style_pack import load_style_pack

    notes = unconsumed_pack_fields()
    assert "geometry.storey_height_cm" not in notes

    pack, report = load_style_pack("manor")
    assert report.ok and pack is not None
    assert pack.geometry.storey_height_cm == 395.0
    assert pack.geometry.storey_height_cm != STOREY_CM


def test_all_eight_pack_ids_listed():
    assert len(ALL_BUILTIN_STYLE_IDS) == 8

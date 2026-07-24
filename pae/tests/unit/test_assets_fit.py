"""Unit tests for snap_fit and footprint evaluation."""

import pytest

from pae.assets.fit import evaluate_footprint_fit, snap_fit
from pae.contract import MODULE_CM, WALL_T_CM


class TestSnapFit:
    def test_exact_module_ok(self):
        decision, scale = snap_fit(MODULE_CM)
        assert decision == "ok"
        assert scale == 1.0

    def test_within_tolerance_ok(self):
        decision, scale = snap_fit(MODULE_CM - 6.0)
        assert decision == "ok"
        assert scale == 1.0

    def test_slight_mismatch_scales(self):
        decision, scale = snap_fit(MODULE_CM - 20.0)
        assert decision == "scale"
        assert pytest.approx(scale, rel=1e-4) == MODULE_CM / (MODULE_CM - 20.0)

    def test_176cm_pillar_rejects(self):
        """§4.3 acceptance: 1.76 m in a 4 m module must not silently accept."""
        decision, factor = snap_fit(176.0)
        assert decision == "reject"
        assert decision != "ok"
        assert factor == pytest.approx(MODULE_CM / 176.0)

    def test_two_modules_ok(self):
        decision, scale = snap_fit(MODULE_CM * 2)
        assert decision == "ok"
        assert scale == 1.0


class TestEvaluateFootprintFit:
    def test_wall_nominal(self):
        fit = evaluate_footprint_fit((WALL_T_CM, MODULE_CM, 350.0), "wall")
        assert fit.decision == "ok"
        assert fit.footprint_modules == (1, 1)

    def test_floor_4x3_modules(self):
        fit = evaluate_footprint_fit((MODULE_CM * 4, MODULE_CM * 3, 30.0), "floor")
        assert fit.decision == "ok"
        assert fit.footprint_modules == (4, 3)

    def test_prop_176cm_rejects(self):
        fit = evaluate_footprint_fit((176.0, 176.0, 350.0), "prop")
        assert fit.decision == "reject"
        assert fit.failures

    def test_pillar_176x400_import_case(self):
        """Long axis fits; short axis (176 cm) fails module snap for generic kind."""
        fit = evaluate_footprint_fit((176.0, MODULE_CM, 350.0), "prop")
        assert fit.decision == "reject"

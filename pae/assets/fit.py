"""snap_fit (§4.4) — WP-2. Seeded from contract; flesh out in WP-2."""

from __future__ import annotations

from typing import Tuple

from pae.contract import MODULE_CM, MAX_STRETCH, TOL_CM


def snap_fit(
    size_cm: float,
    module: float = MODULE_CM,
    tol: float = TOL_CM,
    max_stretch: float = MAX_STRETCH,
) -> Tuple[str, float]:
    """Return (decision, scale_or_1) where decision is ok | scale | reject."""
    n = max(1, round(size_cm / module))
    target = n * module
    err = abs(size_cm - target) / target
    if err <= tol / target:
        return ("ok", 1.0)
    if err <= max_stretch:
        return ("scale", target / size_cm)
    return ("reject", target / size_cm)

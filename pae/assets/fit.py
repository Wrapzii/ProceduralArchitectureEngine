"""snap_fit and footprint evaluation (§4.4) — WP-2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM, MAX_STRETCH, STOREY_CM, TOL_CM, WALL_T_CM


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


def module_count(size_cm: float, scale: float = 1.0, module: float = MODULE_CM) -> int:
    """Whole module cells spanned along one footprint axis after optional scale."""
    adjusted = size_cm * scale
    return max(1, round(adjusted / module))


footprint_modules = module_count


@dataclass(frozen=True)
class AxisFit:
    axis: str
    size_cm: float
    decision: str
    scale: float
    modules: int


@dataclass(frozen=True)
class FootprintFit:
    """Combined XY footprint fit for import (§4.4)."""

    decision: str
    long_axis: AxisFit
    short_axis: AxisFit | None
    scale_xy: Tuple[float, float]
    footprint_modules: Tuple[int, int]
    failures: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.decision == "ok"

    @property
    def rejected(self) -> bool:
        return self.decision == "reject"


def _axis_fit(name: str, size_cm: float) -> AxisFit:
    decision, scale = snap_fit(size_cm)
    applied_scale = scale if decision == "scale" else 1.0
    return AxisFit(
        axis=name,
        size_cm=size_cm,
        decision=decision,
        scale=scale,
        modules=module_count(size_cm, applied_scale),
    )


def _combine_decisions(*decisions: str) -> str:
    if any(d == "reject" for d in decisions):
        return "reject"
    if any(d == "scale" for d in decisions):
        return "scale"
    return "ok"


def _wall_thickness_fit(short_size: float) -> AxisFit:
    wall_err = abs(short_size - WALL_T_CM)
    if wall_err <= TOL_CM:
        return AxisFit("thickness", short_size, "ok", 1.0, 1)
    if wall_err / WALL_T_CM <= MAX_STRETCH:
        return AxisFit("thickness", short_size, "scale", WALL_T_CM / short_size, 1)
    return AxisFit("thickness", short_size, "reject", WALL_T_CM / short_size, 1)


def evaluate_footprint_fit(
    size_cm: Tuple[float, float, float],
    kind: str,
) -> FootprintFit:
    """Evaluate whether measured XY footprint fits module grid."""
    sx, sy, _sz = size_cm
    failures: list[str] = []
    kind = kind.lower()

    if kind == "wall":
        along_x = sx >= sy
        long_size, short_size = (sx, sy) if along_x else (sy, sx)
        long_name = "x" if along_x else "y"
        short_name = "y" if along_x else "x"

        long_fit = _axis_fit(long_name, long_size)
        short_fit = _wall_thickness_fit(short_size)
        decision = _combine_decisions(long_fit.decision, short_fit.decision)

        if long_fit.decision == "reject":
            failures.append(
                f"wall run {long_size:.1f} cm does not fit module grid "
                f"(scale factor {long_fit.scale:.4f})"
            )
        if short_fit.decision == "reject":
            failures.append(
                f"wall thickness {short_size:.1f} cm != nominal {WALL_T_CM} cm"
            )

        scale_long = long_fit.scale if long_fit.decision == "scale" else 1.0
        scale_short = short_fit.scale if short_fit.decision == "scale" else 1.0
        if along_x:
            scale_xy = (scale_short, scale_long)
            footprint_modules = (1, long_fit.modules)
        else:
            scale_xy = (scale_long, scale_short)
            footprint_modules = (long_fit.modules, 1)

        return FootprintFit(
            decision=decision,
            long_axis=long_fit,
            short_axis=short_fit,
            scale_xy=scale_xy,
            footprint_modules=footprint_modules,
            failures=tuple(failures),
        )

    if kind in ("floor", "roof"):
        x_fit = _axis_fit("x", sx)
        y_fit = _axis_fit("y", sy)
        decision = _combine_decisions(x_fit.decision, y_fit.decision)
        if x_fit.decision == "reject":
            failures.append(f"footprint X {sx:.1f} cm does not fit module grid")
        if y_fit.decision == "reject":
            failures.append(f"footprint Y {sy:.1f} cm does not fit module grid")
        long_fit = x_fit if sx >= sy else y_fit
        short_fit = y_fit if sx >= sy else x_fit
        scale_xy = (
            x_fit.scale if x_fit.decision == "scale" else 1.0,
            y_fit.scale if y_fit.decision == "scale" else 1.0,
        )
        return FootprintFit(
            decision=decision,
            long_axis=long_fit,
            short_axis=short_fit,
            scale_xy=scale_xy,
            footprint_modules=(x_fit.modules, y_fit.modules),
            failures=tuple(failures),
        )

    along_x = sx >= sy
    long_size, short_size = (sx, sy) if along_x else (sy, sx)
    long_name = "x" if along_x else "y"
    short_name = "y" if along_x else "x"

    long_fit = _axis_fit(long_name, long_size)
    short_fit = _axis_fit(short_name, short_size) if short_size > TOL_CM else None

    parts = [long_fit.decision]
    if short_fit is not None:
        parts.append(short_fit.decision)
    decision = _combine_decisions(*parts)

    if long_fit.decision == "reject":
        failures.append(f"footprint long axis {long_size:.1f} cm does not fit module grid")
    if short_fit is not None and short_fit.decision == "reject":
        failures.append(f"footprint short axis {short_size:.1f} cm does not fit module grid")

    scale_long = long_fit.scale if long_fit.decision == "scale" else 1.0
    if along_x:
        scale_xy = (1.0, scale_long)
        footprint_modules = (module_count(sx), long_fit.modules)
    else:
        scale_xy = (scale_long, 1.0)
        footprint_modules = (long_fit.modules, module_count(sy))

    return FootprintFit(
        decision=decision,
        long_axis=long_fit,
        short_axis=short_fit,
        scale_xy=scale_xy,
        footprint_modules=footprint_modules,
        failures=tuple(failures),
    )


def height_storeys(size_z_cm: float) -> float:
    """Storey count from measured height."""
    return max(1.0, round(size_z_cm / STOREY_CM, 2))


def floor_slab_height_ok(size_z_cm: float) -> bool:
    return abs(size_z_cm - FLOOR_T_CM) <= TOL_CM

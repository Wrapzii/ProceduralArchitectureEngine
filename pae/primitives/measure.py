"""Footprint / origin measurement checks against the MODULE contract."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM, TOL_CM, WALL_T_CM
from pae.primitives.apertures import get_profile, opening_slices
from pae.primitives.types import PrimitiveDescriptor

Vec3 = Tuple[float, float, float]


def arch_clear_opening_cm(
    profile_name: str,
    *,
    module_cm: float = MODULE_CM,
    storey_cm: float = STOREY_CM,
) -> Tuple[float, float, float]:
    """``(run_width_cm, spring_z_cm, apex_z_cm)`` for an arch / gate profile."""
    profile = get_profile(profile_name)
    run0, run1 = profile.opening_run_cm(module_cm)
    z0, z1 = profile.opening_z_cm(storey_cm)
    rise = profile.head_rise_cm(module_cm)
    return (run1 - run0, z0, z1 + rise)


def arch_clear_height_cm(profile_name: str, *, storey_cm: float = STOREY_CM) -> float:
    """Total vertical clear height including curved head."""
    _, spring, apex = arch_clear_opening_cm(profile_name, storey_cm=storey_cm)
    return apex - spring if apex > spring else 0.0


def monumental_arch_sane(
    profile_name: str,
    *,
    module_cm: float = MODULE_CM,
    storey_cm: float = STOREY_CM,
    min_run_frac: float = 0.55,
    min_clear_frac: float = 0.72,
) -> List[str]:
    """Sanity band for monumental arches — not tiny stepped blobs."""
    profile = get_profile(profile_name)
    run_w, spring, apex = arch_clear_opening_cm(
        profile_name, module_cm=module_cm, storey_cm=storey_cm
    )
    errors: List[str] = []
    if run_w < module_cm * min_run_frac - TOL_CM:
        errors.append(
            f"{profile_name}: run {run_w:.1f} cm < {min_run_frac:.0%} of MODULE"
        )
    clear_h = apex - spring
    if clear_h < storey_cm * min_clear_frac - TOL_CM:
        errors.append(
            f"{profile_name}: clear height {clear_h:.1f} cm < "
            f"{min_clear_frac:.0%} of STOREY"
        )
    return errors


def arch_head_band_step_cm(
    profile_name: str,
    *,
    module_cm: float = MODULE_CM,
) -> float:
    """Max vertical height of one curved-head band — lower reads smoother."""
    profile = get_profile(profile_name)
    rise = profile.head_rise_cm(module_cm)
    if rise <= 0.0 or profile.head_bands <= 0:
        return 0.0
    return rise / profile.head_bands


def monumental_arch_mesh_smooth(
    profile_name: str,
    *,
    module_cm: float = MODULE_CM,
    max_band_step_cm: float = 8.0,
    min_head_bands: int = 24,
) -> List[str]:
    """Mesh smoothness band for monumental arches — not stepped block heads."""
    profile = get_profile(profile_name)
    errors: List[str] = []
    if profile.head_bands < min_head_bands:
        errors.append(
            f"{profile_name}: head_bands {profile.head_bands} < {min_head_bands}"
        )
    step = arch_head_band_step_cm(profile_name, module_cm=module_cm)
    if step > max_band_step_cm + TOL_CM:
        errors.append(
            f"{profile_name}: arch band step {step:.1f} cm > {max_band_step_cm:.1f} cm"
        )
    return errors


def arch_curve_max_deviation_cm(
    profile_name: str,
    *,
    module_cm: float = MODULE_CM,
    storey_cm: float = STOREY_CM,
) -> float:
    """Max run-axis gap between banded mesh and true head curve (cm)."""
    from pae.primitives.apertures import _head_half_width_at

    profile = get_profile(profile_name)
    rise = profile.head_rise_cm(module_cm)
    if rise <= 0.0:
        return 0.0
    run0, run1 = profile.opening_run_cm(module_cm)
    half = (run1 - run0) * 0.5
    z0, z1 = profile.opening_z_cm(storey_cm)
    spring_z = max(z0, z1 - rise)
    max_err = 0.0
    for z_band0, z_band1, s_run0, s_run1 in opening_slices(
        profile, module_cm=module_cm, storey_cm=storey_cm
    ):
        slice_half = (s_run1 - s_run0) * 0.5
        if slice_half >= half - 1e-3:
            continue
        t = min(1.0, max(0.0, (z_band1 - spring_z) / rise))
        expected = _head_half_width_at(profile, half, t)
        max_err = max(max_err, expected - slice_half)
    return max_err


def _axis_err(label: str, got: float, expected: float, tol: float) -> List[str]:
    if abs(got - expected) <= tol:
        return []
    return [f"{label}: got {got:.3f} cm, expected {expected:.3f} cm (±{tol} cm)"]


def footprint_contract_errors(
    desc: PrimitiveDescriptor,
    *,
    tol_cm: float = TOL_CM,
) -> List[str]:
    """Return human-readable failures if declared size drifts from MODULE contract."""
    errors: List[str] = []
    mx, my = desc.footprint_modules
    sx, sy, sz = desc.size_cm
    kind = desc.kind

    if mx < 1 or my < 1:
        errors.append(f"footprint_modules must be ≥ (1,1), got {(mx, my)}")

    if desc.origin == "min_corner" and not desc.rotates_about_center:
        errors.extend(
            _axis_err(f"{desc.id}.aabb_min.x", desc.aabb_min_cm[0], 0.0, tol_cm)
        )
        errors.extend(
            _axis_err(f"{desc.id}.aabb_min.y", desc.aabb_min_cm[1], 0.0, tol_cm)
        )
        errors.extend(
            _axis_err(f"{desc.id}.aabb_min.z", desc.aabb_min_cm[2], 0.0, tol_cm)
        )

    # Module-aligned XY extents by kind
    if kind == "wall":
        # Thin in X (wall thickness), long axis spans my modules along Y.
        errors.extend(_axis_err(f"{desc.id}.size.x (thickness)", sx, WALL_T_CM, tol_cm))
        errors.extend(
            _axis_err(f"{desc.id}.size.y (run)", sy, my * MODULE_CM, tol_cm)
        )
        errors.extend(
            _axis_err(
                f"{desc.id}.size.z (storey)",
                sz,
                desc.height_storeys * STOREY_CM,
                tol_cm,
            )
        )
    elif kind in ("floor", "plinth"):
        errors.extend(_axis_err(f"{desc.id}.size.x", sx, mx * MODULE_CM, tol_cm))
        errors.extend(_axis_err(f"{desc.id}.size.y", sy, my * MODULE_CM, tol_cm))
        errors.extend(_axis_err(f"{desc.id}.size.z", sz, FLOOR_T_CM, tol_cm))
    elif kind == "stair":
        errors.extend(_axis_err(f"{desc.id}.size.x", sx, mx * MODULE_CM, tol_cm))
        errors.extend(_axis_err(f"{desc.id}.size.y", sy, my * MODULE_CM, tol_cm))
        errors.extend(
            _axis_err(
                f"{desc.id}.size.z",
                sz,
                desc.height_storeys * STOREY_CM,
                tol_cm,
            )
        )
    elif kind in ("tower_arc", "tower_crown", "tower_cap"):
        # Centred tower kit: XY AABB matches footprint modules.
        errors.extend(_axis_err(f"{desc.id}.size.x", sx, mx * MODULE_CM, tol_cm))
        errors.extend(_axis_err(f"{desc.id}.size.y", sy, my * MODULE_CM, tol_cm))
    elif kind == "battlement":
        errors.extend(_axis_err(f"{desc.id}.size.x (thickness)", sx, WALL_T_CM, tol_cm))
        errors.extend(
            _axis_err(f"{desc.id}.size.y (run)", sy, my * MODULE_CM, tol_cm)
        )
    elif kind == "roof":
        errors.extend(_axis_err(f"{desc.id}.size.x", sx, mx * MODULE_CM, tol_cm))
        errors.extend(_axis_err(f"{desc.id}.size.y", sy, my * MODULE_CM, tol_cm))
    elif kind == "barrier":
        # Barriers tile on the same boundary lines as walls (§2.3): full module run and
        # contract-locked height. Thickness is free below WALL_T — a railing is
        # deliberately thinner than a wall, and forcing WALL_T would make it read as one.
        errors.extend(
            _axis_err(f"{desc.id}.size.y (run)", sy, my * MODULE_CM, tol_cm)
        )
        errors.extend(
            _axis_err(
                f"{desc.id}.size.z",
                sz,
                desc.height_storeys * STOREY_CM,
                tol_cm,
            )
        )
        if sx > WALL_T_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.x: barrier thickness {sx:.1f} cm exceeds "
                f"WALL_T {WALL_T_CM:.1f} cm"
            )
    elif kind == "band":
        # Banding is applied TO a face, so only its run is grid-locked. Its projection and
        # its height are free by design — a plinth course and a wall plate are different
        # depths, and a vertical member is a full storey while a course is a few percent.
        if sy > my * MODULE_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.y (run): {sy:.1f} cm overflows its "
                f"{my}-module bay ({my * MODULE_CM:.1f} cm)"
            )
        if "coping" in desc.tags:
            # Coping caps a wall head and OVERSAILS BOTH FACES, so it is wider than the
            # wall by design. It must be wider — a coping flush with the wall sheds water
            # down the face — but not wide enough to read as a projecting cornice.
            if not WALL_T_CM < sx <= WALL_T_CM * 1.5:
                errors.append(
                    f"{desc.id}.size.x: coping width {sx:.1f} cm must oversail the wall "
                    f"({WALL_T_CM:.1f} cm) by a margin, up to 1.5x"
                )
        elif sx > WALL_T_CM:
            errors.append(
                f"{desc.id}.size.x: projection {sx:.1f} cm exceeds a wall thickness "
                f"({WALL_T_CM:.1f} cm) — banding articulates a face, it is not a wall"
            )
        if sz > STOREY_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.z: {sz:.1f} cm is taller than a storey"
            )
    elif kind == "surface":
        # Ground surfaces tile the grid: full module square, thin. Kerbs are a strip, so
        # X is allowed to be narrower than a module.
        errors.extend(_axis_err(f"{desc.id}.size.y", sy, my * MODULE_CM, tol_cm))
        if sx > mx * MODULE_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.x: {sx:.1f} cm overflows its "
                f"{mx}-module footprint ({mx * MODULE_CM:.1f} cm)"
            )
        # Flat surfaces stay slab-thin; a step run is a surface that deliberately climbs,
        # so it is measured against its declared storey fraction instead.
        if "steps" in desc.tags:
            errors.extend(
                _axis_err(
                    f"{desc.id}.size.z",
                    sz,
                    desc.height_storeys * STOREY_CM,
                    tol_cm,
                )
            )
        elif sz > FLOOR_T_CM * 2.0:
            errors.append(
                f"{desc.id}.size.z: surface {sz:.1f} cm is thicker than a floor slab"
            )
    elif kind in ("column", "roofline", "light_anchor"):
        # Sub-bay pieces must FIT their declared footprint but need not fill it: a chimney
        # is not a module wide, and padding it to one would put a 4 m box around it.
        # Light anchors are tiny centred markers — same sub-bay rules.
        # Height stays contract-locked so storey stacking still works.
        errors.extend(
            _axis_err(
                f"{desc.id}.size.z",
                sz,
                desc.height_storeys * STOREY_CM,
                tol_cm,
            )
        )
        if sx > mx * MODULE_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.x: {sx:.1f} cm overflows its "
                f"{mx}-module footprint ({mx * MODULE_CM:.1f} cm)"
            )
        if sy > my * MODULE_CM + tol_cm:
            errors.append(
                f"{desc.id}.size.y: {sy:.1f} cm overflows its "
                f"{my}-module footprint ({my * MODULE_CM:.1f} cm)"
            )
    else:
        errors.append(f"{desc.id}: unknown kind {kind!r} for footprint check")

    return errors


def measurement_rows(
    descriptors: Sequence[PrimitiveDescriptor],
    *,
    tol_cm: float = TOL_CM,
) -> List[dict]:
    """Compact rows for Docs/PRIMITIVE_MEASUREMENTS.md and tests."""
    rows = []
    for d in descriptors:
        errs = footprint_contract_errors(d, tol_cm=tol_cm)
        rows.append(
            {
                "id": d.id,
                "kind": d.kind,
                "footprint_modules": d.footprint_modules,
                "size_cm": d.size_cm,
                "aabb_min_cm": d.aabb_min_cm,
                "origin": d.origin,
                "rotates_about_center": d.rotates_about_center,
                "height_storeys": d.height_storeys,
                "ok": len(errs) == 0,
                "errors": errs,
            }
        )
    return rows


def measurement_table_markdown(
    descriptors: Iterable[PrimitiveDescriptor],
    *,
    tol_cm: float = TOL_CM,
) -> str:
    rows = measurement_rows(list(descriptors), tol_cm=tol_cm)
    lines = [
        "# PAE primitive measurement table",
        "",
        f"Tolerance: **{tol_cm} cm**. All dimensions from `pae/contract.py`.",
        "",
        "| id | kind | footprint (mod) | size_cm (X x Y x Z) | aabb_min | origin | centered | ok |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        sx, sy, sz = r["size_cm"]
        ax, ay, az = r["aabb_min_cm"]
        mx, my = r["footprint_modules"]
        lines.append(
            f"| `{r['id']}` | {r['kind']} | {mx}x{my} | "
            f"{sx:.1f}x{sy:.1f}x{sz:.1f} | "
            f"({ax:.1f},{ay:.1f},{az:.1f}) | {r['origin']} | "
            f"{r['rotates_about_center']} | {'yes' if r['ok'] else 'NO'} |"
        )
    lines.append("")
    failed = [r for r in rows if not r["ok"]]
    if failed:
        lines.append("## Failures")
        lines.append("")
        for r in failed:
            for e in r["errors"]:
                lines.append(f"- `{r['id']}`: {e}")
        lines.append("")
    else:
        lines.append("All pieces within tolerance.")
        lines.append("")
    return "\n".join(lines)

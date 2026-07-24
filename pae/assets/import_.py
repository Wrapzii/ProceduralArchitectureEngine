"""Asset import & measure (§4.3) — WP-2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from pae.assets.db import Asset, AssetDB, Socket
from pae.assets.fit import evaluate_footprint_fit, height_storeys
from pae.assets.sockets import GeometryDescriptor, propose_sockets
from pae.report import Failure, Report


@dataclass(frozen=True)
class MeasuredAABB:
    """Pure-Python measured bounds — Blender optional."""

    min_corner: Tuple[float, float, float]
    max_corner: Tuple[float, float, float]

    @property
    def size_cm(self) -> Tuple[float, float, float]:
        mn = self.min_corner
        mx = self.max_corner
        return (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])


def size_cm_from_aabb(
    min_corner: Tuple[float, float, float],
    max_corner: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Measured bounding-box size (never trust declared dimensions)."""
    return MeasuredAABB(min_corner, max_corner).size_cm


def min_corner_origin_offset(
    min_corner: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Translation to move mesh origin to min corner (§2.1)."""
    return (-min_corner[0], -min_corner[1], -min_corner[2])


def normalize_to_min_corner(
    min_corner: Tuple[float, float, float],
    max_corner: Tuple[float, float, float],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return (new_min, new_max) after shifting origin to min corner."""
    offset = min_corner_origin_offset(min_corner)
    new_min = (0.0, 0.0, 0.0)
    new_max = (
        max_corner[0] + offset[0],
        max_corner[1] + offset[1],
        max_corner[2] + offset[2],
    )
    return new_min, new_max


def center_origin_offset(
    min_corner: Tuple[float, float, float],
    max_corner: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Translation to move origin to bbox centre (rotates_about_center pieces)."""
    cx = (min_corner[0] + max_corner[0]) * 0.5
    cy = (min_corner[1] + max_corner[1]) * 0.5
    cz = (min_corner[2] + max_corner[2]) * 0.5
    return (-cx, -cy, -cz)


@dataclass
class ImportResult:
    asset: Optional[Asset]
    report: Report
    fit_decision: str = "reject"
    scale_xy: Tuple[float, float] = (1.0, 1.0)
    measured_size_cm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    proposed_sockets: List[Socket] = field(default_factory=list)


def import_asset_measured(
    asset_id: str,
    path: str,
    kind: str,
    measured: MeasuredAABB,
    *,
    tags: Optional[Set[str]] = None,
    rotates_about_center: bool = False,
    sockets: Optional[List[Socket]] = None,
    db: Optional[AssetDB] = None,
    allow_scale: bool = True,
) -> ImportResult:
    """Import pipeline using measured AABB (§4.3) — no Blender required."""
    tags = set(tags or ())
    failures: List[Failure] = []

    if rotates_about_center:
        origin = "center"
        _nmin, size = (0.0, 0.0, 0.0), measured.size_cm
    else:
        origin = "min_corner"
        _nmin, _nmax = normalize_to_min_corner(measured.min_corner, measured.max_corner)
        size = _nmax

    fit = evaluate_footprint_fit(size, kind)
    proposed = sockets or propose_sockets(
        GeometryDescriptor(size_cm=size, kind=kind, rotates_about_center=rotates_about_center)
    )

    if kind == "wall":
        names = {s.name for s in proposed}
        if not {"end_a", "end_b"}.issubset(names):
            failures.append(
                Failure(
                    check="wall_sockets",
                    message="wall assets must declare end_a and end_b",
                    critical=True,
                )
            )

    if fit.decision == "reject":
        for msg in fit.failures:
            failures.append(Failure(check="snap_fit", message=msg, critical=True))
        failures.append(
            Failure(
                check="snap_fit",
                message=(
                    f"footprint {size[0]:.1f}×{size[1]:.1f} cm does not fit "
                    f"{fit.footprint_modules} modules — re-author required"
                ),
                critical=True,
            )
        )
        report = Report.from_failures(failures)
        return ImportResult(
            asset=None,
            report=report,
            fit_decision="reject",
            scale_xy=fit.scale_xy,
            measured_size_cm=size,
            proposed_sockets=proposed,
        )

    if fit.decision == "scale" and not allow_scale:
        failures.append(
            Failure(
                check="snap_fit",
                message="footprint requires stretch beyond tolerance; scaling disabled",
                critical=True,
            )
        )
        report = Report.from_failures(failures)
        return ImportResult(
            asset=None,
            report=report,
            fit_decision="scale",
            scale_xy=fit.scale_xy,
            measured_size_cm=size,
            proposed_sockets=proposed,
        )

    if fit.decision == "scale":
        failures.append(
            Failure(
                check="snap_fit",
                message=(
                    f"footprint stretched to fit modules "
                    f"(scale_xy={fit.scale_xy[0]:.4f}, {fit.scale_xy[1]:.4f})"
                ),
                critical=False,
            )
        )

    asset = Asset(
        id=asset_id,
        path=path,
        kind=kind,
        footprint_modules=fit.footprint_modules,
        height_storeys=height_storeys(size[2]),
        size_cm=size,
        origin=origin,
        rotates_about_center=rotates_about_center,
        sockets=proposed,
        tags=tags,
    )

    if db is not None:
        db.upsert_asset(asset)

    report = Report.from_failures(failures)
    return ImportResult(
        asset=asset,
        report=report,
        fit_decision=fit.decision,
        scale_xy=fit.scale_xy,
        measured_size_cm=size,
        proposed_sockets=proposed,
    )


def import_asset(
    asset_id: str,
    path: str,
    kind: str,
    *,
    measured_aabb: Optional[MeasuredAABB] = None,
    min_corner: Optional[Tuple[float, float, float]] = None,
    max_corner: Optional[Tuple[float, float, float]] = None,
    tags: Optional[Set[str]] = None,
    rotates_about_center: bool = False,
    db: Optional[AssetDB] = None,
    allow_scale: bool = True,
) -> ImportResult:
    """Public import entry — requires measured geometry (never declared size)."""
    if measured_aabb is not None:
        measured = measured_aabb
    elif min_corner is not None and max_corner is not None:
        measured = MeasuredAABB(min_corner, max_corner)
    else:
        report = Report.from_failures(
            [
                Failure(
                    check="measure",
                    message="import requires measured AABB; declared size is not trusted",
                    critical=True,
                )
            ]
        )
        return ImportResult(asset=None, report=report, fit_decision="reject")

    return import_asset_measured(
        asset_id,
        path,
        kind,
        measured,
        tags=tags,
        rotates_about_center=rotates_about_center,
        db=db,
        allow_scale=allow_scale,
    )

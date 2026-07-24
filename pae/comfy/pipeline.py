"""ComfyUI decorative asset ingest pipeline (§9.2).

```
ComfyUI ──▶ GLB ──▶ normalise ──▶ measure ──▶ auto-socket
        ──▶ human confirm ──▶ assets.db
```

Pure-Python path accepts `MeasuredAABB` / `GlbMetadata` so tests run without
Comfy or Blender. Structural kinds are rejected here; call into `pae.assets`
for measure helpers, socket types, fit height/modules, and DB writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from pae.assets.db import Asset, AssetDB
from pae.assets.fit import height_storeys, module_count
from pae.assets.import_ import MeasuredAABB, import_asset_measured
from pae.comfy.kinds import (
    is_decorative,
    is_structural,
    normalize_kind,
    reject_structural_message,
)
from pae.comfy.materials import DEFAULT_MATERIAL_POLICY, MaterialPolicy, TextureGuide
from pae.comfy.normalize import (
    GlbMetadata,
    NormalizeResult,
    normalize_glb_metadata,
    normalize_measured,
)
from pae.comfy.sockets_decor import propose_decorative_sockets
from pae.report import Failure, Report

TAG_COMFY = "comfy"
TAG_NEEDS_CONFIRM = "needs_human_confirm"
TAG_CONFIRMED = "human_confirmed"
TAG_TEXTURE_GUIDE = "texture_guide_only"


@dataclass
class ComfyIngestArtifact:
    """Pending or committed decorative asset from the Comfy path."""

    asset_id: str
    path: str
    kind: str
    measured_size_cm: Tuple[float, float, float]
    normalize: Optional[NormalizeResult] = None
    proposed_sockets: List = field(default_factory=list)
    human_confirmed: bool = False
    material_policy: MaterialPolicy = field(default_factory=lambda: DEFAULT_MATERIAL_POLICY)
    asset: Optional[Asset] = None
    written_to_db: bool = False


@dataclass
class ComfyIngestResult:
    artifact: Optional[ComfyIngestArtifact]
    report: Report


def _footprint_modules_decorative(size_cm: Tuple[float, float, float]) -> Tuple[int, int]:
    """Approx module span for placement hints — decorative precision is irrelevant."""
    sx, sy, _ = size_cm
    return (module_count(sx), module_count(sy))


def _build_tags(
    kind: str,
    extra: Optional[Set[str]],
    *,
    human_confirmed: bool,
    has_texture_guide: bool,
) -> Set[str]:
    tags: Set[str] = {TAG_COMFY, "decorative", normalize_kind(kind)}
    if extra:
        tags |= set(extra)
    if human_confirmed:
        tags.add(TAG_CONFIRMED)
    else:
        tags.add(TAG_NEEDS_CONFIRM)
    if has_texture_guide:
        tags.add(TAG_TEXTURE_GUIDE)
    return tags


def _asset_from_measured(
    asset_id: str,
    path: str,
    kind: str,
    size_cm: Tuple[float, float, float],
    sockets: List,
    tags: Set[str],
) -> Asset:
    return Asset(
        id=asset_id,
        path=path,
        kind=normalize_kind(kind),
        footprint_modules=_footprint_modules_decorative(size_cm),
        height_storeys=height_storeys(size_cm[2]),
        size_cm=size_cm,
        origin="min_corner",
        rotates_about_center=False,
        sockets=list(sockets),
        tags=tags,
        lod=None,
    )


def ingest_decorative(
    asset_id: str,
    path: str,
    kind: str,
    *,
    measured: Optional[MeasuredAABB] = None,
    glb: Optional[GlbMetadata] = None,
    tags: Optional[Set[str]] = None,
    human_confirmed: bool = False,
    db: Optional[AssetDB] = None,
    material_policy: Optional[MaterialPolicy] = None,
    texture_path: Optional[str] = None,
) -> ComfyIngestResult:
    """Decorative ingest: normalise → measure → auto-socket → optional DB write.

    Requires `measured` or `glb.measured`. Declared sizes are never trusted.
    Structural kinds always fail. DB write only when `human_confirmed` and `db`
    is provided.
    """
    failures: List[Failure] = []
    kind_n = normalize_kind(kind)
    policy = material_policy or DEFAULT_MATERIAL_POLICY

    if is_structural(kind_n):
        failures.append(
            Failure(
                check="comfy_structural_reject",
                message=reject_structural_message(kind_n),
                critical=True,
            )
        )
        return ComfyIngestResult(artifact=None, report=Report.from_failures(failures))

    if not is_decorative(kind_n):
        failures.append(
            Failure(
                check="comfy_kind",
                message=(
                    f"kind '{kind_n}' is not a recognised decorative Comfy kind; "
                    f"refusing unknown class on this path"
                ),
                critical=True,
            )
        )
        return ComfyIngestResult(artifact=None, report=Report.from_failures(failures))

    if glb is not None:
        measured_aabb = glb.measured
        norm = normalize_glb_metadata(glb)
        tex = texture_path or glb.texture_path
    elif measured is not None:
        measured_aabb = measured
        norm = normalize_measured(measured)
        tex = texture_path
    else:
        failures.append(
            Failure(
                check="measure",
                message="Comfy ingest requires MeasuredAABB or GlbMetadata.measured",
                critical=True,
            )
        )
        return ComfyIngestResult(artifact=None, report=Report.from_failures(failures))

    size = norm.size_cm
    if min(size) <= 0.0:
        failures.append(
            Failure(
                check="measure",
                message=f"measured size must be positive, got {size}",
                critical=True,
            )
        )
        return ComfyIngestResult(artifact=None, report=Report.from_failures(failures))

    # Call into assets import helpers (do not trust declared size; measure path).
    # Decorative precision is irrelevant — we do not gate on snap_fit reject.
    # Still exercise import_asset_measured for socket/origin consistency when it
    # accepts; otherwise build Asset from measured + decorative sockets.
    probe = import_asset_measured(
        asset_id,
        path,
        kind_n,
        MeasuredAABB(norm.min_corner, norm.max_corner),
        tags=_build_tags(
            kind_n,
            tags,
            human_confirmed=human_confirmed,
            has_texture_guide=bool(tex) or policy.generated_texture_is_guide_only,
        ),
        db=None,
        allow_scale=True,
    )

    sockets = propose_decorative_sockets(size, kind_n)
    if probe.proposed_sockets:
        # Prefer assets proposals when present; keep decorative base if missing.
        names = {s.name for s in probe.proposed_sockets}
        sockets = list(probe.proposed_sockets)
        for s in propose_decorative_sockets(size, kind_n):
            if s.name not in names:
                sockets.append(s)

    if tex:
        policy = MaterialPolicy(
            engine_authored=policy.engine_authored,
            generated_texture_is_guide_only=True,
            prefer_triplanar_for_kit=policy.prefer_triplanar_for_kit,
            texture_guide=TextureGuide(path=tex),
            policy_version=policy.policy_version,
        )

    tag_set = _build_tags(
        kind_n,
        tags,
        human_confirmed=human_confirmed,
        has_texture_guide=policy.generated_texture_is_guide_only,
    )

    asset = _asset_from_measured(asset_id, path, kind_n, size, sockets, tag_set)
    written = False

    if not human_confirmed:
        failures.append(
            Failure(
                check="human_confirm",
                message="asset pending human socket/material confirm — not written to DB",
                critical=False,
            )
        )
    elif db is None:
        failures.append(
            Failure(
                check="db",
                message="human_confirmed=True but no AssetDB provided — asset not persisted",
                critical=False,
            )
        )
    else:
        db.upsert_asset(asset)
        written = True

    artifact = ComfyIngestArtifact(
        asset_id=asset_id,
        path=path,
        kind=kind_n,
        measured_size_cm=size,
        normalize=norm,
        proposed_sockets=sockets,
        human_confirmed=human_confirmed,
        material_policy=policy,
        asset=asset,
        written_to_db=written,
    )
    return ComfyIngestResult(artifact=artifact, report=Report.from_failures(failures))


def confirm_decorative(
    artifact: ComfyIngestArtifact,
    db: AssetDB,
    *,
    sockets: Optional[List] = None,
) -> ComfyIngestResult:
    """Human confirm step: optionally replace sockets, then write assets.db."""
    if artifact.asset is None:
        return ComfyIngestResult(
            artifact=artifact,
            report=Report.from_failures(
                [
                    Failure(
                        check="confirm",
                        message="nothing to confirm — ingest produced no asset",
                        critical=True,
                    )
                ]
            ),
        )

    sock = list(sockets) if sockets is not None else list(artifact.proposed_sockets)
    tags = set(artifact.asset.tags)
    tags.discard(TAG_NEEDS_CONFIRM)
    tags.add(TAG_CONFIRMED)

    asset = Asset(
        id=artifact.asset.id,
        path=artifact.asset.path,
        kind=artifact.asset.kind,
        footprint_modules=artifact.asset.footprint_modules,
        height_storeys=artifact.asset.height_storeys,
        size_cm=artifact.asset.size_cm,
        origin=artifact.asset.origin,
        rotates_about_center=artifact.asset.rotates_about_center,
        sockets=sock,
        tags=tags,
        lod=artifact.asset.lod,
    )
    db.upsert_asset(asset)

    out = ComfyIngestArtifact(
        asset_id=artifact.asset_id,
        path=artifact.path,
        kind=artifact.kind,
        measured_size_cm=artifact.measured_size_cm,
        normalize=artifact.normalize,
        proposed_sockets=sock,
        human_confirmed=True,
        material_policy=artifact.material_policy,
        asset=asset,
        written_to_db=True,
    )
    return ComfyIngestResult(artifact=out, report=Report.from_failures([]))

"""Phase 1.3 — grand entrance ensemble expander (greybox stub).

A grand entrance is a *composition*: arched door leaf, exterior steps, and either
flanking columns/pilasters or twin interior stair flights. One declarative
``EntranceSpec(ensemble=True)`` expands into tagged pieces; existence checks
assert those pieces actually landed (VALIDATION_HANDBOOK §2 Q7).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.boundary import FACE_OUTWARD_YAW, outward_offset_cm, rotation_offset_cm
from pae.existence import entrance_role_tag, is_door_or_gate_asset
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure
from pae.spec import EntranceSpec

Cell = Tuple[int, int]

ENSEMBLE_TAG = "entrance_ensemble"
ENSEMBLE_ARCH_TAG = "ensemble_arch"
ENSEMBLE_STEPS_TAG = "ensemble_steps"
ENSEMBLE_COLUMN_TAG = "ensemble_column"
ENSEMBLE_STAIR_TAG = "ensemble_stair"

# Greybox kit ids — prefer working stubs over perfect mesh.
_STEPS_ASSET = "steps_external"
_COLUMN_ASSET = "pilaster"
_TWIN_STAIR_ASSET = "stair_half"

_OUTWARD: Dict[str, Cell] = {
    "south": (0, -1),
    "north": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}
_ALONG: Dict[str, Cell] = {
    "south": (1, 0),
    "north": (1, 0),
    "west": (0, 1),
    "east": (0, 1),
}
_INWARD: Dict[str, Cell] = {
    "south": (0, 1),
    "north": (0, -1),
    "west": (1, 0),
    "east": (-1, 0),
}


def ensemble_role_tag(role: str) -> str:
    return f"ensemble_role_{role}"


def _perimeter_face(piece_id: str) -> Optional[str]:
    parts = piece_id.split("_")
    if len(parts) >= 3 and parts[0] == "wall" and parts[1] in _OUTWARD:
        return parts[1]
    return None


def _probe_from_wall_cell(cell: Cell, face: str) -> Cell:
    """Boundary-line wall cell → footprint door probe (§2.3)."""
    x, y = cell
    if face == "east":
        return (x - 1, y)
    if face == "north":
        return (x, y - 1)
    return cell


def _find_entrance_door(
    assembly: Assembly,
    role: str,
) -> Optional[SolidPlacement]:
    tag = entrance_role_tag(role)
    for p in assembly.placements:
        if tag in p.tags and is_door_or_gate_asset(p.asset_id):
            return p
    return None


def _make_placement(
    *,
    asset_id: str,
    cell: Cell,
    level: int,
    yaw: int,
    offset_cm: Tuple[float, float, float],
    suffix: str,
    role: str,
    part_tag: str,
) -> SolidPlacement:
    desc = catalog_by_id()[asset_id]
    cx, cy = cell
    return SolidPlacement(
        piece_id=f"ensemble_{role}_{suffix}_{level}_{cx}_{cy}",
        asset_id=asset_id,
        kind=desc.kind,
        cell=cell,
        level=level,
        yaw=yaw,
        offset_cm=offset_cm,
        size_cm=desc.size_cm,
        rotates_about_center=desc.rotates_about_center,
        # Do NOT stamp entrance_role_* on non-door pieces — that would trip
        # no_bare_aperture (Phase 1.5). Role linkage uses ensemble_role_* only.
        tags=desc.tags
        | frozenset({ENSEMBLE_TAG, part_tag, ensemble_role_tag(role)}),
    )


def _occupied_cells(assembly: Assembly, level: int = 0) -> Set[Cell]:
    """Rough occupancy: every placement cell at *level* (greybox, not covered_cells)."""
    return {p.cell for p in assembly.placements if p.level == level}


def _interior_cells(assembly: Assembly) -> Set[Cell]:
    """Cells with a floor slab at level 0 — walkable interior."""
    return {
        p.cell
        for p in assembly.placements
        if p.level == 0 and p.kind == "floor"
    }


def _free_interior_flanks(
    probe: Cell,
    face: str,
    interiors: Set[Cell],
    occupied_stairs: Set[Cell],
) -> Optional[Tuple[Cell, Cell]]:
    """Pick two free interior cells flanking the entrance axis (left, right)."""
    ix, iy = _INWARD[face]
    ax, ay = _ALONG[face]
    # Prefer one bay in, then scan deeper if the default stair well blocks a flank.
    for depth in (1, 2, 3):
        base = (probe[0] + ix * depth, probe[1] + iy * depth)
        left = (base[0] - ax, base[1] - ay)
        right = (base[0] + ax, base[1] + ay)
        if (
            left in interiors
            and right in interiors
            and left not in occupied_stairs
            and right not in occupied_stairs
            and left != right
        ):
            return left, right
        # Asymmetric fallback: both on the free side, still inward of the door.
        for side in (-1, 1):
            a = (base[0] + ax * side, base[1] + ay * side)
            b = (base[0] + ax * side * 2, base[1] + ay * side * 2)
            if (
                a in interiors
                and b in interiors
                and a not in occupied_stairs
                and b not in occupied_stairs
            ):
                return a, b
    return None


def expand_entrance_ensembles(
    assembly: Assembly,
    entrances: Sequence[EntranceSpec],
    *,
    storeys: int = 1,
) -> Tuple[Assembly, List[Failure]]:
    """Append greybox ensemble pieces for every ``EntranceSpec(ensemble=True)``.

    Emits:
      * exterior ``steps_external`` (always)
      * flanking ``pilaster`` pair on the facade (always when cells free)
      * twin interior ``stair_half`` when ``storeys >= 2`` and flank interiors exist

    Does **not** replace the door/gate leaf — Phase 1.5 ``no_bare_aperture`` stays intact.
    """
    wanted = [e for e in entrances if e.ensemble]
    if not wanted:
        return assembly, []

    catalog = catalog_by_id()
    for aid in (_STEPS_ASSET, _COLUMN_ASSET, _TWIN_STAIR_ASSET):
        if aid not in catalog:
            return assembly, [
                Failure(
                    check="entrance_ensemble",
                    message=f"ensemble kit missing primitive {aid!r}",
                    world_xyz=None,
                    critical=True,
                )
            ]

    extra: List[SolidPlacement] = []
    retagged: List[SolidPlacement] = []
    door_ids: Set[str] = set()
    failures: List[Failure] = []
    occupied = _occupied_cells(assembly, 0)
    interiors = _interior_cells(assembly)
    occupied_stairs = {
        p.cell for p in assembly.placements if p.level == 0 and p.kind == "stair"
    }

    for spec in wanted:
        door = _find_entrance_door(assembly, spec.role)
        if door is None:
            failures.append(
                Failure(
                    check="entrance_ensemble",
                    message=(
                        f"ensemble requested for role {spec.role!r} but no "
                        f"door/gate placement with {entrance_role_tag(spec.role)!r}"
                    ),
                    world_xyz=None,
                    critical=True,
                )
            )
            continue

        face = _perimeter_face(door.piece_id) or (spec.facade or "south")
        face = face.lower()
        if face not in _OUTWARD:
            face = "south"

        # Tag the arch leaf in-place (copy) so existence can see ensemble_arch.
        if door.piece_id not in door_ids:
            door_ids.add(door.piece_id)
            retagged.append(
                SolidPlacement(
                    piece_id=door.piece_id,
                    asset_id=door.asset_id,
                    kind=door.kind,
                    cell=door.cell,
                    level=door.level,
                    yaw=door.yaw,
                    offset_cm=door.offset_cm,
                    size_cm=door.size_cm,
                    rotates_about_center=door.rotates_about_center,
                    tags=door.tags
                    | frozenset({ENSEMBLE_TAG, ENSEMBLE_ARCH_TAG, ensemble_role_tag(spec.role)}),
                )
            )

        wall_cell = door.cell
        probe = _probe_from_wall_cell(wall_cell, face)
        ox, oy = _OUTWARD[face]
        ax, ay = _ALONG[face]

        # --- exterior steps (one bay out from the door) ---
        step_cell = (probe[0] + ox, probe[1] + oy)
        steps_desc = catalog[_STEPS_ASSET]
        # Steps rise toward the threshold: top near z=0 (site surface convention).
        extra.append(
            _make_placement(
                asset_id=_STEPS_ASSET,
                cell=step_cell,
                level=0,
                yaw=FACE_OUTWARD_YAW[face],
                offset_cm=(
                    *rotation_offset_cm(FACE_OUTWARD_YAW[face], steps_desc.size_cm),
                    -steps_desc.size_cm[2],
                ),
                suffix="steps",
                role=spec.role,
                part_tag=ENSEMBLE_STEPS_TAG,
            )
        )
        occupied.add(step_cell)

        # --- flanking columns / pilasters on the facade ---
        for side, label in ((-1, "col_l"), (1, "col_r")):
            flank_wall = (wall_cell[0] + ax * side, wall_cell[1] + ay * side)
            yaw, offset = outward_offset_cm(face, catalog[_COLUMN_ASSET].size_cm)
            extra.append(
                _make_placement(
                    asset_id=_COLUMN_ASSET,
                    cell=flank_wall,
                    level=0,
                    yaw=yaw,
                    offset_cm=offset,
                    suffix=label,
                    role=spec.role,
                    part_tag=ENSEMBLE_COLUMN_TAG,
                )
            )

        # --- twin interior stairs when a second storey exists and cells are free ---
        if storeys >= 2:
            flanks = _free_interior_flanks(probe, face, interiors, occupied_stairs)
            if flanks is not None:
                stair_desc = catalog[_TWIN_STAIR_ASSET]
                stair_yaw = FACE_OUTWARD_YAW[face]
                rx, ry = rotation_offset_cm(stair_yaw, stair_desc.size_cm)
                for sc, label in ((flanks[0], "stair_l"), (flanks[1], "stair_r")):
                    extra.append(
                        _make_placement(
                            asset_id=_TWIN_STAIR_ASSET,
                            cell=sc,
                            level=0,
                            yaw=stair_yaw,
                            offset_cm=(rx, ry, 0.0),
                            suffix=label,
                            role=spec.role,
                            part_tag=ENSEMBLE_STAIR_TAG,
                        )
                    )
                    occupied_stairs.add(sc)

    # Rebuild placements: replace retagged doors, append extras.
    by_id = {p.piece_id: p for p in assembly.placements}
    for p in retagged:
        by_id[p.piece_id] = p
    new_placements = list(by_id.values()) + extra

    return (
        Assembly(
            placements=new_placements,
            floor_plan=assembly.floor_plan,
            circulation=assembly.circulation,
            wall_runs=assembly.wall_runs,
            apertures=assembly.apertures,
            storeys=assembly.storeys,
            aperture_policy=assembly.aperture_policy,
            room_specs=list(assembly.room_specs),
        ),
        failures,
    )


def placed_ensemble_parts(assembly: Assembly, role: Optional[str] = None) -> Dict[str, int]:
    """Count ensemble part tags (optionally filtered to one role)."""
    counts = {
        ENSEMBLE_ARCH_TAG: 0,
        ENSEMBLE_STEPS_TAG: 0,
        ENSEMBLE_COLUMN_TAG: 0,
        ENSEMBLE_STAIR_TAG: 0,
    }
    role_tag = ensemble_role_tag(role) if role else None
    for p in assembly.placements:
        if ENSEMBLE_TAG not in p.tags:
            continue
        if role_tag is not None and role_tag not in p.tags:
            continue
        for part in counts:
            if part in p.tags:
                counts[part] += 1
    return counts


def check_entrance_ensemble_existence(
    entrances: Sequence[EntranceSpec],
    assembly: Assembly,
) -> List[Failure]:
    """Spec asked for an ensemble → arch + steps + (columns OR twin stairs) must exist.

    Handbook §2 Q7 (existence). Does not weaken ``no_bare_aperture`` — the arch part
    must still be a door/gate leaf.
    """
    failures: List[Failure] = []
    for spec in entrances:
        if not spec.ensemble:
            continue
        parts = placed_ensemble_parts(assembly, spec.role)
        missing: List[str] = []
        if parts[ENSEMBLE_ARCH_TAG] < 1:
            # Fallback: role-tagged door/gate still counts as the arch leaf.
            door = _find_entrance_door(assembly, spec.role)
            if door is None:
                missing.append("arch/door")
        if parts[ENSEMBLE_STEPS_TAG] < 1:
            missing.append("steps")
        has_columns = parts[ENSEMBLE_COLUMN_TAG] >= 2
        has_twin_stairs = parts[ENSEMBLE_STAIR_TAG] >= 2
        if not has_columns and not has_twin_stairs:
            missing.append("flanking_columns_or_twin_stairs")
        if missing:
            failures.append(
                Failure(
                    check="entrance_ensemble_existence",
                    message=(
                        f"entrance role {spec.role!r} ensemble=True missing "
                        f"{', '.join(missing)} "
                        f"(got arch={parts[ENSEMBLE_ARCH_TAG]} "
                        f"steps={parts[ENSEMBLE_STEPS_TAG]} "
                        f"cols={parts[ENSEMBLE_COLUMN_TAG]} "
                        f"stairs={parts[ENSEMBLE_STAIR_TAG]})"
                    ),
                    world_xyz=None,
                    critical=True,
                )
            )
        # Arch leaf must remain a door/gate (do not weaken 1.5).
        door = _find_entrance_door(assembly, spec.role)
        if door is not None and not is_door_or_gate_asset(door.asset_id):
            failures.append(
                Failure(
                    check="entrance_ensemble_existence",
                    message=(
                        f"ensemble arch for {spec.role!r} uses {door.asset_id!r} — "
                        "door/gate leaf required (Phase 1.5)"
                    ),
                    world_xyz=None,
                    piece_id=door.piece_id,
                    critical=True,
                )
            )
    return failures

"""Exterior approach stairs — per-gate flanking, height-mated to threshold.

User defect: causeway grid placed 3×N ``steps_grand`` (9–12 pieces) misaligned with
gate arches; each flight rose 175 cm to grade while L0 floor / gate sill is z≈0, so
the top tread overshot the building threshold.

Rules:
  * ONE flanking pair per gate arch (not a rectangular apron grid).
  * Top tread Z ≤ target floor / gate sill + TOL; bottom at exterior grade.
  * Never mate to kerb height alone — use L0 floor deck or gate opening sill.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    TOL_CM,
    floor_placement_z_cm,
    placement_world_aabb,
)
from pae.primitives.catalog import catalog_by_id
from pae.report import Failure
from pae.trim import covered_cells

Cell = Tuple[int, int]

APPROACH_ASSETS = frozenset({"steps_grand", "steps_external"})
APPROACH_TAGS = frozenset(
    {"grand_approach", "ensemble_steps", "steps", "approach", "causeway"}
)

_NEIGHBOURS = {
    "north": (0, 1),
    "south": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
}

CHECK_APPROACH_STAIR_HEIGHT_MATE = "approach_stair_height_mate"
CHECK_APPROACH_STAIR_ALIGNED_TO_GATE = "approach_stair_aligned_to_gate"


def is_approach_step(p: SolidPlacement) -> bool:
    if p.asset_id in APPROACH_ASSETS:
        return True
    if APPROACH_TAGS & set(p.tags) and p.kind in ("surface", "stair", "prop"):
        return True
    if "ensemble_steps" in p.tags:
        return True
    return False


def _placement_aabb(
    p: SolidPlacement,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    return placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _deck_cells_by_level(assembly: Assembly) -> Dict[int, Set[Cell]]:
    out: Dict[int, Set[Cell]] = {}
    for p in assembly.placements:
        if p.kind != "floor" or "hole" in p.asset_id:
            continue
        if "tower_deck" in p.tags or "tower_top" in p.tags:
            continue
        out.setdefault(p.level, set()).update(covered_cells(p))
    return out


def _is_gate_entrance_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall" or p.level != 0:
        return False
    if "door" not in p.asset_id and "gate" not in p.asset_id:
        return False
    if "gate" in p.asset_id:
        return True
    if "entrance_role_gate" in p.tags:
        return True
    if "entrance_role" in p.tags:
        return True
    return any(t.startswith("entrance_role") for t in p.tags)


def _wall_exterior_face(wall: SolidPlacement) -> str:
    bb_min, bb_max = _placement_aabb(wall)
    cx0, cy0 = wall.cell[0] * MODULE_CM, wall.cell[1] * MODULE_CM
    near = MODULE_CM * 0.5
    if (bb_max[0] - bb_min[0]) < (bb_max[1] - bb_min[1]):
        return "west" if (bb_min[0] - cx0) < near else "east"
    return "south" if (bb_min[1] - cy0) < near else "north"


def _flank_dirs(face: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    if face in ("south", "north"):
        return ((-1, 0), (1, 0))
    return ((0, -1), (0, 1))


def _gate_sill_z_cm(gate: SolidPlacement) -> Optional[float]:
    from pae.primitives.walls import aperture_opening_run_vertical

    desc = catalog_by_id().get(gate.asset_id)
    if desc is None or desc.aperture is None:
        return None
    _run0, _run1, z0, _z1 = aperture_opening_run_vertical(desc.aperture, gate.size_cm)
    bb_min, _bb_max = _placement_aabb(gate)
    return bb_min[2] + z0


def resolve_approach_mate_z(
    assembly: Assembly,
    gate: SolidPlacement,
) -> float:
    """World Z for the top tread — L0 floor top under the gate, capped by gate sill."""
    gate_cells = covered_cells(gate)
    floor_tops: List[float] = []
    for p in assembly.placements:
        if p.kind != "floor" or p.level != 0:
            continue
        if "hole" in p.asset_id:
            continue
        if not (covered_cells(p) & gate_cells):
            continue
        _fmin, fmax = _placement_aabb(p)
        floor_tops.append(fmax[2])

    if not floor_tops:
        floor_tops.append(floor_placement_z_cm(0) + FLOOR_T_CM)

    target = max(floor_tops)
    sill = _gate_sill_z_cm(gate)
    if sill is not None:
        target = min(target, sill)
    return target


def resolve_exterior_ground_z(assembly: Assembly, cell: Cell) -> float:
    """Exterior grade under an approach cell — walk/paving top, not kerb crown."""
    tops: List[float] = []
    for p in assembly.placements:
        if p.level != 0:
            continue
        if p.asset_id == "kerb_edge" or "kerb" in p.tags:
            continue
        if p.kind not in ("surface", "floor") and "walk" not in p.tags:
            if p.asset_id not in ("paving_cobble", "paving_flagstone", "sidewalk_slab"):
                continue
        if cell not in covered_cells(p):
            continue
        _smin, smax = _placement_aabb(p)
        tops.append(smax[2])
    return max(tops) if tops else 0.0


def mated_step_pose(
    asset_id: str,
    *,
    ground_z: float,
    target_z: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return (size_cm, offset_cm) so the step bottom sits on grade and top ≤ target."""
    desc = catalog_by_id()[asset_id]
    sx, sy, catalog_h = desc.size_cm
    rise = max(0.0, target_z - ground_z)
    rise = min(rise, catalog_h)
    if rise < TOL_CM:
        rise = TOL_CM
    return (sx, sy, rise), (0.0, 0.0, ground_z)


def expected_flank_cells(
    gate: SolidPlacement,
    *,
    clearance_bays: int = 1,
) -> Set[Cell]:
    """Cells where flanking approach steps should sit for one gate arch."""
    face = _wall_exterior_face(gate)
    dx, dy = _NEIGHBOURS[face]
    out: Set[Cell] = set()
    dist = max(1, clearance_bays + 1)
    for fx, fy in _flank_dirs(face):
        gx = gate.cell[0] + fx + dx * dist
        gy = gate.cell[1] + fy + dy * dist
        out.add((gx, gy))
    return out


def plan_gate_approach_steps(
    assembly: Assembly,
    *,
    steps_piece: str,
    clearance_bays: int = 1,
    building_name: Optional[str] = None,
    extra_tags: Optional[FrozenSet[str]] = None,
) -> List[SolidPlacement]:
    """One flanking composition per gate — height-mated, deduped by cell."""
    catalog = catalog_by_id()
    if steps_piece not in catalog:
        return []

    desc = catalog[steps_piece]
    decks = _deck_cells_by_level(assembly).get(0, set())
    drum_cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.kind in ("tower_arc", "tower_cap"):
            drum_cells |= covered_cells(p)

    tags = frozenset(extra_tags or ()) | desc.tags | frozenset({"trim", "approach"})
    out: List[SolidPlacement] = []
    seen: Set[Cell] = set()

    walls = sorted(
        (p for p in assembly.placements if _is_gate_entrance_wall(p)),
        key=lambda p: (p.cell, p.piece_id),
    )
    for wall in walls:
        if building_name and building_name not in wall.tags:
            if f"building:{building_name}" not in wall.tags:
                continue
        if wall.cell in drum_cells:
            continue
        is_gate = "gate" in wall.asset_id or "entrance_role_gate" in wall.tags
        if not is_gate and "entrance_role" not in wall.tags:
            if not any(t.startswith("entrance_role") for t in wall.tags):
                continue

        target_z = resolve_approach_mate_z(assembly, wall)
        face = _wall_exterior_face(wall)
        dx, dy = _NEIGHBOURS[face]
        flank_dirs = _flank_dirs(face)

        if is_gate:
            targets: List[Cell] = []
            dist = max(1, clearance_bays + 1)
            for fx, fy in flank_dirs:
                targets.append(
                    (wall.cell[0] + fx + dx * dist, wall.cell[1] + fy + dy * dist)
                )
        else:
            targets = [(wall.cell[0] + dx, wall.cell[1] + dy)]

        for tcell in targets:
            if tcell in seen or tcell in drum_cells or tcell in decks:
                continue
            ground_z = resolve_exterior_ground_z(assembly, tcell)
            size_cm, offset_cm = mated_step_pose(
                steps_piece, ground_z=ground_z, target_z=target_z
            )
            cx, cy = tcell
            out.append(
                SolidPlacement(
                    piece_id=f"approach_{steps_piece}_0_{cx}_{cy}_g{wall.cell[0]}_{wall.cell[1]}",
                    asset_id=steps_piece,
                    kind=desc.kind,
                    cell=tcell,
                    level=0,
                    yaw=0,
                    offset_cm=offset_cm,
                    size_cm=size_cm,
                    rotates_about_center=desc.rotates_about_center,
                    tags=tags
                    | frozenset(
                        {
                            f"approach_gate_{wall.cell[0]}_{wall.cell[1]}",
                        }
                    ),
                )
            )
            seen.add(tcell)
    return out


def strip_approach_steps(assembly: Assembly) -> Assembly:
    kept = [p for p in assembly.placements if not is_approach_step(p)]
    if len(kept) == len(assembly.placements):
        return assembly
    return replace(assembly, placements=kept)


def repair_approach_stairs(
    assembly: Assembly,
    *,
    steps_piece: str = "steps_grand",
    clearance_bays: int = 1,
    building_name: Optional[str] = None,
    extra_tags: Optional[FrozenSet[str]] = None,
) -> Assembly:
    """Autofix: remove duplicate/grid approach steps and replan per-gate flanking."""
    stripped = strip_approach_steps(assembly)
    extra = plan_gate_approach_steps(
        stripped,
        steps_piece=steps_piece,
        clearance_bays=clearance_bays,
        building_name=building_name,
        extra_tags=extra_tags,
    )
    if not extra:
        return stripped
    extra.sort(key=lambda p: (p.level, p.cell, p.asset_id, p.piece_id))
    return replace(
        stripped,
        placements=list(stripped.placements) + extra,
    )


def _gates_for_checks(
    assembly: Assembly,
) -> List[SolidPlacement]:
    return [
        p
        for p in assembly.placements
        if _is_gate_entrance_wall(p)
        and (
            "gate" in p.asset_id
            or "entrance_role_gate" in p.tags
            or "entrance_role" in p.tags
        )
    ]


def check_approach_stair_height_mate(assembly: Assembly) -> List[Failure]:
    """Critical: approach step top must not overshoot gate / L0 floor threshold."""
    steps = [p for p in assembly.placements if is_approach_step(p) and p.level == 0]
    if not steps:
        return []

    failures: List[Failure] = []
    gates = _gates_for_checks(assembly)
    gate_by_tag: Dict[str, SolidPlacement] = {}
    for g in gates:
        gate_by_tag[f"approach_gate_{g.cell[0]}_{g.cell[1]}"] = g

    for step in steps:
        gate: Optional[SolidPlacement] = None
        for t in step.tags:
            if t.startswith("approach_gate_"):
                gate = gate_by_tag.get(t)
                if gate is not None:
                    break
        if gate is None:
            for g in gates:
                expected = expected_flank_cells(g, clearance_bays=1)
                if step.cell in expected:
                    gate = g
                    break
        if gate is None:
            continue

        target_z = resolve_approach_mate_z(assembly, gate)
        _smin, smax = _placement_aabb(step)
        if smax[2] <= target_z + TOL_CM:
            continue
        failures.append(
            Failure(
                check=CHECK_APPROACH_STAIR_HEIGHT_MATE,
                message=(
                    f"approach step {step.piece_id} top z={smax[2]:.1f} cm overshoots "
                    f"gate/floor threshold z={target_z:.1f} cm at {gate.piece_id}"
                ),
                world_xyz=_centre(_smin, smax),
                piece_id=step.piece_id,
                critical=True,
            )
        )
    return failures


def check_approach_stair_aligned_to_gate(assembly: Assembly) -> List[Failure]:
    """Critical: at most one flanking pair per gate; cells must match expected flanks."""
    steps = [p for p in assembly.placements if is_approach_step(p) and p.level == 0]
    gates = [
        g
        for g in _gates_for_checks(assembly)
        if "gate" in g.asset_id or "entrance_role_gate" in g.tags
    ]
    if not steps or not gates:
        return []

    failures: List[Failure] = []
    all_expected: Set[Cell] = set()
    for gate in gates:
        all_expected |= expected_flank_cells(gate, clearance_bays=1)

    for step in steps:
        near_gate = any(
            abs(step.cell[0] - g.cell[0]) <= 3 and step.cell[1] < g.cell[1]
            for g in gates
        )
        if near_gate and step.cell not in all_expected:
            smin, smax = _placement_aabb(step)
            failures.append(
                Failure(
                    check=CHECK_APPROACH_STAIR_ALIGNED_TO_GATE,
                    message=(
                        f"approach step {step.piece_id} at {step.cell} is not aligned "
                        f"to a gate flank (expected one of {sorted(all_expected)})"
                    ),
                    world_xyz=_centre(smin, smax),
                    piece_id=step.piece_id,
                    critical=True,
                )
            )

    for gate in gates:
        expected = expected_flank_cells(gate, clearance_bays=1)
        matched = sum(1 for s in steps if s.cell in expected)
        if matched > 2:
            failures.append(
                Failure(
                    check=CHECK_APPROACH_STAIR_ALIGNED_TO_GATE,
                    message=(
                        f"gate {gate.piece_id} at {gate.cell} has {matched} "
                        f"approach steps in flank cells (expected ≤2)"
                    ),
                    world_xyz=None,
                    piece_id=gate.piece_id,
                    critical=True,
                )
            )
    return failures


__all__ = [
    "APPROACH_ASSETS",
    "APPROACH_TAGS",
    "CHECK_APPROACH_STAIR_HEIGHT_MATE",
    "CHECK_APPROACH_STAIR_ALIGNED_TO_GATE",
    "check_approach_stair_aligned_to_gate",
    "check_approach_stair_height_mate",
    "expected_flank_cells",
    "is_approach_step",
    "mated_step_pose",
    "plan_gate_approach_steps",
    "repair_approach_stairs",
    "resolve_approach_mate_z",
    "resolve_exterior_ground_z",
    "strip_approach_steps",
]

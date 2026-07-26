"""Build poisoned cloister stack from merged fortress geometry."""

from __future__ import annotations

from pae.assembly_types import Assembly, SolidPlacement
from pae.boundary import boundary_offset_cm
from pae.compound import (
    _courtyard_cells,
    _ground_cells,
    _NEIGHBOURS,
    _OPPOSITE,
    FACE_YAW,
    _strip_trim_tower_helixes,
    fortress_bailey_ranges,
    fortress_compound_connections,
    place_buildings,
    BuildingInstance,
)
from pae.compound_unify import unify_compound_assembly
from pae.pipeline import run_through_assemble
from pae.primitives import catalog_by_id
from pae.trim import trim, covered_cells
from pae.wall_faces import coplanar_wall_overlap


def cloister_stack_pair() -> tuple[SolidPlacement, SolidPlacement]:
    """Plain + arcade on the same west-cloister court bay (measured from merge)."""
    instances = []
    for style in fortress_bailey_ranges():
        _, _, assembled, _ = run_through_assemble(style.spec)
        trimmed, _ = trim(assembled, style.trim)
        instances.append(BuildingInstance(trimmed, style.cell_offset, style.name))
    merged, _ = place_buildings(instances)
    merged = _strip_trim_tower_helixes(merged)
    merged = unify_compound_assembly(
        merged, connections=fortress_compound_connections()
    )
    court = _courtyard_cells(_ground_cells(merged))
    desc = catalog_by_id()["wall_arcade"]
    for cx, cy in sorted(court):
        for face, (dx, dy) in _NEIGHBOURS.items():
            wc = (cx + dx, cy + dy)
            plain = next(
                (
                    p
                    for p in merged.placements
                    if p.kind == "wall"
                    and p.level == 0
                    and p.asset_id == "wall_plain"
                    and wc in covered_cells(p)
                    and "west_cloister" in p.piece_id
                ),
                None,
            )
            if plain is None:
                continue
            outward = _OPPOSITE[face]
            arcade = SolidPlacement(
                piece_id="poison_cloister_arcade",
                asset_id="wall_arcade",
                kind="wall",
                cell=wc,
                level=0,
                yaw=FACE_YAW[outward],
                offset_cm=boundary_offset_cm(outward, desc.size_cm),
                size_cm=desc.size_cm,
                rotates_about_center=desc.rotates_about_center,
                tags=desc.tags | frozenset({"trim", "cloister", "west_cloister"}),
            )
            if coplanar_wall_overlap(plain, arcade):
                return plain, arcade
    raise RuntimeError("no coplanar west-cloister court bay found")


def make_cloister_wall_stack_defect() -> Assembly:
    plain, arcade = cloister_stack_pair()
    return Assembly(placements=[plain, arcade])

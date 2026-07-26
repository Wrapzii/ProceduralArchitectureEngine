"""Structure identity — declared membership, party walls, circulation (Roadmap 10.1–10.2).

WHY: ``site.place_buildings`` tags each mass ``building:<name>`` so a street of six houses
does not report five freestanding groups. That same tag prevents expressing *one building
assembled from several placed masses* — a fortress bailey is one structure, not three
guardhouses. Membership must be **declared** (``structure:<name>``), never inferred from
adjacency.

Handbook §11d checks live here; ``validate.py`` wires them. ``freestanding`` partitions on
``structure:`` when present (T-102 — same commit as tagging).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Assembly, SolidPlacement
from pae.contract import FLOOR_T_CM, MODULE_CM, STOREY_CM
from pae.report import Failure
from pae.trim import covered_cells

Cell = Tuple[int, int]
StructureId = str  # bare name, e.g. "fortress_bailey"
MassId = str  # building:range or synthetic

CHECK_STRUCTURE_CONTIGUOUS = "structure_contiguous"
CHECK_STRUCTURE_PARTY_WALL = "structure_party_wall_open"
CHECK_STRUCTURE_REACHABLE = "structure_masses_reachable"
CHECK_STRUCTURE_SINGLE_STAIR = "structure_single_stair_core"

_STRUCTURE_PREFIX = "structure:"
_DELTAS = ((0, 1), (0, -1), (1, 0), (-1, 0))

_STAIR_ASSETS = frozenset(
    {
        "stair_straight",
        "stair_half",
        "stair_landing",
        "stair_wide",
        "stair_switchback",
        "stair_spiral_quarter",
    }
)

# Hall / monumental cores — not per-tower helix quarters (D3-1 vs @FORTRESS_SHELL_RESTORE).
_HALL_STAIR_CORE_ASSETS = frozenset(
    {
        "stair_straight",
        "stair_half",
        "stair_landing",
        "stair_wide",
        "stair_switchback",
    }
)

_CAMPUS_RANGE_IDS = frozenset(
    {"fortress_campus", "school_campus", "castle_curtain", "_default"}
)


def structure_tag(name: str) -> str:
    """Canonical ``structure:<name>`` tag."""
    return f"{_STRUCTURE_PREFIX}{name}"


def structure_id_from_tag(tag: str) -> Optional[str]:
    if tag.startswith(_STRUCTURE_PREFIX):
        return tag[len(_STRUCTURE_PREFIX) :]
    return None


def structure_ids_on(p: SolidPlacement) -> Set[str]:
    return {t for t in p.tags if t.startswith(_STRUCTURE_PREFIX)}


def partition_key(p: SolidPlacement) -> str:
    """Island / freestanding partition key — structure when declared, else building."""
    st = next((t for t in p.tags if t.startswith(_STRUCTURE_PREFIX)), "")
    if st:
        return st
    return next((t for t in p.tags if t.startswith("building:")), "")


def apply_structure_tags(assembly: Assembly, structure_id: str) -> Assembly:
    """Stamp ``structure:<id>`` on every placement (idempotent)."""
    if not structure_id:
        return assembly
    tag = structure_tag(structure_id)
    new_placements: List[SolidPlacement] = []
    changed = False
    for p in assembly.placements:
        if tag in p.tags:
            new_placements.append(p)
            continue
        changed = True
        new_placements.append(
            SolidPlacement(
                piece_id=p.piece_id,
                asset_id=p.asset_id,
                kind=p.kind,
                cell=p.cell,
                level=p.level,
                yaw=p.yaw,
                offset_cm=p.offset_cm,
                size_cm=p.size_cm,
                rotates_about_center=p.rotates_about_center,
                tags=p.tags | frozenset({tag}),
            )
        )
    if not changed:
        return assembly
    return Assembly(
        placements=new_placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def has_structure_tags(assembly: Assembly) -> bool:
    return any(structure_ids_on(p) for p in assembly.placements)


def _collect_known_ranges(assembly: Assembly) -> Set[str]:
    from pae.compound_unify import collect_compound_range_names

    return collect_compound_range_names(assembly)


def _mass_id(p: SolidPlacement, known_ranges: Set[str]) -> MassId:
    """Identity mass for structure checks — honour compound merge retags."""
    building_tags = sorted(t for t in p.tags if t.startswith("building:"))
    for t in building_tags:
        rn = t.replace("building:", "")
        if rn in _CAMPUS_RANGE_IDS or rn.endswith("_campus"):
            return t
    for t in building_tags:
        rn = t.replace("building:", "")
        if rn not in _CAMPUS_RANGE_IDS and not rn.endswith("_campus"):
            return t
    for t in p.tags:
        if t in known_ranges:
            return f"building:{t}"
    return building_tags[0] if building_tags else "building:_default"


def _mass_matches_primary(p: SolidPlacement, primary: str, known_ranges: Set[str]) -> bool:
    if not primary:
        return False
    primary_bid = f"building:{primary}"
    mid = _mass_id(p, known_ranges)
    if mid == primary_bid:
        return True
    return primary in p.tags


def _floor_footprint_by_mass(
    assembly: Assembly, structure: str
) -> Dict[MassId, Set[Cell]]:
    """L0 walkable floor cells per mass within one structure."""
    known = _collect_known_ranges(assembly)
    out: Dict[MassId, Set[Cell]] = defaultdict(set)
    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        if structure not in structure_ids_on(p):
            continue
        out[_mass_id(p, known)].update(covered_cells(p))
    return {k: v for k, v in out.items() if v}


def _structure_mass_footprints(
    assembly: Assembly, structure: str
) -> Dict[MassId, Set[Cell]]:
    """L0 walkable footprints per mass — ranges split into body/drum when needed (T-105).

    Range–range interfaces use compound range masses. Range–drum interfaces within one
    range split ``building:foo`` into ``building:foo:body`` and ``building:foo:drum``
    so party-wall checks and repair use one mechanism for both.

    Uses bare range instance names (``west_curtain``, ``north_keep``, …) so a merged
    ``building:fortress_campus`` retag does not collapse the whole bailey into one
    body/drum pair.
    """
    st = structure if structure.startswith(_STRUCTURE_PREFIX) else structure_tag(structure)
    known = _collect_known_ranges(assembly)
    by_range: Dict[str, Set[Cell]] = defaultdict(set)
    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        if st not in structure_ids_on(p):
            continue
        range_names = _placement_range_names(p)
        if not range_names:
            mid = _mass_id(p, known)
            rn = _mass_name_from_id(mid)
            if rn and rn not in _CAMPUS_RANGE_IDS:
                range_names = {rn}
        for rn in range_names:
            if rn in _CAMPUS_RANGE_IDS:
                continue
            by_range[rn].update(covered_cells(p))

    extended: Dict[MassId, Set[Cell]] = {}
    for rn, floor_cells in by_range.items():
        mass_id = f"building:{rn}"
        drum_cells = _drum_cells_for_range(assembly, st, rn)
        if drum_cells and (drum_cells & floor_cells):
            body_only = floor_cells - drum_cells
            if body_only:
                extended[f"{mass_id}:body"] = body_only
            extended[f"{mass_id}:drum"] = drum_cells
        else:
            extended[mass_id] = floor_cells
    return {k: v for k, v in extended.items() if v}


def _drum_cells_for_range(
    assembly: Assembly, structure: str, range_name: str
) -> Set[Cell]:
    """L0 tower-arc cells for one compound range within a structure."""
    st = structure if structure.startswith(_STRUCTURE_PREFIX) else structure_tag(structure)
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.level != 0:
            continue
        if st not in structure_ids_on(p):
            continue
        if p.kind != "tower_arc" and "tower_arc" not in (p.asset_id or ""):
            continue
        if range_name not in _placement_range_names(p):
            continue
        out.add(p.cell)
    return out


def _mass_id_base(mass_id: MassId) -> MassId:
    if mass_id.endswith(":body") or mass_id.endswith(":drum"):
        return mass_id.rsplit(":", 1)[0]
    return mass_id


def _wall_belongs_to_submass(p: SolidPlacement, mass_id: MassId, known: Set[str]) -> bool:
    """True when a wall tags to a mass or its body/drum submass."""
    base = _mass_id_base(mass_id)
    if _wall_belongs_to_mass(p, base):
        return True
    rn = _mass_name_from_id(base)
    return rn in _placement_range_names(p) or base in p.tags


def _touching_mass_pairs(
    footprints: Dict[MassId, Set[Cell]],
) -> List[Tuple[MassId, MassId, Set[Cell]]]:
    names = sorted(footprints)
    pairs: List[Tuple[MassId, MassId, Set[Cell]]] = []
    for i, a in enumerate(names):
        fa = footprints[a]
        if not fa:
            continue
        for b in names[i + 1 :]:
            fb = footprints[b]
            if not fb:
                continue
            iface: Set[Cell] = set()
            for x, y in fa:
                for dx, dy in _DELTAS:
                    n = (x + dx, y + dy)
                    if n in fb:
                        iface.add((x, y))
                        iface.add(n)
            if iface:
                pairs.append((a, b, iface))
    return pairs


def _mass_name_from_id(mid: MassId) -> str:
    return mid.replace("building:", "")


def _is_solid_blocker_wall(p: SolidPlacement) -> bool:
    from pae.compound_unify import _is_solid_blocker_wall as _solid

    return _solid(p)


def _is_passage_wall(p: SolidPlacement) -> bool:
    from pae.compound_unify import _is_passage_wall as _pass

    return _pass(p)


def _wall_belongs_to_mass(p: SolidPlacement, mass: MassId) -> bool:
    rn = _mass_name_from_id(mass)
    return mass in p.tags or rn in p.tags


def _interface_double_skin_submass(
    assembly: Assembly,
    iface: Set[Cell],
    mass_a: MassId,
    mass_b: MassId,
    known: Set[str],
    *,
    level: int = 0,
) -> bool:
    has_a = has_b = False
    for p in assembly.placements:
        if p.level != level or not _is_solid_blocker_wall(p):
            continue
        if not (covered_cells(p) & iface):
            continue
        if _wall_belongs_to_submass(p, mass_a, known):
            has_a = True
        if _wall_belongs_to_submass(p, mass_b, known):
            has_b = True
        if has_a and has_b:
            return True
    return False


def _interface_has_passage(
    assembly: Assembly, iface: Set[Cell], *, level: int = 0
) -> bool:
    for p in assembly.placements:
        if p.level != level or not _is_passage_wall(p):
            continue
        if covered_cells(p) & iface:
            return True
    return False


def _structures_in(assembly: Assembly) -> Set[str]:
    out: Set[str] = set()
    for p in assembly.placements:
        for t in structure_ids_on(p):
            sid = structure_id_from_tag(t)
            if sid:
                out.add(sid)
    return out


def check_structure_contiguous(assembly: Assembly) -> List[Failure]:
    """Every mass in a declared structure must touch another member transitively (T-101)."""
    failures: List[Failure] = []
    for sid in sorted(_structures_in(assembly)):
        fps = _floor_footprint_by_mass(assembly, structure_tag(sid))
        masses = [m for m, cells in fps.items() if cells]
        if len(masses) < 2:
            continue
        parent = {m: m for m in masses}

        def find(x: MassId) -> MassId:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: MassId, b: MassId) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a, b, _iface in _touching_mass_pairs(fps):
            union(a, b)

        groups: Dict[MassId, List[MassId]] = defaultdict(list)
        for m in masses:
            groups[find(m)].append(m)
        if len(groups) < 2:
            continue
        isolated = min(groups.values(), key=len)
        rep = isolated[0]
        cx, cy = sorted(fps[rep])[0]
        failures.append(
            Failure(
                check=CHECK_STRUCTURE_CONTIGUOUS,
                message=(
                    f"structure {sid!r} has {len(groups)} disconnected mass(es) — "
                    f"{_mass_name_from_id(rep)!r} does not touch any other member "
                    f"(declared structures must be contiguous)"
                ),
                world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                critical=True,
            )
        )
    return failures


def check_structure_party_wall_open(assembly: Assembly) -> List[Failure]:
    """No back-to-back exterior skins between masses of one structure (D3-2 / T-105)."""
    failures: List[Failure] = []
    known = _collect_known_ranges(assembly)
    for sid in sorted(_structures_in(assembly)):
        st = structure_tag(sid)
        fps = _structure_mass_footprints(assembly, sid)
        for a, b, iface in _touching_mass_pairs(fps):
            if _interface_double_skin_submass(assembly, iface, a, b, known, level=0):
                cx, cy = sorted(iface)[0]
                failures.append(
                    Failure(
                        check=CHECK_STRUCTURE_PARTY_WALL,
                        message=(
                            f"structure {sid!r}: masses "
                            f"{_mass_name_from_id(a)!r} and "
                            f"{_mass_name_from_id(b)!r} share back-to-back "
                            f"exterior walls — interior party line must be "
                            f"open or carry a passage"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                        critical=True,
                    )
                )
                continue
            solids = [
                p
                for p in assembly.placements
                if p.level == 0
                and _is_solid_blocker_wall(p)
                and bool(covered_cells(p) & iface)
                and st in structure_ids_on(p)
            ]
            if solids and not _interface_has_passage(assembly, iface, level=0):
                cx, cy = sorted(iface)[0]
                failures.append(
                    Failure(
                        check=CHECK_STRUCTURE_PARTY_WALL,
                        message=(
                            f"structure {sid!r}: masses "
                            f"{_mass_name_from_id(a)!r} and "
                            f"{_mass_name_from_id(b)!r} sealed by "
                            f"{len(solids)} solid wall(s) with no passage"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                        piece_id=solids[0].piece_id,
                        critical=True,
                    )
                )
    return failures


def _ground_walk_components(assembly: Assembly, *, structure: str) -> List[Set[Cell]]:
    from pae.compound_unify import _step_blocked

    cells: Set[Cell] = set()
    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        if structure not in structure_ids_on(p):
            continue
        cells |= covered_cells(p)
    if not cells:
        return []
    parent: Dict[Cell, Cell] = {c: c for c in cells}

    def find(c: Cell) -> Cell:
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    def union(c1: Cell, c2: Cell) -> None:
        r1, r2 = find(c1), find(c2)
        if r1 != r2:
            parent[r2] = r1

    for c in cells:
        x, y = c
        for dx, dy in _DELTAS:
            n = (x + dx, y + dy)
            if n not in cells:
                continue
            if _step_blocked(assembly, c, n, level=0):
                continue
            union(c, n)

    groups: Dict[Cell, Set[Cell]] = defaultdict(set)
    for c in cells:
        groups[find(c)].add(c)
    return list(groups.values())


def check_structure_masses_reachable(assembly: Assembly) -> List[Failure]:
    """Every mass of a structure must be walkable from every other (T-106)."""
    failures: List[Failure] = []
    for sid in sorted(_structures_in(assembly)):
        st = structure_tag(sid)
        fps = _structure_mass_footprints(assembly, sid)
        if len(fps) < 2:
            continue
        components = _ground_walk_components(assembly, structure=st)
        if not components:
            continue
        for mid, cells in sorted(fps.items()):
            if not any(cells <= comp for comp in components):
                cx, cy = sorted(cells)[0]
                failures.append(
                    Failure(
                        check=CHECK_STRUCTURE_REACHABLE,
                        message=(
                            f"structure {sid!r}: mass "
                            f"{_mass_name_from_id(mid)!r} is not walkable "
                            f"from other members"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                        critical=True,
                    )
                )
                break
        if len(components) > 1:
            smallest = min(components, key=len)
            cx, cy = sorted(smallest)[0]
            failures.append(
                Failure(
                    check=CHECK_STRUCTURE_REACHABLE,
                    message=(
                        f"structure {sid!r} has {len(components)} disconnected "
                        f"walk components — masses must share one circulation graph"
                    ),
                    world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                    critical=True,
                )
            )
    return failures


def _placement_range_names(p: SolidPlacement) -> Set[str]:
    """Compound range ids on a placement — survives campus merge retag."""
    from pae.compound_unify import _CAMPUS_RANGE_IDS, _FLOOR_META_TAGS

    names: Set[str] = set()
    for t in p.tags:
        if t.startswith("building:"):
            rn = t.replace("building:", "")
            if rn not in _CAMPUS_RANGE_IDS and not rn.endswith("_campus"):
                names.add(rn)
        elif (
            not t.startswith(("structure:", "module_"))
            and t not in _FLOOR_META_TAGS
            and t not in _CAMPUS_RANGE_IDS
            and t not in {"floor", "wall", "roof", "stair", "slab", "ground", "trim", "door", "exterior", "interior", "compound_merged", "fortress_compound", "straight", "switchback", "spiral", "wide", "half", "landing", "tower", "tower_arc", "habitable_drum"}
        ):
            names.add(t)
    pid = p.piece_id or ""
    for prefix in (
        "west_curtain",
        "east_curtain",
        "gatehouse",
        "north_keep",
        "west_cloister",
        "east_cloister",
    ):
        if prefix in pid:
            names.add(prefix)
    return names


def _mass_keeps_stair_core(
    p: SolidPlacement,
    primary: str,
    auxiliary: Sequence[str],
    known_ranges: Set[str],
) -> bool:
    """True when this placement's mass may retain hall / helix stairs after unify."""
    ranges = _placement_range_names(p)
    if primary and primary in ranges:
        return True
    if auxiliary and any(name in ranges for name in auxiliary):
        return True
    if primary and _mass_matches_primary(p, primary, known_ranges):
        return True
    if auxiliary:
        name = _mass_name_from_id(_mass_id(p, known_ranges))
        if name in auxiliary:
            return True
    return False


def check_structure_single_stair_core(
    assembly: Assembly,
    *,
    primary_circulation_mass: Optional[str] = None,
    auxiliary_circulation_masses: Sequence[str] = (),
) -> List[Failure]:
    """One hall stair core per structure, not one per single-storey mass (D3-1 / T-103).

    Multi-storey subsidiary masses listed in ``auxiliary_circulation_masses`` may
    keep their own hall well (fortress gatehouse). Tower ``stair_spiral_quarter``
  pieces are never counted as redundant hall cores.
    """
    failures: List[Failure] = []
    known = _collect_known_ranges(assembly)
    allowed = set(auxiliary_circulation_masses or ())
    if primary_circulation_mass:
        allowed.add(primary_circulation_mass)
    for sid in sorted(_structures_in(assembly)):
        st = structure_tag(sid)
        allowed_for_structure = set(allowed)
        if primary_circulation_mass is None:
            inferred_masses: Set[str] = set()
            for p in assembly.placements:
                if st not in structure_ids_on(p):
                    continue
                if (p.asset_id or "") not in _HALL_STAIR_CORE_ASSETS or p.level != 0:
                    continue
                rn = next(iter(_placement_range_names(p)), None)
                inferred_masses.add(
                    rn if rn is not None else _mass_name_from_id(_mass_id(p, known))
                )
            if inferred_masses:
                # A normal StructureSpec has no named compound primary. Its first
                # (usually only) stair-bearing mass is the primary by definition;
                # only additional masses are redundant.
                allowed_for_structure.add(sorted(inferred_masses)[0])
        stair_count = 0
        illegal: Set[str] = set()
        for p in assembly.placements:
            if st not in structure_ids_on(p):
                continue
            aid = p.asset_id or ""
            if aid not in _HALL_STAIR_CORE_ASSETS or p.level != 0:
                continue
            stair_count += 1
            rn = next(iter(_placement_range_names(p)), None)
            if rn is None:
                rn = _mass_name_from_id(_mass_id(p, known))
            if rn not in allowed_for_structure:
                illegal.add(rn)
        if not illegal:
            continue
        cx, cy = 0, 0
        for p in assembly.placements:
            if st in structure_ids_on(p) and (p.asset_id or "") in _HALL_STAIR_CORE_ASSETS:
                cx, cy = p.cell
                break
        names = ", ".join(sorted(illegal))
        failures.append(
            Failure(
                check=CHECK_STRUCTURE_SINGLE_STAIR,
                message=(
                    f"structure {sid!r} carries redundant hall stair core(s) on "
                    f"mass(es) ({names}) — one structure shares primary circulation "
                    f"on {primary_circulation_mass!r}; subsidiary masses must not "
                    f"each own a separate L0 hall well "
                    f"({stair_count} L0 hall stair piece(s))"
                ),
                world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                critical=True,
            )
        )
    return failures


def repair_structure_single_stair_core(
    assembly: Assembly,
    *,
    structure_id: str,
    primary_mass: str,
    auxiliary_masses: Sequence[str] = (),
) -> Assembly:
    """Strip redundant hall stair cores from non-primary masses (D3-1 autofix).

    Keeps every stair piece on ``primary_mass`` and ``auxiliary_masses`` (e.g.
    fortress gatehouse hall well + tower spirals). Removes L0 ``_HALL_STAIR_CORE_ASSETS``
    from other masses of the same declared structure. Idempotent.
    """
    if not structure_id or not primary_mass:
        return assembly
    st = structure_tag(structure_id)
    known = _collect_known_ranges(assembly)
    if not any(st in structure_ids_on(p) for p in assembly.placements):
        return assembly

    kept: List[SolidPlacement] = []
    for p in assembly.placements:
        if st not in structure_ids_on(p):
            kept.append(p)
            continue
        aid = p.asset_id or ""
        if _mass_keeps_stair_core(p, primary_mass, auxiliary_masses, known):
            kept.append(p)
            continue
        if aid in _HALL_STAIR_CORE_ASSETS and p.level == 0:
            continue
        if aid in _STAIR_ASSETS:
            continue
        kept.append(p)

    if len(kept) == len(assembly.placements):
        return assembly
    return Assembly(
        placements=kept,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=assembly.apertures,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def check_structure_identity(
    assembly: Assembly,
    *,
    primary_circulation_mass: Optional[str] = None,
    auxiliary_circulation_masses: Sequence[str] = (),
) -> List[Failure]:
    """All §11d structure checks (critical, fail-closed)."""
    if not has_structure_tags(assembly):
        return []
    failures: List[Failure] = []
    failures.extend(check_structure_contiguous(assembly))
    failures.extend(check_structure_party_wall_open(assembly))
    failures.extend(check_structure_masses_reachable(assembly))
    failures.extend(
        check_structure_single_stair_core(
            assembly,
            primary_circulation_mass=primary_circulation_mass,
            auxiliary_circulation_masses=auxiliary_circulation_masses,
        )
    )
    return failures


STRUCTURE_PARTY_TAG = "structure_party"


def repair_structure_party_walls(assembly: Assembly) -> Assembly:
    """Autofix sealed / double-skin interfaces between masses of one structure (T-105).

    One mechanism for range–range and range–drum (body vs drum submass) shared edges:
    strip back-to-back duplicate skins and punch an interior arched doorway on the
    party line. Idempotent.
    """
    if not has_structure_tags(assembly):
        return assembly

    from pae.assembly_types import Aperture
    from pae.compound_unify import (
        COMPOUND_LINK_TAG,
        _door_aperture_for,
        _interface_has_passage,
        _interface_solid_walls,
        _wall_as_door,
        _walls_face_each_other,
    )

    known = _collect_known_ranges(assembly)
    out = assembly
    remove_ids: Set[str] = set()
    convert_ids: Dict[str, SolidPlacement] = {}
    new_apertures: List[Aperture] = []

    for sid in sorted(_structures_in(assembly)):
        st = structure_tag(sid)
        fps = _structure_mass_footprints(out, sid)
        for mass_a, mass_b, iface in _touching_mass_pairs(fps):
            if _interface_has_passage(out, iface, level=0) and not _interface_double_skin_submass(
                out, iface, mass_a, mass_b, known, level=0
            ):
                continue

            link_tags = (
                mass_a,
                mass_b,
                _mass_name_from_id(mass_a),
                _mass_name_from_id(mass_b),
                STRUCTURE_PARTY_TAG,
                st,
            )

            while True:
                solids = [
                    p
                    for p in _interface_solid_walls(out, iface, level=0)
                    if p.piece_id not in remove_ids
                    and p.piece_id not in convert_ids
                    and st in structure_ids_on(p)
                ]
                if not solids:
                    break
                paired = False
                for i, w0 in enumerate(solids):
                    mate = None
                    for w1 in solids[i + 1 :]:
                        if _walls_face_each_other(w0, w1):
                            mate = w1
                            break
                    if mate is not None:
                        remove_ids.add(mate.piece_id)
                        door = _wall_as_door(
                            w0,
                            link_tags=link_tags,
                        )
                        door_tags = set(door.tags) | {"interior", STRUCTURE_PARTY_TAG}
                        convert_ids[w0.piece_id] = SolidPlacement(
                            piece_id=door.piece_id,
                            asset_id="wall_door_arched",
                            kind=door.kind,
                            cell=door.cell,
                            level=door.level,
                            yaw=door.yaw,
                            offset_cm=door.offset_cm,
                            size_cm=door.size_cm,
                            rotates_about_center=door.rotates_about_center,
                            tags=frozenset(door_tags),
                        )
                        new_apertures.append(_door_aperture_for(convert_ids[w0.piece_id]))
                        paired = True
                        break
                if not paired:
                    w0 = solids[0]
                    door = _wall_as_door(w0, link_tags=link_tags)
                    door_tags = set(door.tags) | {
                        "interior",
                        STRUCTURE_PARTY_TAG,
                        COMPOUND_LINK_TAG,
                    }
                    convert_ids[w0.piece_id] = SolidPlacement(
                        piece_id=door.piece_id,
                        asset_id="wall_door_arched",
                        kind=door.kind,
                        cell=door.cell,
                        level=door.level,
                        yaw=door.yaw,
                        offset_cm=door.offset_cm,
                        size_cm=door.size_cm,
                        rotates_about_center=door.rotates_about_center,
                        tags=frozenset(door_tags),
                    )
                    new_apertures.append(_door_aperture_for(convert_ids[w0.piece_id]))
                    break

    if not remove_ids and not convert_ids:
        return assembly

    new_placements: List[SolidPlacement] = []
    for p in out.placements:
        if p.piece_id in remove_ids:
            continue
        new_placements.append(convert_ids.get(p.piece_id, p))

    kept_apertures = [
        ap
        for ap in out.apertures
        if ap.wall_piece_id not in remove_ids and ap.wall_piece_id not in convert_ids
    ]
    kept_apertures.extend(new_apertures)

    return Assembly(
        placements=new_placements,
        floor_plan=out.floor_plan,
        circulation=out.circulation,
        wall_runs=out.wall_runs,
        apertures=kept_apertures,
        storeys=out.storeys,
        aperture_policy=out.aperture_policy,
        room_specs=getattr(out, "room_specs", []) or [],
        building_class=getattr(out, "building_class", "generic"),
        stair_kind=getattr(out, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def make_range_drum_sealed_defect() -> Assembly:
    """Poison — one structure, body + inboard drum sealed by solid party skin (T-106)."""
    from pae.contract import STOREY_CM, WALL_T_CM

    st = structure_tag("keep_a")
    bid = "building:north_keep"

    def floor(cell: Cell, pid: str) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="floor",
            kind="floor",
            cell=cell,
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({bid, "north_keep", st, "floor"}),
        )

    def wall(cell: Cell, yaw: int, pid: str, *, door: bool = False) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="wall_door" if door else "wall_plain",
            kind="wall",
            cell=cell,
            level=0,
            yaw=yaw,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({bid, "north_keep", st, "wall"}),
        )

    placements: List[SolidPlacement] = []
    # Body 2×3 + inboard drum at (2,1) — only adjacency is (1,1)|(2,1).
    for x in range(2):
        for y in range(3):
            placements.append(floor((x, y), f"f_{x}_{y}"))
    placements.append(
        SolidPlacement(
            piece_id="drum_floor",
            asset_id="floor",
            kind="floor",
            cell=(2, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({bid, "north_keep", st, "floor"}),
        )
    )
    placements.append(
        SolidPlacement(
            piece_id="drum_arc",
            asset_id="tower_arc_quarter",
            kind="tower_arc",
            cell=(2, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
            rotates_about_center=True,
            tags=frozenset({bid, "north_keep", st, "tower_arc"}),
        )
    )
    # Solid party skin on shared edge (1,1)| (2,1) — east face of body, west of drum.
    placements.append(wall((1, 1), 180, "party_east_body"))
    placements.append(wall((2, 1), 0, "party_west_drum"))
    placements.append(wall((0, 0), 270, "ext_door", door=True))
    return Assembly(placements=placements, storeys=2)


def make_three_stair_masses_defect() -> Assembly:
    """Poison — one structure, three masses each with an L0 stair (D3-1)."""
    from pae.compound_unify import make_three_sealed_buildings_defect

    base = make_three_sealed_buildings_defect()
    st = structure_tag("fortress_bailey")
    placements: List[SolidPlacement] = []
    for p in base.placements:
        tags = set(p.tags) | {st}
        placements.append(
            SolidPlacement(
                piece_id=p.piece_id,
                asset_id=p.asset_id,
                kind=p.kind,
                cell=p.cell,
                level=p.level,
                yaw=p.yaw,
                offset_cm=p.offset_cm,
                size_cm=p.size_cm,
                rotates_about_center=p.rotates_about_center,
                tags=frozenset(tags),
            )
        )
    for bid, cell, pid in (
        ("building:range_a", (0, 0), "stair_a"),
        ("building:range_b", (2, 0), "stair_b"),
        ("building:range_c", (4, 0), "stair_c"),
    ):
        placements.append(
            SolidPlacement(
                piece_id=pid,
                asset_id="stair_straight",
                kind="stair",
                cell=cell,
                level=0,
                yaw=0,
                offset_cm=(0.0, 0.0, 0.0),
                size_cm=(MODULE_CM, MODULE_CM, STOREY_CM),
                tags=frozenset({bid, bid.replace("building:", ""), st, "stair"}),
            )
        )
    return Assembly(placements=placements, storeys=2)


__all__ = [
    "CHECK_STRUCTURE_CONTIGUOUS",
    "CHECK_STRUCTURE_PARTY_WALL",
    "CHECK_STRUCTURE_REACHABLE",
    "CHECK_STRUCTURE_SINGLE_STAIR",
    "_HALL_STAIR_CORE_ASSETS",
    "_mass_keeps_stair_core",
    "apply_structure_tags",
    "check_structure_contiguous",
    "check_structure_identity",
    "check_structure_masses_reachable",
    "check_structure_party_wall_open",
    "check_structure_single_stair_core",
    "has_structure_tags",
    "make_range_drum_sealed_defect",
    "make_three_stair_masses_defect",
    "partition_key",
    "repair_structure_party_walls",
    "repair_structure_single_stair_core",
    "STRUCTURE_PARTY_TAG",
    "structure_id_from_tag",
    "structure_ids_on",
    "structure_tag",
]

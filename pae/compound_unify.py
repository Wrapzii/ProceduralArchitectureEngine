"""Compound unification — one connected structure, not sealed mini-buildings.

USER: a linear hall was emitted as THREE separate buildings sealed by full
exterior-style walls between floor decks. Stairs hit party walls and cannot
reach the next flight. That must never ship.

Hard rules (fail-closed + autofix):
  * Collinear/adjacent ranges on one compound/site share one circulation graph
  * Shared interfaces must not be back-to-back solid exterior skins
  * Building-in-building footprints are illegal
  * Every inhabited building/range needs ≥1 doorway
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pae.assembly_types import Aperture, Assembly, SolidPlacement
from pae.contract import (
    FLOOR_T_CM,
    MODULE_CM,
    STOREY_CM,
    WALL_T_CM,
    placement_world_aabb,
    storey_datum_z_cm,
)
from pae.existence import is_door_or_gate_asset
from pae.report import Failure
from pae.trim import covered_cells

if TYPE_CHECKING:
    from pae.compound import CompoundConnections, ConnectionPolicy

Cell = Tuple[int, int]
BuildingId = str  # e.g. "building:north_keep"
RangeName = str

CHECK_COMPOUND_PARTITIONED = "compound_not_partitioned_as_buildings"
CHECK_COMPOUND_RANGE_DOORS = "compound_range_doors"
CHECK_BUILDING_DOORWAY = "building_doorway_exists"
CHECK_BUILDING_IN_BUILDING = "building_in_building"
CHECK_FOOTPRINT_OVERLAP = "footprint_overlap"
CHECK_STAIR_LANDING_CLEAR = "stair_landing_clear"

COMPOUND_LINK_TAG = "compound_link"
_DELTAS = ((0, 1), (0, -1), (1, 0), (-1, 0))

# Wall yaw → face (assemble._place_wall_run convention).
_YAW_TO_FACE = {0: "west", 180: "east", 270: "south", 90: "north"}
_FACE_DELTA = {
    "north": (0, 1),
    "south": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
}


def _centre(
    a_min: Tuple[float, float, float], a_max: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        (a_min[0] + a_max[0]) * 0.5,
        (a_min[1] + a_max[1]) * 0.5,
        (a_min[2] + a_max[2]) * 0.5,
    )


def _placement_centre(p: SolidPlacement) -> Tuple[float, float, float]:
    bb_min, bb_max = placement_world_aabb(
        p.cell[0],
        p.cell[1],
        p.level,
        p.yaw,
        p.size_cm,
        p.offset_cm,
        rotates_about_center=p.rotates_about_center,
    )
    return _centre(bb_min, bb_max)


def _building_ids(p: SolidPlacement) -> Set[BuildingId]:
    return {t for t in p.tags if t.startswith("building:")}


def _range_name_from_building_id(bid: BuildingId) -> RangeName:
    return bid.replace("building:", "")


# Tags from place_buildings / catalog — never compound range instance names.
_FLOOR_META_TAGS = frozenset(
    {
        "floor",
        "slab",
        "ground",
        "plinth",
        "hole",
        "compound_merged",
        "compound_link",
        "fortress_campus",
        "school_campus",
        "castle_curtain",
        "fortress_compound",
        "module_400",
        "tower",
        "tower_room",
        "tower_room_floor",
        "walkable",
        "arcade",
        "arcade_gallery",
        "walk",
        "structural",
        "tower_entry_landing",
    }
)

_CAMPUS_RANGE_IDS = frozenset(
    {"fortress_campus", "school_campus", "castle_curtain", "_default"}
)


def collect_compound_range_names(assembly: Assembly) -> Set[RangeName]:
    """Instance names from ``place_buildings`` — not style/trim catalog tags."""
    names: Set[RangeName] = set()
    for p in assembly.placements:
        for bid in _building_ids(p):
            rn = _range_name_from_building_id(bid)
            if rn in _CAMPUS_RANGE_IDS or rn.endswith("_campus"):
                continue
            names.add(rn)
    if names:
        return names
    # Campus merge retags ``building:*`` — bare instance names remain on floors.
    for p in assembly.placements:
        if p.kind != "floor" or p.level != 0:
            continue
        for t in p.tags:
            if t.startswith("building:") or t in _FLOOR_META_TAGS:
                continue
            names.add(t)
    return names


def _range_names(
    p: SolidPlacement, known: Optional[Set[RangeName]] = None
) -> Set[RangeName]:
    """Compound range ids on one placement (``building:*`` or bare instance tag)."""
    known = known if known is not None else set()
    out: Set[RangeName] = set()
    for bid in _building_ids(p):
        rn = _range_name_from_building_id(bid)
        if rn in _CAMPUS_RANGE_IDS or rn.endswith("_campus"):
            continue
        out.add(rn)
    if out:
        return out
    return {t for t in p.tags if t in known}


def _merge_strip_zone(fa: Set[Cell], fb: Set[Cell]) -> Set[Cell]:
    """Cells where party walls must be stripped for a merge (overlap or touch only)."""
    overlap = fa & fb
    zone: Set[Cell] = set(overlap)
    if not overlap:
        for cx, cy in fa:
            for dx, dy in _DELTAS:
                n = (cx + dx, cy + dy)
                if n in fb:
                    zone.add((cx, cy))
                    zone.add(n)
    return zone


def _floor_footprint_by_range(
    assembly: Assembly,
    known: Optional[Set[RangeName]] = None,
    *,
    level: int = 0,
) -> Dict[RangeName, Set[Cell]]:
    """Walkable floor cells per compound range — overlap check uses floors only."""
    known = known if known is not None else collect_compound_range_names(assembly)
    out: Dict[RangeName, Set[Cell]] = defaultdict(set)
    for p in assembly.placements:
        if p.level != level or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        for rn in _range_names(p, known):
            out[rn].update(covered_cells(p))
    return dict(out)


def _built_footprint_by_range(
    assembly: Assembly, level: int = 0
) -> Dict[RangeName, Set[Cell]]:
    """Level-0 built envelope per range (walls + floors) for interface strip zones."""
    known = collect_compound_range_names(assembly)
    out: Dict[RangeName, Set[Cell]] = defaultdict(set)
    for p in assembly.placements:
        if p.level != level or p.kind not in ("wall", "floor", "plinth", "ground"):
            continue
        if "hole" in (p.asset_id or ""):
            continue
        for rn in _range_names(p, known):
            out[rn].update(covered_cells(p))
    return dict(out)


def _is_solid_blocker_wall(p: SolidPlacement) -> bool:
    """Exterior-style solid wall — no door/gate/window/arcade passage."""
    if p.kind != "wall":
        return False
    aid = (p.asset_id or "").lower()
    if is_door_or_gate_asset(aid):
        return False
    if "window" in aid or "arcade" in aid or "arrowslit" in aid:
        return False
    if "opening" in aid or "arch" in aid:
        return False
    return True


def _is_passage_wall(p: SolidPlacement) -> bool:
    if p.kind != "wall":
        return False
    aid = (p.asset_id or "").lower()
    return is_door_or_gate_asset(aid) or "arcade" in aid


def _ground_floors_by_building(
    assembly: Assembly,
) -> Dict[BuildingId, Set[Cell]]:
    out: Dict[BuildingId, Set[Cell]] = defaultdict(set)
    for p in assembly.placements:
        if p.kind != "floor" or "hole" in p.asset_id or p.level != 0:
            continue
        cells = covered_cells(p)
        bids = _building_ids(p)
        if not bids:
            # Untagged single-building assembly — one synthetic id.
            out["building:_default"].update(cells)
        else:
            for b in bids:
                out[b].update(cells)
    return dict(out)


def _touching_pairs(
    footprints: Dict[BuildingId, Set[Cell]],
) -> List[Tuple[BuildingId, BuildingId, Set[Cell]]]:
    """Pairs of buildings whose ground floors share a 4-connected edge.

    Returns (a, b, interface_cells) where interface is the union of abutting cells.
    """
    names = sorted(footprints)
    pairs: List[Tuple[BuildingId, BuildingId, Set[Cell]]] = []
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


def _interface_has_passage(
    assembly: Assembly, iface: Set[Cell], level: int = 0
) -> bool:
    for p in assembly.placements:
        if p.level != level or not _is_passage_wall(p):
            continue
        if covered_cells(p) & iface:
            return True
    return False


def _interface_solid_walls(
    assembly: Assembly, iface: Set[Cell], level: int = 0
) -> List[SolidPlacement]:
    return [
        p
        for p in assembly.placements
        if p.level == level
        and _is_solid_blocker_wall(p)
        and bool(covered_cells(p) & iface)
    ]


def _compound_floor_footprints(assembly: Assembly) -> Dict[BuildingId, Set[Cell]]:
    """Per-range L0 floor cells for compound circulation checks."""
    known = collect_compound_range_names(assembly)
    by_range = _floor_footprint_by_range(assembly, known)
    return {
        f"building:{rn}": cells for rn, cells in by_range.items() if cells
    }


def _wall_belongs_to_range(p: SolidPlacement, range_name: RangeName) -> bool:
    return f"building:{range_name}" in p.tags or range_name in p.tags


def _interface_double_skin(
    assembly: Assembly,
    iface: Set[Cell],
    range_a: RangeName,
    range_b: RangeName,
    *,
    level: int = 0,
) -> bool:
    """True when both ranges place solid blocker walls on the same interface."""
    has_a = has_b = False
    for p in assembly.placements:
        if p.level != level or not _is_solid_blocker_wall(p):
            continue
        if not (covered_cells(p) & iface):
            continue
        if _wall_belongs_to_range(p, range_a):
            has_a = True
        if _wall_belongs_to_range(p, range_b):
            has_b = True
        if has_a and has_b:
            return True
    return False


def _structure_for_range(
    assembly: Assembly, range_name: RangeName, known: Set[RangeName]
) -> Optional[str]:
    """Declared ``structure:<id>`` on any L0 floor for this range, if present."""
    from pae.structure_identity import structure_ids_on

    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if range_name not in _range_names(p, known):
            continue
        for t in structure_ids_on(p):
            return t
    return None


def _default_connections() -> "CompoundConnections":
    from pae.compound import CompoundConnections, ConnectionPolicy

    return CompoundConnections(default=ConnectionPolicy.CONNECT)


def is_compound_assembly(assembly: Assembly) -> bool:
    """True when ≥2 distinct ``building:`` tags appear (merged site/compound)."""
    ids = set()
    for p in assembly.placements:
        ids |= _building_ids(p)
        if len(ids) >= 2:
            return True
    return False


# ---------------------------------------------------------------------------
# Checks (fail-closed, critical, no severity knobs)
# ---------------------------------------------------------------------------


def check_compound_not_partitioned(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> List[Failure]:
    """N≥2 floor decks in one compound sealed by solid walls with no door.

    Handbook class 9 (Use) + 6 (Coherence). CRITICAL — not warning, not demotable.
  Fails when:
    * merge/connect policy and back-to-back solid skins remain (even if a door exists
      elsewhere on the interface), or
    * separate policy and the interface is fully sealed with no passage.
    """
    if not is_compound_assembly(assembly):
        return []
    conn = connections or _default_connections()
    footprints = _compound_floor_footprints(assembly)
    if len(footprints) < 2:
        return []

    failures: List[Failure] = []
    for a, b, iface in _touching_pairs(footprints):
        ra, rb = _range_name_from_building_id(a), _range_name_from_building_id(b)
        policy = conn.policy_for(ra, rb)
        known = collect_compound_range_names(assembly)
        st_a = _structure_for_range(assembly, ra, known)
        st_b = _structure_for_range(assembly, rb, known)
        same_structure = bool(st_a and st_a == st_b)
        if same_structure:
            # Declared one structure — interior interface; never treat as separate buildings.
            if _interface_double_skin(assembly, iface, ra, rb, level=0):
                solids = _interface_solid_walls(assembly, iface, level=0)
                world = _placement_centre(solids[0]) if solids else None
                failures.append(
                    Failure(
                        check=CHECK_COMPOUND_PARTITIONED,
                        message=(
                            f"structure {st_a!r}: ranges {ra!r} and {rb!r} share "
                            f"back-to-back exterior skins — party wall must be open "
                            f"or carry a passage"
                        ),
                        world_xyz=world,
                        piece_id=solids[0].piece_id if solids else None,
                        critical=True,
                    )
                )
                continue
            solids = _interface_solid_walls(assembly, iface, level=0)
            if solids and not _interface_has_passage(assembly, iface, level=0):
                world = _placement_centre(solids[0])
                failures.append(
                    Failure(
                        check=CHECK_COMPOUND_PARTITIONED,
                        message=(
                            f"structure {st_a!r}: ranges {ra!r} and {rb!r} sealed by "
                            f"{len(solids)} solid wall(s) with no passage — one "
                            f"structure must share one circulation graph"
                        ),
                        world_xyz=world,
                        piece_id=solids[0].piece_id,
                        critical=True,
                    )
                )
            continue
        if policy.value == "separate":
            if _interface_has_passage(assembly, iface, level=0):
                continue
            solids = _interface_solid_walls(assembly, iface, level=0)
            if not solids:
                continue
            world = _placement_centre(solids[0])
            failures.append(
                Failure(
                    check=CHECK_COMPOUND_PARTITIONED,
                    message=(
                        f"compound ranges {ra!r} and {rb!r} touch but are sealed by "
                        f"{len(solids)} solid wall(s) with no doorway — treated as "
                        f"separate buildings (must be one circulation graph)"
                    ),
                    world_xyz=world,
                    piece_id=solids[0].piece_id,
                    critical=True,
                )
            )
            continue

        # merge / connect — any double skin OR merge-range solid on iface is illegal.
        solids = _interface_solid_walls(assembly, iface, level=0)
        if policy.value == "merge" and solids:
            world = _placement_centre(solids[0])
            failures.append(
                Failure(
                    check=CHECK_COMPOUND_PARTITIONED,
                    message=(
                        f"merge ranges {ra!r} and {rb!r} still have "
                        f"{len(solids)} solid party wall(s) on shared interface "
                        f"(must be one open mass, not sealed boxes)"
                    ),
                    world_xyz=world,
                    piece_id=solids[0].piece_id,
                    critical=True,
                )
            )
            continue
        if _interface_double_skin(assembly, iface, ra, rb, level=0):
            solids = _interface_solid_walls(assembly, iface, level=0)
            world = _placement_centre(solids[0]) if solids else None
            failures.append(
                Failure(
                    check=CHECK_COMPOUND_PARTITIONED,
                    message=(
                        f"compound ranges {ra!r} and {rb!r} share back-to-back "
                        f"exterior skins on interface — treated as separate "
                        f"buildings (policy={policy.value})"
                    ),
                    world_xyz=world,
                    piece_id=solids[0].piece_id if solids else None,
                    critical=True,
                )
            )
            continue
        if solids and not _interface_has_passage(assembly, iface, level=0):
            world = _placement_centre(solids[0])
            failures.append(
                Failure(
                    check=CHECK_COMPOUND_PARTITIONED,
                    message=(
                        f"compound ranges {ra!r} and {rb!r} touch but are sealed "
                        f"by {len(solids)} solid wall(s) with no doorway — "
                        f"treated as separate buildings"
                    ),
                    world_xyz=world,
                    piece_id=solids[0].piece_id,
                    critical=True,
                )
            )
    return failures


def check_compound_range_doors(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> List[Failure]:
    """Adjacent inhabited ranges in a compound need a walkable connecting door.

    Alias intent of ``inter_wing_connection``. Same critical bar as partitioned.
    """
    if not is_compound_assembly(assembly):
        return []
    conn = connections or _default_connections()
    footprints = _compound_floor_footprints(assembly)
    failures: List[Failure] = []
    for a, b, iface in _touching_pairs(footprints):
        ra, rb = _range_name_from_building_id(a), _range_name_from_building_id(b)
        policy = conn.policy_for(ra, rb)
        if policy.value == "merge":
            continue
        if _interface_has_passage(assembly, iface, level=0):
            continue
        solids = _interface_solid_walls(assembly, iface, level=0)
        if not solids:
            continue
        if policy.value == "connect" and _interface_double_skin(assembly, iface, ra, rb):
            world = _placement_centre(solids[0])
            failures.append(
                Failure(
                    check=CHECK_COMPOUND_RANGE_DOORS,
                    message=(
                        f"connected compound ranges {ra!r} and {rb!r} share a walled "
                        f"interface with no walkable doorway (double skin)"
                    ),
                    world_xyz=world,
                    piece_id=solids[0].piece_id,
                    critical=True,
                )
            )
            continue
        world = _placement_centre(solids[0])
        failures.append(
            Failure(
                check=CHECK_COMPOUND_RANGE_DOORS,
                message=(
                    f"connected compound ranges {ra!r} and {rb!r} share a walled "
                    f"interface with no walkable doorway"
                ),
                world_xyz=world,
                piece_id=solids[0].piece_id,
                critical=True,
            )
        )
    return failures


def check_building_doorway_exists(assembly: Assembly) -> List[Failure]:
    """Every inhabited building/range must have ≥1 exterior or role doorway."""
    footprints = _ground_floors_by_building(assembly)
    if not footprints:
        return []
    doors_by_building: Dict[BuildingId, int] = defaultdict(int)
    for p in assembly.placements:
        if p.level != 0 or not _is_passage_wall(p):
            continue
        bids = _building_ids(p)
        if not bids:
            doors_by_building["building:_default"] += 1
        for b in bids:
            doors_by_building[b] += 1

    failures: List[Failure] = []
    for bid, cells in sorted(footprints.items()):
        if not cells:
            continue
        # Curtain-only thin shells without floor habitation skipped? No — user said
        # ALL buildings need some doorway.
        if doors_by_building.get(bid, 0) > 0:
            continue
        # Pick a representative floor cell for framing.
        cx, cy = sorted(cells)[0]
        failures.append(
            Failure(
                check=CHECK_BUILDING_DOORWAY,
                message=(
                    f"{bid} has ground floor area but no door/gate — every building "
                    f"needs ≥1 doorway"
                ),
                world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                piece_id=None,
                critical=True,
            )
        )
    return failures


def check_building_in_building(assembly: Assembly) -> List[Failure]:
    """One footprint fully inside another on the same site — illegal nesting."""
    footprints = _ground_floors_by_building(assembly)
    footprints = {k: v for k, v in footprints.items() if v}
    names = sorted(footprints)
    failures: List[Failure] = []
    for i, a in enumerate(names):
        fa = footprints[a]
        for b in names[i + 1 :]:
            fb = footprints[b]
            if not fa or not fb:
                continue
            if fa < fb:
                cx, cy = sorted(fa)[0]
                failures.append(
                    Failure(
                        check=CHECK_BUILDING_IN_BUILDING,
                        message=(
                            f"{a!r} footprint is inside {b!r} — "
                            f"building-in-building is forbidden; merge or reject"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                        critical=True,
                    )
                )
            elif fb < fa:
                cx, cy = sorted(fb)[0]
                failures.append(
                    Failure(
                        check=CHECK_BUILDING_IN_BUILDING,
                        message=(
                            f"{b!r} footprint is inside {a!r} — "
                            f"building-in-building is forbidden; merge or reject"
                        ),
                        world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                        critical=True,
                    )
                )
    return failures


def check_footprint_overlap(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> List[Failure]:
    """Partial floor overlap between ranges — illegal unless policy is merge."""
    conn = connections or _default_connections()
    from pae.compound import ConnectionPolicy

    known = collect_compound_range_names(assembly)
    built = _floor_footprint_by_range(assembly, known)
    built = {k: v for k, v in built.items() if v}
    names = sorted(built)
    failures: List[Failure] = []
    for i, a in enumerate(names):
        fa = built[a]
        for b in names[i + 1 :]:
            fb = built[b]
            inter = fa & fb
            if not inter:
                continue
            if fa < fb or fb < fa:
                continue
            if conn.policy_for(a, b) == ConnectionPolicy.MERGE:
                continue
            cx, cy = sorted(inter)[0]
            failures.append(
                Failure(
                    check=CHECK_FOOTPRINT_OVERLAP,
                    message=(
                        f"ranges {a!r} and {b!r} overlap on {len(inter)} floor cell(s) "
                        f"— merge envelopes or reject (building-in-building / party wall)"
                    ),
                    world_xyz=(cx * MODULE_CM, cy * MODULE_CM, 0.0),
                    critical=True,
                )
            )
    return failures


def check_compound_circulation(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> List[Failure]:
    """All compound unification checks (partition + doors + nest + doorway + overlap)."""
    failures: List[Failure] = []
    failures.extend(check_building_in_building(assembly))
    failures.extend(check_footprint_overlap(assembly, connections=connections))
    failures.extend(
        check_compound_not_partitioned(assembly, connections=connections)
    )
    failures.extend(check_compound_range_doors(assembly, connections=connections))
    failures.extend(check_building_doorway_exists(assembly))
    return failures


# ---------------------------------------------------------------------------
# Autofix — punch doors / strip duplicate skins on shared interfaces
# ---------------------------------------------------------------------------


def _face_from_yaw(yaw: int) -> Optional[str]:
    return _YAW_TO_FACE.get(int(yaw) % 360)


def _wall_as_door(p: SolidPlacement, *, link_tags: Iterable[str] = ()) -> SolidPlacement:
    tags = set(p.tags) | {COMPOUND_LINK_TAG, "door", "exterior"} | set(link_tags)
    return SolidPlacement(
        piece_id=p.piece_id,
        asset_id="wall_door",
        kind="wall",
        cell=p.cell,
        level=p.level,
        yaw=p.yaw,
        offset_cm=p.offset_cm,
        size_cm=p.size_cm,
        rotates_about_center=p.rotates_about_center,
        tags=frozenset(tags),
    )


def _door_aperture_for(wall: SolidPlacement) -> Aperture:
    face = _face_from_yaw(wall.yaw) or "south"
    dx, dy = _FACE_DELTA[face]
    # Interior = back into the host cell; exterior = through the face.
    # For compound links both sides are inhabited — mark exterior as the step out.
    interior = wall.cell
    exterior = (wall.cell[0] + dx, wall.cell[1] + dy)
    floor_z = storey_datum_z_cm(wall.level)
    wx, wy, wz = _placement_centre(wall)
    return Aperture(
        piece_id=f"door_{wall.piece_id}",
        kind="door",
        wall_piece_id=wall.piece_id,
        level=wall.level,
        sill_z_cm=wz - wall.size_cm[2] * 0.5 + 10.0,
        floor_z_cm=floor_z,
        interior_cell=interior,
        exterior_cell=exterior,
        world_xyz=(wx, wy, floor_z + 100.0),
    )


def _walls_face_each_other(a: SolidPlacement, b: SolidPlacement) -> bool:
    """True when two solids are back-to-back on the same shared edge."""
    fa, fb = _face_from_yaw(a.yaw), _face_from_yaw(b.yaw)
    if fa is None or fb is None:
        return False
    opposites = {("north", "south"), ("south", "north"), ("east", "west"), ("west", "east")}
    if (fa, fb) not in opposites:
        return False
    # Cells must be neighbours along that axis.
    ax, ay = a.cell
    bx, by = b.cell
    if fa in ("north", "south"):
        return ax == bx and abs(ay - by) <= 1
    return ay == by and abs(ax - bx) <= 1


def _merge_union(
    footprints: Dict[BuildingId, Set[Cell]],
    conn: "CompoundConnections",
) -> Dict[RangeName, RangeName]:
    """Union-find merge groups for MERGE policy on touching range pairs."""
    parent: Dict[RangeName, RangeName] = {}

    def find(x: RangeName) -> RangeName:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: RangeName, b: RangeName) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    from pae.compound import ConnectionPolicy

    for a, b, _iface in _touching_pairs(footprints):
        ra = _range_name_from_building_id(a)
        rb = _range_name_from_building_id(b)
        if conn.policy_for(ra, rb) == ConnectionPolicy.MERGE:
            union(ra, rb)

    all_ranges = {_range_name_from_building_id(k) for k in footprints}
    return {r: find(r) for r in all_ranges}


def _apply_merge_tags(
    assembly: Assembly,
    merge_map: Dict[RangeName, RangeName],
    *,
    campus_id: str,
) -> Assembly:
    """Retag merged ranges to a shared ``building:{campus_id}`` identity."""
    if not merge_map:
        return assembly
    groups: Dict[RangeName, Set[RangeName]] = defaultdict(set)
    for rn, root in merge_map.items():
        groups[root].add(rn)
    # Only retag groups with >1 member.
    merge_targets: Dict[RangeName, str] = {}
    for root, members in groups.items():
        if len(members) < 2:
            continue
        target = f"building:{campus_id}"
        for m in members:
            merge_targets[m] = target

    if not merge_targets:
        return assembly

    new_placements: List[SolidPlacement] = []
    for p in assembly.placements:
        tags = set(p.tags)
        changed = False
        for rn, target in merge_targets.items():
            bid = f"building:{rn}"
            if bid in tags:
                tags.discard(bid)
                tags.add(target)
                tags.add(campus_id)
                tags.add("compound_merged")
                changed = True
            # Keep bare range name for trim / validate range lookups.
        if changed:
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
                    tags=frozenset(tags),
                )
            )
        else:
            new_placements.append(p)

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


def unify_compound_interfaces(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> Assembly:
    """Autofix: apply merge/connect policies on shared interfaces.

    * ``merge`` — strip all interface walls (open party line), retag to campus id.
    * ``connect`` — strip back-to-back dupes, punch ≥1 door per sealed interface.
    Idempotent.
    """
    if not is_compound_assembly(assembly):
        return assembly

    conn = connections or _default_connections()
    range_fps = _built_footprint_by_range(assembly)
    range_fps = {k: v for k, v in range_fps.items() if v and k != "_default"}
    if len(range_fps) < 2:
        return assembly

    from pae.compound import ConnectionPolicy

    # Build synthetic building ids for pair detection (range names stay stable).
    synth_fps: Dict[BuildingId, Set[Cell]] = {
        f"building:{rn}": cells for rn, cells in range_fps.items()
    }

    remove_ids: Set[str] = set()
    convert_ids: Dict[str, SolidPlacement] = {}
    new_apertures: List[Aperture] = []
    out = assembly

    for a, b, iface in _touching_pairs(synth_fps):
        ra = _range_name_from_building_id(a)
        rb = _range_name_from_building_id(b)
        policy = conn.policy_for(ra, rb)

        if policy == ConnectionPolicy.MERGE:
            fa_cells = range_fps.get(ra, set())
            fb_cells = range_fps.get(rb, set())
            zone = _merge_strip_zone(fa_cells, fb_cells)
            for p in out.placements:
                if p.level != 0 or p.kind != "wall":
                    continue
                if p.piece_id in remove_ids:
                    continue
                if not _is_solid_blocker_wall(p):
                    continue
                if not (covered_cells(p) & zone):
                    continue
                bid_a, bid_b = f"building:{ra}", f"building:{rb}"
                if (
                    not _wall_belongs_to_range(p, ra)
                    and not _wall_belongs_to_range(p, rb)
                ):
                    continue
                remove_ids.add(p.piece_id)
            continue

        if policy == ConnectionPolicy.CONNECT and _interface_has_passage(
            out, iface, level=0
        ):
            if _interface_double_skin(out, iface, ra, rb, level=0):
                for p in _interface_solid_walls(out, iface, level=0):
                    if p.piece_id not in remove_ids:
                        remove_ids.add(p.piece_id)
            continue

        if _interface_has_passage(out, iface, level=0) and not _interface_double_skin(
            out, iface, ra, rb, level=0
        ):
            continue

        # CONNECT — strip all back-to-back duplicate pairs on the interface.
        while True:
            solids = [
                p
                for p in _interface_solid_walls(out, iface, level=0)
                if p.piece_id not in remove_ids and p.piece_id not in convert_ids
            ]
            if not solids:
                break
            paired = False
            used: Set[str] = set()
            for i, w0 in enumerate(solids):
                if w0.piece_id in used:
                    continue
                mate = None
                for w1 in solids[i + 1 :]:
                    if w1.piece_id in used:
                        continue
                    if _walls_face_each_other(w0, w1):
                        mate = w1
                        break
                if mate is not None:
                    remove_ids.add(mate.piece_id)
                    door = _wall_as_door(w0, link_tags=(a, b, ra, rb))
                    convert_ids[w0.piece_id] = door
                    new_apertures.append(_door_aperture_for(door))
                    paired = True
                    break
            if not paired:
                w0 = solids[0]
                door = _wall_as_door(w0, link_tags=(a, b, ra, rb))
                convert_ids[w0.piece_id] = door
                new_apertures.append(_door_aperture_for(door))
                break
            continue

    if remove_ids or convert_ids:
        new_placements: List[SolidPlacement] = []
        for p in out.placements:
            if p.piece_id in remove_ids:
                continue
            if p.piece_id in convert_ids:
                new_placements.append(convert_ids[p.piece_id])
            else:
                new_placements.append(p)
        kept_apertures = [
            ap
            for ap in out.apertures
            if ap.wall_piece_id not in remove_ids
            and ap.wall_piece_id not in convert_ids
        ]
        kept_apertures.extend(new_apertures)
        out = Assembly(
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
                out, "wide_stair_well_available", False
            ),
        )

    merge_map = _merge_union(synth_fps, conn)
    return _apply_merge_tags(out, merge_map, campus_id=conn.campus_id)


def ensure_building_doorways(assembly: Assembly) -> Assembly:
    """Autofix: if a building has ground floor but no door, punch one exterior wall."""
    footprints = _ground_floors_by_building(assembly)
    if not footprints:
        return assembly

    doors_by_building: Dict[BuildingId, int] = defaultdict(int)
    for p in assembly.placements:
        if p.level != 0 or not _is_passage_wall(p):
            continue
        bids = _building_ids(p) or {"building:_default"}
        for b in bids:
            doors_by_building[b] += 1

    convert_ids: Dict[str, SolidPlacement] = {}
    new_apertures: List[Aperture] = []
    for bid, cells in sorted(footprints.items()):
        if not cells or doors_by_building.get(bid, 0) > 0:
            continue
        # Find a solid ground wall tagged with this building.
        candidates = [
            p
            for p in assembly.placements
            if p.level == 0
            and _is_solid_blocker_wall(p)
            and (bid in _building_ids(p) or bid == "building:_default")
            and p.piece_id not in convert_ids
        ]
        if not candidates:
            continue
        # Prefer a south wall (assemble convention for main entrance).
        candidates.sort(
            key=lambda p: (
                0 if _face_from_yaw(p.yaw) == "south" else 1,
                p.cell[0],
                p.cell[1],
                p.piece_id,
            )
        )
        door = _wall_as_door(candidates[0], link_tags=(bid,))
        convert_ids[candidates[0].piece_id] = door
        new_apertures.append(_door_aperture_for(door))

    if not convert_ids:
        return assembly

    new_placements = [
        convert_ids.get(p.piece_id, p) for p in assembly.placements
    ]
    kept = [
        ap
        for ap in assembly.apertures
        if ap.wall_piece_id not in convert_ids
    ]
    kept.extend(new_apertures)
    return Assembly(
        placements=new_placements,
        floor_plan=assembly.floor_plan,
        circulation=assembly.circulation,
        wall_runs=assembly.wall_runs,
        apertures=kept,
        storeys=assembly.storeys,
        aperture_policy=assembly.aperture_policy,
        room_specs=getattr(assembly, "room_specs", []) or [],
        building_class=getattr(assembly, "building_class", "generic"),
        stair_kind=getattr(assembly, "stair_kind", "straight"),
        wide_stair_well_available=getattr(
            assembly, "wide_stair_well_available", False
        ),
    )


def repair_building_in_building(assembly: Assembly) -> Assembly:
    """Autofix: merge nested building tags into the outer building's identity."""
    footprints = _ground_floors_by_building(assembly)
    footprints = {k: v for k, v in footprints.items() if v}
    names = sorted(footprints)
    # Map inner -> outer
    merge_into: Dict[BuildingId, BuildingId] = {}
    for i, a in enumerate(names):
        fa = footprints[a]
        for b in names:
            if a == b:
                continue
            fb = footprints[b]
            if fa and fb and fa < fb:
                merge_into[a] = b

    if not merge_into:
        return assembly

    new_placements: List[SolidPlacement] = []
    for p in assembly.placements:
        tags = set(p.tags)
        changed = False
        for inner, outer in merge_into.items():
            if inner in tags:
                tags.discard(inner)
                tags.add(outer)
                # Also merge bare range name tags when present.
                inner_name = inner.replace("building:", "")
                outer_name = outer.replace("building:", "")
                if inner_name in tags:
                    tags.discard(inner_name)
                    tags.add(outer_name)
                changed = True
        if changed:
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
                    tags=frozenset(tags),
                )
            )
        else:
            new_placements.append(p)

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


def repair_footprint_overlap(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> Assembly:
    """Autofix duplicate floor slabs in merge-policy overlap cells."""
    conn = connections or _default_connections()
    from pae.compound import ConnectionPolicy

    known = collect_compound_range_names(assembly)
    by_range = _floor_footprint_by_range(assembly, known)
    names = sorted(by_range)
    merge_pairs: Set[Tuple[RangeName, RangeName]] = set()
    for i, a in enumerate(names):
        fa = by_range[a]
        for b in names[i + 1 :]:
            fb = by_range[b]
            inter = fa & fb
            if not inter or fa < fb or fb < fa:
                continue
            if conn.policy_for(a, b) == ConnectionPolicy.MERGE:
                merge_pairs.add(tuple(sorted((a, b))))

    if not merge_pairs:
        return assembly

    remove_ids: Set[str] = set()
    claimed: Dict[Cell, str] = {}

    for p in sorted(assembly.placements, key=lambda x: (x.level, x.cell, x.piece_id)):
        if p.level != 0 or p.kind != "floor" or p.piece_id in remove_ids:
            continue
        if "hole" in (p.asset_id or ""):
            continue
        pr = _range_names(p, known)
        if not pr:
            continue
        cells = covered_cells(p)
        drop = False
        for c in cells:
            owner = claimed.get(c)
            if owner is None:
                claimed[c] = p.piece_id
                continue
            if owner == p.piece_id:
                continue
            # Duplicate slab in a merge overlap — drop the later piece.
            for a, b in merge_pairs:
                if a in pr or b in pr:
                    drop = True
                    break
            if drop:
                break
        if drop:
            remove_ids.add(p.piece_id)
        else:
            for c in cells:
                claimed.setdefault(c, p.piece_id)

    if not remove_ids:
        return assembly

    return Assembly(
        placements=[p for p in assembly.placements if p.piece_id not in remove_ids],
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


def unify_compound_assembly(
    assembly: Assembly,
    *,
    connections: Optional["CompoundConnections"] = None,
) -> Assembly:
    """Full autofix pipeline for compound/site assemblies."""
    conn = connections or _default_connections()
    out = repair_building_in_building(assembly)
    out = unify_compound_interfaces(out, connections=conn)
    out = repair_footprint_overlap(out, connections=conn)
    from pae.wall_faces import repair_wall_face_stacks

    out = repair_wall_face_stacks(out)
    out = ensure_building_doorways(out)
    from pae.structure_identity import (
        apply_structure_tags,
        repair_structure_party_walls,
        repair_structure_single_stair_core,
    )

    if conn.structure_id:
        out = apply_structure_tags(out, conn.structure_id)
        if conn.primary_circulation_mass:
            out = repair_structure_single_stair_core(
                out,
                structure_id=conn.structure_id,
                primary_mass=conn.primary_circulation_mass,
                auxiliary_masses=conn.auxiliary_circulation_masses,
            )
    out = repair_structure_party_walls(out)
    return out


# ---------------------------------------------------------------------------
# Broken fixtures (Handbook §6 — can-fire first)
# ---------------------------------------------------------------------------


def make_three_sealed_buildings_defect() -> Assembly:
    """Top-down 'three blue rooms sealed' — collinear floors, solid party walls."""
    placements: List[SolidPlacement] = []

    def floor(bid: str, cell: Cell, pid: str) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="floor",
            kind="floor",
            cell=cell,
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({bid, bid.replace("building:", ""), "floor"}),
        )

    def wall(
        bid: str, cell: Cell, yaw: int, pid: str, *, door: bool = False
    ) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="wall_door" if door else "wall_plain",
            kind="wall",
            cell=cell,
            level=0,
            yaw=yaw,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({bid, bid.replace("building:", ""), "wall"}),
        )

    # Three 2×1 rooms along +X: A [0..1], B [2..3], C [4..5] — touch at x=1↔2 and 3↔4.
    for x in (0, 1):
        placements.append(floor("building:range_a", (x, 0), f"fa_{x}"))
    for x in (2, 3):
        placements.append(floor("building:range_b", (x, 0), f"fb_{x}"))
    for x in (4, 5):
        placements.append(floor("building:range_c", (x, 0), f"fc_{x}"))

    # Exterior door on A only — B and C sealed.
    placements.append(wall("building:range_a", (0, 0), 270, "door_a", door=True))
    # Party walls sealing A|B and B|C (back-to-back skins).
    placements.append(wall("building:range_a", (1, 0), 180, "party_a_east"))
    placements.append(wall("building:range_b", (2, 0), 0, "party_b_west"))
    placements.append(wall("building:range_b", (3, 0), 180, "party_b_east"))
    placements.append(wall("building:range_c", (4, 0), 0, "party_c_west"))
    # Outer skins.
    placements.append(wall("building:range_c", (5, 0), 180, "wall_c_east"))

    return Assembly(placements=placements, storeys=1)


def make_building_in_building_defect() -> Assembly:
    """Inner 1×1 footprint fully inside outer 3×3 — nesting illegal."""
    placements: List[SolidPlacement] = []
    for y in range(3):
        for x in range(3):
            placements.append(
                SolidPlacement(
                    piece_id=f"outer_{x}_{y}",
                    asset_id="floor",
                    kind="floor",
                    cell=(x, y),
                    level=0,
                    yaw=0,
                    offset_cm=(0.0, 0.0, -FLOOR_T_CM),
                    size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
                    tags=frozenset({"building:outer", "outer", "floor"}),
                )
            )
    placements.append(
        SolidPlacement(
            piece_id="inner_1_1",
            asset_id="floor",
            kind="floor",
            cell=(1, 1),
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({"building:inner", "inner", "floor"}),
        )
    )
    placements.append(
        SolidPlacement(
            piece_id="outer_door",
            asset_id="wall_door",
            kind="wall",
            cell=(0, 0),
            level=0,
            yaw=270,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({"building:outer", "outer", "wall", "door"}),
        )
    )
    return Assembly(placements=placements, storeys=1)


def make_fortress_five_boxes_defect() -> Assembly:
    """Fortress regression — 3 overlapping south barbican boxes + 2 side wings.

    Mimics top-down read: west_curtain | gatehouse | east_curtain share overlapping
    wall envelopes with back-to-back party skins; west/east cloisters sealed off.
    """
    placements: List[SolidPlacement] = []

    def floor(bid: str, cell: Cell, pid: str) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="floor",
            kind="floor",
            cell=cell,
            level=0,
            yaw=0,
            offset_cm=(0.0, 0.0, -FLOOR_T_CM),
            size_cm=(MODULE_CM, MODULE_CM, FLOOR_T_CM),
            tags=frozenset({bid, bid.replace("building:", ""), "floor"}),
        )

    def wall(bid: str, cell: Cell, yaw: int, pid: str) -> SolidPlacement:
        return SolidPlacement(
            piece_id=pid,
            asset_id="wall_plain",
            kind="wall",
            cell=cell,
            level=0,
            yaw=yaw,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({bid, bid.replace("building:", ""), "wall"}),
        )

    # South barbican — 3×2 each, overlapping wall cells on shared edges (y=-1..0).
    for x in range(0, 3):
        for y in (-1, 0):
            placements.append(floor("building:west_curtain", (x, y), f"wc_f_{x}_{y}"))
    for x in range(2, 5):
        for y in (-1, 0):
            placements.append(floor("building:gatehouse", (x, y), f"gh_f_{x}_{y}"))
    for x in range(4, 7):
        for y in (-1, 0):
            placements.append(floor("building:east_curtain", (x, y), f"ec_f_{x}_{y}"))

    # Overlapping wall skins on shared interfaces (double envelope).
    for y in (-1, 0):
        placements.append(wall("building:west_curtain", (2, y), 180, f"wc_e_{y}"))
        placements.append(wall("building:gatehouse", (2, y), 0, f"gh_w_{y}"))
        placements.append(wall("building:gatehouse", (4, y), 180, f"gh_e_{y}"))
        placements.append(wall("building:east_curtain", (4, y), 0, f"ec_w_{y}"))

    # Side wings — sealed from barbican.
    for y in range(1, 4):
        placements.append(floor("building:west_cloister", (0, y), f"wcl_f_{y}"))
        placements.append(floor("building:east_cloister", (6, y), f"ecl_f_{y}"))
    placements.append(wall("building:west_cloister", (0, 0), 270, "wcl_s"))
    placements.append(wall("building:west_curtain", (0, 0), 90, "wc_n"))
    placements.append(wall("building:east_cloister", (6, 0), 270, "ecl_s"))
    placements.append(wall("building:east_curtain", (6, 0), 90, "ec_n"))

    placements.append(
        SolidPlacement(
            piece_id="wc_door",
            asset_id="wall_door",
            kind="wall",
            cell=(0, -1),
            level=0,
            yaw=270,
            offset_cm=(0.0, 0.0, 0.0),
            size_cm=(WALL_T_CM, MODULE_CM, STOREY_CM),
            tags=frozenset({"building:west_curtain", "west_curtain", "wall", "door"}),
        )
    )
    return Assembly(placements=placements, storeys=1)


# ---------------------------------------------------------------------------
# Ground circulation graph (tests — room-to-room across former party walls)
# ---------------------------------------------------------------------------


def inhabited_ground_floor_cells(assembly: Assembly) -> Set[Cell]:
    """Walkable L0 floor cells (any range), excluding holes."""
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        out |= covered_cells(p)
    return out


def _step_blocked(
    assembly: Assembly, c1: Cell, c2: Cell, *, level: int = 0
) -> bool:
    """True when a solid blocker wall blocks walking between adjacent cells."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    if abs(dx) + abs(dy) != 1:
        return True
    if dx == 1:
        faces = (("east", c1), ("west", c2))
    elif dx == -1:
        faces = (("west", c1), ("east", c2))
    elif dy == 1:
        faces = (("north", c1), ("south", c2))
    else:
        faces = (("south", c1), ("north", c2))
    for face, cell in faces:
        yaw = {f: y for y, f in _YAW_TO_FACE.items()}.get(face)
        if yaw is None:
            continue
        for p in assembly.placements:
            if p.level != level or p.kind != "wall":
                continue
            if _is_passage_wall(p):
                continue
            if not _is_solid_blocker_wall(p):
                continue
            if p.cell != cell or int(p.yaw) % 360 != yaw:
                continue
            if cell in covered_cells(p):
                return True
    return False


def ground_walk_components(assembly: Assembly) -> List[Set[Cell]]:
    """4-connected components over inhabited ground floors (solid walls block edges)."""
    cells = inhabited_ground_floor_cells(assembly)
    if not cells:
        return []
    remaining = set(cells)
    components: List[Set[Cell]] = []
    while remaining:
        start = min(remaining)
        comp: Set[Cell] = set()
        stack = [start]
        while stack:
            c = stack.pop()
            if c not in remaining:
                continue
            remaining.discard(c)
            comp.add(c)
            x, y = c
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                n = (nx, ny)
                if n not in remaining:
                    continue
                if _step_blocked(assembly, c, n):
                    continue
                stack.append(n)
        components.append(comp)
    return components


def range_floor_cells(assembly: Assembly, range_name: RangeName) -> Set[Cell]:
    bid = f"building:{range_name}"
    out: Set[Cell] = set()
    for p in assembly.placements:
        if p.level != 0 or p.kind != "floor":
            continue
        if "hole" in (p.asset_id or ""):
            continue
        if bid not in p.tags and range_name not in p.tags:
            continue
        out |= covered_cells(p)
    return out


def compound_ranges_ground_connected(
    assembly: Assembly, range_names: Sequence[RangeName]
) -> bool:
    """True when every named range's floor cells lie in one walk component."""
    components = ground_walk_components(assembly)
    if not components:
        return False
    for rn in range_names:
        cells = range_floor_cells(assembly, rn)
        if not cells:
            return False
        if not any(cells <= comp for comp in components):
            return False
    # All ranges must share the same component.
    first = range_floor_cells(assembly, range_names[0])
    host = next((c for c in components if first <= c), None)
    if host is None:
        return False
    return all(range_floor_cells(assembly, rn) <= host for rn in range_names[1:])


__all__ = [
    "CHECK_BUILDING_DOORWAY",
    "CHECK_BUILDING_IN_BUILDING",
    "CHECK_COMPOUND_PARTITIONED",
    "CHECK_COMPOUND_RANGE_DOORS",
    "CHECK_FOOTPRINT_OVERLAP",
    "CHECK_STAIR_LANDING_CLEAR",
    "COMPOUND_LINK_TAG",
    "check_building_doorway_exists",
    "check_building_in_building",
    "check_compound_circulation",
    "check_compound_not_partitioned",
    "check_compound_range_doors",
    "check_footprint_overlap",
    "collect_compound_range_names",
    "compound_ranges_ground_connected",
    "ensure_building_doorways",
    "ground_walk_components",
    "inhabited_ground_floor_cells",
    "is_compound_assembly",
    "make_building_in_building_defect",
    "make_fortress_five_boxes_defect",
    "make_three_sealed_buildings_defect",
    "range_floor_cells",
    "repair_building_in_building",
    "repair_footprint_overlap",
    "unify_compound_assembly",
    "unify_compound_interfaces",
]

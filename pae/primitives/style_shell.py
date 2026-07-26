"""Style-shell kit pieces — forecourt walls, doorcases, porch posts, bargeboards.

WHY THIS EXISTS: style packs that only swap window/door *tags* still read as the same
4×3 box. These pieces give unmistakable silhouette vocabulary per pack (low front
garden walls, entrance doorcases, porch posts, gable bargeboards, chimney stubs)
without baked textures.

Kinds reused (handbook §3 — no half-registered kinds):
  * ``barrier`` — forecourt / garden walls (tile on boundary lines like fences)
  * ``band`` — doorcases and bargeboards (face-attached projection contract)
  * ``column`` — porch posts (structural-looking posts flanking an entrance)
  * ``roofline`` — chimney stubs (short stack on pitched roofs)

Handbook seven questions (forecourt_wall):
  1. Touch — south façade wall / ground plinth (placed via boundary outward kiss)
  2. Under — ground / site (vertical_support via ground_plinth or surface)
  3. Not overlap — door bay left open; not interior decks
  4. Not stick through — waist-high, clear of openings
  5. Isolation — tagged ``attached`` + ``style_shell``; must kiss building
     (not island-exempt — freestanding catches orphans)
  6. Interaction — no walk-through; gap at door bay for approach
  7. Spec — style pack ``shell.forecourt`` requests them

Door surround (runtime): ``style_apply`` places wall-flush jambs + lintel
(``band_pilaster`` / ``band_course`` strips) — not the freestanding U-portal
meshes below. Those descriptors remain for mesh/catalog completeness but are
not placed as proud portals (they read as a frame dropped on the ground).
Stoop = shallow ``steps_external``; forecourt = low garden walls with door gap.
Porch posts are not placed (read as mystery rails).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pae.contract import MODULE_CM, STOREY_CM, WALL_T_CM
from pae.primitives.types import PrimitiveDescriptor, SocketDesc, module_tag

BoxPart = Tuple[Tuple[float, float, float], Tuple[float, float, float]]

# Fractions of contract dims — never bare centimetres in descriptors.
_FORECOURT_H_FRAC = 0.32  # of STOREY — low stone garden wall
_FORECOURT_T_FRAC = 0.72  # of WALL_T — chunkier than a fence, thinner than a wall
_DOORCASE_PROJ_FRAC = 0.45  # of WALL_T — projects past façade
_DOORCASE_H_FRAC = 0.92  # of STOREY — frames the leaf
_DOORCASE_RUN_FRAC = 0.72  # of MODULE — centred on door bay
_PORCH_POST_W_FRAC = 0.12  # of MODULE
_PORCH_POST_H_FRAC = 0.55  # of STOREY — half-height porch posts
_BARGE_PROJ_FRAC = 0.35  # of WALL_T
_BARGE_H_FRAC = 0.18  # of STOREY
_CHIMNEY_STUB_W_FRAC = 0.18  # of MODULE
_CHIMNEY_STUB_H_FRAC = 0.55  # of STOREY — short stack, not full chimney_stack


def _barrier_sockets(height_cm: float, thick_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "barrier", "style_shell"})
    return (
        SocketDesc(
            name="end_a",
            pos_cm=(thick_cm * 0.5, 0.0, height_cm * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="barrier_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(thick_cm * 0.5, MODULE_CM, height_cm * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="barrier_end",
            tags=tag,
        ),
        SocketDesc(
            name="bottom",
            pos_cm=(thick_cm * 0.5, MODULE_CM * 0.5, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="barrier_base",
            tags=tag,
        ),
        SocketDesc(
            name="back",
            pos_cm=(0.0, MODULE_CM * 0.5, height_cm * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_face",
            tags=tag,
        ),
    )


def _band_sockets(size_cm: Tuple[float, float, float], piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "band", "style_shell"})
    sx, sy, sz = size_cm
    return (
        SocketDesc(
            name="back",
            pos_cm=(0.0, sy * 0.5, sz * 0.5),
            normal=(-1.0, 0.0, 0.0),
            type="wall_face",
            tags=tag,
        ),
        SocketDesc(
            name="end_a",
            pos_cm=(sx * 0.5, 0.0, sz * 0.5),
            normal=(0.0, -1.0, 0.0),
            type="band_end",
            tags=tag,
        ),
        SocketDesc(
            name="end_b",
            pos_cm=(sx * 0.5, sy, sz * 0.5),
            normal=(0.0, 1.0, 0.0),
            type="band_end",
            tags=tag,
        ),
    )


def _column_sockets(width_cm: float, height_cm: float, piece: str) -> tuple:
    tag = frozenset({module_tag(), piece, "column", "style_shell"})
    half = MODULE_CM * 0.5
    return (
        SocketDesc(
            name="bottom",
            pos_cm=(half, half, 0.0),
            normal=(0.0, 0.0, -1.0),
            type="column_base",
            tags=tag,
        ),
        SocketDesc(
            name="top",
            pos_cm=(half, half, height_cm),
            normal=(0.0, 0.0, 1.0),
            type="column_head",
            tags=tag,
        ),
    )


def forecourt_wall() -> PrimitiveDescriptor:
    """Low stone garden / forecourt wall — one module run, waist-high."""
    h = STOREY_CM * _FORECOURT_H_FRAC
    t = WALL_T_CM * _FORECOURT_T_FRAC
    return PrimitiveDescriptor(
        id="forecourt_wall",
        kind="barrier",
        footprint_modules=(1, 1),
        height_storeys=_FORECOURT_H_FRAC,
        size_cm=(t, MODULE_CM, h),
        sockets=_barrier_sockets(h, t, "forecourt_wall"),
        tags=frozenset(
            {
                "barrier",
                "forecourt",
                "garden_wall",
                "exterior",
                "attached",
                "style_shell",
                "stone",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes=(
            "Attached low stone forecourt wall. Place on exterior approach cells "
            "via boundary outward offset; leave door bay clear."
        ),
    )


def _doorcase(piece_id: str, *, run_frac: float, h_frac: float, tags: frozenset, notes: str) -> PrimitiveDescriptor:
    sx = WALL_T_CM * _DOORCASE_PROJ_FRAC
    sy = MODULE_CM * run_frac
    sz = STOREY_CM * h_frac
    return PrimitiveDescriptor(
        id=piece_id,
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=h_frac,
        size_cm=(sx, sy, sz),
        sockets=_band_sockets((sx, sy, sz), piece_id),
        tags=frozenset(
            {"band", "doorcase", "entrance", "trim", "style_shell", module_tag()}
        )
        | tags,
        origin="min_corner",
        notes=notes,
    )


def doorcase_plain() -> PrimitiveDescriptor:
    return _doorcase(
        "doorcase_plain",
        run_frac=_DOORCASE_RUN_FRAC,
        h_frac=_DOORCASE_H_FRAC,
        tags=frozenset({"plain", "timber"}),
        notes="Simple rectangular door surround for rustic / townhouse.",
    )


def doorcase_arched() -> PrimitiveDescriptor:
    return _doorcase(
        "doorcase_arched",
        run_frac=_DOORCASE_RUN_FRAC * 1.05,
        h_frac=_DOORCASE_H_FRAC,
        tags=frozenset({"arched", "stone"}),
        notes="Round-headed stone doorcase for medieval / keep.",
    )


def doorcase_grand() -> PrimitiveDescriptor:
    return _doorcase(
        "doorcase_grand",
        run_frac=min(0.95, _DOORCASE_RUN_FRAC * 1.25),
        h_frac=1.0,
        tags=frozenset({"grand", "ornate", "stone"}),
        notes="Wide ornate doorcase for manor / civic entrances.",
    )


def doorcase_gothic() -> PrimitiveDescriptor:
    return _doorcase(
        "doorcase_gothic",
        run_frac=_DOORCASE_RUN_FRAC,
        h_frac=1.0,
        tags=frozenset({"gothic", "pointed", "stone"}),
        notes="Pointed / lancet doorcase for academy styles.",
    )


def porch_post() -> PrimitiveDescriptor:
    """Half-height square porch post flanking a grand entrance."""
    w = MODULE_CM * _PORCH_POST_W_FRAC
    h = STOREY_CM * _PORCH_POST_H_FRAC
    # Centred in bay like other columns, min_corner origin.
    return PrimitiveDescriptor(
        id="porch_post",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=_PORCH_POST_H_FRAC,
        size_cm=(w, w, h),
        sockets=_column_sockets(w, h, "porch_post"),
        tags=frozenset(
            {
                "column",
                "porch",
                "post",
                "entrance",
                "style_shell",
                "stone",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Porch post — place flanking the door bay on the approach face.",
    )


def bargeboard() -> PrimitiveDescriptor:
    """Gable-edge bargeboard strip — timber / stone rake trim."""
    sx = WALL_T_CM * _BARGE_PROJ_FRAC
    sy = MODULE_CM
    sz = STOREY_CM * _BARGE_H_FRAC
    return PrimitiveDescriptor(
        id="bargeboard",
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=_BARGE_H_FRAC,
        size_cm=(sx, sy, sz),
        sockets=_band_sockets((sx, sy, sz), "bargeboard"),
        tags=frozenset(
            {"band", "bargeboard", "gable", "roof_trim", "style_shell", module_tag()}
        ),
        origin="min_corner",
        notes="Bargeboard on gable ends — pitched-roof packs only.",
    )


def chimney_stub() -> PrimitiveDescriptor:
    """Short chimney stub for rustic / manor roof silhouette."""
    w = MODULE_CM * _CHIMNEY_STUB_W_FRAC
    h = STOREY_CM * _CHIMNEY_STUB_H_FRAC
    half = w * 0.5
    tag = frozenset({module_tag(), "chimney_stub", "roofline", "style_shell"})
    return PrimitiveDescriptor(
        id="chimney_stub",
        kind="roofline",
        footprint_modules=(1, 1),
        height_storeys=_CHIMNEY_STUB_H_FRAC,
        size_cm=(w, w, h),
        sockets=(
            SocketDesc(
                name="bottom",
                pos_cm=(half, half, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="roof_mount",
                tags=tag,
            ),
            SocketDesc(
                name="top",
                pos_cm=(half, half, h),
                normal=(0.0, 0.0, 1.0),
                type="chimney_cap",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {"roofline", "chimney", "stub", "style_shell", "masonry", module_tag()}
        ),
        origin="min_corner",
        notes="Short chimney stub on pitched roofs — silhouette cue, not full stack.",
    )


_PORCH_SLAB_H_FRAC = 0.12  # of STOREY — raised deck / engawa / shop platform
_PORCH_ROOF_H_FRAC = 0.06  # of STOREY — canopy thickness
_PORCH_ROOF_DEPTH_FRAC = 0.55  # of MODULE — projects out over steps
_PLANTER_H_FRAC = 0.22  # of STOREY — low planter / terrace wall


def porch_slab() -> PrimitiveDescriptor:
    """Raised entrance deck — farmhouse porch, engawa, or street shop platform."""
    h = STOREY_CM * _PORCH_SLAB_H_FRAC
    depth = MODULE_CM * 0.55
    width = MODULE_CM * 0.95
    return PrimitiveDescriptor(
        id="porch_slab",
        kind="surface",
        footprint_modules=(1, 1),
        height_storeys=_PORCH_SLAB_H_FRAC,
        size_cm=(depth, width, h),
        sockets=(
            SocketDesc(
                name="bottom",
                pos_cm=(depth * 0.5, width * 0.5, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="surface_base",
                tags=frozenset({module_tag(), "porch_slab", "style_shell"}),
            ),
            SocketDesc(
                name="top",
                pos_cm=(depth * 0.5, width * 0.5, h),
                normal=(0.0, 0.0, 1.0),
                type="surface_deck",
                tags=frozenset({module_tag(), "porch_slab", "style_shell"}),
            ),
        ),
        tags=frozenset(
            {
                "surface",
                "porch",
                "deck",
                "platform",
                "entrance",
                "attached",
                "style_shell",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Raised porch / shop platform — place projecting from door bay via outward_offset.",
    )


def porch_roof() -> PrimitiveDescriptor:
    """Entry canopy / awning / porch roof — MUST sit ABOVE the door opening.

    Kind ``band`` so vertical_support is the face-attachment contract (handbook §3),
    not a floating slab on posts. Projection = local X (deep awning).
    """
    h = STOREY_CM * _PORCH_ROOF_H_FRAC
    depth = MODULE_CM * _PORCH_ROOF_DEPTH_FRAC
    width = MODULE_CM * 0.98
    return PrimitiveDescriptor(
        id="porch_roof",
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=_PORCH_ROOF_H_FRAC,
        size_cm=(depth, width, h),
        sockets=_band_sockets((depth, width, h), "porch_roof"),
        tags=frozenset(
            {
                "band",
                "porch",
                "awning",
                "canopy",
                "entrance",
                "attached",
                "style_shell",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes=(
            "Porch roof / awning as a deep face-attached band at door-head Z — "
            "never a freestanding portal on the ground."
        ),
    )


def planter_wall() -> PrimitiveDescriptor:
    """Low capped planter / terrace wall — shorter than forecourt_wall."""
    h = STOREY_CM * _PLANTER_H_FRAC
    t = WALL_T_CM * 0.85
    return PrimitiveDescriptor(
        id="planter_wall",
        kind="barrier",
        footprint_modules=(1, 1),
        height_storeys=_PLANTER_H_FRAC,
        size_cm=(t, MODULE_CM, h),
        sockets=_barrier_sockets(h, t, "planter_wall"),
        tags=frozenset(
            {
                "barrier",
                "planter",
                "terrace",
                "forecourt",
                "garden_wall",
                "exterior",
                "attached",
                "style_shell",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Low planter / terrace wall with coping — leave door bay clear.",
    )


# ---------------------------------------------------------------------------
# MP-WS-K2 — window sill / hood / box, balcony deck / bracket
# ---------------------------------------------------------------------------

_SILL_PROJ_FRAC = 0.28  # of WALL_T — projects past façade
_SILL_H_FRAC = 0.035  # of STOREY — thin projecting sill
_HOOD_PROJ_FRAC = 0.40
_HOOD_H_FRAC = 0.045
_WINDOW_BOX_PROJ_FRAC = 0.55  # of MODULE depth
_WINDOW_BOX_H_FRAC = 0.10
_BALCONY_DEPTH_FRAC = 0.70  # of MODULE — walkable depth
_BALCONY_DECK_H_FRAC = 0.06  # of STOREY
_BALCONY_BRACKET_H_FRAC = 0.28  # of STOREY — under-deck support


def window_sill() -> PrimitiveDescriptor:
    """Projecting sill under a window opening — sized to opening width at place time."""
    sx = WALL_T_CM * _SILL_PROJ_FRAC
    sy = MODULE_CM * 0.42  # default; arch_detail resizes to opening run
    sz = STOREY_CM * _SILL_H_FRAC
    return PrimitiveDescriptor(
        id="window_sill",
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=_SILL_H_FRAC,
        size_cm=(sx, sy, sz),
        sockets=_band_sockets((sx, sy, sz), "window_sill"),
        tags=frozenset(
            {
                "band",
                "window_sill",
                "sill",
                "trim",
                "attached",
                "style_shell",
                "arch_detail",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Projecting sill below an opening — never on blank walls.",
    )


def window_hood() -> PrimitiveDescriptor:
    """Shallow hood / drip mould above a window (manor / civic / gothic)."""
    sx = WALL_T_CM * _HOOD_PROJ_FRAC
    sy = MODULE_CM * 0.48
    sz = STOREY_CM * _HOOD_H_FRAC
    return PrimitiveDescriptor(
        id="window_hood",
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=_HOOD_H_FRAC,
        size_cm=(sx, sy, sz),
        sockets=_band_sockets((sx, sy, sz), "window_hood"),
        tags=frozenset(
            {
                "band",
                "window_hood",
                "hood",
                "lintel",
                "trim",
                "attached",
                "style_shell",
                "arch_detail",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Optional head/hood above window openings.",
    )


def window_box() -> PrimitiveDescriptor:
    """Attached window-box planter — below sill, does not block the opening."""
    depth = MODULE_CM * _WINDOW_BOX_PROJ_FRAC * 0.35
    width = MODULE_CM * 0.36
    h = STOREY_CM * _WINDOW_BOX_H_FRAC
    return PrimitiveDescriptor(
        id="window_box",
        kind="band",
        footprint_modules=(1, 1),
        height_storeys=_WINDOW_BOX_H_FRAC,
        size_cm=(depth, width, h),
        sockets=_band_sockets((depth, width, h), "window_box"),
        tags=frozenset(
            {
                "band",
                "window_box",
                "planter",
                "prop",
                "attached",
                "style_shell",
                "arch_detail",
                "vegetation_socket",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Small window-box planter under selected windows; sparse + deterministic.",
    )


def balcony_deck() -> PrimitiveDescriptor:
    """Walkable upper balcony deck — floor-datum slab projecting from façade."""
    depth = MODULE_CM * _BALCONY_DEPTH_FRAC
    width = MODULE_CM * 0.95
    h = STOREY_CM * _BALCONY_DECK_H_FRAC
    return PrimitiveDescriptor(
        id="balcony_deck",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=_BALCONY_DECK_H_FRAC,
        size_cm=(depth, width, h),
        sockets=(
            SocketDesc(
                name="bottom",
                pos_cm=(depth * 0.5, width * 0.5, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="floor_base",
                tags=frozenset({module_tag(), "balcony_deck", "style_shell"}),
            ),
            SocketDesc(
                name="top",
                pos_cm=(depth * 0.5, width * 0.5, h),
                normal=(0.0, 0.0, 1.0),
                type="floor_deck",
                tags=frozenset({module_tag(), "balcony_deck", "style_shell"}),
            ),
        ),
        tags=frozenset(
            {
                "floor",
                "balcony",
                "deck",
                "walkable",
                "attached",
                "style_shell",
                "arch_detail",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes=(
            "Functional balcony deck at upper floor datum. Requires balcony_door, "
            "exposed-edge guards, and structural supports."
        ),
    )


def balcony_bracket() -> PrimitiveDescriptor:
    """Under-deck bracket / support for a projecting balcony."""
    depth = MODULE_CM * 0.28
    width = MODULE_CM * 0.12
    h = STOREY_CM * _BALCONY_BRACKET_H_FRAC
    return PrimitiveDescriptor(
        id="balcony_bracket",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=_BALCONY_BRACKET_H_FRAC,
        size_cm=(depth, width, h),
        sockets=_column_sockets(width, h, "balcony_bracket"),
        tags=frozenset(
            {
                "column",
                "balcony",
                "support",
                "bracket",
                "attached",
                "style_shell",
                "arch_detail",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes="Structural balcony bracket under the deck — not decorative alone.",
    )


# ---------------------------------------------------------------------------
# Machiya / minka set — the deep-eave timber vocabulary
#
# ATTACHMENT CONTRACT for these three, enforced by ``validate_machiya`` in
# ``pae/machiya.py``. Written here so the rules travel with the geometry:
#
#   engawa_deck    must BEAR on an exterior wall face at floor datum, project
#                  OUTWARD only, and never cover an interior cell. It is walkable,
#                  so it must also be reachable — a veranda you cannot step onto is
#                  a shelf.
#   engawa_post    must stand UNDER an engawa deck, at its outer edge, on ground.
#                  A post inboard of the deck edge is inside the crawl space.
#   eave_bracket   must sit UNDER a roof overhang and ABOVE a wall head, on the
#                  same face. A bracket carrying nothing is a peg on a wall.
#
# All three are ``attached`` + ``style_shell``, so ``freestanding`` catches orphans
# rather than letting them float.
# ---------------------------------------------------------------------------

_ENGAWA_DEPTH_FRAC = 0.34   # of MODULE — one comfortable pace, not a room
_ENGAWA_DECK_H_FRAC = 0.09  # of STOREY
_ENGAWA_POST_W_FRAC = 0.07  # of MODULE
_EAVE_BRACKET_D_FRAC = 0.22  # of MODULE — projection under the overhang
_EAVE_BRACKET_H_FRAC = 0.14  # of STOREY


def engawa_deck() -> PrimitiveDescriptor:
    """Raised veranda running along a facade — the machiya/minka engawa.

    Not a balcony: it sits at GROUND floor datum and wraps the outside of the wall,
    which is why it needs posts under its outer edge rather than brackets.
    """
    depth = MODULE_CM * _ENGAWA_DEPTH_FRAC
    width = MODULE_CM
    h = STOREY_CM * _ENGAWA_DECK_H_FRAC
    tag = frozenset({module_tag(), "engawa", "style_shell"})
    return PrimitiveDescriptor(
        id="engawa_deck",
        kind="floor",
        footprint_modules=(1, 1),
        height_storeys=_ENGAWA_DECK_H_FRAC,
        size_cm=(depth, width, h),
        sockets=(
            SocketDesc(
                name="back",
                pos_cm=(depth, width * 0.5, h * 0.5),
                normal=(1.0, 0.0, 0.0),
                type="wall_face",
                tags=tag,
            ),
            SocketDesc(
                name="top",
                pos_cm=(depth * 0.5, width * 0.5, h),
                normal=(0.0, 0.0, 1.0),
                type="floor_deck",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {
                # NB: deliberately NOT tagged "deck"/"attached". `footprint_overlap`
                # partitions floors into RANGES by tag, so those two turned every
                # veranda into a rival building overlapping its own host
                # ("ranges 'attached' and 'deck' overlap on 9 floor cells").
                # A veranda is part of the building it is bolted to, not a range.
                "floor",
                "engawa",
                "walkable",
                "exterior",
                "style_shell",
                module_tag(),
            }
        ),
        origin="min_corner",
        notes=(
            "Veranda deck at ground datum; BACK face (+X) mates to the wall, so use "
            "trim._pier_pose, never outward_offset_cm. Needs engawa_post under its "
            "outer edge."
        ),
    )


def engawa_post() -> PrimitiveDescriptor:
    """Slender post carrying the outer edge of an engawa deck."""
    w = MODULE_CM * _ENGAWA_POST_W_FRAC
    h = STOREY_CM * _ENGAWA_DECK_H_FRAC
    tag = frozenset({module_tag(), "engawa", "style_shell"})
    return PrimitiveDescriptor(
        id="engawa_post",
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=_ENGAWA_DECK_H_FRAC,
        size_cm=(w, w, h),
        sockets=(
            SocketDesc(
                name="bottom",
                pos_cm=(w * 0.5, w * 0.5, 0.0),
                normal=(0.0, 0.0, -1.0),
                type="column_base",
                tags=tag,
            ),
            SocketDesc(
                name="top",
                pos_cm=(w * 0.5, w * 0.5, h),
                normal=(0.0, 0.0, 1.0),
                type="column_head",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {"column", "engawa", "structural", "attached", "exterior",
             "style_shell", module_tag()}
        ),
        origin="min_corner",
        notes="Stands on ground under the engawa's OUTER edge. Never inboard of it.",
    )


def eave_bracket() -> PrimitiveDescriptor:
    """Bracket under a deep eave — the visual signature of the temple/minka roof."""
    depth = MODULE_CM * _EAVE_BRACKET_D_FRAC
    w = MODULE_CM * 0.16
    h = STOREY_CM * _EAVE_BRACKET_H_FRAC
    tag = frozenset({module_tag(), "eave_bracket", "style_shell"})
    return PrimitiveDescriptor(
        id="eave_bracket",
        # COLUMN, not band. A band RUNS ALONG a wall and its contract measures contact
        # over its length; a bracket PROJECTS OUT of one, so it reported "contacts its
        # wall over 0 of 88 cm" — the 88 was its depth. A corbel is the same species as
        # `pilaster` and `buttress`: a small structural projection off a wall face.
        kind="column",
        footprint_modules=(1, 1),
        height_storeys=_EAVE_BRACKET_H_FRAC,
        size_cm=(depth, w, h),
        sockets=(
            SocketDesc(
                name="back",
                pos_cm=(depth, w * 0.5, h * 0.5),
                normal=(1.0, 0.0, 0.0),
                type="wall_face",
                tags=tag,
            ),
        ),
        tags=frozenset(
            {"column", "eave_bracket", "decorative", "attached", "exterior",
             "style_shell", module_tag()}
        ),
        origin="min_corner",
        notes=(
            "Corbel at the wall head carrying a deep eave. BACK (+X) mates to the "
            "wall, so place with trim._pier_pose. Sits IN the wall head, not up at "
            "the roof underside — see pae/machiya.py."
        ),
    )


def all_style_shell() -> tuple:
    return (
        forecourt_wall(),
        planter_wall(),
        doorcase_plain(),
        doorcase_arched(),
        doorcase_grand(),
        doorcase_gothic(),
        porch_post(),
        porch_slab(),
        porch_roof(),
        bargeboard(),
        chimney_stub(),
        window_sill(),
        window_hood(),
        window_box(),
        balcony_deck(),
        balcony_bracket(),
        engawa_deck(),
        engawa_post(),
        eave_bracket(),
    )


# ---------------------------------------------------------------------------
# Mesh builders (box-kit — no baked textures)
# ---------------------------------------------------------------------------


def _forecourt_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    tx, ty, tz = size_cm
    coping_h = tz * 0.14
    return [
        ((0.0, 0.0, 0.0), (tx, ty, tz - coping_h)),
        ((-tx * 0.08, 0.0, tz - coping_h), (tx * 1.16, ty, coping_h)),
    ]


def _doorcase_parts(size_cm: Tuple[float, float, float], *, arched: bool, pointed: bool) -> List[BoxPart]:
    """U-shaped surround: two jambs + lintel (+ arched / pointed head blocks)."""
    sx, sy, sz = size_cm
    jamb_w = sy * 0.14
    lintel_h = sz * 0.14
    parts: List[BoxPart] = [
        ((0.0, 0.0, 0.0), (sx, jamb_w, sz)),
        ((0.0, sy - jamb_w, 0.0), (sx, jamb_w, sz)),
        ((0.0, 0.0, sz - lintel_h), (sx, sy, lintel_h)),
    ]
    if arched or pointed:
        # Stepped head above the lintel reads as arch / lancet at kit scale.
        head_h = sz * 0.18
        steps = 5 if pointed else 4
        for i in range(steps):
            t = (i + 1) / (steps + 1)
            inset = sy * (0.08 + 0.10 * t) if pointed else sy * (0.06 + 0.05 * t)
            z0 = sz - lintel_h - head_h * (1.0 - t)
            zh = head_h / steps
            parts.append(((0.0, inset, z0), (sx * 1.05, sy - 2.0 * inset, zh)))
    return parts


def _porch_post_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    # Centre the post in its MODULE bay (column convention).
    cx = MODULE_CM * 0.5
    cy = MODULE_CM * 0.5
    base_h = sz * 0.12
    cap_h = sz * 0.10
    parts: List[BoxPart] = [
        ((cx - sx * 0.65, cy - sy * 0.65, 0.0), (sx * 1.3, sy * 1.3, base_h)),
        ((cx - sx * 0.5, cy - sy * 0.5, base_h), (sx, sy, sz - base_h - cap_h)),
        ((cx - sx * 0.7, cy - sy * 0.7, sz - cap_h), (sx * 1.4, sy * 1.4, cap_h)),
    ]
    return parts


def _bargeboard_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.55)),
        ((0.0, 0.0, sz * 0.55), (sx * 0.7, sy, sz * 0.45)),
    ]


def _chimney_stub_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.82)),
        ((-sx * 0.1, -sy * 0.1, sz * 0.82), (sx * 1.2, sy * 1.2, sz * 0.18)),
    ]


def _porch_slab_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    # Deck top + slight edge nosing so it reads as a raised platform.
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.82)),
        ((-sx * 0.04, -sy * 0.02, sz * 0.82), (sx * 1.08, sy * 1.04, sz * 0.18)),
    ]


def _porch_roof_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    # Flat canopy + thin fascia lip at the outer edge.
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.70)),
        ((sx * 0.85, 0.0, -sz * 0.35), (sx * 0.15, sy, sz * 1.05)),
    ]


def _window_sill_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.70)),
        ((sx * 0.15, -sy * 0.02, sz * 0.70), (sx * 0.95, sy * 1.04, sz * 0.30)),
    ]


def _window_hood_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.55)),
        ((0.0, sy * 0.05, sz * 0.55), (sx * 1.05, sy * 0.90, sz * 0.45)),
    ]


def _window_box_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    wall = sx * 0.12
    return [
        # Box floor + three walls (open toward façade attach face at x=0).
        ((0.0, 0.0, 0.0), (sx, sy, wall)),
        ((0.0, 0.0, wall), (wall, sy, sz - wall)),
        ((0.0, 0.0, wall), (sx, wall, sz - wall)),
        ((0.0, sy - wall, wall), (sx, wall, sz - wall)),
        ((sx - wall, 0.0, wall), (wall, sy, sz - wall)),
    ]


def _balcony_deck_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    return [
        ((0.0, 0.0, 0.0), (sx, sy, sz * 0.75)),
        ((-sx * 0.02, -sy * 0.02, sz * 0.75), (sx * 1.04, sy * 1.04, sz * 0.25)),
    ]


def _balcony_bracket_parts(size_cm: Tuple[float, float, float]) -> List[BoxPart]:
    sx, sy, sz = size_cm
    # Diagonal-ish stepped bracket under the deck.
    return [
        ((0.0, 0.0, sz * 0.55), (sx, sy, sz * 0.45)),
        ((0.0, 0.0, sz * 0.25), (sx * 0.65, sy, sz * 0.30)),
        ((0.0, 0.0, 0.0), (sx * 0.35, sy, sz * 0.25)),
    ]


def build_style_shell_mesh(desc: PrimitiveDescriptor, *, name: Optional[str] = None):
    from pae.primitives import bpy_util

    bpy_util.require_bpy()
    obj_name = name or desc.id
    aid = desc.id
    if aid in ("forecourt_wall", "planter_wall"):
        parts = _forecourt_parts(desc.size_cm)
    elif aid == "doorcase_plain":
        parts = _doorcase_parts(desc.size_cm, arched=False, pointed=False)
    elif aid == "doorcase_arched":
        parts = _doorcase_parts(desc.size_cm, arched=True, pointed=False)
    elif aid == "doorcase_grand":
        parts = _doorcase_parts(desc.size_cm, arched=True, pointed=False)
    elif aid == "doorcase_gothic":
        parts = _doorcase_parts(desc.size_cm, arched=False, pointed=True)
    elif aid == "porch_post":
        parts = _porch_post_parts(desc.size_cm)
    elif aid == "porch_slab":
        parts = _porch_slab_parts(desc.size_cm)
    elif aid == "porch_roof":
        parts = _porch_roof_parts(desc.size_cm)
    elif aid == "bargeboard":
        parts = _bargeboard_parts(desc.size_cm)
    elif aid == "chimney_stub":
        parts = _chimney_stub_parts(desc.size_cm)
    elif aid == "window_sill":
        parts = _window_sill_parts(desc.size_cm)
    elif aid == "window_hood":
        parts = _window_hood_parts(desc.size_cm)
    elif aid == "window_box":
        parts = _window_box_parts(desc.size_cm)
    elif aid == "balcony_deck":
        parts = _balcony_deck_parts(desc.size_cm)
    elif aid == "balcony_bracket":
        parts = _balcony_bracket_parts(desc.size_cm)
    else:
        parts = [((0.0, 0.0, 0.0), desc.size_cm)]
    return bpy_util.build_mesh_from_box_parts(
        obj_name, parts, origin_at_min_corner=True
    )


__all__ = [
    "all_style_shell",
    "balcony_bracket",
    "balcony_deck",
    "bargeboard",
    "build_style_shell_mesh",
    "chimney_stub",
    "doorcase_arched",
    "doorcase_gothic",
    "doorcase_grand",
    "doorcase_plain",
    "forecourt_wall",
    "planter_wall",
    "porch_post",
    "porch_roof",
    "porch_slab",
    "window_box",
    "window_hood",
    "window_sill",
]

"""Pytest plugin: revert this session's stair SEMANTICS, keep the hang + perf fixes.

Used only to measure which failures pre-date the stair work. The recursion fix in
``check_floor_islands`` cannot be reverted - the old code never terminated.
"""

from pae.plan import CellRole


def pytest_configure(config):
    import pae.assemble as A
    import pae.validate as V

    A._continuous_shaft_cells = lambda fp, level: (
        set()
        if level <= 0 or level >= len(fp.storeys)
        else {c for c, r in fp.storeys[level].cells.items() if r == CellRole.STAIR}
    )
    A._flight_anchor_in_pad = lambda pad, other, kind, yaw, axis: (
        min(c[0] for c in pad),
        min(c[1] for c in pad),
    )
    A._flight_footprint_from_anchor = lambda anchor, kind, yaw, pad: list(pad)
    A._pads_flip_yaw = lambda axis, yaw: True

    _orig = V._check_floor_respects_plan_voids

    def _with_stair_forbidden(assembly):
        from pae.contract import storey_datum_z_cm
        from pae.report import Failure
        from pae.trim import covered_cells

        forbidden = {
            CellRole.COURTYARD,
            CellRole.VOID,
            CellRole.DOUBLE_VOID,
            CellRole.STAIR,
        }
        out = []
        for p in assembly.placements:
            if (
                p.kind != "floor"
                or p.asset_id == "floor_hole"
                or p.level <= 0
                or "tower_room_floor" in p.tags
                or "tower_entry_landing" in p.tags
            ):
                continue
            layer = assembly.floor_plan.get(p.level)
            if layer is None:
                continue
            for cx, cy in sorted(covered_cells(p)):
                role = layer.role_at(cx, cy)
                if role not in forbidden:
                    continue
                out.append(
                    Failure(
                        check="floor_respects_plan_voids",
                        message=f"{p.piece_id} covers {role.name} cell ({cx}, {cy})",
                        world_xyz=None,
                        piece_id=p.piece_id,
                        critical=True,
                    )
                )
        return out

    V._check_floor_respects_plan_voids = _with_stair_forbidden

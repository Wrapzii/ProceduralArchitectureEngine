"""Unit tests for socket auto-proposal."""

from pae.assets.sockets import GeometryDescriptor, propose_sockets, sockets_compatible
from pae.contract import MODULE_CM, WALL_T_CM


def test_wall_sockets_along_y():
    desc = GeometryDescriptor(size_cm=(WALL_T_CM, MODULE_CM, 350.0), kind="wall")
    sockets = propose_sockets(desc)
    names = {s.name for s in sockets}
    assert names == {"end_a", "end_b"}
    end_a = next(s for s in sockets if s.name == "end_a")
    assert end_a.type == "wall_end"
    assert end_a.normal == (0.0, -1.0, 0.0)


def test_floor_four_edges():
    desc = GeometryDescriptor(size_cm=(MODULE_CM, MODULE_CM, 30.0), kind="floor")
    sockets = propose_sockets(desc)
    assert len(sockets) == 4
    assert all(s.type == "floor_edge" for s in sockets)


def test_stair_bottom_top():
    desc = GeometryDescriptor(size_cm=(MODULE_CM * 2, MODULE_CM, 350.0), kind="stair")
    sockets = propose_sockets(desc)
    by_name = {s.name: s for s in sockets}
    assert by_name["bottom"].pos_cm[2] == 0.0
    assert by_name["top"].pos_cm[2] == 350.0


def test_tower_arc_centred_sockets():
    desc = GeometryDescriptor(
        size_cm=(MODULE_CM, MODULE_CM, 350.0),
        kind="tower_arc",
        rotates_about_center=True,
    )
    sockets = propose_sockets(desc)
    for sock in sockets:
        assert abs(sock.pos_cm[0]) <= MODULE_CM * 0.5
        assert abs(sock.pos_cm[1]) <= MODULE_CM * 0.5


def test_socket_compatibility():
    a = propose_sockets(GeometryDescriptor((WALL_T_CM, MODULE_CM, 350.0), "wall"))[0]
    b = propose_sockets(GeometryDescriptor((WALL_T_CM, MODULE_CM, 350.0), "wall"))[1]
    assert sockets_compatible(a, b)

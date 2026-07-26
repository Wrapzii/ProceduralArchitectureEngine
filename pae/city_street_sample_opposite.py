"""Grok street frontage — south lane facing Composer across the road.

True across-the-street layout: same X columns as ``street_lots()``, south (−Y).
No eastward extension / north partner row (that was the confusing perpendicular split).

    from pae.city_street_sample import build_street
    build_street(side="both")  # Composer north + Grok south
"""

from __future__ import annotations

from typing import List

from pae.city_street_sample import StreetLot

# Local sketches — equal-length rows; S = stair for multi-storey walkability.
OPP_SHOP_1 = """
######
######
"""

OPP_SHOP_2 = """
######
######
##S###
######
######
"""

OPP_SHOP_3 = """
########
########
###S####
########
########
"""

OPP_MARKET = """
########
########
########
"""

OPP_INN = """
#######
#######
##S####
#######
#######
#######
"""

OPP_LONGHOUSE = """
#########
#########
###S#####
#########
#########
"""


def opp_noble_manor_spec():
    """Grand opposite-side manor — warm stone/manor massing, corner towers."""
    from pae.spec import (
        BuildingSpec,
        CirculationSpec,
        FootprintSpec,
        OpeningPolicy,
        RoofSpec,
        TowerSpec,
    )

    return BuildingSpec(
        name="opp_noble_manor",
        style="manor",
        footprint=FootprintSpec(kind="rect", bays_x=7, bays_y=5),
        storeys=4,
        storey_use=["hall"] * 4,
        towers=[
            TowerSpec(cell=(0, 0), storeys=4),
            TowerSpec(cell=(6, 4), storeys=5),
        ],
        roof=RoofSpec(kind="pitched", pitch=1.75),
        circulation=CirculationSpec(stair_kind="wide", stair_cells=[(2, 2)]),
        openings=OpeningPolicy(
            windows_per_bay=2,
            doors_ground=1,
            windows_ground=None,
            skip_ground_windows=False,
        ),
        seed=142,
        ground_slab=True,
    )


OPPOSITE_SPEC_FACTORIES = {
    "opp_noble_manor_spec": opp_noble_manor_spec,
}


def opposite_lots() -> List[StreetLot]:
    """Grok lane — entire **south** frontage (−Y), X-aligned with Composer north."""
    y_s = -8
    return [
        StreetLot(
            "opp_shop_1storey",
            "commerce_1",
            1,
            (0, y_s),
            OPP_SHOP_1,
            "medieval",
            111,
        ),
        StreetLot(
            "opp_shop_2storey",
            "commerce_2",
            2,
            (7, y_s),
            OPP_SHOP_2,
            "townhouse",
            112,
        ),
        StreetLot(
            "opp_shop_3storey",
            "commerce_3",
            3,
            (15, y_s),
            OPP_SHOP_3,
            "keep",
            113,
        ),
        StreetLot(
            "opp_market_hall",
            "market",
            1,
            (24, y_s),
            OPP_MARKET,
            "civic",
            121,
        ),
        StreetLot(
            "opp_inn",
            "inn",
            2,
            (33, y_s),
            OPP_INN,
            "townhouse",
            122,
        ),
        StreetLot(
            "opp_longhouse",
            "residential",
            2,
            (41, y_s),
            OPP_LONGHOUSE,
            "medieval",
            131,
        ),
        StreetLot(
            "opp_shop_corner",
            "commerce_2",
            2,
            (51, y_s),
            OPP_SHOP_2,
            "medieval",
            132,
        ),
        StreetLot(
            "opp_noble_manor",
            "noble",
            4,
            (59, y_s - 1),
            spec_factory="opp_noble_manor_spec",
            style="manor",
            seed=142,
        ),
    ]


def opposite_side_names() -> List[str]:
    """Names counted as the Grok (south) inventory for reports."""
    return [
        "opp_shop_1storey",
        "opp_shop_2storey",
        "opp_shop_3storey",
        "opp_market_hall",
        "opp_inn",
        "opp_longhouse",
        "opp_shop_corner",
        "opp_noble_manor",
    ]

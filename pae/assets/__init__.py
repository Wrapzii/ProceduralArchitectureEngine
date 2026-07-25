"""Asset subsystem (WP-2).

Note: the design doc names `import.py`; Python cannot import a module named `import`,
so the implementation lives in `import_.py` (`pae.assets.import_`).
"""

from pae.assets.db import Asset, AssetDB, Socket
from pae.assets.fit import (
    evaluate_footprint_fit,
    footprint_modules as module_count_for_axis,
    snap_fit,
)
from pae.assets.import_ import (
    ImportResult,
    MeasuredAABB,
    center_origin_offset,
    import_asset,
    import_asset_measured,
    min_corner_origin_offset,
    normalize_to_min_corner,
    size_cm_from_aabb,
)
from pae.assets.query import (
    DEFAULT_DECOR_TAGS,
    list_by_tags,
    list_decorative_for_generator,
)
from pae.assets.sockets import GeometryDescriptor, propose_sockets, sockets_compatible

__all__ = [
    "Asset",
    "AssetDB",
    "DEFAULT_DECOR_TAGS",
    "GeometryDescriptor",
    "ImportResult",
    "MeasuredAABB",
    "Socket",
    "center_origin_offset",
    "evaluate_footprint_fit",
    "import_asset",
    "import_asset_measured",
    "list_by_tags",
    "list_decorative_for_generator",
    "min_corner_origin_offset",
    "module_count_for_axis",
    "normalize_to_min_corner",
    "propose_sockets",
    "size_cm_from_aabb",
    "snap_fit",
    "sockets_compatible",
]

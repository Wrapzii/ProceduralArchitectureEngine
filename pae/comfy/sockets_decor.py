"""Decorative socket proposals for Comfy assets.

Structural sockets live in `pae.assets.sockets`. Decorative kinds get a
placement `base` socket so humans can confirm / refine before DB commit.
"""

from __future__ import annotations

from typing import List, Tuple

from pae.assets.db import Socket
from pae.assets.sockets import GeometryDescriptor, propose_sockets
from pae.contract import MODULE_CM


def propose_decorative_sockets(size_cm: Tuple[float, float, float], kind: str) -> List[Socket]:
    """Auto-propose sockets: reuse assets.propose_sockets, then add base mount."""
    # Assets returns [] for unknown/decorative kinds — that is expected.
    base_list = list(
        propose_sockets(GeometryDescriptor(size_cm=size_cm, kind=kind))
    )
    sx, sy, _sz = size_cm
    tags = {f"module_{int(MODULE_CM)}", "decorative", kind.lower()}
    base = Socket(
        name="base",
        pos_cm=(sx * 0.5, sy * 0.5, 0.0),
        normal=(0.0, 0.0, -1.0),
        type="prop_base",
        tags=tags,
    )
    names = {s.name for s in base_list}
    if "base" not in names:
        base_list.append(base)
    return base_list

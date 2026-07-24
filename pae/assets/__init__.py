"""Asset subsystem (WP-2).

Note: the design doc names `import.py`; Python cannot import a module named `import`,
so the implementation lives in `import_.py` (`pae.assets.import_`).
"""

from pae.assets.fit import snap_fit

__all__ = ["snap_fit"]

"""Procedural Building — single public entry point.

**This module is the ONLY supported entry for CITY&BEYOND / Georgian procedural
townhouses.** Sliders compile to a continuous exterior shell via
:func:`pae.facade_shell.build_shell_assembly` (skin + floors + stairwell +
grammar-cut openings).

LEGACY — **not** Procedural Building:

- :mod:`pae.assemble` + :mod:`pae.pipeline` — fortress, school, gallery, and
  other compound builders that emit per-cell modular walls.
- :func:`pae.facade_grammar.build_from_params` with ``mode="modular"`` — debug
  path only; do not use for user-facing or demo builds.

Callers (Blender add-on, CLI tools, tests) should import
:func:`build_building` from here — not shell internals or ``assemble.py``.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from pae.facade_grammar import FacadeParams, params_to_spec
from pae.facade_shell import build_shell_assembly
from pae.report import Report
from pae.spec import BuildingSpec

__all__ = ["build_building"]


def build_building(
    params: FacadeParams,
    *,
    validate_assembly: bool = True,
    spec: Optional[BuildingSpec] = None,
    **kwargs: Any,
) -> Tuple[None, None, Any, Report, FacadeParams]:
    """Build a procedural building from facade sliders (shell mode only).

  ``kwargs`` are accepted for forward compatibility but ignored — shell assembly
  does not use modular style/detail pipeline flags.

  Returns ``(massing, floor_plan, assembly, report, params)`` where ``massing``
  and ``floor_plan`` are always ``None`` (geometry is a flat ``Assembly``).
  """
    del kwargs  # shell path — no modular style/detail flags
    spec = spec or params_to_spec(params)
    assembly, report = build_shell_assembly(params, spec)
    if validate_assembly:
        from pae.validate import validate

        _validated_asm, vreport = validate(assembly)
        report = Report.from_failures(
            list(report.failures) + list(vreport.failures)
        )
    return None, None, assembly, report, params

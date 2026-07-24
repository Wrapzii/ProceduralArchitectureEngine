"""Stage reports — every pipeline stage returns (artifact, report)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Failure:
    check: str
    message: str
    world_xyz: Optional[Tuple[float, float, float]] = None
    piece_id: Optional[str] = None
    critical: bool = True


@dataclass
class Report:
    ok: bool
    failures: List[Failure] = field(default_factory=list)
    critical: List[Failure] = field(default_factory=list)
    warnings: List[Failure] = field(default_factory=list)

    @classmethod
    def from_failures(cls, failures: List[Failure]) -> "Report":
        critical = [f for f in failures if f.critical]
        warnings = [f for f in failures if not f.critical]
        return cls(
            ok=(len(critical) == 0),
            failures=list(failures),
            critical=critical,
            warnings=warnings,
        )

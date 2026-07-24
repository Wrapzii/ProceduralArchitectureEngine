"""Session persistence — JSON codecs for validation reports (no bpy)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from pae.report import Failure, Report


def failure_to_dict(failure: Failure) -> Dict[str, Any]:
    return {
        "check": failure.check,
        "message": failure.message,
        "world_xyz": list(failure.world_xyz) if failure.world_xyz else None,
        "piece_id": failure.piece_id,
        "critical": failure.critical,
    }


def failure_from_dict(data: Dict[str, Any]) -> Failure:
    xyz = data.get("world_xyz")
    world = tuple(float(v) for v in xyz) if xyz else None
    return Failure(
        check=str(data["check"]),
        message=str(data["message"]),
        world_xyz=world,
        piece_id=data.get("piece_id"),
        critical=bool(data.get("critical", True)),
    )


def report_to_json(report: Report) -> str:
    payload = {
        "ok": report.ok,
        "failures": [failure_to_dict(f) for f in report.failures],
    }
    return json.dumps(payload, separators=(",", ":"))


def report_from_json(raw: str) -> Optional[Report]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    failures = [failure_from_dict(item) for item in data.get("failures", [])]
    return Report.from_failures(failures)

"""Loading and validation for machine-readable shared-core contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .hashing import development_shared_root


def load_route_ownership(shared_root: Path | None = None) -> Dict[str, Any]:
    root = (shared_root or development_shared_root()).resolve()
    path = root / "api_route_ownership.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported api route ownership schema")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("shared API route ownership is empty")
    keys = [(row.get("method"), row.get("path")) for row in routes]
    if len(keys) != len(set(keys)):
        raise ValueError("shared API route ownership contains duplicates")
    return payload

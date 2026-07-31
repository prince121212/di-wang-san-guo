"""Loading and validation for machine-readable shared-core contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .hashing import bundled_contract_text, development_shared_root, has_development_sources


def load_route_ownership(shared_root: Path | None = None) -> Dict[str, Any]:
    root = (shared_root or development_shared_root()).resolve()
    if shared_root is not None or has_development_sources(root):
        raw = (root / "api_route_ownership.json").read_text(encoding="utf-8")
    else:
        raw = bundled_contract_text("api_route_ownership.json")
    payload = json.loads(raw)
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported api route ownership schema")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("shared API route ownership is empty")
    keys = [(row.get("method"), row.get("path")) for row in routes]
    if len(keys) != len(set(keys)):
        raise ValueError("shared API route ownership contains duplicates")
    return payload

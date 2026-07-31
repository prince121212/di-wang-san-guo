"""Loading and validation for machine-readable shared-core contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .hashing import bundled_contract_text, development_shared_root, has_development_sources


def load_json_contract(name: str, shared_root: Path | None = None) -> Dict[str, Any]:
    root = (shared_root or development_shared_root()).resolve()
    if shared_root is not None or has_development_sources(root):
        raw = (root / name).read_text(encoding="utf-8")
    else:
        raw = bundled_contract_text(name)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"shared-core contract must be an object: {name}")
    return payload


def load_behavior_contract(shared_root: Path | None = None) -> Dict[str, Any]:
    payload = load_json_contract("assistant_behavior_contract.json", shared_root)
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported assistant behavior contract schema")
    return payload


def load_route_ownership(shared_root: Path | None = None) -> Dict[str, Any]:
    payload = load_json_contract("api_route_ownership.json", shared_root)
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported api route ownership schema")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("shared API route ownership is empty")
    keys = [(row.get("method"), row.get("path")) for row in routes]
    if len(keys) != len(set(keys)):
        raise ValueError("shared API route ownership contains duplicates")
    return payload

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
    owner_model = payload.get("currentOwnerModel")
    if not isinstance(owner_model, dict):
        raise ValueError("shared API current owner model is missing")
    allowed = set(owner_model.get("allowed") or [])
    expected_allowed = {"desktop-python", "android-kotlin", "shared-python"}
    if allowed != expected_allowed:
        raise ValueError("shared API current owner values are invalid")
    defaults = owner_model.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("shared API current owner defaults are missing")
    overrides = owner_model.get("overrides")
    if not isinstance(overrides, list):
        raise ValueError("shared API current owner overrides are invalid")
    override_by_key = {
        (str(row.get("method") or "").upper(), str(row.get("path") or "")): row
        for row in overrides
        if isinstance(row, dict)
    }
    if len(override_by_key) != len(overrides):
        raise ValueError("shared API current owner overrides contain duplicates")
    route_keys = {(str(method).upper(), str(path)) for method, path in keys}
    if not set(override_by_key).issubset(route_keys):
        raise ValueError("shared API current owner override targets unknown route")
    normalized_routes = []
    for route in routes:
        key = (str(route.get("method") or "").upper(), str(route.get("path") or ""))
        override = override_by_key.get(key) or {}
        desktop_owner = str(override.get("desktop") or defaults.get("desktop") or "")
        android_owner = str(override.get("android") or defaults.get("android") or "")
        if desktop_owner not in allowed or android_owner not in allowed:
            raise ValueError(f"shared API route has invalid current owner: {key}")
        normalized_routes.append({
            **route,
            "currentDesktopOwner": desktop_owner,
            "currentAndroidOwner": android_owner,
        })
    payload["routes"] = normalized_routes
    return payload

"""Deterministic source hashing shared by desktop and Android packaging."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


CORE_CONTRACT_NAMES = (
    "api_route_ownership.json",
    "assistant_behavior_contract.json",
    "feature_parity_matrix.json",
    "protocol_parity_fixtures.json",
)


def development_shared_root() -> Path:
    """Return the repository shared_core directory for an editable checkout."""

    return Path(__file__).resolve().parents[2]


def source_records(shared_root: Path | None = None) -> List[Tuple[str, Path]]:
    """Return every file which contributes to the cross-platform core hash."""

    root = (shared_root or development_shared_root()).resolve()
    package_root = root / "python" / "dwpm_core"
    records: List[Tuple[str, Path]] = []
    for path in sorted(package_root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            records.append((path.relative_to(root).as_posix(), path))
    pyproject = root / "python" / "pyproject.toml"
    if pyproject.is_file():
        records.append((pyproject.relative_to(root).as_posix(), pyproject))
    for name in CORE_CONTRACT_NAMES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"shared core contract is missing: {path}")
        records.append((path.relative_to(root).as_posix(), path))
    if not records:
        raise FileNotFoundError(f"shared Python core sources are missing below {root}")
    return sorted(records, key=lambda item: item[0])


def hash_records(records: Iterable[Tuple[str, bytes]]) -> str:
    """Hash normalized relative names and bytes without depending on host paths."""

    digest = hashlib.sha256()
    normalized = sorted((str(name).replace("\\", "/"), data) for name, data in records)
    for name, data in normalized:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def compute_core_hash(shared_root: Path | None = None) -> str:
    """Compute a deterministic SHA-256 over source and behavior contracts."""

    return hash_records(
        (name, path.read_bytes())
        for name, path in source_records(shared_root)
    )


def source_manifest(shared_root: Path | None = None) -> dict:
    """Return the build-time manifest which Android will package later."""

    records = source_records(shared_root)
    return {
        "schemaVersion": 1,
        "coreHash": compute_core_hash(shared_root),
        "files": [name for name, _path in records],
    }


def manifest_json(shared_root: Path | None = None) -> str:
    return json.dumps(
        source_manifest(shared_root),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

"""Desktop implementations of shared-core data, log and event ports."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Mapping

from dwpm_core.ports import PlatformPorts


class DesktopDataDirectoryPort:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def data_directory(self) -> Path:
        return self._root


class DesktopJsonlPort:
    """Small append-only host sink; shared business state stays elsewhere."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    def publish(self, event: Mapping[str, object]) -> None:
        self._append(event)

    def write(self, event: Mapping[str, object]) -> None:
        self._append(event)

    def _append(self, event: Mapping[str, object]) -> None:
        line = json.dumps(
            dict(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as output:
                output.write(line + "\n")


def create_desktop_platform_ports(data_root: Path) -> PlatformPorts:
    root = data_root.resolve()
    events = DesktopJsonlPort(root / "shared_core" / "events.jsonl")
    logs = DesktopJsonlPort(root / "shared_core" / "core.jsonl")
    return PlatformPorts(
        data_directory=DesktopDataDirectoryPort(root),
        events=events,
        logs=logs,
    )

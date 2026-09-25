"""Device-local game observations. No cloud transport or account policy here.

One file per platform/server/kind; expedition ownership stays in the durable
account ledgers, never in an expiring cache. A scan replaces only its own cell.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional


class LocalMapStore:
    def __init__(self, path: Optional[Path]) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._cells: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("version") == 1 and isinstance(value.get("cells"), dict):
                    for cell in value["cells"].values():
                        int(cell["observedAtMillis"])
                        for target in cell["targets"]:
                            if int(target["id"]) <= 0:
                                raise ValueError("invalid cached target")
                    self._cells = value["cells"]
            except (ValueError, OSError, TypeError, KeyError):
                # Recoverable observations, NOT expedition ownership.
                pass

    def observe(self, coordinate: tuple[int, int], targets: list[dict[str, Any]],
                observed_at: int, ttl: int) -> None:
        with self._lock:
            cells = {key: deepcopy(value) for key, value in self._cells.items()
                     if observed_at - int(value.get("observedAtMillis") or 0) <= ttl}
            key = f"{coordinate[0]},{coordinate[1]}"
            cells[key] = {"observedAtMillis": observed_at,
                          "targets": deepcopy(targets)}
            # Overlapping cells must not resurrect an older view of a target.
            incoming = {int(t["id"]) for t in targets}
            for other_key, cell in cells.items():
                if other_key != key:
                    cell["targets"] = [t for t in cell["targets"]
                                       if int(t["id"]) not in incoming]
            self._save(cells)

    def targets(self, now: int, ttl: int,
                coordinates: Optional[list[tuple[int, int]]] = None) -> list[dict[str, Any]]:
        allowed = None if coordinates is None else {f"{x},{y}" for x, y in coordinates}
        with self._lock:
            rows: dict[int, dict[str, Any]] = {}
            for key, cell in self._cells.items():
                seen = int(cell.get("observedAtMillis") or 0)
                if not 0 <= now - seen <= ttl or (allowed is not None and key not in allowed):
                    continue
                for target in cell.get("targets") or []:
                    row = {**deepcopy(target), "fromCache": True,
                           "fromLocalSnapshot": True, "localObservedAtMillis": seen}
                    if seen >= int(rows.get(int(row["id"]), {}).get("localObservedAtMillis") or 0):
                        rows[int(row["id"])] = row
            return list(rows.values())

    def invalidate(self, target_id: int) -> None:
        with self._lock:
            cells = deepcopy(self._cells)
            for cell in cells.values():
                cell["targets"] = [t for t in cell["targets"] if int(t["id"]) != target_id]
            self._save(cells)

    def _save(self, cells: dict[str, Any]) -> None:
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as stream:
                json.dump({"version": 1, "cells": cells}, stream, ensure_ascii=False,
                          separators=(",", ":"))
            os.replace(temp, self._path)
        self._cells = cells

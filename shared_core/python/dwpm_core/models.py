"""Small host-neutral response models for the shared-core facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class CoreResponse:
    status: int
    body: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": int(self.status),
            "body": dict(self.body),
        }

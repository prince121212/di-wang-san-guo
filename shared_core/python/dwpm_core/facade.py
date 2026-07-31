"""Host-neutral entry point for the shared Python business core."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .contracts import load_route_ownership
from .hashing import compute_core_hash
from .models import CoreResponse
from .version import CORE_ID, CORE_VERSION


class CoreFacade:
    """Single facade which both hosts will call as migration progresses."""

    def __init__(self, shared_root: Optional[Path] = None) -> None:
        self._shared_root = shared_root
        self._route_contract = load_route_ownership(shared_root)
        self._core_hash = compute_core_hash(shared_root)

    def health(self) -> Dict[str, Any]:
        routes = self._route_contract["routes"]
        return {
            "ok": True,
            "core": CORE_ID,
            "coreVersion": CORE_VERSION,
            "coreHash": self._core_hash,
            "routeContractVersion": self._route_contract["schemaVersion"],
            "sharedRouteCount": len(routes),
            "localRouteCount": sum(row["responseClass"] == "local" for row in routes),
            "networkOperationRouteCount": sum(
                row["responseClass"] == "network-operation" for row in routes
            ),
        }

    def dispatch_local(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> CoreResponse:
        """Minimal phase-2 dispatcher; real routes migrate behind this facade later."""

        normalized_method = str(method).upper()
        normalized_path = str(path).split("?", 1)[0]
        if (normalized_method, normalized_path) == ("GET", "/api/health"):
            return CoreResponse(200, self.health())
        return CoreResponse(
            404,
            {
                "ok": False,
                "error": f"shared core route not migrated: {normalized_method} {normalized_path}",
            },
        )

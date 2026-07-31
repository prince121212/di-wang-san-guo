"""Host-neutral entry point for the shared Python business core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .contracts import load_route_ownership
from .hashing import compute_core_hash
from .models import CoreResponse
from .operations import DurableOperationStore
from .verification import verify_protocol_fixtures
from .version import CORE_ID, CORE_VERSION


class CoreFacade:
    """Single facade which both hosts will call as migration progresses."""

    def __init__(
        self,
        shared_root: Optional[Path] = None,
        operation_store_path: Optional[str] = None,
    ) -> None:
        self._shared_root = shared_root
        self._route_contract = load_route_ownership(shared_root)
        self._core_hash = compute_core_hash(shared_root)
        store_path = Path(operation_store_path) if operation_store_path else None
        self._operations = DurableOperationStore(store_path)

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
            "operationModel": {
                "submission": "immediate",
                "persistence": "durable" if self._operations.persistent else "memory",
                "networkLane": "per-account-planned",
            },
        }

    def health_json(self) -> str:
        return self._json(self.health())

    def submit_simulated_network_operation(
        self,
        duration_millis: int,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a durable delayed operation which performs no network I/O."""

        return self._operations.submit_simulated(
            duration_millis,
            idempotency_key,
            payload,
        )

    def submit_simulated_network_operation_json(
        self,
        duration_millis: int,
        idempotency_key: str,
        payload_json: str = "{}",
    ) -> str:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError("simulated operation payload must be an object")
        return self._json(
            self.submit_simulated_network_operation(
                duration_millis,
                idempotency_key,
                payload,
            )
        )

    def operation_status(self, operation_id: str) -> Dict[str, Any]:
        operation = self._operations.status(operation_id)
        if operation is None:
            return {"ok": False, "error": "operation not found"}
        return {"ok": True, "operation": operation}

    def operation_status_json(self, operation_id: str) -> str:
        return self._json(self.operation_status(operation_id))

    def operations_snapshot(self) -> Dict[str, Any]:
        operations = self._operations.list_operations()
        return {"ok": True, "operations": operations, "count": len(operations)}

    def operations_snapshot_json(self) -> str:
        return self._json(self.operations_snapshot())

    def cancel_operation(self, operation_id: str) -> Dict[str, Any]:
        operation = self._operations.cancel(operation_id)
        if operation is None:
            return {"ok": False, "error": "operation not found"}
        return {"ok": True, "operation": operation}

    def cancel_operation_json(self, operation_id: str) -> str:
        return self._json(self.cancel_operation(operation_id))

    def protocol_fixture_report(self) -> Dict[str, Any]:
        return verify_protocol_fixtures()

    def protocol_fixture_report_json(self) -> str:
        return self._json(self.protocol_fixture_report())

    def close(self) -> None:
        self._operations.close()

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

    @staticmethod
    def _json(value: Dict[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

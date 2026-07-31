"""Host-neutral entry point for the shared Python business core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .contracts import load_route_ownership
from .hashing import compute_core_hash
from .models import CoreResponse
from .operations import (
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    UNCERTAIN,
    DurableOperationStore,
    OperationExecutionContext,
)
from .ports import PlatformPorts
from .verification import verify_protocol_fixtures
from .version import CORE_ID, CORE_VERSION


LocalRouteHandler = Callable[[Dict[str, Any], Dict[str, Any]], Any]
NetworkRouteHandler = Callable[
    [Dict[str, Any], Dict[str, Any], OperationExecutionContext],
    Dict[str, Any],
]
PersistedPayloadBuilder = Callable[
    [Dict[str, Any], Dict[str, Any]],
    Dict[str, Any],
]

SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "cookie",
    "authorization",
)
SENSITIVE_KEY_SUFFIXES = ("token", "secret", "credential")
SENSITIVE_EXACT_KEYS = frozenset(("dm", "session"))


class CoreFacade:
    """The one request and operation facade called by both platform hosts."""

    def __init__(
        self,
        shared_root: Optional[Path] = None,
        operation_store_path: Optional[str] = None,
        ports: Optional[PlatformPorts] = None,
    ) -> None:
        self._shared_root = shared_root
        self._ports = ports or PlatformPorts()
        self._route_contract = load_route_ownership(shared_root)
        self._route_index = {
            (str(row["method"]).upper(), str(row["path"])): dict(row)
            for row in self._route_contract["routes"]
        }
        self._core_hash = compute_core_hash(shared_root)
        store_path = self._resolve_operation_store_path(operation_store_path)
        self._operations = DurableOperationStore(
            store_path,
            now_millis=self._ports.clock.now_millis,
            event_callback=self._publish_operation_event,
        )
        self._local_handlers: Dict[tuple[str, str], LocalRouteHandler] = {
            ("GET", "/api/health"): self._health_route,
        }
        self._network_handlers: Dict[
            tuple[str, str],
            Dict[str, Any],
        ] = {}

    def health(self) -> Dict[str, Any]:
        routes = self._route_contract["routes"]
        registered = set(self._local_handlers) | set(self._network_handlers)
        return {
            "ok": True,
            "core": CORE_ID,
            "coreVersion": CORE_VERSION,
            "coreHash": self._core_hash,
            "routeContractVersion": self._route_contract["schemaVersion"],
            "sharedRouteCount": len(routes),
            "localRouteCount": sum(
                row["responseClass"] == "local" for row in routes
            ),
            "networkOperationRouteCount": sum(
                row["responseClass"] == "network-operation" for row in routes
            ),
            "migratedRouteCount": len(registered),
            "operationModel": {
                "submission": "immediate",
                "persistence": (
                    "durable" if self._operations.persistent else "memory"
                ),
                "localLane": "direct",
                "networkLane": "per-account",
                "eventLane": "platform-port",
                "states": [
                    QUEUED,
                    RUNNING,
                    SUCCEEDED,
                    FAILED,
                    CANCELLED,
                    UNCERTAIN,
                ],
            },
        }

    def health_json(self) -> str:
        return self._json(self.health())

    def route_metadata(self, method: str, path: str) -> Optional[Dict[str, Any]]:
        key = self._route_key(method, path)
        route = self._route_index.get(key)
        return dict(route) if route is not None else None

    def registered_routes(self) -> Dict[str, Any]:
        rows = []
        for key, route in sorted(self._route_index.items()):
            rows.append(
                {
                    **route,
                    "registered": (
                        key in self._local_handlers
                        or key in self._network_handlers
                    ),
                }
            )
        return {"ok": True, "routes": rows, "count": len(rows)}

    def register_local_route(
        self,
        method: str,
        path: str,
        handler: LocalRouteHandler,
        *,
        replace: bool = False,
    ) -> None:
        key, route = self._declared_route(method, path)
        if route.get("responseClass") != "local":
            raise ValueError(f"route is not local: {key[0]} {key[1]}")
        if not callable(handler):
            raise TypeError("local route handler must be callable")
        if key in self._local_handlers and not replace:
            raise ValueError(f"local route already registered: {key[0]} {key[1]}")
        self._local_handlers[key] = handler

    def register_network_route(
        self,
        method: str,
        path: str,
        handler: NetworkRouteHandler,
        *,
        persisted_payload_builder: Optional[PersistedPayloadBuilder] = None,
    ) -> None:
        key, route = self._declared_route(method, path)
        if route.get("responseClass") != "network-operation":
            raise ValueError(
                f"route is not a network operation: {key[0]} {key[1]}"
            )
        if key in self._network_handlers:
            raise ValueError(
                f"network route already registered: {key[0]} {key[1]}"
            )
        if not callable(handler):
            raise TypeError("network route handler must be callable")
        operation_kind = f"route:{key[0]}:{key[1]}"

        def runner(
            execution: OperationExecutionContext,
            persisted: Dict[str, Any],
        ) -> Dict[str, Any]:
            body = dict(persisted.get("body") or {})
            context = dict(persisted.get("requestContext") or {})
            return handler(body, context, execution)

        self._operations.register_runner(operation_kind, runner)
        self._network_handlers[key] = {
            "kind": operation_kind,
            "operationType": str(route["operationKind"]),
            "payloadBuilder": persisted_payload_builder,
        }

    def dispatch(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> CoreResponse:
        try:
            normalized_body = self._object(body or {}, "request body")
            context = self._object(
                request_context or {},
                "request context",
            )
        except ValueError as error:
            return self._error(400, "INVALID_REQUEST", str(error))

        key = self._route_key(method, path)
        route = self._route_index.get(key)
        if route is None:
            return self._error(
                404,
                "ROUTE_NOT_DECLARED",
                f"shared core route is not declared: {key[0]} {key[1]}",
            )
        if route["responseClass"] == "local":
            handler = self._local_handlers.get(key)
            if handler is None:
                return self._not_migrated(key, route)
            try:
                return self._normalize_handler_response(
                    handler(normalized_body, context)
                )
            except ValueError as error:
                return self._error(400, "LOCAL_VALIDATION_FAILED", str(error))
            except Exception as error:
                self._log_exception(key, error)
                return self._error(
                    500,
                    "LOCAL_HANDLER_FAILED",
                    str(error) or error.__class__.__name__,
                )

        registration = self._network_handlers.get(key)
        if registration is None:
            return self._not_migrated(key, route)
        account_ref = self._account_ref(normalized_body, context)
        if not account_ref:
            return self._error(
                400,
                "ACCOUNT_REF_REQUIRED",
                "network operation requires accountRef",
            )
        idempotency_key = self._idempotency_key(normalized_body, context)
        if not idempotency_key:
            return self._error(
                400,
                "IDEMPOTENCY_KEY_REQUIRED",
                "network operation requires idempotencyKey or requestId",
            )
        try:
            payload_builder = registration.get("payloadBuilder")
            if payload_builder is None:
                self._assert_no_sensitive_values(normalized_body)
                persisted_body = dict(normalized_body)
            else:
                persisted_body = self._object(
                    payload_builder(normalized_body, context),
                    "persisted operation payload",
                )
                self._assert_no_sensitive_values(persisted_body)
            persisted_context = {
                key_name: context[key_name]
                for key_name in (
                    "requestId",
                    "source",
                    "platform",
                )
                if key_name in context
            }
            submission = self.submit_network_operation(
                account_ref=account_ref,
                operation_type=str(registration["operationType"]),
                operation_kind=str(registration["kind"]),
                payload={
                    "body": persisted_body,
                    "requestContext": persisted_context,
                },
                idempotency_key=idempotency_key,
            )
            return CoreResponse(202, submission)
        except ValueError as error:
            return self._error(400, "NETWORK_OPERATION_REJECTED", str(error))
        except Exception as error:
            self._log_exception(key, error)
            return self._error(
                500,
                "NETWORK_OPERATION_SUBMIT_FAILED",
                str(error) or error.__class__.__name__,
            )

    def dispatch_json(
        self,
        method: str,
        path: str,
        body_json: str = "{}",
        request_context_json: str = "{}",
    ) -> str:
        try:
            body = json.loads(body_json or "{}")
            context = json.loads(request_context_json or "{}")
        except json.JSONDecodeError as error:
            response = self._error(400, "INVALID_JSON", str(error))
        else:
            response = self.dispatch(method, path, body, context)
        return self._json(response.to_dict())

    def dispatch_local(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> CoreResponse:
        """Compatibility alias retained while desktop handlers migrate."""

        route = self.route_metadata(method, path)
        if route is not None and route.get("responseClass") != "local":
            return self._error(
                409,
                "NETWORK_ROUTE_REQUIRES_ASYNC_DISPATCH",
                "network route cannot run through dispatch_local",
            )
        return self.dispatch(method, path, body, {})

    def submit_network_operation(
        self,
        account_ref: str,
        operation_type: str,
        operation_kind: str,
        payload: Dict[str, Any],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        return self._operations.submit_network(
            account_ref=account_ref,
            operation_type=operation_type,
            kind=operation_kind,
            idempotency_key=idempotency_key,
            payload=payload,
        )

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
        return {
            "ok": True,
            "operations": operations,
            "count": len(operations),
        }

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

    def _resolve_operation_store_path(
        self,
        operation_store_path: Optional[str],
    ) -> Optional[Path]:
        if operation_store_path:
            return Path(operation_store_path)
        data_port = self._ports.data_directory
        if data_port is None:
            return None
        return data_port.data_directory() / "shared_core" / "operations-v2.json"

    def _health_route(
        self,
        body: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.health()

    def _publish_operation_event(self, event: Dict[str, Any]) -> None:
        self._ports.events.publish(event)
        self._ports.logs.write(
            {
                "level": "info",
                "source": "shared-core-operation",
                **event,
            }
        )

    def _log_exception(
        self,
        key: tuple[str, str],
        error: Exception,
    ) -> None:
        self._ports.logs.write(
            {
                "level": "error",
                "source": "shared-core-dispatch",
                "method": key[0],
                "path": key[1],
                "errorType": error.__class__.__name__,
                "message": str(error),
            }
        )

    def _declared_route(
        self,
        method: str,
        path: str,
    ) -> tuple[tuple[str, str], Dict[str, Any]]:
        key = self._route_key(method, path)
        route = self._route_index.get(key)
        if route is None:
            raise ValueError(f"route is not declared: {key[0]} {key[1]}")
        return key, route

    @staticmethod
    def _route_key(method: str, path: str) -> tuple[str, str]:
        return str(method or "").upper(), str(path or "").split("?", 1)[0]

    @staticmethod
    def _account_ref(
        body: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        for source in (context, body):
            for key in ("accountRef", "accountId", "sessionId"):
                value = str(source.get(key) or "").strip()
                if value:
                    return value
        return ""

    @staticmethod
    def _idempotency_key(
        body: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        for source in (context, body):
            for key in ("idempotencyKey", "requestId"):
                value = str(source.get(key) or "").strip()
                if value:
                    return value
        return ""

    @classmethod
    def _assert_no_sensitive_values(
        cls,
        value: Any,
        prefix: str = "body",
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).replace("_", "").replace("-", "").lower()
                if normalized in SENSITIVE_EXACT_KEYS or any(
                    fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS
                ) or normalized.endswith(SENSITIVE_KEY_SUFFIXES):
                    raise ValueError(
                        f"sensitive field cannot enter operation ledger: {prefix}.{key}"
                    )
                cls._assert_no_sensitive_values(child, f"{prefix}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                cls._assert_no_sensitive_values(child, f"{prefix}[{index}]")

    @staticmethod
    def _normalize_handler_response(value: Any) -> CoreResponse:
        if isinstance(value, CoreResponse):
            return value
        if not isinstance(value, dict):
            raise TypeError("local route handler result must be an object")
        return CoreResponse(200, dict(value))

    @staticmethod
    def _object(value: Any, label: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        return json.loads(json.dumps(value, ensure_ascii=False))

    @staticmethod
    def _error(status: int, code: str, message: str) -> CoreResponse:
        return CoreResponse(
            status,
            {
                "ok": False,
                "code": code,
                "error": message,
            },
        )

    def _not_migrated(
        self,
        key: tuple[str, str],
        route: Dict[str, Any],
    ) -> CoreResponse:
        return CoreResponse(
            501,
            {
                "ok": False,
                "code": "ROUTE_NOT_MIGRATED",
                "error": (
                    f"shared core route not migrated: {key[0]} {key[1]}"
                ),
                "responseClass": route["responseClass"],
                "targetOwner": self._route_contract["targetOwner"],
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

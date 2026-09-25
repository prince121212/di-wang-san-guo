"""Adapters from an embedded Java/Kotlin host object to Python platform ports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .ports import NullDailyCompletionPort, PlatformPorts


class HostedCredentialPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def save_password(self, account_ref: str, password: str) -> None:
        self._bridge.savePassword(str(account_ref), str(password))

    def load_password(self, account_ref: str) -> Optional[str]:
        value = self._bridge.loadPassword(str(account_ref))
        return None if value is None else str(value)

    def delete(self, account_ref: str) -> None:
        self._bridge.deleteCredential(str(account_ref))


class HostedSessionSecretPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def save(self, account_ref: str, values: Mapping[str, str]) -> None:
        normalized = {
            str(key): str(value)
            for key, value in values.items()
            if str(key).strip() and str(value)
        }
        self._bridge.saveSessionSecrets(str(account_ref), _json(normalized))

    def load(self, account_ref: str) -> Mapping[str, str]:
        raw = str(self._bridge.loadSessionSecrets(str(account_ref)) or "{}")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("host session secrets must be an object")
        return {
            str(key): str(item)
            for key, item in value.items()
            if str(key).strip() and str(item)
        }

    def delete(self, account_ref: str) -> None:
        self._bridge.deleteSessionSecrets(str(account_ref))


class HostedDataDirectoryPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def data_directory(self) -> Path:
        return Path(str(self._bridge.dataDirectory()))


class HostedNetworkStatePort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def is_available(self) -> bool:
        return bool(self._bridge.networkAvailable())


class HostedNotificationPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def notify(self, event: Mapping[str, object]) -> None:
        self._bridge.notifyEvent(_json(event))


class HostedWakePort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def schedule(self, account_ref: str, wake_at_millis: int) -> None:
        self._bridge.scheduleWake(str(account_ref), int(wake_at_millis))

    def cancel(self, account_ref: str) -> None:
        self._bridge.cancelWake(str(account_ref))


class HostedLogPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def write(self, event: Mapping[str, object]) -> None:
        self._bridge.writeLog(_json(event))


class HostedEventPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def publish(self, event: Mapping[str, object]) -> None:
        self._bridge.publishEvent(_json(event))


class HostedDailyCompletionPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def count(self, account_ref: str, key: str, now_millis: int) -> int:
        return max(
            0,
            int(
                self._bridge.dailyCompletionCount(
                    str(account_ref), str(key), int(now_millis)
                )
            ),
        )

    def add(
        self,
        account_ref: str,
        key: str,
        count: int,
        now_millis: int,
    ) -> int:
        return max(
            0,
            int(
                self._bridge.addDailyCompletion(
                    str(account_ref),
                    str(key),
                    int(count),
                    int(now_millis),
                )
            ),
        )


class HostedMapSnapshotPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def save(self, snapshot: Mapping[str, object]) -> None:
        self._bridge.saveMapSnapshot(_json(snapshot))

    def load(
        self,
        account_ref: str,
        kind: str,
        fingerprint: str,
    ) -> Optional[Mapping[str, object]]:
        loader = getattr(self._bridge, "loadMapSnapshot", None)
        if loader is None:
            return None
        raw = loader(str(account_ref), str(kind), str(fingerprint))
        if not raw:
            return None
        try:
            snapshot = json.loads(str(raw))
        except Exception:
            return None
        return snapshot if isinstance(snapshot, dict) and snapshot else None

    def invalidate(
        self,
        account_ref: str,
        kind: str,
        target_id: int,
        reason: str,
        invalidated_at_millis: int,
    ) -> None:
        self._bridge.invalidateMapTarget(
            str(account_ref),
            str(kind),
            int(target_id),
            str(reason),
            int(invalidated_at_millis),
        )


class HostGameCommandError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "HOST_GAME_COMMAND_FAILED",
        status: int = 500,
    ) -> None:
        super().__init__(message)
        self.code = str(code or "HOST_GAME_COMMAND_FAILED")
        self.status = int(status)


class HostedGameCommandPort:
    """Calls Android's generic authenticated transport without adding rules."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def execute(
        self,
        account_ref: str,
        opcode: int,
        payload: bytes,
        phase: str,
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        raw = self._bridge.executeGameCommand(
            str(account_ref),
            _json({
                "opcode": int(opcode),
                "payloadHex": bytes(payload).hex(),
                "phase": str(phase),
                "readOnly": bool(context.get("readOnly", False)),
            }),
            _json(context),
        )
        try:
            response = json.loads(str(raw or "{}"))
        except json.JSONDecodeError as error:
            raise HostGameCommandError(
                "Android raw game transport returned invalid JSON"
            ) from error
        if not isinstance(response, dict):
            raise HostGameCommandError(
                "Android raw game transport response must be an object"
            )
        status = int(response.get("status") or 500)
        body = response.get("body")
        if not isinstance(body, dict):
            raise HostGameCommandError(
                "Android raw game transport body must be an object",
                status=status,
            )
        if not 200 <= status < 300 or body.get("ok") is False:
            raise HostGameCommandError(
                str(
                    body.get("error")
                    or body.get("message")
                    or f"Android raw game transport failed with status {status}"
                ),
                code=str(body.get("code") or "HOST_GAME_COMMAND_FAILED"),
                status=status,
            )
        fact = body.get("gameCommandFact")
        if not isinstance(fact, dict):
            raise HostGameCommandError(
                "Android raw game transport did not return gameCommandFact",
                status=status,
            )
        return dict(fact)


class HostedRawHttpPort:
    """Adapts a host's byte-only HTTP transport to the shared core port."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        body = request.get("body")
        if body is None:
            body_bytes = b""
        elif isinstance(body, (bytes, bytearray)):
            body_bytes = bytes(body)
        else:
            raise TypeError("raw HTTP request body must be bytes")
        wire_request = {
            key: value
            for key, value in request.items()
            if key != "body"
        }
        wire_request["bodyHex"] = body_bytes.hex()
        raw = self._bridge.executeRawHttp(_json(wire_request))
        try:
            response = json.loads(str(raw or "{}"))
        except json.JSONDecodeError as error:
            raise RuntimeError("host raw HTTP transport returned invalid JSON") from error
        if not isinstance(response, dict):
            raise RuntimeError("host raw HTTP transport response must be an object")
        try:
            status = int(response.get("status") or 0)
        except (TypeError, ValueError) as error:
            raise RuntimeError("host raw HTTP transport status is invalid") from error
        body_hex = str(response.get("bodyHex") or "")
        try:
            response_body = bytes.fromhex(body_hex) if body_hex else b""
        except ValueError as error:
            raise RuntimeError("host raw HTTP transport bodyHex is invalid") from error
        headers = response.get("headers")
        return {
            "status": status,
            "body": response_body,
            "headers": dict(headers) if isinstance(headers, dict) else {},
        }


class HostedMembershipPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def check(self, force: bool = False) -> Mapping[str, object]:
        value = json.loads(str(self._bridge.checkMembership(bool(force))))
        if not isinstance(value, dict):
            raise RuntimeError("会员授权宿主响应无效")
        return value


class HostedCloudSharedDataPort:
    """Keeps the Worker URL/token in Android while returning JSON facts."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def configured(self) -> bool:
        return bool(self._bridge.cloudSharedDataConfigured())

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        raw = self._bridge.executeCloudRequest(_json(request))
        try:
            response = json.loads(str(raw or "{}"))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "host cloud shared-data transport returned invalid JSON"
            ) from error
        if not isinstance(response, dict):
            raise RuntimeError(
                "host cloud shared-data transport response must be an object"
            )
        status = int(response.get("status") or 0)
        body = response.get("body")
        if not isinstance(body, dict):
            raise RuntimeError(
                "host cloud shared-data transport body must be an object"
            )
        return {"status": status, "body": dict(body)}


class HostedAccountRuntimePort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def commit_login(
        self,
        previous_account_ref: str,
        account_ref: str,
        runtime: Mapping[str, object],
        mode: str,
    ) -> None:
        self._bridge.commitAccountRuntime(
            str(previous_account_ref),
            str(account_ref),
            _json(runtime),
            str(mode),
        )

    def start_hosting(self, account_ref: str) -> None:
        self._bridge.startAccountHosting(str(account_ref))

    def is_hosting(self, account_ref: str) -> Optional[bool]:
        if hasattr(self._bridge, "isAccountHosting"):
            return bool(self._bridge.isAccountHosting(str(account_ref)))
        if hasattr(self._bridge, "executionOwnerActive"):
            return bool(self._bridge.executionOwnerActive())
        return None


def platform_ports_from_host_bridge(bridge: Any) -> PlatformPorts:
    return PlatformPorts(
        membership=HostedMembershipPort(bridge) if hasattr(bridge, "checkMembership") else None,
        credentials=HostedCredentialPort(bridge),
        session_secrets=HostedSessionSecretPort(bridge),
        data_directory=HostedDataDirectoryPort(bridge),
        network_state=HostedNetworkStatePort(bridge),
        notifications=HostedNotificationPort(bridge),
        wake=HostedWakePort(bridge),
        logs=HostedLogPort(bridge),
        events=HostedEventPort(bridge),
        daily_completions=(
            HostedDailyCompletionPort(bridge)
            if hasattr(bridge, "dailyCompletionCount")
            and hasattr(bridge, "addDailyCompletion")
            else NullDailyCompletionPort()
        ),
        game_commands=(
            HostedGameCommandPort(bridge)
            if hasattr(bridge, "executeGameCommand")
            else None
        ),
        raw_http=(
            HostedRawHttpPort(bridge)
            if hasattr(bridge, "executeRawHttp")
            else None
        ),
        cloud_shared_data=(
            HostedCloudSharedDataPort(bridge)
            if hasattr(bridge, "cloudSharedDataConfigured")
            and hasattr(bridge, "executeCloudRequest")
            else None
        ),
        account_runtime=(
            HostedAccountRuntimePort(bridge)
            if hasattr(bridge, "commitAccountRuntime")
            and hasattr(bridge, "startAccountHosting")
            else None
        ) or PlatformPorts().account_runtime,
        map_snapshots=(
            HostedMapSnapshotPort(bridge)
            if hasattr(bridge, "saveMapSnapshot")
            and hasattr(bridge, "invalidateMapTarget")
            else None
        ),
    )


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

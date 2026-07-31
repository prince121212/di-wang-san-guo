"""Adapters from an embedded Java/Kotlin host object to Python platform ports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .ports import PlatformPorts


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


def platform_ports_from_host_bridge(bridge: Any) -> PlatformPorts:
    return PlatformPorts(
        credentials=HostedCredentialPort(bridge),
        session_secrets=HostedSessionSecretPort(bridge),
        data_directory=HostedDataDirectoryPort(bridge),
        network_state=HostedNetworkStatePort(bridge),
        notifications=HostedNotificationPort(bridge),
        wake=HostedWakePort(bridge),
        logs=HostedLogPort(bridge),
        events=HostedEventPort(bridge),
    )


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

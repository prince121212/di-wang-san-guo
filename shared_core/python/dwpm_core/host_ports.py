"""Adapters from an embedded Java/Kotlin host object to Python platform ports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .ports import PlatformPorts


class HostedCredentialPort:
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def load_password(self, account_ref: str) -> Optional[str]:
        value = self._bridge.loadPassword(str(account_ref))
        return None if value is None else str(value)

    def delete(self, account_ref: str) -> None:
        self._bridge.deleteCredential(str(account_ref))


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

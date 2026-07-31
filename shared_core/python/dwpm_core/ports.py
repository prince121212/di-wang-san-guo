"""Host capability ports; business decisions remain inside the shared core."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Protocol


class CredentialPort(Protocol):
    def load_password(self, account_ref: str) -> Optional[str]:
        ...

    def delete(self, account_ref: str) -> None:
        ...


class DataDirectoryPort(Protocol):
    def data_directory(self) -> Path:
        ...


class ClockPort(Protocol):
    def now_millis(self) -> int:
        ...


class NetworkStatePort(Protocol):
    def is_available(self) -> bool:
        ...


class NotificationPort(Protocol):
    def notify(self, event: Mapping[str, object]) -> None:
        ...


class WakePort(Protocol):
    def schedule(self, account_ref: str, wake_at_millis: int) -> None:
        ...

    def cancel(self, account_ref: str) -> None:
        ...


class PlatformLogPort(Protocol):
    def write(self, event: Mapping[str, object]) -> None:
        ...


class PlatformEventPort(Protocol):
    def publish(self, event: Mapping[str, object]) -> None:
        ...


class SystemClockPort:
    def now_millis(self) -> int:
        return int(time.time() * 1000)


class AlwaysOnlineNetworkStatePort:
    def is_available(self) -> bool:
        return True


class NullNotificationPort:
    def notify(self, event: Mapping[str, object]) -> None:
        return None


class NullWakePort:
    def schedule(self, account_ref: str, wake_at_millis: int) -> None:
        return None

    def cancel(self, account_ref: str) -> None:
        return None


class NullPlatformLogPort:
    def write(self, event: Mapping[str, object]) -> None:
        return None


class NullPlatformEventPort:
    def publish(self, event: Mapping[str, object]) -> None:
        return None


@dataclass(frozen=True)
class PlatformPorts:
    """The complete host boundary passed to one process-wide CoreFacade."""

    credentials: Optional[CredentialPort] = None
    data_directory: Optional[DataDirectoryPort] = None
    clock: ClockPort = field(default_factory=SystemClockPort)
    network_state: NetworkStatePort = field(
        default_factory=AlwaysOnlineNetworkStatePort
    )
    notifications: NotificationPort = field(default_factory=NullNotificationPort)
    wake: WakePort = field(default_factory=NullWakePort)
    logs: PlatformLogPort = field(default_factory=NullPlatformLogPort)
    events: PlatformEventPort = field(default_factory=NullPlatformEventPort)

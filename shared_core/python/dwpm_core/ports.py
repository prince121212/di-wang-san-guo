"""Host capability ports; business decisions remain inside the shared core."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol


class CredentialPort(Protocol):
    def save_password(self, account_ref: str, password: str) -> None:
        ...

    def load_password(self, account_ref: str) -> Optional[str]:
        ...

    def delete(self, account_ref: str) -> None:
        ...


class SessionSecretPort(Protocol):
    def save(self, account_ref: str, values: Mapping[str, str]) -> None:
        ...

    def load(self, account_ref: str) -> Mapping[str, str]:
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


class GameCommandPort(Protocol):
    """Authenticated raw game exchange; feature decisions stay in Python."""

    def execute(
        self,
        account_ref: str,
        opcode: int,
        payload: bytes,
        phase: str,
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...


class RawHttpPort(Protocol):
    """Raw HTTP exchange used by shared login/bootstrap workflows.

    URLs, query parameters, headers and request bytes are all supplied by the
    Python core.  A platform implementation must only perform the exchange and
    return transport facts; it must not interpret passport text, game opcodes or
    response payloads.
    """

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...


class MembershipPort(Protocol):
    """Device-wide, native-protected membership authorization; no bearer secrets cross this port."""

    def check(self, force: bool = False) -> Mapping[str, object]:
        ...


class CloudSharedDataPort(Protocol):
    """Authenticated transport for the narrow shared-data Worker API.

    The host owns the endpoint and runtime token. The core can only select one
    of the Worker's fixed paths and exchange normalized JSON; Cloudflare
    management credentials never cross this boundary.
    """

    def configured(self) -> bool:
        ...

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...


class AccountRuntimePort(Protocol):
    """Mirrors a successful shared login into temporary host runtime state.

    The durable public account and encrypted Session secrets are owned by the
    core and their dedicated ports.  This capability exists only while legacy
    host schedulers still need a transient in-memory Session mirror.
    """

    def commit_login(
        self,
        previous_account_ref: str,
        account_ref: str,
        runtime: Mapping[str, object],
        mode: str,
    ) -> None:
        ...

    def start_hosting(self, account_ref: str) -> None:
        ...

    def is_hosting(self, account_ref: str) -> Optional[bool]:
        """Return current-process hosting evidence for one account.

        ``True`` and ``False`` are host observations. ``None`` means that the
        host cannot observe runtime ownership, so callers must fail closed
        instead of treating a durable ``enabled`` flag as live evidence.
        """

        ...


class MapSnapshotPort(Protocol):
    """Stores normalized map observations without deciding filters or TTLs.

    ``load`` is what makes scanning worth anything for a single account.  The
    port used to be write-only, so hosts faithfully recorded every discovered
    target and the core then re-swept the same coordinates on the next
    dispatch: only the cloud path could read discoveries back.
    """

    def save(self, snapshot: Mapping[str, object]) -> None:
        ...

    def load(
        self,
        account_ref: str,
        kind: str,
        fingerprint: str,
    ) -> Optional[Mapping[str, object]]:
        """Return the stored snapshot for this exact scan identity, if any.

        Freshness stays a core decision: the snapshot carries its own
        ``scannedAtMillis`` and the contract TTL is applied by the caller.
        """

        ...

    def invalidate(
        self,
        account_ref: str,
        kind: str,
        target_id: int,
        reason: str,
        invalidated_at_millis: int,
    ) -> None:
        ...


class DailyCompletionPort(Protocol):
    """Stores completion counts; cycle and success decisions stay in Python."""

    def count(self, account_ref: str, key: str, now_millis: int) -> int:
        ...

    def add(
        self,
        account_ref: str,
        key: str,
        count: int,
        now_millis: int,
    ) -> int:
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


class NullDailyCompletionPort:
    def count(self, account_ref: str, key: str, now_millis: int) -> int:
        return 0

    def add(
        self,
        account_ref: str,
        key: str,
        count: int,
        now_millis: int,
    ) -> int:
        return max(0, int(count))


class NullAccountRuntimePort:
    def commit_login(
        self,
        previous_account_ref: str,
        account_ref: str,
        runtime: Mapping[str, object],
        mode: str,
    ) -> None:
        return None

    def start_hosting(self, account_ref: str) -> None:
        return None

    def is_hosting(self, account_ref: str) -> Optional[bool]:
        return None


@dataclass(frozen=True)
class PlatformPorts:
    """The complete host boundary passed to one process-wide CoreFacade."""

    credentials: Optional[CredentialPort] = None
    session_secrets: Optional[SessionSecretPort] = None
    data_directory: Optional[DataDirectoryPort] = None
    clock: ClockPort = field(default_factory=SystemClockPort)
    network_state: NetworkStatePort = field(
        default_factory=AlwaysOnlineNetworkStatePort
    )
    notifications: NotificationPort = field(default_factory=NullNotificationPort)
    wake: WakePort = field(default_factory=NullWakePort)
    logs: PlatformLogPort = field(default_factory=NullPlatformLogPort)
    events: PlatformEventPort = field(default_factory=NullPlatformEventPort)
    game_commands: Optional[GameCommandPort] = None
    raw_http: Optional[RawHttpPort] = None
    cloud_shared_data: Optional[CloudSharedDataPort] = None
    membership: Optional[MembershipPort] = None
    account_runtime: AccountRuntimePort = field(
        default_factory=NullAccountRuntimePort
    )
    map_snapshots: Optional[MapSnapshotPort] = None
    daily_completions: DailyCompletionPort = field(
        default_factory=NullDailyCompletionPort
    )

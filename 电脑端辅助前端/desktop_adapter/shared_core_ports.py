"""Desktop implementations of shared-core data, log and event ports."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Optional

from dwpm_core.ports import NullDailyCompletionPort, PlatformPorts


DEFAULT_CLOUD_SHARED_DATA_URL = "https://dwpm-data.292828.xyz"
MACOS_CLOUD_RUNTIME_TOKEN_SERVICE = "dwpm-cloud-shared-data-runtime-token"


def _macos_cloud_runtime_token() -> str:
    """Read the local runtime-only token without exposing it to shared Python."""

    security = Path("/usr/bin/security")
    if not security.is_file():
        return ""
    try:
        result = subprocess.run(
            [
                str(security),
                "find-generic-password",
                "-s",
                MACOS_CLOUD_RUNTIME_TOKEN_SERVICE,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(result.stdout or "").strip()


class DesktopCredentialPort:
    def __init__(
        self,
        save_callback: Callable[[str, str], None],
        load_callback: Callable[[str], Optional[str]],
        delete_callback: Callable[[str], None],
    ) -> None:
        self._save_callback = save_callback
        self._load_callback = load_callback
        self._delete_callback = delete_callback

    def save_password(self, account_ref: str, password: str) -> None:
        self._save_callback(str(account_ref), str(password))

    def load_password(self, account_ref: str) -> Optional[str]:
        return self._load_callback(str(account_ref))

    def delete(self, account_ref: str) -> None:
        self._delete_callback(str(account_ref))


class DesktopSessionSecretPort:
    def __init__(
        self,
        save_callback: Callable[[str, Mapping[str, str]], None],
        load_callback: Callable[[str], Mapping[str, str]],
        delete_callback: Callable[[str], None],
    ) -> None:
        self._save_callback = save_callback
        self._load_callback = load_callback
        self._delete_callback = delete_callback

    def save(self, account_ref: str, values: Mapping[str, str]) -> None:
        self._save_callback(str(account_ref), dict(values))

    def load(self, account_ref: str) -> Mapping[str, str]:
        return dict(self._load_callback(str(account_ref)))

    def delete(self, account_ref: str) -> None:
        self._delete_callback(str(account_ref))


class DesktopRawHttpPort:
    """Generic byte transport; all request meaning stays in shared Python."""

    def __init__(
        self,
        game_exchange_callback: Callable[
            [Mapping[str, object]], Mapping[str, object]
        ] | None = None,
    ) -> None:
        # Login/passport traffic is ordinary raw HTTP. Authenticated game
        # traffic must instead use the desktop account's selected route,
        # pacing and game-compatible headers. The core marks only those
        # requests with ``requireExecutionOwner``.
        self._game_exchange_callback = game_exchange_callback

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        if (
            request.get("requireExecutionOwner") is True
            and self._game_exchange_callback is not None
        ):
            return dict(self._game_exchange_callback(dict(request)))
        method = str(request.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("shared raw HTTP supports only GET/POST")
        url = str(request.get("url") or "").strip()
        if not url:
            raise ValueError("shared raw HTTP URL is missing")
        query = request.get("query")
        if isinstance(query, Mapping) and query:
            encoded = urllib.parse.urlencode(
                {str(key): str(value) for key, value in query.items()}
            )
            url += ("&" if "?" in url else "?") + encoded
        body = request.get("body")
        if body is None:
            body_bytes = b""
        elif isinstance(body, (bytes, bytearray)):
            body_bytes = bytes(body)
        else:
            raise TypeError("shared raw HTTP body must be bytes")
        headers = request.get("headers")
        normalized_headers = (
            {str(key): str(value) for key, value in headers.items()}
            if isinstance(headers, Mapping)
            else {}
        )
        request_value = urllib.request.Request(
            url,
            data=body_bytes if method == "POST" else None,
            method=method,
            headers=normalized_headers,
        )
        timeout = max(
            1.0,
            min(
                120.0,
                float(request.get("readTimeoutMillis") or 25_000) / 1000.0,
            ),
        )
        try:
            with urllib.request.urlopen(
                request_value,
                context=ssl._create_unverified_context(),
                timeout=timeout,
            ) as response:
                return {
                    "status": int(response.status),
                    "body": response.read(),
                    "headers": dict(response.headers.items()),
                }
        except urllib.error.HTTPError as error:
            return {
                "status": int(error.code),
                "body": error.read(),
                "headers": dict(error.headers.items()) if error.headers else {},
            }


class DesktopCloudSharedDataPort:
    """Narrow Worker transport configured only from the desktop environment."""

    def __init__(
        self,
        base_url: str | None = None,
        runtime_token: str | None = None,
    ) -> None:
        self._base_url = str(
            base_url
            if base_url is not None
            else os.environ.get(
                "DWPM_CLOUD_SHARED_DATA_URL",
                DEFAULT_CLOUD_SHARED_DATA_URL,
            )
        ).strip().rstrip("/")
        self._runtime_token = str(
            runtime_token
            if runtime_token is not None
            else os.environ.get("DWPM_CLOUD_SHARED_DATA_TOKEN", "")
        ).strip()

    @classmethod
    def for_local_runtime(cls) -> "DesktopCloudSharedDataPort":
        """Use environment configuration, then this Mac's local Keychain."""

        return cls(
            runtime_token=(
                os.environ.get("DWPM_CLOUD_SHARED_DATA_TOKEN", "").strip()
                or _macos_cloud_runtime_token()
            ),
        )

    def configured(self) -> bool:
        if not self._base_url or not self._runtime_token:
            return False
        parsed = urllib.parse.urlsplit(self._base_url)
        return bool(
            parsed.hostname
            and (
                parsed.scheme == "https"
                or (
                    parsed.scheme == "http"
                    and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                )
            )
        )

    def exchange(
        self,
        request: Mapping[str, object],
    ) -> Mapping[str, object]:
        if not self.configured():
            raise RuntimeError("共享云端数据未配置")
        method = str(request.get("method") or "POST").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("共享云端数据仅支持 GET/POST")
        path = str(request.get("path") or "").strip()
        if not path.startswith("/v1/") or "?" in path or "#" in path:
            raise ValueError("共享云端数据接口路径无效")
        payload = request.get("body")
        if payload is None:
            normalized_body: Mapping[str, object] = {}
        elif isinstance(payload, Mapping):
            normalized_body = payload
        else:
            raise TypeError("共享云端数据请求体必须是对象")
        encoded = json.dumps(
            dict(normalized_body),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request_value = urllib.request.Request(
            self._base_url + path,
            data=encoded if method == "POST" else None,
            method=method,
            headers={
                "authorization": f"Bearer {self._runtime_token}",
                "content-type": "application/json; charset=utf-8",
                "accept": "application/json",
                "user-agent": "DWPM-Cloud-Shared-Data/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request_value, timeout=8.0) as response:
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = int(error.code)
            raw = error.read()
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "共享云端数据返回了无效 JSON"
            ) from error
        if not isinstance(body, dict):
            raise RuntimeError("共享云端数据响应必须是对象")
        return {"status": status, "body": body}


class DesktopAccountRuntimePort:
    def __init__(
        self,
        commit_callback: Callable[[str, str, Mapping[str, object], str], None],
        start_callback: Callable[[str], None],
        is_hosting_callback: Callable[[str], bool] | None = None,
    ) -> None:
        self._commit_callback = commit_callback
        self._start_callback = start_callback
        self._is_hosting_callback = is_hosting_callback

    def commit_login(
        self,
        previous_account_ref: str,
        account_ref: str,
        runtime: Mapping[str, object],
        mode: str,
    ) -> None:
        self._commit_callback(
            str(previous_account_ref),
            str(account_ref),
            dict(runtime),
            str(mode),
        )

    def start_hosting(self, account_ref: str) -> None:
        self._start_callback(str(account_ref))

    def is_hosting(self, account_ref: str) -> Optional[bool]:
        if self._is_hosting_callback is None:
            return None
        return bool(self._is_hosting_callback(str(account_ref)))


class DesktopGameCommandPort:
    """Host-only raw transport adapter for the shared Python workflows.

    The callback is deliberately supplied by the desktop host.  This module
    contains no game opcode, response parser or business decision; it merely
    exposes the same narrow capability port used by Android's Kotlin bridge.
    """

    def __init__(
        self,
        executor: Callable[
            [str, int, bytes, str, Mapping[str, object]],
            Mapping[str, object],
        ],
    ) -> None:
        self._executor = executor

    def execute(
        self,
        account_ref: str,
        opcode: int,
        payload: bytes,
        phase: str,
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        return dict(
            self._executor(
                str(account_ref),
                int(opcode),
                bytes(payload),
                str(phase),
                dict(context),
            )
        )


class DesktopDailyCompletionPort:
    """Raw counter storage adapter; Python owns completion decisions."""

    def __init__(
        self,
        count_callback: Callable[[str, str, int], int],
        add_callback: Callable[[str, str, int, int], int],
    ) -> None:
        self._count_callback = count_callback
        self._add_callback = add_callback

    def count(self, account_ref: str, key: str, now_millis: int) -> int:
        return max(
            0,
            int(self._count_callback(str(account_ref), str(key), int(now_millis))),
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
                self._add_callback(
                    str(account_ref),
                    str(key),
                    int(count),
                    int(now_millis),
                )
            ),
        )


class DesktopMapSnapshotPort:
    """Forwards normalized observations to the desktop persistence host."""

    def __init__(
        self,
        save_callback: Callable[[Mapping[str, object]], None],
        invalidate_callback: Callable[[str, str, int, str, int], None],
        load_callback: (
            Callable[[str, str, str], Mapping[str, object] | None] | None
        ) = None,
    ) -> None:
        self._save_callback = save_callback
        self._invalidate_callback = invalidate_callback
        self._load_callback = load_callback

    def save(self, snapshot: Mapping[str, object]) -> None:
        self._save_callback(dict(snapshot))

    def load(
        self,
        account_ref: str,
        kind: str,
        fingerprint: str,
    ) -> Mapping[str, object] | None:
        # A host without a reader simply never reuses its own scans, which is
        # exactly how every host behaved before this existed.
        if self._load_callback is None:
            return None
        snapshot = self._load_callback(
            str(account_ref), str(kind), str(fingerprint)
        )
        return dict(snapshot) if isinstance(snapshot, Mapping) else None

    def invalidate(
        self,
        account_ref: str,
        kind: str,
        target_id: int,
        reason: str,
        invalidated_at_millis: int,
    ) -> None:
        self._invalidate_callback(
            str(account_ref),
            str(kind),
            int(target_id),
            str(reason),
            int(invalidated_at_millis),
        )


class DesktopDataDirectoryPort:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def data_directory(self) -> Path:
        return self._root


class DesktopJsonlPort:
    """Small append-only host sink; shared business state stays elsewhere."""

    def __init__(
        self,
        path: Path,
        callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self._path = path
        self._callback = callback
        self._lock = threading.RLock()

    def publish(self, event: Mapping[str, object]) -> None:
        self._append(event)

    def write(self, event: Mapping[str, object]) -> None:
        self._append(event)

    def notify(self, event: Mapping[str, object]) -> None:
        self._append(event)

    def _append(self, event: Mapping[str, object]) -> None:
        line = json.dumps(
            dict(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
        if self._callback is not None:
            self._callback(dict(event))


def create_desktop_platform_ports(
    data_root: Path,
    *,
    game_commands: DesktopGameCommandPort | None = None,
    daily_completions: DesktopDailyCompletionPort | None = None,
    map_snapshots: DesktopMapSnapshotPort | None = None,
    credentials: DesktopCredentialPort | None = None,
    session_secrets: DesktopSessionSecretPort | None = None,
    raw_http: DesktopRawHttpPort | None = None,
    cloud_shared_data: DesktopCloudSharedDataPort | None = None,
    account_runtime: DesktopAccountRuntimePort | None = None,
    log_callback: Callable[[Mapping[str, object]], None] | None = None,
) -> PlatformPorts:
    root = data_root.resolve()
    events = DesktopJsonlPort(root / "shared_core" / "events.jsonl")
    logs = DesktopJsonlPort(
        root / "shared_core" / "core.jsonl",
        callback=log_callback,
    )
    notifications = DesktopJsonlPort(
        root / "shared_core" / "notifications.jsonl"
    )
    return PlatformPorts(
        data_directory=DesktopDataDirectoryPort(root),
        credentials=credentials,
        session_secrets=session_secrets,
        events=events,
        logs=logs,
        notifications=notifications,
        game_commands=game_commands,
        raw_http=raw_http,
        cloud_shared_data=(
            cloud_shared_data or DesktopCloudSharedDataPort()
        ),
        account_runtime=(
            account_runtime or PlatformPorts().account_runtime
        ),
        daily_completions=(daily_completions or NullDailyCompletionPort()),
        map_snapshots=map_snapshots,
    )

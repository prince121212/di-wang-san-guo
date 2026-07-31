#!/usr/bin/env python3
"""ADB-only debugger for the Android helper's existing local API controller."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = "com.example.dwpmclone"
DEFAULT_APK = ROOT / "app/build/outputs/apk/debug/app-debug.apk"
DEFAULT_GRADLEW = ROOT / "gradlew"
POST_CONFIRMATION = "ALLOW_REAL_POST"
PROVIDER_PROTOCOL = 1
RESULT_PATTERN = re.compile(r"(?:^|[\s,{])debug_result=([A-Za-z0-9_-]+)")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class DebuggerError(RuntimeError):
    """A concise, user-facing debugger failure."""


def json_text(value: Any, *, pretty: bool = True) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=pretty,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode_base64url(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_base64url(encoded: str) -> str:
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise DebuggerError("调试 Provider 返回了无效的 Base64 数据") from error


def decode_provider_output(output: str) -> dict[str, Any]:
    match = RESULT_PATTERN.search(output)
    if not match:
        compact = " ".join(output.strip().split())
        raise DebuggerError(f"无法解析调试 Provider 返回：{compact[:500] or '<空>'}")
    try:
        value = json.loads(decode_base64url(match.group(1)))
    except json.JSONDecodeError as error:
        raise DebuggerError("调试 Provider 返回的内容不是 JSON") from error
    if not isinstance(value, dict):
        raise DebuggerError("调试 Provider 返回的 JSON 不是对象")
    return value


def make_api_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    normalized_method = method.upper()
    if normalized_method not in {"GET", "POST"}:
        raise DebuggerError("只允许 GET/POST")
    if not path.startswith("/api/"):
        raise DebuggerError("API 路径必须以 /api/ 开头")
    return {
        "apiVersion": "v1",
        "id": request_id or f"debug-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
        "method": normalized_method,
        "path": path,
        "body": body or {},
    }


def encode_api_request(request: dict[str, Any]) -> str:
    return encode_base64url(json_text(request, pretty=False))


def expected_source_version(root: Path = ROOT) -> tuple[str | None, int | None]:
    build_file = root / "app/build.gradle.kts"
    if not build_file.is_file():
        return None, None
    source = build_file.read_text(encoding="utf-8")
    name_match = re.search(r'versionName\s*=\s*"([^"]+)"', source)
    code_match = re.search(r"versionCode\s*=\s*(\d+)", source)
    return (
        name_match.group(1) if name_match else None,
        int(code_match.group(1)) if code_match else None,
    )


@dataclass
class AdbClient:
    adb_bin: str = "adb"
    serial: str | None = None
    timeout: float = 60.0

    def command(self, *args: str) -> list[str]:
        prefix = [self.adb_bin]
        if self.serial:
            prefix.extend(["-s", self.serial])
        return [*prefix, *args]

    def run(
        self,
        args: Iterable[str],
        *,
        timeout: float | None = None,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = self.command(*list(args))
        try:
            completed = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as error:
            raise DebuggerError(f"找不到 adb：{self.adb_bin}") from error
        except subprocess.TimeoutExpired as error:
            raise DebuggerError(f"adb 执行超时：{' '.join(command)}") from error
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            raise DebuggerError(
                f"adb 执行失败（{completed.returncode}）：{details or '无错误详情'}"
            )
        return completed

    def content_call(
        self,
        authority: str,
        method: str,
        argument: str | None = None,
        extras: Iterable[str] = (),
    ) -> dict[str, Any]:
        command = [
            "shell",
            "content",
            "call",
            "--uri",
            f"content://{authority}",
            "--method",
            method,
        ]
        if argument is not None:
            command.extend(["--arg", argument])
        for extra in extras:
            command.extend(["--extra", extra])
        completed = self.run(command)
        return decode_provider_output(completed.stdout or "")


@dataclass
class DebugConnection:
    adb: AdbClient
    package: str
    authority: str
    apk: Path
    allow_installed_mismatch: bool = False
    identity: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None

    def attach(self, *, require_local_apk: bool = True) -> dict[str, Any]:
        identity = self.adb.content_call(self.authority, "identity")
        verification, hard_errors, installed_errors = verify_identity(
            identity,
            expected_package=self.package,
            apk=self.apk,
            require_local_apk=require_local_apk,
        )
        if hard_errors or (installed_errors and not self.allow_installed_mismatch):
            details = "；".join([*hard_errors, *installed_errors])
            if installed_errors:
                details += "（如需只读检查旧版现场，可加 --allow-installed-mismatch）"
            raise DebuggerError(f"调试身份校验失败：{details}")
        self.identity = identity
        verification["installedMismatchAllowed"] = bool(
            installed_errors and self.allow_installed_mismatch
        )
        self.verification = verification
        return identity

    def call_api(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        allow_post: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        if normalized_method == "POST" and not allow_post:
            raise DebuggerError(
                "POST 可能改变真实账号状态；确认需要执行时请显式加 --allow-post"
            )
        request = make_api_request(normalized_method, path, body, request_id)
        extras: list[str] = []
        if normalized_method == "POST":
            extras = [
                "allow_post:b:true",
                f"post_confirmation:s:{POST_CONFIRMATION}",
            ]
        return self.adb.content_call(
            self.authority,
            "api",
            encode_api_request(request),
            extras,
        )


def verify_identity(
    identity: dict[str, Any],
    *,
    expected_package: str,
    apk: Path,
    require_local_apk: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    hard_errors: list[str] = []
    installed_errors: list[str] = []
    expected_name, expected_code = expected_source_version()
    actual_sha = str(identity.get("apkSha256", ""))
    local_exists = apk.is_file()
    local_sha = sha256_file(apk) if local_exists else None

    if identity.get("packageName") != expected_package:
        hard_errors.append(
            f"包名不匹配：{identity.get('packageName')} != {expected_package}"
        )
    if identity.get("debugProtocol") != PROVIDER_PROTOCOL:
        hard_errors.append("调试协议版本不匹配")
    if identity.get("debuggable") is not True:
        hard_errors.append("设备上不是 Debug APK")
    if not isinstance(identity.get("pid"), int) or int(identity.get("pid", 0)) <= 0:
        hard_errors.append("PID 无效")
    if not isinstance(identity.get("uid"), int) or int(identity.get("uid", -1)) < 0:
        hard_errors.append("UID 无效")
    if not SHA256_PATTERN.fullmatch(actual_sha):
        hard_errors.append("APK SHA-256 无效")
    if expected_name and identity.get("versionName") != expected_name:
        installed_errors.append(
            f"版本名不匹配：{identity.get('versionName')} != {expected_name}"
        )
    if expected_code is not None and identity.get("versionCode") != expected_code:
        installed_errors.append(
            f"版本号不匹配：{identity.get('versionCode')} != {expected_code}"
        )
    if require_local_apk and not local_exists:
        hard_errors.append(f"本地 Debug APK 不存在：{apk}")
    if local_sha and actual_sha != local_sha:
        installed_errors.append("设备 APK SHA-256 与本地 APK 不一致")

    verification = {
        "package": identity.get("packageName") == expected_package,
        "versionName": expected_name,
        "versionCode": expected_code,
        "pid": identity.get("pid"),
        "uid": identity.get("uid"),
        "localApk": str(apk),
        "localApkExists": local_exists,
        "localApkSha256": local_sha,
        "installedApkSha256": actual_sha,
        "apkMatches": bool(local_sha and actual_sha == local_sha),
        "installedMismatch": bool(installed_errors),
    }
    return verification, hard_errors, installed_errors


def body_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.body is not None:
        raw = args.body
    elif args.body_file is not None:
        raw = sys.stdin.read() if args.body_file == "-" else Path(args.body_file).read_text(encoding="utf-8")
    else:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DebuggerError(f"请求体 JSON 无效：{error}") from error
    if not isinstance(value, dict):
        raise DebuggerError("请求体必须是 JSON 对象")
    return value


def response_exit_code(response: dict[str, Any]) -> int:
    status = response.get("status")
    return 0 if isinstance(status, int) and 200 <= status < 300 else 3


def account_path(path: str, account_id: str, **params: Any) -> str:
    values = {"sessionId": account_id, **params}
    query = "&".join(f"{quote(str(key))}={quote(str(value))}" for key, value in values.items())
    return f"{path}?{query}"


def default_snapshot_paths(account_id: str) -> list[str]:
    return [
        "/api/accounts",
        account_path("/api/accounts/settings", account_id),
        account_path("/api/automation/status", account_id),
        account_path("/api/logs/account", account_id, limit=100),
        account_path("/api/success-records", account_id, limit=50),
        account_path("/api/maps/bandits", account_id),
        account_path("/api/maps/mines", account_id),
    ]


def recursive_diff(
    before: Any,
    after: Any,
    *,
    path: str = "$",
    ignored_keys: set[str] | None = None,
    changes: list[dict[str, Any]] | None = None,
    max_changes: int = 200,
) -> list[dict[str, Any]]:
    ignored_keys = ignored_keys or set()
    changes = changes if changes is not None else []
    if len(changes) >= max_changes:
        return changes
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key in ignored_keys:
                continue
            child_path = f"{path}.{key}"
            if key not in before:
                changes.append({"path": child_path, "kind": "added", "after": after[key]})
            elif key not in after:
                changes.append({"path": child_path, "kind": "removed", "before": before[key]})
            else:
                recursive_diff(
                    before[key],
                    after[key],
                    path=child_path,
                    ignored_keys=ignored_keys,
                    changes=changes,
                    max_changes=max_changes,
                )
            if len(changes) >= max_changes:
                break
        return changes
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                changes.append({"path": child_path, "kind": "added", "after": after[index]})
            elif index >= len(after):
                changes.append({"path": child_path, "kind": "removed", "before": before[index]})
            else:
                recursive_diff(
                    before[index],
                    after[index],
                    path=child_path,
                    ignored_keys=ignored_keys,
                    changes=changes,
                    max_changes=max_changes,
                )
            if len(changes) >= max_changes:
                break
        return changes
    if before != after:
        changes.append({"path": path, "kind": "changed", "before": before, "after": after})
    return changes


def make_connection(args: argparse.Namespace) -> DebugConnection:
    package = args.package
    authority = args.authority or f"{package}.debug"
    return DebugConnection(
        adb=AdbClient(args.adb_bin, args.serial, args.timeout),
        package=package,
        authority=authority,
        apk=Path(args.apk).expanduser().resolve(),
        allow_installed_mismatch=args.allow_installed_mismatch,
    )


def command_identity(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    identity = connection.attach()
    print(json_text({"identity": identity, "verification": connection.verification}))
    return 0


def command_call(args: argparse.Namespace) -> int:
    # Reject an unconfirmed POST before even attaching to a device.
    if args.method == "POST" and not args.allow_post:
        raise DebuggerError(
            "POST 可能改变真实账号状态；确认需要执行时请显式加 --allow-post"
        )
    body = body_from_args(args)
    connection = make_connection(args)
    connection.attach()
    response = connection.call_api(
        args.method,
        args.path,
        body,
        allow_post=args.allow_post,
        request_id=args.request_id,
    )
    print(json_text(response))
    return response_exit_code(response)


def command_status(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    connection.attach()
    response = connection.call_api(
        "GET",
        account_path("/api/automation/status", args.account_id),
    )
    print(json_text(response))
    return response_exit_code(response)


def command_logs(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    connection.attach()
    response = connection.call_api(
        "GET",
        account_path("/api/logs/account", args.account_id, limit=args.limit),
    )
    print(json_text(response))
    return response_exit_code(response)


def command_snapshot(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    identity = connection.attach()
    paths = args.path or default_snapshot_paths(args.account_id)
    responses: dict[str, Any] = {}
    for path in paths:
        responses[path] = connection.call_api("GET", path)
    snapshot = {
        "schemaVersion": 1,
        "capturedAt": int(time.time() * 1000),
        "accountId": args.account_id,
        "identity": identity,
        "verification": connection.verification,
        "responses": responses,
    }
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json_text(snapshot) + "\n", encoding="utf-8")
    print(f"已保存调试快照：{output}")
    return 0 if all(response_exit_code(item) == 0 for item in responses.values()) else 3


def command_diff(args: argparse.Namespace) -> int:
    before_path = Path(args.before).expanduser().resolve()
    after_path = Path(args.after).expanduser().resolve()
    try:
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads(after_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DebuggerError(f"读取快照失败：{error}") from error
    changes = recursive_diff(
        before,
        after,
        ignored_keys=set(args.ignore_key),
        max_changes=args.max_changes,
    )
    print(json_text({"changeCount": len(changes), "changes": changes}))
    return 1 if changes else 0


def command_watch(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    connection.attach()
    previous: str | None = None
    iteration = 0
    try:
        while args.count == 0 or iteration < args.count:
            state = {
                "capturedAt": int(time.time() * 1000),
                "status": connection.call_api(
                    "GET",
                    account_path("/api/automation/status", args.account_id),
                ),
                "logs": connection.call_api(
                    "GET",
                    account_path("/api/logs/account", args.account_id, limit=args.limit),
                ),
            }
            comparable = json_text({"status": state["status"], "logs": state["logs"]}, pretty=False)
            if comparable != previous:
                print(json_text(state), flush=True)
                previous = comparable
            iteration += 1
            if args.count == 0 or iteration < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    return 0


def gradle_environment() -> dict[str, str]:
    environment = os.environ.copy()
    bundled_jdk = Path.home() / ".cache/codex-jdks/zulu17/zulu-17.jdk/Contents/Home"
    if not environment.get("JAVA_HOME") and bundled_jdk.is_dir():
        environment["JAVA_HOME"] = str(bundled_jdk)
    return environment


def command_fast(args: argparse.Namespace) -> int:
    gradlew = Path(args.gradlew).expanduser().resolve()
    if not gradlew.is_file():
        raise DebuggerError(f"找不到 Gradle Wrapper：{gradlew}")
    print("正在增量构建 Debug APK…", flush=True)
    try:
        build = subprocess.run(
            [str(gradlew), ":app:assembleDebug"],
            cwd=ROOT,
            env=gradle_environment(),
            check=False,
        )
    except OSError as error:
        raise DebuggerError(f"无法启动 Gradle：{error}") from error
    if build.returncode != 0:
        raise DebuggerError(f"Debug APK 构建失败（{build.returncode}）")

    apk = Path(args.apk).expanduser().resolve()
    if not apk.is_file():
        raise DebuggerError(f"构建完成但找不到 APK：{apk}")
    connection = make_connection(args)
    connection.allow_installed_mismatch = False
    install = connection.adb.run(["install", "-r", str(apk)], timeout=180)
    if install.stdout:
        print(install.stdout.strip())
    identity = connection.attach(require_local_apk=True)
    print(
        json_text(
            {
                "message": "Debug APK 已安装，未启动界面、未自动开始任务",
                "identity": identity,
                "verification": connection.verification,
            }
        )
    )
    return 0


def command_open_ui(args: argparse.Namespace) -> int:
    connection = make_connection(args)
    connection.attach()
    activity = args.activity or f"{args.package}/.AssistantWebActivity"
    completed = connection.adb.run(["shell", "am", "start", "-n", activity])
    print((completed.stdout or "").strip() or "已启动手机辅助界面")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "通过 ADB 直接复用手机辅助 LocalAssistantApiController 的 Debug-only 调试器"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用示例：
  python3 tools/mobile_debug.py identity
  python3 tools/mobile_debug.py call GET /api/health
  python3 tools/mobile_debug.py status 1608600
  python3 tools/mobile_debug.py logs 1608600 --limit 100
  python3 tools/mobile_debug.py snapshot 1608600 --out before.json
  python3 tools/mobile_debug.py diff before.json after.json --ignore-key capturedAt
  python3 tools/mobile_debug.py call POST /api/automation/stop --body '{"sessionId":"1608600"}' --allow-post
  python3 tools/mobile_debug.py fast
  python3 tools/mobile_debug.py open-ui
""",
    )
    parser.add_argument("--adb-bin", default=os.environ.get("ADB_BIN", "adb"), help="adb 可执行文件")
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL"), help="ADB 设备序列号")
    parser.add_argument("--package", default=DEFAULT_PACKAGE, help="应用包名")
    parser.add_argument("--authority", help="Debug Provider authority，默认为 <package>.debug")
    parser.add_argument("--activity", help="需要打开的 Activity")
    parser.add_argument("--apk", default=str(DEFAULT_APK), help="用于 SHA-256 比对的本地 Debug APK")
    parser.add_argument("--gradlew", default=str(DEFAULT_GRADLEW), help="Gradle Wrapper 路径")
    parser.add_argument("--timeout", type=float, default=60.0, help="ADB 超时秒数")
    parser.add_argument(
        "--allow-installed-mismatch",
        action="store_true",
        help="只读检查旧版现场时，允许设备版本/APK SHA 与本地不同",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    identity = subparsers.add_parser("identity", aliases=["attach"], help="校验包名、版本、PID 和 APK SHA")
    identity.set_defaults(handler=command_identity)

    call = subparsers.add_parser("call", help="调用任意现有 /api/ 接口")
    call.add_argument("method", type=str.upper, choices=["GET", "POST"])
    call.add_argument("path")
    body_group = call.add_mutually_exclusive_group()
    body_group.add_argument("--body", help="JSON 对象字符串")
    body_group.add_argument("--body-file", help="JSON 文件，- 表示标准输入")
    call.add_argument("--request-id", help="自定义请求 ID")
    call.add_argument("--allow-post", action="store_true", help="显式允许真实 POST")
    call.set_defaults(handler=command_call)

    status = subparsers.add_parser("status", help="查看账号任务与调度状态")
    status.add_argument("account_id")
    status.set_defaults(handler=command_status)

    logs = subparsers.add_parser("logs", help="查看账号中文任务日志")
    logs.add_argument("account_id")
    logs.add_argument("--limit", type=int, choices=range(1, 201), default=100, metavar="1..200")
    logs.set_defaults(handler=command_logs)

    snapshot = subparsers.add_parser("snapshot", help="保存账号诊断快照")
    snapshot.add_argument("account_id")
    snapshot.add_argument("--out", required=True)
    snapshot.add_argument(
        "--path",
        action="append",
        help="自定义 GET 路径（可重复）；不传则采集通用状态/日志/配置",
    )
    snapshot.set_defaults(handler=command_snapshot)

    diff = subparsers.add_parser("diff", help="对比两份 JSON 快照")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--ignore-key", action="append", default=[])
    diff.add_argument("--max-changes", type=int, default=200)
    diff.set_defaults(handler=command_diff)

    watch = subparsers.add_parser("watch", help="持续观察任务状态和日志变化")
    watch.add_argument("account_id")
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--limit", type=int, choices=range(1, 201), default=30, metavar="1..200")
    watch.add_argument("--count", type=int, default=0, help="采样次数，0 表示持续到 Ctrl-C")
    watch.set_defaults(handler=command_watch)

    fast = subparsers.add_parser("fast", help="增量构建、adb install -r、SHA 校验，不启动界面")
    fast.set_defaults(handler=command_fast)

    open_ui = subparsers.add_parser("open-ui", help="单独打开手机辅助 WebView")
    open_ui.set_defaults(handler=command_open_ui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except DebuggerError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

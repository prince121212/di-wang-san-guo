"""Shared account login/bootstrap workflow over a byte-only HTTP host port.

The host performs HTTP.  This module owns platform selection, passport fields,
game opcodes, packet bytes, response parsing, role selection and the normalized
public/secret Session facts consumed by both desktop and Android.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct
import urllib.parse
from typing import Any, Callable, Mapping

from ..features.daily import parse_e200_daily_activity
from ..features.generals import (
    parse_8004_head,
    parse_idle_army_from_8004,
    recover_generals_from_8004,
)
from ..features.inventory import parse_8104_inventory
from ..features.raid import build_raid_fief_list_payload, parse_raid_fief_list
from ..ports import RawHttpPort
from ..protocol.wire import encode_utf, make_packet, parse_response
from ..reference import normalize_platform_key, platform_display_name
from .protocol import find_login_area, parse_8003_login, parse_passport_area_list


SOURCE = "diwang.sanguo"
GAME_KEY = "diwang.sanguo"
CTYPE = "7054"
VERSION = "1660606"
TARGETS = "1,2,3,5,11,12,13,14,15,16,17,18,19,20,21,31,32,33,34,41,91"
GAME_PATH = "/kingWapServer/HttpClient"

PLATFORM_LOGIN_PROFILES: dict[str, dict[str, Any]] = {
    "sglm": {
        "key": "sglm",
        "name": "热血三国联盟",
        "passport": "https://sglmpass.3gking.net:12443/",
        "channel": "0000480502",
        "header": "1660606`7054`0000480502",
        "auth": "direct_passport",
        "defaultServerQuery": "周年服351区",
    },
    "downjoy": {
        "key": "downjoy",
        "name": "当乐帝王三国",
        "passport": "https://3gking.net:11443/",
        "channel": "0000430000",
        "header": "1660606`7054`0000430000",
        "auth": "downjoy_sdk",
        "sdkLogin": "https://ngsdk.d.cn/api/user/login",
        "sdkVersion": "4.9.4",
        "sdkProtocolVersion": "2.0",
        "sdkCid": "0",
        "sdkScreen": "2296x1035",
        "appId": "89",
        "appKey": "d0JG9Jn2",
        "serverSeqNum": "1",
        "defaultServerQuery": "1025区",
    },
}


class SharedLoginError(RuntimeError):
    """A deterministic or retry-safe login failure."""

    def __init__(self, message: str, *, code: str = "ACCOUNT_LOGIN_FAILED") -> None:
        super().__init__(message)
        self.code = str(code or "ACCOUNT_LOGIN_FAILED")


def perform_shared_login(
    http: RawHttpPort,
    *,
    username: str,
    password: str,
    server_query: str,
    platform: Any = None,
    now_millis: Callable[[], int],
    before_first_request: Callable[[], None] | None = None,
    progress: Callable[[int, Mapping[str, object]], None] | None = None,
    on_area_catalog: Callable[[str, list[dict[str, str]]], None] | None = None,
) -> dict[str, Any]:
    """Perform one complete login and return normalized, host-neutral facts."""

    username = str(username or "").strip()
    password = str(password or "")
    if not username:
        raise SharedLoginError("账号不能为空", code="ACCOUNT_USERNAME_REQUIRED")
    if not password:
        raise SharedLoginError("密码不能为空", code="ACCOUNT_PASSWORD_REQUIRED")
    platform_key = normalize_platform_key(platform)
    profile = PLATFORM_LOGIN_PROFILES[platform_key]
    server_query = str(
        server_query or profile["defaultServerQuery"]
    ).strip()
    if not server_query:
        raise SharedLoginError("区服不能为空", code="ACCOUNT_SERVER_REQUIRED")

    request_started = False

    def stage(value: int, phase: str) -> None:
        if progress is not None:
            progress(int(value), {"phase": str(phase)})

    def exchange(request: Mapping[str, object], phase: str) -> bytes:
        nonlocal request_started
        if not request_started:
            request_started = True
            if before_first_request is not None:
                before_first_request()
        try:
            response = http.exchange(request)
        except SharedLoginError:
            raise
        except Exception as error:
            raise SharedLoginError(
                f"{phase}网络失败：{error}",
                code="ACCOUNT_LOGIN_NETWORK_FAILED",
            ) from error
        try:
            status = int(response.get("status") or 0)
        except (TypeError, ValueError) as error:
            raise SharedLoginError(
                f"{phase}返回无效 HTTP 状态",
                code="ACCOUNT_LOGIN_TRANSPORT_INVALID",
            ) from error
        body = response.get("body")
        if not isinstance(body, (bytes, bytearray)):
            raise SharedLoginError(
                f"{phase}返回非字节响应",
                code="ACCOUNT_LOGIN_TRANSPORT_INVALID",
            )
        raw = bytes(body)
        if not 200 <= status < 300:
            preview = raw.decode("utf-8", errors="ignore")[:240]
            raise SharedLoginError(
                f"{phase} HTTP {status}：{preview}",
                code="ACCOUNT_LOGIN_HTTP_FAILED",
            )
        return raw

    stage(5, "passport-auth")
    passport_overrides: dict[str, str] = {}
    if profile["auth"] == "downjoy_sdk":
        passport_overrides = _downjoy_sdk_login(
            exchange,
            profile,
            username,
            password,
        )
    list_params: dict[str, str] = {
        "username": username,
        "password": password,
        "channelId": str(profile["channel"]),
        "source": SOURCE,
        "cType": CTYPE,
        "cVersion": VERSION,
        "gameKey": GAME_KEY,
        "target": TARGETS,
    }
    list_params.update(passport_overrides)
    passport_text = exchange(
        _get_request(
            str(profile["passport"]) + "common/area/list.action",
            list_params,
        ),
        "获取区服列表",
    ).decode("utf-8", errors="ignore")
    try:
        passport_session, user_id, areas = parse_passport_area_list(passport_text)
    except Exception as error:
        raise SharedLoginError(str(error), code="ACCOUNT_PASSPORT_REJECTED") from error
    if on_area_catalog is not None:
        # The area list is a complete public passport snapshot.  Hosts may
        # enqueue its cloud publication here, before selecting one area; a
        # publication failure must never turn an otherwise valid login into a
        # login failure.
        try:
            on_area_catalog(platform_key, [dict(area) for area in areas])
        except Exception:
            pass
    area = find_login_area(areas, server_query)
    if area is None:
        raise SharedLoginError(
            f"未找到区服：{server_query}",
            code="ACCOUNT_SERVER_NOT_FOUND",
        )

    account_with_suffix = ""
    try:
        validate = exchange(
            _get_request(
                str(profile["passport"]) + "system/user/validate.action",
                {"session": passport_session, "target": "1,2"},
            ),
            "验证账号标识",
        ).decode("utf-8", errors="ignore")
        account_with_suffix = (
            validate.strip().split("`")[1]
            if len(validate.strip().split("`")) > 1
            else ""
        )
    except SharedLoginError:
        # This optional display identifier is not a login commit gate.
        account_with_suffix = ""

    stage(18, "passport-enter-area")
    entered = exchange(
        _get_request(
            str(profile["passport"]) + "common/area/enter.action",
            {"session": passport_session, "areaKey": area["serverKey"]},
        ),
        "进入区服",
    ).decode("utf-8", errors="ignore").strip()
    if entered != "1":
        raise SharedLoginError(
            f"进入区服失败：{entered}",
            code="ACCOUNT_ENTER_SERVER_REJECTED",
        )

    game_http = str(area["serverUrl"]).rstrip("/") + GAME_PATH

    def game_exchange(opcode: int, payload: bytes, dm: int, phase: str) -> list[dict[str, Any]]:
        request_bytes = make_packet(
            [(int(opcode), bytes(payload))],
            int(dm),
            header=str(profile["header"]),
            timestamp_millis=int(now_millis()),
        )
        response_bytes = exchange(
            {
                "method": "POST",
                "url": game_http,
                "headers": {
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "DWPMSharedCore/1.0",
                },
                "body": request_bytes,
                "connectTimeoutMillis": 15_000,
                "readTimeoutMillis": 25_000,
            },
            phase,
        )
        packets = parse_response(response_bytes)
        parse_error = next(
            (
                str(packet.get("parseError") or "")
                for packet in packets
                if isinstance(packet, dict) and packet.get("parseError")
            ),
            "",
        )
        if parse_error:
            raise SharedLoginError(
                f"{phase}响应解析失败：{parse_error}",
                code="ACCOUNT_GAME_RESPONSE_INVALID",
            )
        return packets

    stage(30, "game-login-base")
    login_payload = (
        encode_utf(user_id)
        + encode_utf(passport_session)
        + encode_utf(str(profile["channel"]))
    )
    login_packets = game_exchange(0x1003, login_payload, 0, "游戏服登录")
    login_packet = _packet(login_packets, 0x8003)
    if login_packet is None:
        raise SharedLoginError(
            "0x1003 未返回 0x8003 登录回执",
            code="ACCOUNT_GAME_LOGIN_UNCONFIRMED",
        )
    try:
        login_info = parse_8003_login(bytes(login_packet["payload"]))
    except Exception as error:
        raise SharedLoginError(
            f"0x8003 登录回执解析失败：{error}",
            code="ACCOUNT_GAME_LOGIN_INVALID",
        ) from error
    if int(login_info.get("status") or 0) != 0:
        raise SharedLoginError(
            f"游戏服登录失败：{login_info.get('message') or 'unknown'}",
            code="ACCOUNT_GAME_LOGIN_REJECTED",
        )
    roles = list(login_info.get("roles") or [])
    if not roles:
        raise SharedLoginError("账号在该区服无角色", code="ACCOUNT_ROLE_MISSING")
    selected_index = max(0, int(login_info.get("selected") or 0))
    selected_role = dict(
        roles[selected_index] if selected_index < len(roles) else roles[0]
    )
    role_id = int(selected_role["roleId"])
    dm = int(login_info["dm"])

    stage(45, "game-role-bootstrap")
    state_packets_1004 = game_exchange(
        0x1004,
        struct.pack(">q", -1),
        dm,
        "游戏角色初始化",
    )
    state_packets_1016 = game_exchange(
        0x1016,
        struct.pack(">q", role_id),
        dm,
        "游戏角色状态同步",
    )
    state_packet = _packet(state_packets_1016, 0x8004) or _packet(
        state_packets_1004,
        0x8004,
    )
    if state_packet is None:
        raise SharedLoginError(
            "0x1004/0x1016 均未返回 0x8004 角色状态",
            code="ACCOUNT_ROLE_STATE_UNCONFIRMED",
        )
    state_payload = bytes(state_packet["payload"])
    role_state = parse_8004_head(state_payload, "shared-login/0x8004")
    if role_state.get("parseError"):
        raise SharedLoginError(
            f"0x8004 角色状态解析失败：{role_state['parseError']}",
            code="ACCOUNT_ROLE_STATE_INVALID",
        )
    if int(role_state.get("roleId") or 0) != role_id:
        raise SharedLoginError(
            "0x8004 返回角色与 0x8003 选中角色不一致",
            code="ACCOUNT_ROLE_ID_MISMATCH",
        )
    state_hex = state_payload.hex()
    generals = recover_generals_from_8004(state_hex)
    army = parse_idle_army_from_8004(state_hex, generals)

    stage(62, "game-optional-state")
    optional_packets: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {"items": [], "equipment": []}
    daily_activity: dict[str, Any] = {}
    owned_fiefs: list[dict[str, Any]] = []
    optional_warnings: list[str] = []

    try:
        inventory_packets = game_exchange(0x1104, b"\x00", dm, "刷新背包")
        optional_packets.extend(inventory_packets)
        packet_8104 = _packet(inventory_packets, 0x8104)
        if packet_8104 is not None:
            inventory = parse_8104_inventory(
                bytes(packet_8104["payload"]),
                "shared-login/0x8104",
            )
    except SharedLoginError as error:
        optional_warnings.append(str(error))

    try:
        daily_packets = game_exchange(0x6200, b"", dm, "刷新日常进度")
        optional_packets.extend(daily_packets)
        packet_e200 = _packet(daily_packets, 0xE200)
        if packet_e200 is not None:
            daily_activity = parse_e200_daily_activity(
                bytes(packet_e200["payload"]),
                "shared-login/0xe200",
            )
    except SharedLoginError as error:
        optional_warnings.append(str(error))

    try:
        fief_packets = game_exchange(
            0x1310,
            build_raid_fief_list_payload(str(role_state.get("roleName") or "")),
            dm,
            "刷新自有封地",
        )
        optional_packets.extend(fief_packets)
        packet_8310 = _packet(fief_packets, 0x8310)
        if packet_8310 is not None:
            parsed_fiefs = parse_raid_fief_list(bytes(packet_8310["payload"]))
            if parsed_fiefs.get("parseError"):
                optional_warnings.append(str(parsed_fiefs["parseError"]))
            else:
                owned_fiefs = [dict(item) for item in parsed_fiefs.get("fiefs") or []]
    except SharedLoginError as error:
        optional_warnings.append(str(error))

    all_packets = (
        login_packets
        + state_packets_1004
        + state_packets_1016
        + optional_packets
    )
    stage(82, "login-facts-ready")
    return {
        "accountRef": str(role_id),
        "username": username,
        "platformKey": platform_key,
        "platform": platform_display_name(platform_key),
        "area": dict(area),
        "gameHttp": game_http,
        "passportSession": passport_session,
        "userId": user_id,
        "accountWithSuffix": account_with_suffix,
        "dm": dm,
        "roles": roles,
        "selectedRole": selected_role,
        "roleState": role_state,
        "state8004PayloadHex": state_hex,
        "generals": generals,
        "army": army,
        "inventory": inventory,
        "dailyActivity": daily_activity,
        "ownedFiefs": owned_fiefs,
        "warnings": optional_warnings,
        "responseOpcodes": [
            f"0x{int(packet.get('opcode') or 0):04x}"
            for packet in all_packets
            if isinstance(packet, dict) and packet.get("opcode") is not None
        ],
        "syncedAtMillis": int(now_millis()),
    }


def _packet(
    packets: list[dict[str, Any]],
    opcode: int,
) -> dict[str, Any] | None:
    return next(
        (
            packet
            for packet in packets
            if isinstance(packet, dict)
            and int(packet.get("opcode") or -1) == int(opcode)
            and isinstance(packet.get("payload"), (bytes, bytearray))
        ),
        None,
    )


def _get_request(url: str, query: Mapping[str, object]) -> dict[str, object]:
    return {
        "method": "GET",
        "url": str(url),
        "query": {str(key): str(value) for key, value in query.items()},
        "headers": {"User-Agent": "DWPMSharedCore/1.0"},
        "body": b"",
        "connectTimeoutMillis": 15_000,
        "readTimeoutMillis": 25_000,
    }


def _downjoy_sdk_login(
    exchange: Callable[[Mapping[str, object], str], bytes],
    profile: Mapping[str, Any],
    username: str,
    password: str,
) -> dict[str, str]:
    params = _downjoy_login_parameters(profile, username, password)
    plain_body = urllib.parse.urlencode(params) + "&"
    encrypted_body = urllib.parse.urlencode(
        {"data": _downjoy_httpbody_encrypt(plain_body)}
    ).encode("ascii")
    encrypted_response = exchange(
        {
            "method": "POST",
            "url": str(profile["sdkLogin"]),
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "SDK_VERSION": "4940",
                "User-Agent": (
                    "Dalvik/2.1.0 (Linux; U; Android 15; "
                    "24117RK2CC Build/AQ3A.240829.003)"
                ),
            },
            "body": encrypted_body,
            "connectTimeoutMillis": 15_000,
            "readTimeoutMillis": 25_000,
        },
        "当乐 SDK 认证",
    ).decode("ascii", errors="strict")
    try:
        payload = json.loads(_downjoy_httpbody_decrypt(encrypted_response))
    except Exception as error:
        raise SharedLoginError(
            f"当乐 SDK 登录响应无效：{error}",
            code="ACCOUNT_DOWNJOY_AUTH_INVALID",
        ) from error
    if not isinstance(payload, dict):
        raise SharedLoginError(
            "当乐 SDK 登录返回结构异常",
            code="ACCOUNT_DOWNJOY_AUTH_INVALID",
        )
    nested = payload.get("data")
    user = nested if isinstance(nested, dict) else payload
    code = payload.get("msg_code", user.get("msg_code"))
    try:
        success = int(code) == 2000
    except (TypeError, ValueError):
        success = False
    if not success:
        message = (
            payload.get("msg_desc")
            or user.get("msg_desc")
            or payload.get("message")
            or "未知错误"
        )
        raise SharedLoginError(
            f"当乐 SDK 认证失败：code={code}，{message}",
            code="ACCOUNT_DOWNJOY_AUTH_REJECTED",
        )
    token = str(user.get("access_token") or "").strip()
    umid = str(user.get("umid") or user.get("mid") or "").strip()
    if not token or not umid:
        raise SharedLoginError(
            "当乐 SDK 登录成功响应缺少 access_token/umid",
            code="ACCOUNT_DOWNJOY_AUTH_INVALID",
        )
    return {
        "session": token,
        "username": umid,
        "password": "",
        "imei": "",
        "macId": "",
    }


def _downjoy_login_parameters(
    profile: Mapping[str, Any],
    username: str,
    password: str,
) -> dict[str, str]:
    stable_device_id = str(
        os.environ.get("DWPM_DOWNJOY_UDID")
        or "3ec080de8d6f635ebf722c1bf4c3a476"
    ).strip()
    android_id = str(
        os.environ.get("DWPM_DOWNJOY_ANDROID_ID")
        or "a4c0fc067f919560"
    )
    model = str(os.environ.get("DWPM_DOWNJOY_MODEL") or "24117RK2CC")
    display = str(
        os.environ.get("DWPM_DOWNJOY_DISPLAY") or "AQ3A.240829.003"
    )
    release = str(os.environ.get("DWPM_DOWNJOY_RELEASE") or "15")
    sdk_version = str(profile["sdkVersion"])
    cid = str(profile.get("sdkCid") or "0")
    screen = str(profile.get("sdkScreen") or "1920x1080")
    app_id = str(profile["appId"])
    app_key = str(profile["appKey"])
    sov = str(profile["sdkProtocolVersion"])
    di = str(
        os.environ.get("DWPM_DOWNJOY_DI")
        or "6a73070e91f234fe21d45d0fb825b753"
    )
    sinfo = _downjoy_sdk_encrypt(
        f"null&null&null&{model}&{display}&{release}&null&null"
    )
    old_di = _downjoy_sign_param([stable_device_id])
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest().upper()
    info = _downjoy_sdk_encrypt(f"{username}&{password_hash}&&")
    par_sig = _downjoy_sign_param(
        [sdk_version, cid, screen, "1", app_id, sov, di, sinfo, info]
    )
    return {
        "ss": screen,
        "par_sig": par_sig,
        "sinfo": sinfo,
        "di": di,
        "language": "zh",
        "server_id": str(profile["serverSeqNum"]),
        "emu": "0",
        "version": sdk_version,
        "edk": "0",
        "local": "zh_CN",
        "vcode": "",
        "sig": hashlib.md5(f"{app_id}|{app_key}".encode()).hexdigest().upper(),
        "pf": "1",
        "appid": app_id,
        "old_di": old_di,
        "root": "0",
        "sov": sov,
        "udid": _downjoy_sdk_encrypt(f"{app_key}&{stable_device_id}"),
        "oaid": str(
            os.environ.get("DWPM_DOWNJOY_OAID") or "342a9bd4165f13eb"
        ),
        "cid": cid,
        "xposed": "0",
        "info": info,
    }


def _downjoy_sdk_encrypt(value: str) -> str:
    source = str(value or "").encode("utf-8")
    key = b"bNA-!/Nf"
    encrypted = bytes(
        ((~(byte ^ key[index % len(key)])) + index) & 0xFF
        for index, byte in enumerate(source)
    )
    encoded = bytearray(base64.urlsafe_b64encode(encrypted))
    if encoded:
        middle = len(encoded) // 2
        encoded[0], encoded[middle] = encoded[middle], encoded[0]
    return encoded.decode("ascii")


def _downjoy_sign_param(values: list[Any]) -> str:
    material = "shzy" + "".join(str(value or "") for value in values) + "gj88"
    return hashlib.md5(material.encode("utf-8")).hexdigest()


_DOWNJOY_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def _downjoy_httpbody_encrypt(value: str) -> str:
    source = str(value or "").encode("utf-8")
    random_bytes = secrets.token_bytes(8)
    first = bytes(_DOWNJOY_ALPHABET[value % len(_DOWNJOY_ALPHABET)] for value in random_bytes[:4])
    second = bytes(_DOWNJOY_ALPHABET[value % len(_DOWNJOY_ALPHABET)] for value in random_bytes[4:])
    key = bytearray(b"bNA-!/Nf")
    for index, value_byte in (
        (1, first[1]), (3, first[3]), (2, first[2]), (6, second[2]),
        (0, first[0]), (4, second[0]), (5, second[1]), (7, second[3]),
    ):
        key[index] ^= value_byte
    encrypted = bytearray(len(source) + 8)
    encrypted[:4] = bytes((first[0] ^ 0xFF, first[1] ^ 0xFE, first[2] ^ 0xFD, first[3] ^ 0xFC))
    for index, byte in enumerate(source):
        encrypted[index + 4] = ((~byte ^ key[index % 8]) + index) & 0xFF
    for index, byte in enumerate(second):
        encrypted[len(source) + 4 + index] = ((~byte) ^ index) & 0xFF
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def _downjoy_httpbody_decrypt(value: str) -> str:
    encoded = str(value or "").strip()
    raw = base64.urlsafe_b64decode(
        encoded + "=" * ((4 - len(encoded) % 4) % 4)
    )
    if len(raw) < 8:
        raise RuntimeError("当乐 SDK 加密响应长度异常")
    source_length = len(raw) - 8
    first = bytes((raw[0] ^ 0xFF, raw[1] ^ 0xFE, raw[2] ^ 0xFD, raw[3] ^ 0xFC))
    tail = raw[source_length + 4:source_length + 8]
    second = bytes((((tail[index] ^ index) ^ 0xFF) & 0xFF) for index in range(4))
    key = bytearray(b"bNA-!/Nf")
    for index, value_byte in (
        (1, first[1]), (3, first[3]), (2, first[2]), (6, second[2]),
        (0, first[0]), (4, second[0]), (5, second[1]), (7, second[3]),
    ):
        key[index] ^= value_byte
    plain = bytes(
        ((((raw[index + 4] - index) & 0xFF) ^ key[index % 8]) ^ 0xFF) & 0xFF
        for index in range(source_length)
    )
    return plain.decode("utf-8", errors="strict")

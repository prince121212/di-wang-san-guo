#!/usr/bin/env python3
from __future__ import annotations

import html
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("refresh_device_session_from_login.py")
spec = importlib.util.spec_from_file_location("refresh_device_session_from_login", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["refresh_device_session_from_login"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def utf(s: str) -> bytes:
    b = s.encode("utf-8")
    return len(b).to_bytes(2, "big") + b


def i8(v: int) -> bytes:
    return struct.pack(">b", v)


def u8(v: int) -> bytes:
    return struct.pack(">B", v)


def i16(v: int) -> bytes:
    return struct.pack(">h", v)


def i32(v: int) -> bytes:
    return struct.pack(">i", v)


def i64(v: int) -> bytes:
    return struct.pack(">q", v)


def make_8004_payload() -> bytes:
    head = b"".join([
        i8(0), i8(0), i64(123456789), i64(764), utf("东方美"), i8(0), u8(54),
        i64(784532), i64(1256683), i64(0), i8(1), i16(3), i8(0),
        i64(228462), i64(1000), i64(246682), i64(0), i8(0),
        i32(1006), i32(707), i64(0), i64(0), i64(1002), i64(2560),
        u8(10), u8(12), u8(0), u8(3),
    ])
    general = (7066187).to_bytes(8, "big") + utf("何颜鸥") + b"\x00\x00"
    return head + general


def make_status_payload() -> bytes:
    return b"".join([
        b"\x00" * 8,
        utf("董全基地"),
        b"\x00" * 12,
        b"\x00" * 8,
        b"\x03\x13",
        utf("建业"),
        b"\x00\xaa\x00\x0a\x00\x00\x00\x00\x00\x03",
        b"\x00\x01\x2f\x0d", utf("神农"), utf("降低20%伤兵治疗费用"),
        b"\x00\x02\x2f\x0c", utf("蚩尤"), utf("守军攻防提升10%"),
        b"\x00\x03\x2f\x0b", utf("风后"), utf("铜钱粮食产能提升30%"),
    ])


class RefreshDeviceSessionFromLoginTest(unittest.TestCase):
    def make_xml(self) -> str:
        root = {
            "accounts": [{
                "id": 1,
                "username": "1608600",
                "displayName": "旧角色",
                "serverName": "周年服351区(新服)",
                "session": {
                    "accountId": 1,
                    "sourceMode": 1,
                    "channelExtra": {
                        "realActionNetworkAllowed": "true",
                        "formationsJson": "[]",
                    },
                },
            }]
        }
        return '<map><string name="accounts_json">' + html.escape(json.dumps(root, ensure_ascii=False), quote=False) + "</string></map>"

    def test_parse_8004_head_extracts_role_resource_and_tail(self):
        state = mod.parse_8004_head(make_8004_payload())
        self.assertEqual(764, state["roleId"])
        self.assertEqual("东方美", state["roleName"])
        self.assertEqual(54, state["level"])
        self.assertEqual(784532, state["copper"])
        self.assertEqual(1256683, state["food"])
        self.assertGreater(state["tailByteCount"], 0)

    def test_apply_updates_preserves_existing_gate_and_updates_session(self):
        prefix, root, suffix = mod.parse_accounts_xml(self.make_xml())
        inventory_payload = bytes.fromhex(
            "0000000000000000000000000000"
            "0032"
            "0001"
            "000900050000000000000000"
            "01f4000a05"
        )
        result = {
            "fresh": {
                "dm": -123,
                "gameHttp": "http://game/kingWapServer/HttpClient",
                "accountWithSuffix": "1608600@gbsglm",
                "userId": "42",
                "area": {"serverUrl": "http://game", "serverKey": "qzone_351", "areaName": "周年服351区(新服)"},
                "role": {"country": "大汉", "title": ""},
            },
            "state": mod.parse_8004_head(make_8004_payload()),
            "inventory": mod.parse_8104_inventory(inventory_payload),
        }
        updates = mod.build_updates(result)
        account = mod.apply_updates_to_root(root, updates, result)
        rendered = mod.device_extra.render_accounts_xml(prefix, root, suffix)
        _, parsed, _ = mod.parse_accounts_xml(rendered)
        extra = parsed["accounts"][0]["session"]["channelExtra"]
        self.assertEqual(764, account["id"])
        self.assertEqual("东方美", account["displayName"])
        self.assertEqual("true", extra["realActionNetworkAllowed"])
        self.assertEqual("-123", extra["dm"])
        self.assertTrue(extra["state8004PayloadHex"])
        self.assertEqual("1", extra["state8004GeneralRecordCount"])
        self.assertEqual("50", extra["inventoryCapacity"])
        self.assertEqual("1", extra["inventoryItemCount"])
        items = json.loads(extra["inventoryJson"])
        self.assertEqual("传音符", items[0]["name"])
        self.assertEqual(5, items[0]["count"])

    def test_recover_status_from_8004_extracts_fief_city_and_policy_text(self):
        records = mod.recover_status_from_8004(make_status_payload().hex())

        self.assertEqual("董全基地", next(r for r in records if r["kind"] == "fiefName")["detail"])
        self.assertEqual("建业", next(r for r in records if r["kind"] == "cityName")["detail"])
        policies = [r for r in records if r["kind"] == "policyBuff"]
        self.assertEqual(["神农", "蚩尤", "风后"], [r["name"] for r in policies])
        self.assertEqual("2f0d", policies[0]["timerRawHex"])


if __name__ == "__main__":
    unittest.main()

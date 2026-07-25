from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_platform_adaptation_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class PlatformAdaptationTests(unittest.TestCase):
    def test_downjoy_httpbody_codec_round_trip(self) -> None:
        plain = "ss=2296x1035&version=4.9.4&info=test%3Dvalue&"
        encrypted = SERVER.downjoy_httpbody_encrypt(plain)
        self.assertNotEqual(encrypted, plain)
        self.assertEqual(SERVER.downjoy_httpbody_decrypt(encrypted), plain)

    def test_platforms_use_distinct_default_game_zones(self) -> None:
        self.assertEqual(
            SERVER.default_server_query("热血三国联盟"),
            "周年服351区",
        )
        self.assertEqual(
            SERVER.default_server_query("当乐帝王三国"),
            "1025区",
        )
        # Downjoy SERVER_SEQ_NUM is SDK application configuration, not the
        # selected game zone.
        self.assertEqual(
            SERVER.PLATFORM_PROFILES["downjoy"]["serverSeqNum"],
            "1",
        )

    def test_downjoy_native_algorithms_fixed_vectors(self) -> None:
        self.assertEqual(SERVER.downjoy_sdk_encrypt("abc"), "TN_f")
        self.assertEqual(
            SERVER.downjoy_sdk_encrypt("user&ABC&&"),
            "-MPdo_yW6eHDoA==",
        )
        self.assertEqual(
            SERVER.downjoy_sign_param([
                "4.9.3", "0", "1920x1080", "1", "89", "2.0", "", "abc", "xyz",
            ]),
            "3268836d4638a2c85a591fb9b7314064",
        )

    def test_downjoy_password_is_sha256_uppercase_inside_encrypted_info(self) -> None:
        params = SERVER.downjoy_login_parameters("tester", "123456")
        self.assertEqual(
            params["info"],
            "gdXPqb-nnajhkZL2p6IFvugDEakBqJm39JsZ_wgGocDNFaoNDL6d0AarIhLGEh7Q2yEqxyHIJt_nusYd2SbB6Rw2PyfhLskGAw==",
        )
        self.assertEqual(params["sig"], "F7179DA36EF465D9D5AD4ADAAFCB9F56")
        self.assertEqual(
            params["par_sig"],
            SERVER.downjoy_sign_param([
                params["version"], params["cid"], params["ss"],
                params["pf"], params["appid"], params["sov"],
                params["di"], params["sinfo"], params["info"],
            ]),
        )

    def test_downjoy_device_info_matches_apk_md5_fields(self) -> None:
        params = SERVER.downjoy_login_parameters(
            "tester",
            "123456",
            device_id="udid-1",
            android_id="android-1",
            model="MODEL",
            display="DISPLAY",
            release="11",
        )
        self.assertEqual(
            params["di"],
            SERVER.downjoy_sign_param(["udid-1", "android-1"]),
        )
        self.assertEqual(
            params["old_di"],
            SERVER.downjoy_sign_param(["udid-1"]),
        )
        self.assertEqual(
            params["sinfo"],
            SERVER.downjoy_sdk_encrypt(
                "null&null&null&MODEL&DISPLAY&11&null&null"
            ),
        )

    def test_packet_header_and_shared_maps_are_platform_scoped(self) -> None:
        packet = SERVER.make_packet(
            [(0x1003, b"")],
            0,
            header=SERVER.PLATFORM_PROFILES["downjoy"]["header"],
        )
        size = struct.unpack(">H", packet[:2])[0]
        self.assertEqual(
            packet[2:2 + size].decode(),
            "1660606`7054`0000430000",
        )
        sglm = {
            "platform": "热血三国联盟",
            "area": {"serverKey": "qzone_352"},
        }
        downjoy = {
            "platform": "当乐帝王三国",
            "area": {"serverKey": "qzone_352"},
        }
        self.assertEqual(SERVER.shared_map_server_key(sglm), "区352")
        self.assertEqual(
            SERVER.shared_map_server_key(downjoy),
            "downjoy:区352",
        )

    def test_same_username_and_zone_on_two_platforms_are_distinct(self) -> None:
        common = {"username": "10001", "serverQuery": "352区"}
        self.assertNotEqual(
            SERVER.account_stable_identity({
                **common,
                "platform": "热血三国联盟",
            }),
            SERVER.account_stable_identity({
                **common,
                "platform": "当乐帝王三国",
            }),
        )

    def test_downjoy_passport_exchange_uses_token_umid_and_empty_sdk_username(self) -> None:
        captured: dict = {}

        def fake_http_get(base: str, params: dict) -> str:
            captured.update({"base": base, "params": params})
            return (
                "game-session`game-user-id\n"
                "1`352`周年服352区`http://115.159.51.193:8888"
                "`0`0`0`0`0`0`0`qzone_352\n"
            )

        with (
            mock.patch.object(
                SERVER,
                "downjoy_sdk_login",
                return_value={
                    "token": "sdk-token",
                    "umid": "sdk-umid",
                    "callbackUsername": "",
                },
            ),
            mock.patch.object(SERVER, "http_get", side_effect=fake_http_get),
        ):
            session, user_id, areas = SERVER.fetch_passport_area_list(
                "login-name",
                "login-password",
                "当乐帝王三国",
            )
        self.assertEqual(session, "game-session")
        self.assertEqual(user_id, "game-user-id")
        self.assertEqual(areas[0]["serverKey"], "qzone_352")
        self.assertEqual(
            captured["base"],
            "https://3gking.net:11443/common/area/list.action",
        )
        self.assertEqual(captured["params"]["session"], "sdk-token")
        self.assertEqual(captured["params"]["username"], "sdk-umid")
        self.assertEqual(captured["params"]["password"], "")
        self.assertEqual(captured["params"]["channelId"], "0000430000")


if __name__ == "__main__":
    unittest.main()

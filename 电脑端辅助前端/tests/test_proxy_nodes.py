from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
APP_JS_PATH = ROOT / "电脑端辅助前端" / "app.js"
SPEC = importlib.util.spec_from_file_location("dwpm_server_proxy_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class ProxyNodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_clash_api = SERVER.clash_api
        self.original_groups = list(SERVER.CLASH_GROUP_CANDIDATES)
        self.original_domestic_group = SERVER.CLASH_DOMESTIC_GROUP
        self.original_parent_groups = list(SERVER.CLASH_PARENT_GROUP_CANDIDATES)

    def tearDown(self) -> None:
        SERVER.clash_api = self.original_clash_api
        SERVER.CLASH_GROUP_CANDIDATES = self.original_groups
        SERVER.CLASH_DOMESTIC_GROUP = self.original_domestic_group
        SERVER.CLASH_PARENT_GROUP_CANDIDATES = self.original_parent_groups
        SERVER.ACCOUNTS.clear()
        SERVER.SESSIONS.clear()

    def test_domestic_group_imports_all_real_nodes(self) -> None:
        nodes = ["香港节点", "[飞鸟云] hy2台湾07", "嵌套分组"]
        proxies = {
            "国内分组": {"type": "Selector", "all": nodes},
            "香港节点": {"type": "Shadowsocks"},
            "[飞鸟云] hy2台湾07": {"type": "Hysteria2"},
            "嵌套分组": {"type": "Selector"},
        }
        SERVER.CLASH_DOMESTIC_GROUP = "国内分组"
        SERVER.CLASH_GROUP_CANDIDATES = ["国内分组"]
        SERVER.clash_api = lambda *_args, **_kwargs: (200, {"proxies": proxies})

        group, imported = SERVER.clash_proxy_groups()

        self.assertEqual(group, "国内分组")
        self.assertEqual(imported, ["香港节点", "[飞鸟云] hy2台湾07"])

    def test_frontend_loads_proxy_nodes_without_an_account(self) -> None:
        source = APP_JS_PATH.read_text(encoding="utf-8")
        start = source.index("async function loadProxyNodes(")
        end = source.index("\nfunction renderLoginAreaOptions", start)
        function_source = source[start:end]

        self.assertNotIn("if (!appState.sessionId)", function_source)
        self.assertIn('sessionId: appState.sessionId || ""', function_source)
        self.assertIn("/api/proxy/nodes?", function_source)

    def test_switching_domestic_node_activates_parent_selector(self) -> None:
        calls: list[tuple[str, str]] = []
        proxies = {
            "黄大卫订阅": {
                "type": "Selector",
                "all": ["顶级机场", "国内分组"],
                "now": "顶级机场",
            },
            "国内分组": {
                "type": "Selector",
                "all": ["台湾节点"],
                "now": "台湾节点",
            },
        }

        def fake_api(method: str, path: str, payload=None):
            if method == "GET":
                return 200, {"proxies": proxies}
            calls.append((path, str((payload or {}).get("name") or "")))
            return 204, None

        SERVER.CLASH_PARENT_GROUP_CANDIDATES = ["黄大卫订阅"]
        SERVER.clash_api = fake_api

        SERVER.switch_clash_node("国内分组", "台湾节点")

        self.assertEqual(
            calls,
            [
                ("/proxies/%E9%BB%84%E5%A4%A7%E5%8D%AB%E8%AE%A2%E9%98%85", "国内分组"),
                ("/proxies/%E5%9B%BD%E5%86%85%E5%88%86%E7%BB%84", "台湾节点"),
            ],
        )

    def test_imported_nodes_have_short_names_and_ip_labels(self) -> None:
        node = "[飞鸟云] hy2台湾07"
        self.assertEqual(SERVER.clean_proxy_node_name(node), "台湾 飞鸟07")
        self.assertEqual(SERVER.known_outbound_ip(node), "111.243.111.170")

    def test_top_airport_only_exposes_game_server_verified_nodes(self) -> None:
        verified = list(SERVER.WEB_PROXY_NODE_ALLOWLIST)
        top_nodes = [
            node for node in verified
            if node not in SERVER.PROXY_NODE_SELECTOR_GROUPS
        ]
        sub_nodes = [
            node for node in verified
            if node in SERVER.PROXY_NODE_SELECTOR_GROUPS
        ]
        proxies = {
            "顶级机场": {
                "type": "Selector",
                "all": [
                    "剩余流量：100 GB",
                    *top_nodes,
                    SERVER.CLASH_SUB_GROUP,
                    "美国未通过节点",
                    "嵌套分组",
                ],
            },
            SERVER.CLASH_SUB_GROUP: {
                "type": "Selector",
                "all": sub_nodes,
            },
            **{node: {"type": "Shadowsocks"} for node in verified},
            "美国未通过节点": {"type": "Hysteria2"},
            "嵌套分组": {"type": "Selector"},
        }
        SERVER.CLASH_GROUP_CANDIDATES = ["顶级机场", "国内分组"]
        SERVER.clash_api = lambda *_args, **_kwargs: (200, {"proxies": proxies})

        group, imported = SERVER.clash_proxy_groups()

        self.assertEqual(group, "顶级机场")
        self.assertEqual(imported, verified)
        self.assertEqual(SERVER.clean_proxy_node_name("[824] sh - 香港"), "香港 824")
        self.assertEqual(SERVER.known_outbound_ip("[824] sh - 香港"), "104.28.152.117")

    def test_switching_sub_node_activates_top_airport_then_child(self) -> None:
        node = "[SUB] 测试节点"
        calls: list[tuple[str, str]] = []
        proxies = {
            "顶级机场": {
                "type": "Selector",
                "all": ["sub国内分组", "日本节点"],
                "now": "日本节点",
            },
            "sub国内分组": {
                "type": "Selector",
                "all": [node],
                "now": node,
            },
            node: {"type": "Shadowsocks"},
        }

        def fake_api(method: str, path: str, payload=None):
            if method == "GET":
                return 200, {"proxies": proxies}
            calls.append((path, str((payload or {}).get("name") or "")))
            return 204, None

        original_selector = dict(SERVER.PROXY_NODE_SELECTOR_GROUPS)
        try:
            SERVER.PROXY_NODE_SELECTOR_GROUPS[node] = "sub国内分组"
            SERVER.CLASH_PARENT_GROUP_CANDIDATES = ["顶级机场"]
            SERVER.clash_api = fake_api

            SERVER.switch_clash_node("顶级机场", node)
        finally:
            SERVER.PROXY_NODE_SELECTOR_GROUPS.clear()
            SERVER.PROXY_NODE_SELECTOR_GROUPS.update(original_selector)

        self.assertEqual(
            calls,
            [
                ("/proxies/%E9%A1%B6%E7%BA%A7%E6%9C%BA%E5%9C%BA", "sub国内分组"),
                ("/proxies/sub%E5%9B%BD%E5%86%85%E5%88%86%E7%BB%84", node),
            ],
        )

    def test_removed_hzvpn_mode_migrates_to_local_direct(self) -> None:
        account = {
            "proxyMode": "direct",
            "proxyGroup": "旧分组",
            "proxyNode": "旧节点",
            "proxyIp": "59.125.53.4",
        }

        SERVER.migrate_removed_proxy_routes(account)

        self.assertEqual(account["proxyMode"], "local")
        self.assertEqual(account["proxyNode"], "")
        self.assertEqual(account["proxyIp"], "")

    def test_proxy_ip_capacity_counts_different_nodes_with_same_egress(self) -> None:
        shared_ip = "203.0.113.10"
        SERVER.ACCOUNTS.update({
            "s1": {"started": True, "proxyNode": "节点A", "proxyIp": shared_ip},
            "s2": {"started": True, "proxyNode": "节点B", "proxyIp": shared_ip},
            "s3": {"started": True, "proxyNode": "节点C", "proxyIp": shared_ip},
        })
        SERVER.SESSIONS.update({
            "s1": {"sessionId": "s1"},
            "s2": {"sessionId": "s2"},
            "s3": {"sessionId": "s3"},
        })

        self.assertEqual(
            SERVER.live_account_count_for_proxy_ip(
                shared_ip,
                exclude_account_id="s1",
            ),
            2,
        )
        with self.assertRaisesRegex(RuntimeError, "每个IP最多登录 2 个账号"):
            SERVER.ensure_proxy_ip_capacity(shared_ip, account_id="s1")

    def test_heartbeat_rotation_skips_full_egress_ip(self) -> None:
        SERVER.ACCOUNTS.update({
            "s1": {
                "sessionId": "s1",
                "started": True,
                "proxyMode": "manual",
                "proxyNode": "节点A",
                "proxyIp": "203.0.113.1",
                "heartbeatNetworkFailureCount": 3,
            },
            "s2": {
                "sessionId": "s2",
                "started": True,
                "proxyNode": "其他节点1",
                "proxyIp": "203.0.113.2",
            },
            "s3": {
                "sessionId": "s3",
                "started": True,
                "proxyNode": "其他节点2",
                "proxyIp": "203.0.113.2",
            },
        })
        SERVER.SESSIONS.update({
            sid: {"sessionId": sid}
            for sid in ("s1", "s2", "s3")
        })
        known_ips = {
            "节点A": "203.0.113.1",
            "节点B": "203.0.113.2",
            "节点C": "203.0.113.3",
        }
        switched: list[str] = []

        with patch.object(
            SERVER,
            "clash_proxy_groups",
            return_value=("可选分组", ["节点A", "节点B", "节点C"]),
        ), patch.object(
            SERVER,
            "known_outbound_ip",
            side_effect=lambda node: known_ips[node],
        ), patch.object(
            SERVER,
            "switch_clash_node",
            side_effect=lambda _group, node: switched.append(node),
        ), patch.object(
            SERVER,
            "resolve_outbound_ip",
            side_effect=lambda node, **_kwargs: known_ips[node],
        ), patch.object(
            SERVER,
            "persist_runtime_state",
        ), patch.object(
            SERVER,
            "account_log",
        ):
            result = SERVER.rotate_heartbeat_proxy("s1")

        self.assertTrue(result["success"])
        self.assertEqual(result["node"], "节点C")
        self.assertEqual(switched, ["节点C"])
        self.assertEqual(SERVER.ACCOUNTS["s1"]["proxyIp"], "203.0.113.3")
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkFailureCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkSwitchCount"], 1)


if __name__ == "__main__":
    unittest.main()

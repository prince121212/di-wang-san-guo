from __future__ import annotations

import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server.py"
APP_JS_PATH = ROOT / "app.js"
INDEX_PATH = ROOT / "index.html"
SPEC = importlib.util.spec_from_file_location("dwpm_server_starter_batch_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class StarterBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_accounts = SERVER.ACCOUNTS
        self.original_sessions = SERVER.SESSIONS
        SERVER.ACCOUNTS = {}
        SERVER.SESSIONS = {}

    def tearDown(self) -> None:
        SERVER.ACCOUNTS = self.original_accounts
        SERVER.SESSIONS = self.original_sessions

    def test_dashboard_button_opens_multi_account_server_picker(self) -> None:
        html = INDEX_PATH.read_text(encoding="utf-8")
        source = APP_JS_PATH.read_text(encoding="utf-8")

        self.assertIn('id="starterBatchModal"', html)
        self.assertIn('id="starterBatchAccountList"', html)
        self.assertIn('class="starter-batch-server"', source)
        self.assertIn(
            'addEventListener("click", openStarterBatchModal)',
            source,
        )
        self.assertIn('"/api/starter/jobs/create-batch"', source)

    def test_balancer_uses_every_distinct_ip_before_reusing_one(self) -> None:
        account_ids = [f"account-{index}" for index in range(5)]
        SERVER.ACCOUNTS.update({
            account_id: {
                "sessionId": account_id,
                "username": account_id,
                "status": "stopped",
                "started": False,
            }
            for account_id in account_ids
        })
        ips = {
            "node-a": "203.0.113.1",
            "node-b": "203.0.113.2",
            "node-c": "203.0.113.3",
        }

        with patch.object(
            SERVER,
            "clash_proxy_groups",
            return_value=("starter-group", list(ips)),
        ), patch.object(
            SERVER,
            "known_outbound_ip",
            side_effect=lambda node: ips[node],
        ), patch.object(SERVER, "persist_runtime_state"):
            result = SERVER.assign_balanced_proxy_nodes(account_ids)

        assigned_ips = [
            result["assignments"][account_id]["ip"]
            for account_id in account_ids
        ]
        self.assertEqual(len(set(assigned_ips[:3])), 3)
        self.assertLessEqual(max(Counter(assigned_ips).values()), 2)
        self.assertFalse(result["errors"])
        self.assertTrue(all(
            SERVER.ACCOUNTS[account_id]["proxyMode"] == "auto"
            for account_id in account_ids
        ))

    def test_balancer_refuses_a_third_account_on_each_ip(self) -> None:
        account_ids = [f"account-{index}" for index in range(7)]
        SERVER.ACCOUNTS.update({
            account_id: {
                "sessionId": account_id,
                "username": account_id,
                "status": "stopped",
                "started": False,
            }
            for account_id in account_ids
        })
        ips = {
            "node-a": "203.0.113.1",
            "node-b": "203.0.113.2",
            "node-c": "203.0.113.3",
        }

        with patch.object(
            SERVER,
            "clash_proxy_groups",
            return_value=("starter-group", list(ips)),
        ), patch.object(
            SERVER,
            "known_outbound_ip",
            side_effect=lambda node: ips[node],
        ), patch.object(SERVER, "persist_runtime_state"):
            result = SERVER.assign_balanced_proxy_nodes(account_ids)

        self.assertEqual(len(result["assignments"]), 6)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("最多同时登录2个账号", next(iter(result["errors"].values())))

    def test_connecting_account_reserves_ip_capacity(self) -> None:
        SERVER.ACCOUNTS["connecting"] = {
            "sessionId": "connecting",
            "started": True,
            "status": "checking",
            "proxyIp": "203.0.113.9",
        }

        self.assertEqual(
            SERVER.live_account_count_for_proxy_ip("203.0.113.9"),
            1,
        )

    def test_login_fallback_skips_an_ip_already_at_capacity(self) -> None:
        SERVER.ACCOUNTS.update({
            "selected": {
                "sessionId": "selected",
                "started": True,
                "proxyNode": "node-a",
                "proxyIp": "203.0.113.1",
            },
            "busy-1": {
                "sessionId": "busy-1",
                "started": True,
                "proxyIp": "203.0.113.2",
            },
            "busy-2": {
                "sessionId": "busy-2",
                "started": True,
                "proxyIp": "203.0.113.2",
            },
        })
        ips = {
            "node-a": "203.0.113.1",
            "node-b": "203.0.113.2",
            "node-c": "203.0.113.3",
        }

        with patch.object(
            SERVER,
            "known_outbound_ip",
            side_effect=lambda node: ips[node],
        ):
            ordered = SERVER.ordered_proxy_nodes_for_account(
                "selected", list(ips), "node-a",
            )

        self.assertEqual(ordered[0], "node-a")
        self.assertIn("node-c", ordered)
        self.assertNotIn("node-b", ordered)

    def test_batch_prepares_all_routes_before_starting_workers(self) -> None:
        SERVER.ACCOUNTS.update({
            "source-a": {
                "sessionId": "source-a", "username": "user-a",
                "password": "secret-a", "platform": "热血三国联盟",
                "serverQuery": "351区", "status": "stopped",
            },
            "source-b": {
                "sessionId": "source-b", "username": "user-b",
                "password": "secret-b", "platform": "热血三国联盟",
                "serverQuery": "351区", "status": "stopped",
            },
        })
        prepared = {
            "source-a": {
                "sourceAccountId": "source-a", "accountId": "target-a",
                "username": "user-a", "platform": "热血三国联盟",
                "serverQuery": "352区", "account": {},
            },
            "source-b": {
                "sourceAccountId": "source-b", "accountId": "target-b",
                "username": "user-b", "platform": "热血三国联盟",
                "serverQuery": "352区", "account": {},
            },
        }

        def prepare(source_id, _server):
            row = dict(prepared[source_id])
            SERVER.ACCOUNTS[row["accountId"]] = {
                "sessionId": row["accountId"],
                "username": row["username"],
                "status": "stopped",
            }
            return row

        proxy_result = {
            "group": "starter-group",
            "assignments": {
                "target-a": {"group": "starter-group", "node": "a", "ip": "203.0.113.1"},
                "target-b": {"group": "starter-group", "node": "b", "ip": "203.0.113.2"},
            },
            "errors": {},
        }
        with patch.object(
            SERVER, "prepare_starter_account_for_server", side_effect=prepare,
        ), patch.object(
            SERVER, "assign_balanced_proxy_nodes", return_value=proxy_result,
        ) as assign, patch.object(
            SERVER, "create_starter_job",
            side_effect=lambda account_id, _level, start_worker=False: {
                "job_id": f"job-{account_id}", "account_id": account_id,
            },
        ) as create, patch.object(
            SERVER, "start_starter_worker",
        ) as start, patch.object(
            SERVER, "save_starter_container_count", return_value=2,
        ), patch.object(
            SERVER, "list_starter_jobs", return_value=[{}, {}],
        ):
            result = SERVER.create_starter_jobs_batch([
                {"accountId": "source-a", "serverQuery": "352区"},
                {"accountId": "source-b", "serverQuery": "352区"},
            ])

        assign.assert_called_once_with(["target-a", "target-b"])
        self.assertTrue(all(
            call.kwargs.get("start_worker") is False
            for call in create.call_args_list
        ))
        self.assertEqual(start.call_count, 2)
        self.assertEqual(result["successCount"], 2)
        self.assertEqual(result["failedCount"], 0)


if __name__ == "__main__":
    unittest.main()

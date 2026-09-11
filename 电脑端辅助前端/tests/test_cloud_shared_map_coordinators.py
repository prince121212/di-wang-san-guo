from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_cloud_shared_map_coordinator_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


LOCAL_POLICY = {
    "mode": "LOCAL_ONLY",
    "legacyLocalMapPrefetchAllowed": True,
}
CLOUD_POLICY = {
    "mode": "CLOUD_SHARED",
    "legacyLocalMapPrefetchAllowed": False,
}
OUTAGE_POLICY = {
    "mode": "CLOUD_UNAVAILABLE",
    "legacyLocalMapPrefetchAllowed": False,
}


class CloudSharedMapCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sid = "coordinator-account"
        self.route_key = "direct:test"
        self.sess = {
            "sessionId": self.sid,
            "gameHttp": "https://game.example/HttpClient",
            "dm": 1,
            "area": {"areaId": 352, "areaName": "352区"},
            "role": {"level": 50},
            "roleState": {"level": 50},
        }
        self.server_key = SERVER.shared_map_server_key(self.sess)
        self.old_sessions = SERVER.SESSIONS
        self.old_bandit_state = SERVER.BANDIT_COORDINATOR_STATE
        self.old_mine_state = SERVER.MINE_COORDINATOR_STATE
        SERVER.SESSIONS = {self.sid: self.sess}
        SERVER.BANDIT_COORDINATOR_STATE = {
            "servers": {},
            "accountLastAt": {},
            "routeLastAt": {},
            "inflightAccounts": {self.sid},
            "inflightRoutes": {self.route_key},
            "inflightServers": {self.server_key},
            "inflightCount": 1,
        }
        SERVER.MINE_COORDINATOR_STATE = {
            "servers": {},
            "accountLastAt": {},
            "routeLastAt": {},
            "inflightAccounts": {self.sid},
            "inflightRoutes": {self.route_key},
        }

    def tearDown(self) -> None:
        SERVER.SESSIONS = self.old_sessions
        SERVER.BANDIT_COORDINATOR_STATE = self.old_bandit_state
        SERVER.MINE_COORDINATOR_STATE = self.old_mine_state

    def test_single_account_bandit_coordinator_keeps_existing_scan(self) -> None:
        with patch.object(
            SERVER,
            "legacy_map_prefetch_policy",
            return_value=LOCAL_POLICY,
        ), patch.object(
            SERVER,
            "search_targets",
            return_value={"requestCount": 1, "allTargetCount": 2},
        ) as search:
            SERVER.bandit_coordinator_scan_worker(
                self.server_key,
                self.sid,
                self.route_key,
                {"level": "normal", "intervalSec": 2},
            )

        search.assert_called_once()
        state = SERVER.BANDIT_COORDINATOR_STATE["servers"][self.server_key]
        self.assertEqual(state["state"], "local_prefetch")
        self.assertEqual(state["lastRequestCount"], 1)

    def test_cloud_shared_bandit_coordinator_sends_no_map_request(self) -> None:
        with patch.object(
            SERVER,
            "legacy_map_prefetch_policy",
            return_value=CLOUD_POLICY,
        ), patch.object(SERVER, "search_targets") as search:
            SERVER.bandit_coordinator_scan_worker(
                self.server_key,
                self.sid,
                self.route_key,
                {"level": "normal", "intervalSec": 2},
            )

        search.assert_not_called()
        state = SERVER.BANDIT_COORDINATOR_STATE["servers"][self.server_key]
        self.assertEqual(state["state"], "cloud_managed")
        self.assertEqual(state["cloudMode"], "CLOUD_SHARED")
        self.assertEqual(SERVER.BANDIT_COORDINATOR_STATE["inflightCount"], 0)

    def test_single_account_mine_coordinator_keeps_existing_scan(self) -> None:
        demand = {
            "task": {},
            "cfg": {"centerX": 90, "centerY": 30},
            "row": {"resourceType": "银矿", "level": 1, "scope": "附近"},
        }
        with patch.object(
            SERVER,
            "legacy_map_prefetch_policy",
            return_value=LOCAL_POLICY,
        ), patch.object(
            SERVER,
            "search_mine_targets",
            return_value={"requestCount": 1, "matchedCount": 1, "targets": [{}]},
        ) as search:
            SERVER.mine_coordinator_scan_worker(
                self.server_key,
                self.sid,
                self.route_key,
                demand,
            )

        search.assert_called_once()
        state = SERVER.MINE_COORDINATOR_STATE["servers"][self.server_key]
        self.assertEqual(state["state"], "local_prefetch")
        self.assertEqual(demand["task"]["mapPreparation"]["state"], "ready")

    def test_post_shared_outage_mine_coordinator_sends_no_map_request(self) -> None:
        demand = {
            "task": {},
            "cfg": {"centerX": 90, "centerY": 30},
            "row": {"resourceType": "银矿", "level": 1, "scope": "附近"},
        }
        with patch.object(
            SERVER,
            "legacy_map_prefetch_policy",
            return_value=OUTAGE_POLICY,
        ), patch.object(SERVER, "search_mine_targets") as search:
            SERVER.mine_coordinator_scan_worker(
                self.server_key,
                self.sid,
                self.route_key,
                demand,
            )

        search.assert_not_called()
        state = SERVER.MINE_COORDINATOR_STATE["servers"][self.server_key]
        self.assertEqual(state["state"], "cloud_unavailable")
        self.assertEqual(state["cloudMode"], "CLOUD_UNAVAILABLE")

    def test_legacy_starter_search_is_redirected_to_cloud_coordination(self) -> None:
        expected = {
            "targets": [{"id": 7, "name": "1级山贼"}],
            "requestCount": 0,
            "sharedMap": {"enabled": True, "cloud": True},
        }
        with patch.object(
            SERVER,
            "legacy_map_prefetch_policy",
            return_value=CLOUD_POLICY,
        ), patch.object(
            SERVER,
            "cloud_coordinated_legacy_bandit_search",
            return_value=expected,
        ) as cloud_search, patch.object(SERVER, "post_game") as post_game:
            result = SERVER.search_targets(
                self.sess,
                {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                    "levels": [1],
                },
                allow_under30=True,
            )

        self.assertIs(result, expected)
        cloud_search.assert_called_once()
        post_game.assert_not_called()

    def test_legacy_starter_dispatch_sends_nothing_when_cloud_target_is_taken(self) -> None:
        self.sess["generals"] = [{
            "id": 7,
            "idHex": "0000000000000007",
            "name": "赵云",
        }]
        target = {
            "id": 0x1234,
            "idHex": "0000000000001234",
            "x": 10,
            "y": 10,
            "name": "1级山贼",
        }
        with patch.object(
            SERVER.SHARED_PYTHON_CORE,
            "cloud_prepare_host_target_dispatch",
            return_value={
                "mode": "CLOUD_SHARED",
                "reservationRequired": True,
                "reserved": False,
                "reason": "target already reserved",
            },
        ), patch.object(SERVER, "post_game") as post_game:
            result = SERVER.execute_brush(
                self.sess,
                {
                    "confirm": "brush-yellow",
                    "target": target,
                    "generalIds": ["7"],
                },
                allow_under30=True,
            )

        self.assertFalse(result["success"])
        self.assertTrue(result["cloudConflict"])
        post_game.assert_not_called()

    def test_legacy_starter_dispatch_finishes_cloud_reservation(self) -> None:
        self.sess["generals"] = [{
            "id": 7,
            "idHex": "0000000000000007",
            "name": "赵云",
        }]
        target = {
            "id": 0x1234,
            "idHex": "0000000000001234",
            "x": 10,
            "y": 10,
            "name": "1级山贼",
        }
        summaries = [
            [],
            [{
                "opcode": f"0x{SERVER.BRUSH_DISPATCH_RESPONSE_OPCODE:04x}",
                "dispatch8522": {"success": True, "battleId": 9123},
                "textPreview": "出征成功",
            }],
        ]
        with patch.object(
            SERVER.SHARED_PYTHON_CORE,
            "cloud_prepare_host_target_dispatch",
            return_value={
                "mode": "CLOUD_SHARED",
                "reservationRequired": True,
                "reserved": True,
                "reservationToken": "reservation-1",
            },
        ), patch.object(
            SERVER.SHARED_PYTHON_CORE,
            "cloud_finish_host_target_dispatch",
            return_value=True,
        ) as finish, patch.object(
            SERVER,
            "post_game",
            return_value=(200, b"", []),
        ) as post_game, patch.object(
            SERVER,
            "summarize_packets",
            side_effect=summaries,
        ), patch.object(SERVER.time, "sleep"):
            result = SERVER.execute_brush(
                self.sess,
                {
                    "confirm": "brush-yellow",
                    "target": target,
                    "generalIds": ["7"],
                },
                allow_under30=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["successBattleId"], 9123)
        self.assertEqual(post_game.call_count, 2)
        self.assertEqual(finish.call_args.args[4], "dispatched")


if __name__ == "__main__":
    unittest.main()

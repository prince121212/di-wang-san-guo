from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_bandit_sqlite_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def bandit(target_id: int, *, x: int = 20, y: int = 13) -> dict:
    return {
        "id": target_id,
        "idHex": f"{target_id:016x}",
        "kind": "山贼",
        "name": "9级山贼",
        "level": 9,
        "x": x,
        "y": y,
        "resource": "大批资源,",
        "dropCategories": ["资源"],
        "lootIds": [1067],
        "composition": {
            "foot": 1,
            "bow": 2,
            "cavalry": 1,
            "chariot": 0,
            "source": "8540-units",
        },
        "source": "8540-structured",
    }


class BanditSQLiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_dir = SERVER.SHARED_MAP_DIR
        self.original_initialized = SERVER.BANDIT_DB_INITIALIZED_PATHS
        SERVER.SHARED_MAP_DIR = Path(self.tempdir.name)
        SERVER.BANDIT_DB_INITIALIZED_PATHS = set()
        self.sess = {
            "sessionId": "account-a",
            "area": {"areaName": "351区"},
        }

    def tearDown(self) -> None:
        SERVER.SHARED_MAP_DIR = self.original_dir
        SERVER.BANDIT_DB_INITIALIZED_PATHS = self.original_initialized
        self.tempdir.cleanup()

    def record(self, scan_x: int, scan_y: int, targets: list[dict]) -> dict:
        return SERVER.record_shared_map_region(
            self.sess,
            "bandit",
            x=scan_x,
            y=scan_y,
            http_code=200,
            opcodes=["0x8540"],
            response_data=b"raw-response-must-not-be-stored",
            response_payloads=[b"raw-payload-must-not-be-stored"],
            targets=targets,
        )

    def available(self) -> list[dict]:
        return SERVER.shared_map_available_targets(
            self.sess,
            "bandit",
            target_kind="山贼",
            level=9,
            drops=["资源"],
            composition_filter={
                "maxFoot": 1,
                "maxBow": 2,
                "maxCavalry": 1,
                "maxChariot": 0,
            },
        )

    def test_scan_upserts_compact_target_and_public_api_shape(self) -> None:
        self.record(18, 12, [bandit(123)])
        targets = self.available()
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["scanCoord"], [18, 12])
        self.assertEqual(targets[0]["idHex"], "000000000000007b")
        self.assertEqual(targets[0]["lootIds"], [1067])

        public = SERVER.public_bandit_map(self.sess)
        self.assertEqual(public["serverKey"], "区351")
        self.assertEqual(len(public["points"]), 1)
        self.assertEqual(public["points"][0]["compositionCode"], "1210")

        database_bytes = SERVER.bandit_db_path().read_bytes()
        self.assertNotIn(b"raw-response-must-not-be-stored", database_bytes)
        self.assertFalse(list(SERVER.SHARED_MAP_DIR.glob("*_bandit_responses.jsonl")))

    def test_overlapping_regions_keep_target_until_all_relations_disappear(self) -> None:
        target = bandit(123)
        self.record(18, 12, [target])
        self.record(24, 12, [target])
        self.record(18, 12, [])
        self.assertEqual(len(self.available()), 1)
        self.assertEqual(self.available()[0]["scanCoord"], [24, 12])

        self.record(24, 12, [])
        self.assertEqual(self.available(), [])

    def test_reservation_is_atomic_between_accounts(self) -> None:
        self.record(18, 12, [bandit(123)])
        target = self.available()[0]
        results: list[bool] = []
        barrier = threading.Barrier(3)

        def reserve(owner: str) -> None:
            barrier.wait()
            results.append(SERVER.reserve_shared_map_target(
                self.sess,
                "bandit",
                target,
                owner=owner,
                task_id=f"task-{owner}",
            ))

        threads = [
            threading.Thread(target=reserve, args=("account-a",)),
            threading.Thread(target=reserve, args=("account-b",)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.available(), [])

    def test_expired_targets_are_deleted_regardless_of_status(self) -> None:
        self.record(18, 12, [bandit(123)])
        target = self.available()[0]
        self.assertTrue(SERVER.reserve_shared_map_target(
            self.sess,
            "bandit",
            target,
            owner="account-a",
            task_id="task-a",
        ))
        SERVER.update_shared_map_target_status(
            self.sess,
            "bandit",
            target,
            owner="account-a",
            status="dispatched",
        )
        with SERVER._bandit_db_connect() as connection:
            connection.execute(
                "UPDATE bandit_targets SET last_seen_at=?",
                (SERVER.now_ms() - SERVER.SHARED_MAP_TARGET_TTL_MS - 1,),
            )
        self.assertEqual(SERVER.public_bandit_map(self.sess)["points"], [])

    def test_scan_lease_allows_only_one_owner_and_can_be_released(self) -> None:
        self.assertTrue(SERVER.claim_shared_map_scan(
            self.sess, "bandit", "18,12", "account-a",
        ))
        self.assertFalse(SERVER.claim_shared_map_scan(
            self.sess, "bandit", "18,12", "account-b",
        ))
        SERVER.release_shared_map_scan(
            self.sess, "bandit", "18,12", "account-a",
        )
        self.assertTrue(SERVER.claim_shared_map_scan(
            self.sess, "bandit", "18,12", "account-b",
        ))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_notice_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class ImportantNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.originals = {
            "ACCOUNT_STATE_DB_FILE": SERVER.ACCOUNT_STATE_DB_FILE,
            "ACCOUNT_STATE_DB_READY": SERVER.ACCOUNT_STATE_DB_READY,
            "ACCOUNT_RECORDS_FILE": SERVER.ACCOUNT_RECORDS_FILE,
            "RUNTIME_STATE_FILE": SERVER.RUNTIME_STATE_FILE,
            "ACCOUNT_CONFIG_DIR": SERVER.ACCOUNT_CONFIG_DIR,
            "ACCOUNT_RECORD_BACKUP_DIR": SERVER.ACCOUNT_RECORD_BACKUP_DIR,
            "LOG_DIR": SERVER.LOG_DIR,
            "ACCOUNT_LOG_DIR": SERVER.ACCOUNT_LOG_DIR,
            "SYSTEM_LOG_FILE": SERVER.SYSTEM_LOG_FILE,
            "AREA_CATALOG_FILE": SERVER.AREA_CATALOG_FILE,
            "SESSIONS": SERVER.SESSIONS,
            "ACCOUNTS": SERVER.ACCOUNTS,
            "AUTO_TASKS": SERVER.AUTO_TASKS,
            "COMMAND_CENTER_CLAIMS": SERVER.COMMAND_CENTER_CLAIMS,
            "IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS": SERVER.IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS,
        }
        root = Path(self.tempdir.name)
        SERVER.ACCOUNT_STATE_DB_FILE = root / "assistant_state.sqlite3"
        SERVER.ACCOUNT_STATE_DB_READY = False
        SERVER.ACCOUNT_RECORDS_FILE = root / "account_records.json"
        SERVER.RUNTIME_STATE_FILE = root / "runtime_state.json"
        SERVER.ACCOUNT_CONFIG_DIR = root / "account_configs"
        SERVER.ACCOUNT_CONFIG_DIR.mkdir()
        SERVER.ACCOUNT_RECORD_BACKUP_DIR = root / "account_record_backups"
        SERVER.LOG_DIR = root / "logs"
        SERVER.ACCOUNT_LOG_DIR = SERVER.LOG_DIR / "accounts"
        SERVER.SYSTEM_LOG_FILE = SERVER.LOG_DIR / "system_recent.jsonl"
        SERVER.AREA_CATALOG_FILE = root / "area_catalog.json"
        SERVER.SESSIONS = {
            "s1": {
                "sessionId": "s1",
                "username": "1608602",
                "area": {"areaId": "351"},
                "role": {"roleId": 928},
            }
        }
        SERVER.ACCOUNTS = {
            "s1": {
                "sessionId": "s1",
                "username": "1608602",
                "area": {"areaId": "351"},
                "status": "online",
                "started": True,
            }
        }
        SERVER.AUTO_TASKS = {}
        SERVER.COMMAND_CENTER_CLAIMS = {}
        SERVER.IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS = set()
        SERVER.initialize_account_state_database()

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)
        self.tempdir.cleanup()

    def test_brush_error_creates_notice_and_restart_resolves_it(self) -> None:
        task = {
            "taskId": "t1",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "error",
            "error": "状态机阻止刷黄：闲兵不足，已停止",
            "cycle": 0,
            "logs": [],
            "stopEvent": threading.Event(),
        }

        SERVER.task_log(task, task["error"])
        account_key = SERVER.account_storage_key(session_id="s1")
        notices = SERVER.database_read_active_important_notices(account_key)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["key"], "task:brushYellow")
        self.assertEqual(notices[0]["title"], "刷黄已中止")
        self.assertIn("闲兵不足", notices[0]["message"])

        task["status"] = "running"
        task.pop("error")
        SERVER.task_log(task, "自动刷黄启动：重新检查编队")

        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_definitive_shared_success_resolves_previous_task_notice(self) -> None:
        task = {
            "taskId": "dungeon-task",
            "type": "dungeon",
            "sessionId": "s1",
            "status": "error",
            "error": "副本前置操作已开始，但尚无正式出征成功证据",
            "cycle": 0,
            "logs": [],
            "stopEvent": threading.Event(),
        }
        SERVER.task_log(task, task["error"])
        task["status"] = "running"
        task.pop("error")

        SERVER.task_log(
            task,
            "共享常驻：feature=dungeon state=dispatched；副本出征已确认",
        )

        account_key = SERVER.account_storage_key(session_id="s1")
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_dungeon_resource_wait_warns_then_verified_recovery_resolves(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:dungeon",
            severity="error",
            title="副本已中止",
            message="副本前置操作已开始，但尚无正式出征成功证据",
            source="task",
        )

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "dungeon",
            {
                "state": "waiting-resources",
                "requiresAttention": False,
                "message": (
                    "赵云体力不足且宝库没有活血丹；本轮副本已跳过，"
                    "5分钟后重新检查"
                ),
            },
        )
        notices = SERVER.database_read_active_important_notices(account_key)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["severity"], "warning")
        self.assertEqual(notices[0]["title"], "副本等待资源")
        visible = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertIn("5分钟后会自动重新检查", visible[0]["advice"])

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "dungeon",
            {
                "state": "fighting",
                "success": True,
                "requiresAttention": False,
                "message": "副本出征已确认",
            },
        )
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_lossless_settlement_resolves_old_network_ledger_notice(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:lossless",
            severity="error",
            title="无损已中止",
            message="无损前置操作已开始，但尚无正式出征成功证据",
            source="task",
        )

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "lossless",
            {
                "state": "waiting-resources",
                "success": True,
                "requiresAttention": False,
                "message": "无损将领体力不足且宝库没有活血丹，5分钟后重试",
            },
        )
        waiting = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertEqual(waiting[0]["title"], "无损等待资源")
        self.assertIn("5分钟后会自动重新检查", waiting[0]["advice"])

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "lossless",
            {
                "state": "settled",
                "success": True,
                "requiresAttention": False,
                "message": "无损战斗已完成结算",
            },
        )

        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_sign_in_inventory_full_keeps_one_actionable_notice(self) -> None:
        sess = SERVER.SESSIONS["s1"]
        account_key = SERVER.account_storage_key(session_id="s1")

        SERVER.log_daily_feature_result(
            sess,
            "autoSignIn",
            {
                "success": False,
                "completed": False,
                "message": (
                    "签到响应未能识别：宝库空间不足，；"
                    "请清理宝库后再来领取"
                ),
            },
        )
        SERVER.log_daily_feature_result(
            sess,
            "autoSignIn",
            {
                "success": False,
                "completed": False,
                "message": "此前日常请求回执不明，当前周期禁止自动重放",
            },
        )

        notices = SERVER.current_important_notices(sess)
        sign_in = [
            notice
            for notice in notices
            if notice["key"] == "daily:autoSignIn"
        ]
        self.assertEqual(len(sign_in), 1)
        self.assertEqual(
            sign_in[0]["message"],
            SERVER.AUTO_SIGN_IN_INVENTORY_FULL_NOTICE,
        )
        self.assertNotIn("回执不明", sign_in[0]["message"])
        self.assertIn("清理宝库空位", sign_in[0]["advice"])

        SERVER.log_daily_feature_result(
            sess,
            "autoSignIn",
            {
                "success": True,
                "completed": True,
                "message": "本日已签到",
            },
        )
        self.assertFalse(
            SERVER.database_read_important_notice_record(
                account_key,
                "daily:autoSignIn",
            )["active"]
        )

    def test_healthy_shared_waiting_resolves_previous_inventory_notice(self) -> None:
        task = {
            "taskId": "inventory-task",
            "type": "auto-inventory",
            "sessionId": "s1",
            "status": "error",
            "error": "装备元数据不完整，已禁止自动丢弃",
            "cycle": 0,
            "logs": [],
            "stopEvent": threading.Event(),
        }
        SERVER.task_log(task, task["error"])
        task["status"] = "running"
        task.pop("error")

        SERVER.task_log(
            task,
            "共享常驻：feature=inventory state=waiting；背包中没有需要处理的项目",
        )

        account_key = SERVER.account_storage_key(session_id="s1")
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_shared_task_attach_resolves_its_previous_notice_immediately(self) -> None:
        task = {
            "taskId": "inventory-restarted",
            "type": "auto-inventory",
            "sessionId": "s1",
            "status": "error",
            "error": "装备元数据不完整，已禁止自动丢弃",
            "cycle": 0,
            "logs": [],
            "stopEvent": threading.Event(),
        }
        SERVER.task_log(task, task["error"])
        task["status"] = "running"
        task.pop("error")

        SERVER.task_log(
            task,
            "已接入账号共享常驻调度；同一账号只保留一个唤醒线程",
        )

        account_key = SERVER.account_storage_key(session_id="s1")
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_general_energy_notice_is_removed_from_inventory_and_alarm_only(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        message = (
            "将领维护检查到统弓1体力=38，低于自动加体阈值40，"
            "但宝库没有活血丹"
        )
        for notice_key, title in (
            ("task:general", "将领维护已中止"),
            ("task:inventory", "背包整理已中止"),
            ("task:alarm", "军情警报已中止"),
        ):
            SERVER.database_upsert_important_notice(
                account_key,
                notice_key,
                severity="error",
                title=title,
                message=message,
                source="task",
            )

        visible = SERVER.current_important_notices(SERVER.SESSIONS["s1"])

        self.assertEqual(
            [notice["key"] for notice in visible],
            ["task:general"],
        )
        records = {
            notice_key: SERVER.database_read_important_notice_record(
                account_key,
                notice_key,
            )
            for notice_key in (
                "task:general", "task:inventory", "task:alarm",
            )
        }
        self.assertTrue(records["task:general"]["active"])
        self.assertFalse(records["task:inventory"]["active"])
        self.assertFalse(records["task:alarm"]["active"])

        # The cleanup is based on contradictory feature identity, not merely
        # on the destination row. A genuine inventory error must stay visible.
        SERVER.database_upsert_important_notice(
            account_key,
            "task:inventory",
            severity="error",
            title="背包整理已中止",
            message="装备元数据不完整，已禁止自动丢弃",
            source="task",
        )
        visible = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertEqual(
            {notice["key"] for notice in visible},
            {"task:general", "task:inventory"},
        )
        inventory_notice = next(
            notice
            for notice in visible
            if notice["key"] == "task:inventory"
        )
        self.assertIn("不依赖将领体力", inventory_notice["advice"])
        self.assertIn(
            "不依赖将领体力",
            SERVER.important_notice_advice("task:alarm"),
        )

    def test_operator_maintenance_suppresses_cancel_before_signalling_worker(self) -> None:
        task: dict[str, object] = {
            "taskId": "inventory-maintenance-race",
            "type": "auto-inventory",
            "sessionId": "s1",
            "status": "running",
            "config": {"sessionId": "s1"},
            "cycle": 0,
            "logs": [],
        }

        class CancelOnSet:
            def __init__(self) -> None:
                self.value = False

            def is_set(self) -> bool:
                return self.value

            def set(self) -> None:
                self.value = True
                # Model the exact race: stopEvent wakes the operation waiter,
                # which reports CANCELLED before the stop helper continues.
                task["status"] = "error"
                task["error"] = "共享 operation 结束：CANCELLED"
                SERVER.task_log(task, str(task["error"]))

        task["stopEvent"] = CancelOnSet()
        SERVER.AUTO_TASKS[str(task["taskId"])] = task

        stopped = SERVER.stop_tasks_for_session_invalid(
            "s1",
            "人工结清旧出征账本",
            operator_maintenance=True,
        )

        account_key = SERVER.account_storage_key(session_id="s1")
        self.assertEqual(stopped, ["inventory-maintenance-race"])
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )
        self.assertTrue(task["_suppressImportantNotice"])
        self.assertTrue(task["_operatorMaintenancePause"])
        self.assertNotIn("_transientNetworkPause", task)
        self.assertIn("本地人工维护", str(task["stopReason"]))

    def test_offline_account_is_returned_as_critical_notice(self) -> None:
        SERVER.ACCOUNTS["s1"].update({
            "status": "offline",
            "lastError": "当前节点无法连接游戏服",
        })

        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        connection = next(item for item in notices if item["key"] == "account:connection")

        self.assertEqual(connection["severity"], "critical")
        self.assertIn("无法连接游戏服", connection["message"])
        self.assertEqual(
            connection["summary"],
            "账号连接异常：当前节点无法连接游戏服",
        )
        self.assertIn("检查当前IP", connection["advice"])

        self.assertTrue(
            SERVER.dismiss_important_notice(
                SERVER.SESSIONS["s1"],
                "account:connection",
            )
        )
        self.assertFalse(any(
            item["key"] == "account:connection"
            for item in SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        ))

        SERVER.ACCOUNTS["s1"]["lastError"] = "新的连接失败原因"
        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertTrue(any(
            item["key"] == "account:connection"
            for item in notices
        ))

    def test_long_brush_troop_error_has_short_summary(self) -> None:
        summary = SERVER.important_notice_summary({
            "title": "刷黄已中止",
            "message": (
                "状态机阻止刷黄：出征前配兵失败：将领 21765092；"
                "车2改 配兵中止：目标 259弩车，当前将领带兵=无配兵，"
                "可用弩车=0（闲兵0），不足以达到目标；当前闲兵：轻骑兵=4"
            ),
        })

        self.assertEqual(summary, "刷黄已中止：弩车闲兵不足（需要259，当前0）")

    def test_running_brush_troop_shortage_creates_notice_and_recovery_resolves_it(self) -> None:
        sess = SERVER.SESSIONS["s1"]
        reason = (
            "统弓2 配兵中止：目标 150弩兵，当前将领带兵=无配兵，"
            "可用弩兵=0（闲兵0），不足以达到目标；当前闲兵：强弩兵=285"
        )

        SERVER.upsert_brush_troop_shortage_notice(sess, 0, reason)
        notices = SERVER.current_important_notices(sess)
        notice = next(
            item for item in notices
            if item["key"] == "task:brushYellow:troopShortage:0"
        )

        self.assertEqual(notice["severity"], "warning")
        self.assertEqual(notice["title"], "刷黄配兵不足")
        self.assertEqual(
            notice["summary"],
            "刷黄配兵不足：弩兵闲兵不足（需要150，当前0）",
        )
        self.assertIn("军事-配兵", notice["advice"])

        SERVER.resolve_brush_troop_shortage_notice(sess, 0)
        self.assertFalse(any(
            item["key"] == "task:brushYellow:troopShortage:0"
            for item in SERVER.current_important_notices(sess)
        ))

    def test_high_level_brush_rejection_creates_one_rule_notice_and_recovers(self) -> None:
        sess = SERVER.SESSIONS["s1"]
        account_key = SERVER.account_storage_key(sess=sess)
        rejected = {
            "feature": "brush",
            "state": "retry",
            "success": False,
            "requiresAttention": False,
            "errorCode": "BRUSH_DISPATCH_REJECTED",
            "sourceRowIndex": 2,
            "message": "刷黄编队3未满足每个将领配兵达到1000",
            "serverMessage": (
                "出征失败！攻打9级山贼、10级山贼，"
                "每个将领至少需配1000兵力。"
            ),
        }

        SERVER.sync_shared_resident_feature_notice("s1", "brush", rejected)
        SERVER.sync_shared_resident_feature_notice("s1", "brush", rejected)
        notices = SERVER.database_read_active_important_notices(account_key)

        self.assertEqual(len(notices), 1)
        self.assertEqual(
            notices[0]["key"],
            "task:brushYellow:highLevelTroops:2",
        )
        self.assertEqual(notices[0]["title"], "刷黄编队3配兵不足")
        self.assertEqual(
            notices[0]["message"],
            "刷黄编队3未满足每个将领配兵达到1000",
        )
        visible = SERVER.current_important_notices(sess)
        self.assertIn("每名将领的配兵改为至少1000", visible[0]["advice"])

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "brush",
            {
                "state": "dispatched",
                "success": True,
                "sourceRowIndex": 2,
                "target": {"level": 8},
                "selectedLevels": [8, 9],
            },
        )
        self.assertEqual(
            len(SERVER.database_read_active_important_notices(account_key)),
            1,
        )

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "brush",
            {
                "state": "dispatched",
                "success": True,
                "sourceRowIndex": 2,
                "target": {"level": 9},
                "selectedLevels": [8, 9],
            },
        )
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

        SERVER.sync_shared_resident_feature_notice("s1", "brush", rejected)
        SERVER.resolve_brush_high_level_troops_notices(sess)
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_click_delete_equivalent_hides_stored_task_notice(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:brushYellow",
            severity="error",
            title="刷黄已中止",
            message="状态机阻止刷黄：闲兵不足",
            source="task",
        )

        self.assertTrue(
            SERVER.dismiss_important_notice(
                SERVER.SESSIONS["s1"],
                "task:brushYellow",
            )
        )
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_legacy_cross_feature_shared_notice_is_resolved_on_read(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:autoDomestic",
            severity="error",
            title="自动内政已中止",
            message="副本前置操作已开始，但尚无正式出征成功证据",
            source="task",
        )
        SERVER.database_upsert_important_notice(
            account_key,
            "task:dungeon",
            severity="error",
            title="副本已中止",
            message="副本前置操作已开始，但尚无正式出征成功证据",
            source="task",
        )

        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        keys = {str(item["key"]) for item in notices}
        self.assertNotIn("task:autoDomestic", keys)
        self.assertIn("task:dungeon", keys)
        self.assertFalse(
            SERVER.database_read_important_notice_record(
                account_key,
                "task:autoDomestic",
            )["active"]
        )

    def test_brush_recovery_step_notice_is_never_owned_by_other_features(
        self,
    ) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        message = (
            "刷黄战后步骤 healByFief/205 曾越过发送边界，"
            "当前禁止自动重放"
        )
        for key, title in (
            ("task:lossless", "无损已中止"),
            ("task:dungeon", "副本已中止"),
            ("task:inventory", "背包整理已中止"),
            ("task:alarm", "军情警报已中止"),
            ("task:brushYellow", "刷黄已中止"),
        ):
            SERVER.database_upsert_important_notice(
                account_key,
                key,
                severity="error",
                title=title,
                message=message,
                source="task",
            )

        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        keys = {str(item["key"]) for item in notices}
        self.assertEqual(keys & {
            "task:lossless",
            "task:dungeon",
            "task:inventory",
            "task:alarm",
            "task:brushYellow",
        }, {"task:brushYellow"})

    def test_healthy_brush_recovery_resolves_previous_brush_notice(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:brushYellow",
            severity="error",
            title="刷黄已中止",
            message="刷黄战后步骤 healByFief/205 需要处理",
            source="automation",
        )

        SERVER.sync_shared_resident_feature_notice(
            "s1",
            "brushYellow",
            {
                "feature": "brushYellow",
                "state": "completed",
                "success": True,
                "requiresAttention": False,
                "message": "刷黄战后对账完成",
            },
        )

        self.assertFalse(
            SERVER.database_read_important_notice_record(
                account_key,
                "task:brushYellow",
            )["active"]
        )

    def test_legacy_task_network_notice_is_not_a_feature_failure(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:brushYellow",
            severity="error",
            title="刷黄已中止",
            message="手动选择的IP SUB 阿里·上海01 无法连接游戏服",
            source="task",
        )
        SERVER.database_upsert_important_notice(
            account_key,
            "task:inventory",
            severity="warning",
            title="背包整理已停止",
            message=(
                "网络暂时不可用，已暂停后台任务并等待心跳恢复："
                "当前账号没有可用于网络请求的已验证 Session"
            ),
            source="task",
        )

        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertFalse(any(
            item["key"] in {"task:brushYellow", "task:inventory"}
            for item in notices
        ))
        self.assertFalse(
            SERVER.database_read_important_notice_record(
                account_key,
                "task:brushYellow",
            )["active"]
        )
        self.assertFalse(
            SERVER.database_read_important_notice_record(
                account_key,
                "task:inventory",
            )["active"]
        )


if __name__ == "__main__":
    unittest.main()

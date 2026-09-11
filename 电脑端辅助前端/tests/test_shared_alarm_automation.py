from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.alarm import (  # noqa: E402
    alarm_event_fingerprint,
    plan_alarm_observation,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 90_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class RecordingPort:
    def __init__(self) -> None:
        self.values: list[dict[str, object]] = []
        self.fail = False

    def notify(self, event) -> None:
        if self.fail:
            raise RuntimeError("平台通知端口暂时失败")
        self.values.append(dict(event))

    def write(self, event) -> None:
        self.values.append(dict(event))


class FakeExecution:
    operation_id = "op_alarm_fixture"

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None


def incoming(record_id: int, countdown: str = "60秒") -> dict[str, object]:
    return {
        "recordId": record_id,
        "eventTimeMs": 1_800_000_000_000,
        "attackerName": "敌军甲",
        "targetId": 88,
        "actionType": 1,
        "incoming": True,
        "state": "来袭",
        "text": f"敌军甲正在掠夺主城，剩余{countdown}",
        "remainingSeconds": int(countdown.removesuffix("秒")),
    }


class SharedAlarmPlanningTests(unittest.TestCase):
    def test_stable_fingerprint_ignores_countdown_changes(self) -> None:
        self.assertEqual(
            alarm_event_fingerprint(incoming(7, "60秒")),
            alarm_event_fingerprint(incoming(7, "30秒")),
        )

    def test_baseline_history_and_config_change_never_replay(self) -> None:
        policy = {
            "incomingEnabled": True,
            "incomingMode": "声音+日志",
            "militaryEnabled": False,
            "errorEnabled": True,
        }
        first = plan_alarm_observation(
            {"actions": [incoming(1)]},
            policy,
            {},
            now_millis=1_000,
        )
        self.assertTrue(first["baselineEstablished"])
        self.assertEqual([], first["events"])

        second = plan_alarm_observation(
            {"actions": [incoming(1), incoming(2)]},
            policy,
            first["state"],
            now_millis=2_000,
        )
        self.assertEqual([2], [event["action"]["recordId"] for event in second["events"]])

        disappeared = plan_alarm_observation(
            {"actions": []},
            policy,
            second["state"],
            now_millis=3_000,
        )
        reappeared = plan_alarm_observation(
            {"actions": [incoming(2)]},
            policy,
            disappeared["state"],
            now_millis=4_000,
        )
        self.assertEqual([], reappeared["events"])

        changed = plan_alarm_observation(
            {"actions": [incoming(2), incoming(3)]},
            {**policy, "incomingMode": "仅日志"},
            reappeared["state"],
            now_millis=5_000,
        )
        self.assertTrue(changed["baselineEstablished"])
        self.assertEqual([], changed["events"])


class SharedAlarmFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.clock = FixedClock()
        self.notifications = RecordingPort()
        self.logs = RecordingPort()
        self.facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(
                Path(self.directory.name) / "operations.json"
            ),
            ports=PlatformPorts(
                clock=self.clock,
                notifications=self.notifications,
                logs=self.logs,
            ),
        )
        self.facade.account_record_upsert({
            "accountRef": "707",
            "id": 707,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 707,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "707",
                    "gameHttp": "https://fixture.invalid/game",
                    "lastValidatedAt": str(self.clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "alarm",
                    "generalsJson": "[]",
                },
            },
        })

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def configure(self, *, incoming_mode: str = "声音+日志") -> None:
        self.facade.configure_resident_automation_from_habits(
            "707",
            {
                "config": {
                    "alarm": {
                        "incomingEnabled": True,
                        "incomingMode": incoming_mode,
                        "militaryEnabled": False,
                        "errorEnabled": True,
                        "vibrateOnAlarm": True,
                    }
                }
            },
        )
        self.facade.set_resident_automation_activation(
            "707", True, ["alarm"]
        )

    def install_snapshots(self, *snapshots: dict[str, object]) -> list[int]:
        values = iter(snapshots)
        calls: list[int] = []

        def refresh(_facade, *_args, **_kwargs):
            calls.append(self.clock.value)
            return next(values)

        self.facade._refresh_military_snapshot_game = types.MethodType(  # type: ignore[method-assign]  # noqa: SLF001
            refresh,
            self.facade,
        )
        return calls

    def tick(self) -> dict[str, object]:
        return self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(),
            "707",
            {"allowedFeatures": ["alarm"]},
        )

    def test_log_only_records_once_without_notification(self) -> None:
        self.configure(incoming_mode="仅日志")
        self.install_snapshots(
            {"actions": []},
            {"actions": [incoming(9)]},
            {"actions": [incoming(9, "30秒")]},
        )
        self.assertEqual("baseline", self.tick()["state"])
        self.clock.value += 30_000
        second = self.tick()
        self.assertEqual("notified", second["state"])
        self.assertEqual(0, second["notificationCount"])
        self.clock.value += 30_000
        self.assertEqual("waiting", self.tick()["state"])
        self.assertEqual([], self.notifications.values)
        self.assertEqual(1, len(self.logs.values))

    def test_pending_notification_recovery_does_not_refetch_or_rejudge(self) -> None:
        self.configure()
        calls = self.install_snapshots(
            {"actions": []},
            {"actions": [incoming(10)]},
        )
        self.assertEqual("baseline", self.tick()["state"])
        self.clock.value += 30_000
        self.notifications.fail = True
        failed = self.tick()
        self.assertEqual("retry", failed["state"])
        public = self.facade._account_public_state("707")  # noqa: SLF001
        self.assertTrue(json.loads(public["alarmPendingEventsJson"])["events"])

        self.notifications.fail = False
        recovered = self.tick()
        self.assertEqual("delivered-pending", recovered["state"])
        self.assertEqual(2, len(calls))
        self.assertEqual(1, len(self.logs.values))
        self.assertEqual(1, len(self.notifications.values))

    def test_error_alarm_is_python_owned_and_deduplicated(self) -> None:
        self.configure()
        first = self.facade.emit_host_alarm_error(
            "707", "后台调度异常：连接中断", "android-scheduler"
        )
        second = self.facade.emit_host_alarm_error(
            "707", "后台调度异常：连接中断", "android-scheduler"
        )
        self.assertTrue(first["emitted"])
        self.assertFalse(second["emitted"])
        self.assertEqual("deduplicated", second["reason"])
        self.assertEqual(1, len(self.notifications.values))

        self.clock.value += 300_001
        third = self.facade.emit_host_alarm_error(
            "707", "后台调度异常：连接中断", "android-scheduler"
        )
        self.assertTrue(third["emitted"])
        self.assertEqual(2, len(self.notifications.values))

    def test_missing_alarm_config_disables_host_error_notification(self) -> None:
        result = self.facade.emit_host_alarm_error(
            "707", "不应展示", "android-scheduler"
        )
        self.assertFalse(result["emitted"])
        self.assertEqual("disabled", result["reason"])
        self.assertEqual([], self.notifications.values)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.ports import MapSnapshotPort


class RecordingMapSnapshotPort:
    """Minimal host store: writes what it is given, reads it back verbatim."""

    def __init__(self) -> None:
        self.saved: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        self.load_calls: list[tuple[str, str, str]] = []

    def save(self, snapshot: Mapping[str, object]) -> None:
        key = (
            str(snapshot["accountRef"]),
            str(snapshot["kind"]),
            str(snapshot["fingerprint"]),
        )
        self.saved[key] = dict(snapshot)

    def load(
        self,
        account_ref: str,
        kind: str,
        fingerprint: str,
    ) -> Optional[Mapping[str, object]]:
        self.load_calls.append((account_ref, kind, fingerprint))
        return self.saved.get((account_ref, kind, fingerprint))

    def invalidate(self, *_args, **_kwargs) -> None:
        return None


class MapSnapshotPortContractTests(unittest.TestCase):
    def test_the_port_exposes_a_read_path(self) -> None:
        """The port was write-only, so a single account could never reuse a scan.

        Hosts recorded every discovered target and the core then re-swept the
        same coordinates on the next dispatch: only the cloud path could read
        discoveries back.
        """

        self.assertTrue(hasattr(MapSnapshotPort, "load"))
        self.assertTrue(hasattr(MapSnapshotPort, "save"))
        self.assertTrue(hasattr(MapSnapshotPort, "invalidate"))

    def test_a_recording_host_satisfies_the_protocol(self) -> None:
        port: MapSnapshotPort = RecordingMapSnapshotPort()
        port.save({
            "accountRef": "176",
            "kind": "BANDIT",
            "fingerprint": "91,26|SHAN_ZEI",
            "scannedAtMillis": 1_000,
            "targets": [],
        })
        self.assertIsNotNone(port.load("176", "BANDIT", "91,26|SHAN_ZEI"))
        self.assertIsNone(port.load("176", "BANDIT", "other"))


class LoadMapSnapshotTargetsTests(unittest.TestCase):
    """Covers the reducer that turns stored rows back into usable targets."""

    class _Clock:
        def __init__(self, value: int) -> None:
            self.value = value

        def now_millis(self) -> int:
            return self.value

    def _facade_stub(self, port, now: int):
        from dwpm_core.facade import CoreFacade

        stub = CoreFacade.__new__(CoreFacade)
        clock = self._Clock(now)

        class _Ports:
            def __init__(self) -> None:
                self.map_snapshots = port
                self.clock = clock
                self.logs = type(
                    "_Logs", (), {"write": staticmethod(lambda _row: None)}
                )()

        stub._ports = _Ports()  # noqa: SLF001
        return stub

    def _saved_port(self, scanned_at: int) -> RecordingMapSnapshotPort:
        port = RecordingMapSnapshotPort()
        port.save({
            "accountRef": "176",
            "kind": "BANDIT",
            "fingerprint": "91,26|SHAN_ZEI",
            "scannedAtMillis": scanned_at,
            "targets": [
                {
                    "targetId": 5189080,
                    "x": 105,
                    "y": 26,
                    "type": "山贼",
                    "level": 8,
                    "filterFields": {
                        "compositionCode": "4000",
                        "dropCategories": '["宝物","资源"]',
                    },
                    "firstDiscoveredAtMillis": scanned_at,
                }
            ],
        })
        return port

    def test_a_fresh_snapshot_is_rebuilt_into_dispatchable_targets(self) -> None:
        port = self._saved_port(10_000)
        facade = self._facade_stub(port, now=11_000)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=60_000,
        )

        self.assertEqual(len(targets), 1)
        target = targets[0]
        # Same shape the cloud path produces, so one filter serves both.
        self.assertEqual(target["id"], 5189080)
        self.assertEqual((target["x"], target["y"]), (105, 26))
        self.assertEqual(target["level"], 8)
        self.assertEqual(target["kind"], "山贼")
        self.assertEqual(target["compositionCode"], "4000")
        self.assertEqual(target["dropCategories"], ["宝物", "资源"])
        self.assertTrue(target["fromCache"])

    def test_a_stale_snapshot_is_ignored_so_the_account_rescans(self) -> None:
        port = self._saved_port(10_000)
        facade = self._facade_stub(port, now=10_000 + 60_001)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=60_000,
        )

        self.assertEqual(targets, [])

    def test_a_missing_snapshot_is_not_an_error(self) -> None:
        facade = self._facade_stub(RecordingMapSnapshotPort(), now=1_000)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=60_000,
        )

        self.assertEqual(targets, [])

    def test_a_host_without_a_reader_degrades_to_scanning(self) -> None:
        class WriteOnly:
            def save(self, _snapshot) -> None:
                return None

            def invalidate(self, *_args, **_kwargs) -> None:
                return None

        facade = self._facade_stub(WriteOnly(), now=1_000)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=60_000,
        )

        self.assertEqual(targets, [])

    def test_a_failing_reader_never_breaks_the_scan(self) -> None:
        class Broken(RecordingMapSnapshotPort):
            def load(self, *_args, **_kwargs):
                raise RuntimeError("host store unavailable")

        facade = self._facade_stub(Broken(), now=1_000)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=60_000,
        )

        self.assertEqual(targets, [])


class CachedTargetsMustSurviveTheRealFiltersTests(unittest.TestCase):
    """A cached target has to pass the same filters a freshly scanned one does.

    ``match_composition`` refuses any target whose per-arm counts it cannot
    see, and the snapshot stores only the flat ``compositionCode``.  So the
    cache was write-only in practice: a real account held 216 cached bandits
    and every one of them failed the 兵种 filter, which is why both accounts on
    one server kept re-sweeping the map five coordinates at a time.
    """

    class _Clock:
        def __init__(self, value: int) -> None:
            self.value = value

        def now_millis(self) -> int:
            return self.value

    def _facade(self, port, now: int):
        from dwpm_core.facade import CoreFacade

        stub = CoreFacade.__new__(CoreFacade)
        clock = self._Clock(now)

        class _Ports:
            def __init__(self) -> None:
                self.map_snapshots = port
                self.clock = clock
                self.logs = type(
                    "_Logs", (), {"write": staticmethod(lambda _row: None)}
                )()

        stub._ports = _Ports()  # noqa: SLF001
        return stub

    def _loaded(self, composition_code: str):
        port = RecordingMapSnapshotPort()
        port.save({
            "accountRef": "176",
            "kind": "BANDIT",
            "fingerprint": "91,26|SHAN_ZEI",
            "scannedAtMillis": 10_000,
            "targets": [{
                "targetId": 5457528,
                "x": 100,
                "y": 18,
                "type": "山贼",
                "level": 8,
                "filterFields": {
                    "compositionCode": composition_code,
                    "dropCategories": '["资源","宝箱","装备"]',
                    "level": "8",
                    "kind": "山贼",
                },
            }],
        })
        facade = self._facade(port, now=11_000)
        return facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=1_800_000,
        )

    def test_a_cached_target_passes_the_shipped_composition_filter(self) -> None:
        from dwpm_core.features.targets import target_matches_search_filter

        targets = self._loaded("3100")
        self.assertEqual(len(targets), 1)
        self.assertTrue(
            target_matches_search_filter(
                targets[0],
                "山贼",
                [8],
                ["宝物", "资源", "装备", "宝箱"],
                {
                    "maxFoot": 5,
                    "maxBow": 5,
                    "maxCavalry": 0,
                    "maxChariot": 0,
                    "requireFoot": False,
                },
            )
        )
        self.assertEqual(
            targets[0]["composition"],
            {
                "foot": 3,
                "bow": 1,
                "cavalry": 0,
                "chariot": 0,
                "source": "8540-units",
            },
        )

    def test_a_target_over_the_arm_limits_is_still_rejected(self) -> None:
        from dwpm_core.features.targets import target_matches_search_filter

        targets = self._loaded("3190")
        self.assertFalse(
            target_matches_search_filter(
                targets[0], "山贼", [8], ["资源"],
                {"maxFoot": 5, "maxBow": 5, "maxCavalry": 0, "maxChariot": 0},
            )
        )

    def test_an_unreadable_code_fails_closed_rather_than_being_guessed(self) -> None:
        """Guessing would send a formation at a defence nobody measured."""

        from dwpm_core.features.targets import target_matches_search_filter

        for code in ("", "31", "31000", "3a00"):
            with self.subTest(code=code):
                targets = self._loaded(code)
                self.assertNotIn("composition", targets[0])
                self.assertFalse(
                    target_matches_search_filter(
                        targets[0], "山贼", [8], ["资源"],
                        {"maxFoot": 9, "maxBow": 9},
                    )
                )


class InvalidatedTargetsAreNotCandidatesTests(unittest.TestCase):
    """A target the game said was gone must never be offered again.

    On a real device 215 cached bandits contained exactly one live target; the
    loader returned all 215, so nearly every dispatch came back "目标不存在，
    不能到达".  A cache that serves corpses is worse than no cache: each dead
    row costs a full dispatch attempt.
    """

    class _Clock:
        def __init__(self, value: int) -> None:
            self.value = value

        def now_millis(self) -> int:
            return self.value

    def _facade(self, port, now: int):
        from dwpm_core.facade import CoreFacade

        stub = CoreFacade.__new__(CoreFacade)
        clock = self._Clock(now)

        class _Ports:
            def __init__(self) -> None:
                self.map_snapshots = port
                self.clock = clock
                self.logs = type(
                    "_Logs", (), {"write": staticmethod(lambda _row: None)}
                )()

        stub._ports = _Ports()  # noqa: SLF001
        return stub

    def _row(self, target_id: int, **extra):
        row = {
            "targetId": target_id,
            "x": 100,
            "y": 18,
            "type": "山贼",
            "level": 8,
            "filterFields": {"compositionCode": "3100"},
        }
        row.update(extra)
        return row

    def test_only_live_targets_are_returned(self) -> None:
        port = RecordingMapSnapshotPort()
        port.save({
            "accountRef": "176",
            "kind": "BANDIT",
            "fingerprint": "91,26|SHAN_ZEI",
            "scannedAtMillis": 10_000,
            "targets": [
                self._row(1),
                self._row(2, invalidatedAtMillis=9_000),
                self._row(3, invalidatedAtMillis=9_500, invalidReason="occupied"),
            ],
        })
        facade = self._facade(port, now=11_000)

        targets = facade._load_map_snapshot_targets(  # noqa: SLF001
            account_ref="176",
            kind="BANDIT",
            fingerprint="91,26|SHAN_ZEI",
            ttl_millis=1_800_000,
        )

        self.assertEqual([target["id"] for target in targets], [1])

    def test_a_snapshot_of_only_dead_targets_reads_as_empty(self) -> None:
        port = RecordingMapSnapshotPort()
        port.save({
            "accountRef": "202",
            "kind": "BANDIT",
            "fingerprint": "91,26|SHAN_ZEI",
            "scannedAtMillis": 10_000,
            "targets": [self._row(i, invalidatedAtMillis=9_000) for i in (1, 2, 3)],
        })
        facade = self._facade(port, now=11_000)

        self.assertEqual(
            facade._load_map_snapshot_targets(  # noqa: SLF001
                account_ref="202",
                kind="BANDIT",
                fingerprint="91,26|SHAN_ZEI",
                ttl_millis=1_800_000,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()

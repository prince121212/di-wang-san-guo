from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.contracts import load_route_ownership


MATRIX_PATH = ROOT / "shared_core" / "api_route_ownership.json"
DESKTOP_SERVER = ROOT / "电脑端辅助前端" / "server.py"
FRONTEND_APP = ROOT / "电脑端辅助前端" / "app.js"
ANDROID_ROUTE_SOURCES = (
    ROOT
    / "自研辅助源码"
    / "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
    ROOT
    / "自研辅助源码"
    / "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
)


class CoreMigrationRouteOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        cls.shared = cls.matrix["routes"]
        cls.host_only = cls.matrix["hostOnlyRoutes"]
        cls.legacy = cls.matrix["legacyRoutes"]
        cls.exact_rows = [
            row for row in cls.shared + cls.host_only + cls.legacy
            if "*" not in row["path"] and row["method"] != "*"
        ]
        cls.exact_pairs = {
            (row["method"], row["path"]) for row in cls.exact_rows
        }
        cls.exact_paths = {row["path"] for row in cls.exact_rows}

    def test_matrix_has_unique_routes_and_valid_response_classes(self) -> None:
        keys = [(row["method"], row["path"]) for row in self.exact_rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self.matrix["schemaVersion"], 1)
        for row in self.shared:
            self.assertEqual(self.matrix["targetOwner"], "shared-python")
            self.assertIn(row["responseClass"], {"local", "network-operation"})
            if row["responseClass"] == "network-operation":
                self.assertIn(row.get("operationKind"), {"query", "mutation"})
            else:
                self.assertNotIn("operationKind", row)

    def test_every_route_resolves_current_owner_for_both_hosts(self) -> None:
        normalized = load_route_ownership(ROOT / "shared_core")
        allowed = {"desktop-python", "android-kotlin", "shared-python"}
        for row in normalized["routes"]:
            self.assertIn(row["currentDesktopOwner"], allowed)
            self.assertIn(row["currentAndroidOwner"], allowed)
        health = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("GET", "/api/health")
        )
        self.assertEqual(health["currentDesktopOwner"], "shared-python")
        self.assertEqual(health["currentAndroidOwner"], "shared-python")
        accounts = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("GET", "/api/accounts")
        )
        self.assertEqual(accounts["currentDesktopOwner"], "shared-python")
        self.assertEqual(accounts["currentAndroidOwner"], "shared-python")
        for path in ("/api/areas", "/api/reference/guide"):
            reference = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("GET", path)
            )
            self.assertEqual(reference["currentDesktopOwner"], "shared-python")
            self.assertEqual(reference["currentAndroidOwner"], "shared-python")
        for path in ("/api/automation/start-saved", "/api/automation/stop"):
            automation = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(automation["currentDesktopOwner"], "shared-python")
            self.assertEqual(automation["currentAndroidOwner"], "shared-python")
        for path in ("/api/accounts/add", "/api/accounts/start"):
            lifecycle = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(lifecycle["currentDesktopOwner"], "shared-python")
            self.assertEqual(lifecycle["currentAndroidOwner"], "shared-python")
        self.assertTrue(all(
            row["currentDesktopOwner"] == "shared-python"
            and row["currentAndroidOwner"] == "shared-python"
            for row in normalized["routes"]
        ))
        military = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("GET", "/api/military/intel")
        )
        self.assertEqual(military["currentDesktopOwner"], "shared-python")
        self.assertEqual(military["currentAndroidOwner"], "shared-python")
        future_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"])
            == ("POST", "/api/military/future/save")
        )
        self.assertEqual(future_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(future_settings["currentAndroidOwner"], "shared-python")
        ministry_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("POST", "/api/liubu/save")
        )
        self.assertEqual(ministry_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(ministry_settings["currentAndroidOwner"], "shared-python")
        account_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"])
            == ("GET", "/api/accounts/settings")
        )
        self.assertEqual(account_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(account_settings["currentAndroidOwner"], "shared-python")
        formation_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("POST", "/api/formations/save")
        )
        self.assertEqual(formation_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(formation_settings["currentAndroidOwner"], "shared-python")
        mine_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("POST", "/api/mine/save")
        )
        self.assertEqual(mine_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(mine_settings["currentAndroidOwner"], "shared-python")
        scoped_settings = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"]) == ("POST", "/api/settings/save")
        )
        self.assertEqual(scoped_settings["currentDesktopOwner"], "shared-python")
        self.assertEqual(scoped_settings["currentAndroidOwner"], "shared-python")
        for path in (
            "/api/raid/execute",
            "/api/lossless/execute",
            "/api/dungeon/execute",
        ):
            route = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(route["currentDesktopOwner"], "shared-python")
            self.assertEqual(route["currentAndroidOwner"], "shared-python")
        for path in ("/api/maps/bandits", "/api/maps/mines"):
            route = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("GET", path)
            )
            self.assertEqual(route["currentDesktopOwner"], "shared-python")
            self.assertEqual(route["currentAndroidOwner"], "shared-python")
        formation_apply = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"])
            == ("POST", "/api/formations/apply")
        )
        self.assertEqual(formation_apply["currentDesktopOwner"], "shared-python")
        self.assertEqual(formation_apply["currentAndroidOwner"], "shared-python")
        inventory_open = next(
            row for row in normalized["routes"]
            if (row["method"], row["path"])
            == ("POST", "/api/inventory/open-one")
        )
        self.assertEqual(inventory_open["currentDesktopOwner"], "shared-python")
        self.assertEqual(inventory_open["currentAndroidOwner"], "shared-python")
        for path in ("/api/troops/assign", "/api/troops/refill", "/api/troops/heal"):
            route = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(route["currentDesktopOwner"], "shared-python")
            self.assertEqual(route["currentAndroidOwner"], "shared-python")
        for path in ("/api/brush/search", "/api/mine/search"):
            search = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(search["currentDesktopOwner"], "shared-python")
            self.assertEqual(search["currentAndroidOwner"], "shared-python")
        for path in ("/api/brush/execute", "/api/mine/execute"):
            expedition = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(expedition["currentDesktopOwner"], "shared-python")
            self.assertEqual(expedition["currentAndroidOwner"], "shared-python")
        for path in (
            "/api/liubu/hubu/query",
            "/api/liubu/hubu/plant",
            "/api/domestic/query",
            "/api/domestic/action",
            "/api/daily/general-visit/candidates",
            "/api/raid/fiefs",
        ):
            workflow = next(
                row for row in normalized["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(workflow["currentDesktopOwner"], "shared-python")
            self.assertEqual(workflow["currentAndroidOwner"], "shared-python")

    def test_desktop_handler_paths_are_all_classified(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        handler = source[source.index("class Handler("):source.index("def main()")]
        paths = set(re.findall(r'["\'](/api/[A-Za-z0-9_./-]+)', handler))
        missing = sorted(path for path in paths if not self._classified_path(path))
        self.assertEqual(missing, [])

    def test_shared_frontend_paths_are_all_classified(self) -> None:
        source = FRONTEND_APP.read_text(encoding="utf-8")
        paths = set(re.findall(r"/api/[A-Za-z0-9_./-]+", source))
        missing = sorted(path for path in paths if not self._classified_path(path))
        self.assertEqual(missing, [])

    def test_future_military_settings_route_delegates_to_shared_core(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/military/future/save":',
            1,
        )[1].split('if self.path == "/api/troops/refill":', 1)[0]

        self.assertIn("shared_settings_write_plan(self.path, body)", route)
        self.assertNotIn("normalize_military_future_settings(", route)

    def test_ministry_settings_route_uses_shared_write_plan(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/liubu/save":',
            1,
        )[1].split('if self.path == "/api/mine/save":', 1)[0]

        self.assertIn("shared_settings_write_plan(self.path, body)", route)
        self.assertNotIn("normalize_ministry_settings(body)", route)
        self.assertNotIn("require_account_online", route)

    def test_account_settings_read_uses_shared_projection_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        desktop_route = desktop.split(
            'if self.path.startswith("/api/accounts/settings"):',
            1,
        )[1].split('if self.path.startswith("/api/areas"):', 1)[0]
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        android_route = android.split(
            "private fun accountSettings",
            1,
        )[1].split("private fun accountJson", 1)[0]

        self.assertIn('"/api/accounts/settings"', desktop_route)
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", desktop_route)
        self.assertIn('"/api/accounts/settings"', android_route)
        self.assertIn("sharedPythonCore.dispatch(", android_route)
        self.assertNotIn("selected.toString(2)", android_route)

    def test_area_and_guide_reads_use_shared_projection_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        activity = (
            ROOT
            / "自研辅助源码/app/src/main/java/com/example/dwpmclone/AssistantWebActivity.kt"
        ).read_text(encoding="utf-8")
        guide_repository = (
            ROOT
            / "自研辅助源码/app/src/main/java/com/example/dwpmclone/data/local/LocalGuideRepository.kt"
        ).read_text(encoding="utf-8")

        desktop_areas = desktop.split(
            'if self.path.startswith("/api/areas"):', 1
        )[1].split('if self.path.startswith("/api/dashboard"):', 1)[0]
        desktop_guide = desktop.split(
            'if parsed_request.path == "/api/reference/guide":', 1
        )[1].split('if parsed_request.path == "/api/health":', 1)[0]
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", desktop_areas)
        self.assertIn('"/api/areas"', desktop_areas)
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", desktop_guide)
        self.assertIn('"/api/reference/guide"', desktop_guide)

        self.assertIn('"GET" to "/api/areas" -> areaCatalog(request)', android)
        self.assertIn(
            '"GET" to "/api/reference/guide" -> referenceGuide(request)',
            android,
        )
        self.assertIn("dispatchSharedLocal(", android.split(
            "private fun referenceGuide", 1
        )[1].split("private fun submitSharedNetworkOperation", 1)[0])
        self.assertNotIn("DWPMNativeGuide", activity)
        self.assertNotIn("OpenServerTimeCalculator", android)
        self.assertNotIn("GUIDE_ASSETS", guide_repository)

    def test_account_stop_and_delete_use_shared_local_plans_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        for path, next_path in (
            ("/api/accounts/stop", "/api/accounts/delete"),
            ("/api/accounts/delete", "/api/brush/search"),
        ):
            desktop_route = desktop.split(
                f'if self.path == "{path}":',
                1,
            )[1].split(f'if self.path == "{next_path}":', 1)[0]
            self.assertIn("shared_local_write_plan(", desktop_route)
            owner = next(
                row for row in load_route_ownership(ROOT / "shared_core")["routes"]
                if (row["method"], row["path"]) == ("POST", path)
            )
            self.assertEqual(owner["currentDesktopOwner"], "shared-python")
            self.assertEqual(owner["currentAndroidOwner"], "shared-python")
        stop_android = android.split(
            "private fun stopAccount",
            1,
        )[1].split("private fun deleteAccount", 1)[0]
        delete_android = android.split(
            "private fun deleteAccount",
            1,
        )[1].split("private fun startSavedTasks", 1)[0]
        self.assertIn('"/api/accounts/stop"', stop_android)
        self.assertIn("dispatchSharedLocal(", stop_android)
        self.assertIn('"/api/accounts/delete"', delete_android)
        self.assertIn("dispatchSharedLocal(", delete_android)

    def test_automation_start_and_stop_use_shared_local_plans_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        desktop_start = desktop.split(
            'if self.path == "/api/automation/start-saved":', 1
        )[1].split(
            "if parsed_request.path in DESKTOP_SHARED_DAILY_OPERATION_ROUTES:", 1
        )[0]
        desktop_stop = desktop.split(
            'if self.path == "/api/automation/stop":', 1
        )[1].split('if self.path == "/api/server/shutdown":', 1)[0]
        android_start = android.split(
            "private fun startSavedTasks", 1
        )[1].split("private fun stopAutomation", 1)[0]
        android_stop = android.split(
            "private fun stopAutomation", 1
        )[1].split("private fun saveMappedSettings", 1)[0]

        self.assertIn("shared_local_write_plan(", desktop_start)
        self.assertNotIn("require_account_online", desktop_start)
        self.assertIn("shared_local_write_plan(", desktop_stop)
        self.assertIn('"/api/automation/start-saved"', android_start)
        self.assertIn("dispatchSharedLocal(", android_start)
        self.assertNotIn("startAccount(request)", android_start)
        self.assertNotIn("loginService", android_start)
        self.assertIn('"/api/automation/stop"', android_stop)
        self.assertIn("dispatchSharedLocal(", android_stop)
        self.assertNotIn("accounts.setEnabled", android_stop)

    def test_account_add_and_start_use_shared_durable_operations_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        hosted_factory = (
            ROOT / "shared_core/python/dwpm_core/__init__.py"
        ).read_text(encoding="utf-8")
        android_port = (
            ROOT
            / "自研辅助源码/app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        ).read_text(encoding="utf-8")

        desktop_add = desktop.split(
            'if self.path in {"/api/accounts/add", "/api/login"}:', 1
        )[1].split('if self.path == "/api/accounts/start":', 1)[0]
        desktop_start = desktop.split(
            'if self.path == "/api/accounts/start":', 1
        )[1].split('if self.path == "/api/accounts/stop":', 1)[0]
        android_add = android.split(
            "private fun addAccount", 1
        )[1].split("private fun startAccount", 1)[0]
        android_start = android.split(
            "private fun startAccount", 1
        )[1].split("private fun stopAccount", 1)[0]

        self.assertIn("account_add_prepare", desktop_add)
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", desktop_add)
        self.assertNotIn("start_account(", desktop_start)
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", desktop_start)
        self.assertIn("prepareAccountAdd", android_add)
        self.assertIn("sharedPythonCore.dispatch(", android_add)
        self.assertNotIn("loginAndPersist", android_add)
        self.assertIn("sharedPythonCore.dispatch(", android_start)
        self.assertNotIn("loginService", android_start)
        for path in ("/api/accounts/add", "/api/accounts/start"):
            self.assertIn(f'"{path}"', hosted_factory)
        self.assertIn("account_add_operation_payload", hosted_factory)
        self.assertIn("account_start_operation_payload", hosted_factory)
        self.assertIn("register_account_login_routes", hosted_factory)
        self.assertIn("executeRawHttp", android_port)
        self.assertIn("commitAccountRuntime", android_port)
        self.assertIn("startAccountHosting", android_port)
        self.assertIn("private val accounts by lazy", android_port)
        self.assertNotIn("LocalAccountLoginService", android_port)
        self.assertNotIn("loginAndPersist", android_port)
        self.assertNotIn("executeAccountLifecycleOperation", android_port)

    def test_map_reads_use_shared_projection_on_both_hosts(self) -> None:
        desktop = DESKTOP_SERVER.read_text(encoding="utf-8")
        android = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        bandit = desktop.split("def public_bandit_map(", 1)[1].split(
            "def public_mine_map(", 1
        )[0]
        mine = desktop.split("def public_mine_map(", 1)[1].split(
            "def shared_map_region_entry(", 1
        )[0]
        android_map = android.split("private fun localMap(", 1)[1].split(
            "private fun accountSettings(", 1
        )[0]

        self.assertIn('shared_local_view("GET", "/api/maps/bandits"', bandit)
        self.assertIn('shared_local_view("GET", "/api/maps/mines"', mine)
        self.assertNotIn("points.append", bandit)
        self.assertNotIn("points.append", mine)
        self.assertIn("dispatchSharedLocal", android_map)
        self.assertIn("rawLocalMapJson", android_map)
        self.assertNotIn("LocalMapApiMapper", android_map)

    def test_formation_settings_route_uses_shared_write_plan(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/formations/save":',
            1,
        )[1].split('if self.path == "/api/formations/unassign-all":', 1)[0]

        self.assertIn("shared_settings_write_plan(self.path, planning_body)", route)
        self.assertIn('"/api/formations/apply"', route)
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
        self.assertNotIn("start_apply_formations_task(", route)
        self.assertNotIn("sanitize_formation_rows", route)
        self.assertNotIn("normalize_formation_rules", route)

    def test_inventory_open_route_submits_full_shared_operation(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/inventory/open-one":',
            1,
        )[1].split('if self.path == "/api/brush/recommended-center":', 1)[0]

        self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
        self.assertIn('"/api/inventory/open-one"', route)
        self.assertIn("_desktop_shared_operation_body(body)", route)
        self.assertNotIn("shared_plan_open_one_inventory(", route)
        self.assertNotIn("use_inventory_item(", route)
        self.assertNotIn("name not in AUTO_OPEN_ITEM_NAMES", route)
        self.assertNotIn("AUTO_OPEN_KEY_REQUIREMENTS.get", route)

    def test_mine_settings_route_uses_shared_write_plan_without_online_wait(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/mine/save":',
            1,
        )[1].split('if self.path == "/api/dashboard/mine-settings":', 1)[0]

        self.assertIn("shared_settings_write_plan(", route)
        self.assertNotIn("normalize_mine_settings", route)
        self.assertNotIn("require_account_online", route)

    def test_desktop_migrated_resident_workers_only_wake_shared_tick(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        brush = source.split("def auto_brush_worker(", 1)[1].split(
            "def start_auto_brush(", 1
        )[0]
        mine = source.split("def auto_mine_worker(", 1)[1].split(
            "def start_auto_mine(", 1
        )[0]
        raid = source.split("def raid_worker(", 1)[1].split(
            "def start_raid_task(", 1
        )[0]
        lossless = source.split("def lossless_worker(", 1)[1].split(
            "def start_lossless_task(", 1
        )[0]
        dungeon = source.split("def dungeon_worker(", 1)[1].split(
            "def start_dungeon_task(", 1
        )[0]
        ministry = source.split("def auto_ministry_worker(", 1)[1].split(
            "def start_auto_ministry(", 1
        )[0]
        general = source.split("def auto_general_worker(", 1)[1].split(
            "def start_auto_general(", 1
        )[0]
        domestic = source.split("def auto_domestic_worker(", 1)[1].split(
            "def start_auto_domestic(", 1
        )[0]
        alarm = source.split("def start_auto_alarm(", 1)[1].split(
            "def start_auto_ministry(", 1
        )[0]
        daily = source.split("def execute_daily_once_tasks(", 1)[1].split(
            "def update_daily_automation_retry_state(", 1
        )[0]

        self.assertIn("execute_shared_resident_automation_tick(", brush)
        self.assertIn("configured_execution_allowed=not stop_requested", brush)
        self.assertNotIn('sess["savedTasksStarted"] = True', brush)
        self.assertNotIn("execute_brush(", brush)
        self.assertNotIn("execute_mine(", brush)
        self.assertIn("auto_brush_worker(task_id)", mine)
        self.assertIn("auto_brush_worker(task_id)", raid)
        self.assertIn("auto_brush_worker(task_id)", lossless)
        self.assertIn("auto_brush_worker(task_id)", dungeon)
        self.assertIn("auto_brush_worker(task_id)", ministry)
        self.assertIn("auto_brush_worker(task_id)", general)
        self.assertIn("auto_brush_worker(task_id)", domestic)
        self.assertIn("target=auto_brush_worker", alarm)
        self.assertNotIn("execute_building_action(", domestic)
        self.assertNotIn("execute_technology_upgrade(", domestic)
        self.assertIn("execute_shared_daily_automation_tick(", daily)
        self.assertNotIn("_legacy_auto_brush_worker", source)
        self.assertNotIn("_legacy_auto_mine_worker", source)
        self.assertNotIn("_legacy_raid_worker", source)
        self.assertNotIn("_legacy_lossless_worker", source)
        self.assertNotIn("_legacy_dungeon_worker", source)
        self.assertNotIn("_legacy_auto_ministry_worker", source)
        self.assertNotIn("_legacy_auto_general_worker", source)
        self.assertNotIn("_legacy_auto_domestic_worker", source)
        self.assertNotIn("_legacy_execute_daily_once_tasks", source)

    def test_scoped_settings_route_uses_shared_write_plan_and_async_follow_ups(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/settings/save":',
            1,
        )[1].split('if self.path == "/api/domestic/query":', 1)[0]

        self.assertIn("shared_settings_write_plan(self.path, planning_body)", route)
        self.assertIn('"dailyResults": {}', route)
        self.assertIn('"dailyExecution": daily_results', route)
        self.assertNotIn("normalize_settings_scope_patch(", route)
        self.assertNotIn("require_brush_save_level(", route)
        self.assertIn("threading.Thread(", route)

    def test_android_retired_resident_tasks_cannot_regain_business_execution(self) -> None:
        scheduler_dir = (
            ROOT
            / "自研辅助源码/app/src/main/java/com/example/dwpmclone/domain/scheduler"
        )
        tasks = (scheduler_dir / "AssistantTasks.kt").read_text(
            encoding="utf-8"
        )
        factory = (scheduler_dir / "TaskFactory.kt").read_text(
            encoding="utf-8"
        )
        brush = tasks.split("class ShuaHuangTask", 1)[1].split(
            "class MineTask", 1
        )[0]
        mine = tasks.split("class MineTask", 1)[1].split(
            "class InventoryCleanupTask", 1
        )[0]
        alarm = tasks.split("class AlarmTask", 1)[1]

        for body in (brush, mine, alarm):
            self.assertIn("sharedOwnerStop", body)
            self.assertNotIn("ctx.protocol", body)
            self.assertNotIn("dispatchFormation", body)
            self.assertNotIn("occupyMine", body)
            self.assertNotIn("searchMap", body)
            self.assertNotIn("searchMines", body)
        self.assertNotIn("class BanditPrefetchTask", tasks)
        self.assertNotIn("class MinePrefetchTask", tasks)
        self.assertNotIn("class StateRefreshTask", tasks)
        self.assertNotIn("class FoodToCopperTask", tasks)
        self.assertNotIn("class FormationUpdateTask", tasks)
        self.assertNotIn("add(StateRefreshTask", factory)
        self.assertNotIn("add(FoodToCopperTask", factory)
        android_main = ROOT / "自研辅助源码/app/src/main/java"
        excluded = {"SessionAwareGameProtocolClient.kt", "ProtocolAndTasks.kt"}
        production_callers = "\n".join(
            path.read_text(encoding="utf-8")
            for path in android_main.rglob("*.kt")
            if path.name not in excluded
        )
        for retired_call in (
            "dispatchFormation",
            "searchMines",
            "revalidateMineTarget",
            "occupyMine",
            "withdrawMineDefense",
            "accelerateMineMarch",
            "clearMinePendingGarrison",
            "clearBrushPendingRecovery",
        ):
            self.assertNotRegex(
                production_callers,
                rf"\.\s*{retired_call}\s*\(",
            )

    def test_android_health_reports_no_remaining_kotlin_business_owner(self) -> None:
        controller = ANDROID_ROUTE_SOURCES[0].read_text(encoding="utf-8")
        health = controller.split("private fun sharedCoreHealth", 1)[1].split(
            "private fun sharedCoreAccounts", 1
        )[0]

        self.assertIn('"androidRouteBusinessOwner", "shared-python"', health)
        self.assertIn('"androidLegacyBusinessOwner", "none"', health)
        self.assertIn('"androidRemainingKotlinBackgroundOwners"', health)
        for owner in (
            "general-maintenance",
            "internal-affairs",
            "inventory-cleanup",
            "military-alarm",
        ):
            self.assertNotIn(f'"{owner}"', health)

    def test_resident_save_routes_use_shared_plans_without_online_wait(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route_boundaries = (
            ("/api/raid/execute", "/api/lossless/execute", "normalize_raid_rows"),
            ("/api/lossless/execute", "/api/dungeon/execute", "normalize_lossless_rows"),
            ("/api/dungeon/execute", "/api/military/future/save", "normalize_dungeon_rows"),
        )
        for path, next_path, old_normalizer in route_boundaries:
            route = source.split(
                f'if self.path == "{path}":',
                1,
            )[1].split(f'if self.path == "{next_path}":', 1)[0]
            self.assertIn("shared_settings_write_plan(self.path, planning_body)", route)
            self.assertNotIn("require_account_online", route)
            self.assertNotIn(old_normalizer, route)
            self.assertIn("activationError", route)

    def test_android_allow_list_is_covered_and_known_gaps_are_explicit(self) -> None:
        source = "\n".join(path.read_text(encoding="utf-8") for path in ANDROID_ROUTE_SOURCES)
        android_pairs = set(re.findall(r'"(GET|POST)"\s+to\s+"(/api/[^"]+)"', source))
        self.assertEqual(sorted(android_pairs - self.exact_pairs), [])

        expected_missing = set()
        declared_missing = {
            (row["method"], row["path"])
            for row in self.shared
            if row["currentAndroid"] == "missing"
        }
        self.assertEqual(declared_missing, expected_missing)
        self.assertTrue(expected_missing.isdisjoint(android_pairs))

    def test_response_model_separates_local_saves_from_network_work(self) -> None:
        by_key = {(row["method"], row["path"]): row for row in self.shared}
        for path in (
            "/api/settings/save",
            "/api/formations/save",
            "/api/raid/execute",
            "/api/mine/save",
            "/api/liubu/save",
            "/api/lossless/execute",
            "/api/dungeon/execute",
            "/api/military/future/save",
        ):
            self.assertEqual(by_key[("POST", path)]["responseClass"], "local")

        for method, path in (
            ("GET", "/api/state/refresh"),
            ("GET", "/api/military/intel"),
            ("POST", "/api/formations/apply"),
            ("POST", "/api/brush/search"),
            ("POST", "/api/brush/execute"),
            ("POST", "/api/mine/search"),
            ("POST", "/api/mine/execute"),
        ):
            self.assertEqual(by_key[(method, path)]["responseClass"], "network-operation")

    def test_desktop_expedition_http_routes_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        brush = source.split(
            'if self.path == "/api/brush/execute":',
            1,
        )[1].split('if self.path == "/api/mine/search":', 1)[0]
        mine = source.split(
            'if self.path == "/api/mine/execute":',
            1,
        )[1].split('if self.path == "/api/liubu/hubu/query":', 1)[0]

        for route, path in (
            (brush, "/api/brush/execute"),
            (mine, "/api/mine/execute"),
        ):
            self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
            self.assertIn(f'"{path}"', route)
            self.assertIn("_desktop_expedition_body(", route)
            self.assertNotIn("execute_brush(", route)
            self.assertNotIn("execute_mine(", route)

    def test_desktop_state_heartbeat_and_military_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        heartbeat = source.split(
            'if self.path.startswith("/api/heartbeat"):', 1
        )[1].split('if self.path.startswith("/api/automation/status"):', 1)[0]
        state = source.split(
            'if self.path.startswith("/api/state/refresh"):', 1
        )[1].split('if self.path.startswith("/api/military/intel"):', 1)[0]
        military = source.split(
            'if self.path.startswith("/api/military/intel"):', 1
        )[1].split("super().do_GET()", 1)[0]
        for route, path, forbidden in (
            (heartbeat, "/api/heartbeat", "execute_heartbeat("),
            (state, "/api/state/refresh", "refresh_generals("),
            (military, "/api/military/intel", "refresh_military_snapshot("),
        ):
            self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
            self.assertIn(f'"{path}"', route)
            self.assertNotIn(forbidden, route)

        registrations = source.split(
            "def _register_desktop_shared_expedition_routes()", 1
        )[1].split("_register_desktop_shared_expedition_routes()", 1)[0]
        for path in (
            "/api/heartbeat",
            "/api/state/refresh",
            "/api/military/intel",
        ):
            self.assertIn(f'"{path}"', registrations)
        self.assertIn("state_refresh_operation_payload", registrations)
        self.assertIn("heartbeat_operation_payload", registrations)
        self.assertIn("_run_state_refresh_game_workflow", registrations)
        self.assertIn("_run_heartbeat_game_workflow", registrations)
        self.assertIn("_run_military_intel_game_workflow", registrations)
        self.assertNotIn("_desktop_shared_state_refresh", source)
        self.assertNotIn("_desktop_shared_heartbeat", source)
        self.assertNotIn("_desktop_shared_military_refresh", source)

    def test_desktop_search_http_routes_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        brush = source.split(
            'if self.path == "/api/brush/search":',
            1,
        )[1].split('if self.path == "/api/brush/execute":', 1)[0]
        mine = source.split(
            'if self.path == "/api/mine/search":',
            1,
        )[1].split('if self.path == "/api/mine/execute":', 1)[0]
        for route, path, old_call in (
            (brush, "/api/brush/search", "search_targets("),
            (mine, "/api/mine/search", "search_mine_targets("),
        ):
            self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
            self.assertIn(f'"{path}"', route)
            self.assertIn("_desktop_shared_operation_body(body)", route)
            self.assertNotIn(old_call, route)
        registrations = source.split(
            "def _register_desktop_shared_expedition_routes()",
            1,
        )[1].split("_register_desktop_shared_expedition_routes()", 1)[0]
        self.assertIn(
            "SHARED_PYTHON_CORE._run_cloud_coordinated_brush_search_game_workflow",
            registrations,
        )
        self.assertIn(
            "SHARED_PYTHON_CORE._run_cloud_coordinated_mine_search_game_workflow",
            registrations,
        )
        self.assertIn("map_snapshots=DesktopMapSnapshotPort(", source)

    def test_desktop_maintenance_http_routes_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        boundaries = (
            ("/api/troops/refill", "/api/inventory/open-one"),
            ("/api/inventory/open-one", "/api/brush/recommended-center"),
            ("/api/troops/assign", "/api/troops/heal"),
            ("/api/troops/heal", "/api/formations/save"),
            ("/api/formations/apply", "/api/formations/unassign-all"),
            ("/api/formations/unassign-all", "/api/settings/save"),
        )
        old_calls = (
            "execute_refill_troops(",
            "use_inventory_item(",
            "execute_assign_troops(",
            "execute_heal_wounded(",
            "start_apply_formations_task(",
            "unassign_all_idle_generals(",
        )
        for (path, next_path), old_call in zip(boundaries, old_calls):
            route = source.split(
                f'if self.path == "{path}":',
                1,
            )[1].split(f'if self.path == "{next_path}":', 1)[0]
            self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
            self.assertIn(f'"{path}"', route)
            self.assertIn("_desktop_shared_operation_body(body)", route)
            self.assertNotIn(old_call, route)

    def test_desktop_daily_http_routes_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            "if parsed_request.path in DESKTOP_SHARED_DAILY_OPERATION_ROUTES:",
            1,
        )[1].split('if self.path == "/api/notices/dismiss":', 1)[0]
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
        self.assertIn("parsed_request.path", route)
        self.assertIn("_desktop_shared_operation_body(body)", route)
        registrations = source.split(
            "def _register_desktop_shared_expedition_routes()",
            1,
        )[1].split("_register_desktop_shared_expedition_routes()", 1)[0]
        paths = (
            "/api/daily/sign-in/claim",
            "/api/daily/arena-coins/claim",
            "/api/daily/donate/claim",
            "/api/daily/donate/custom",
            "/api/daily/salary/claim",
            "/api/daily/national-collect/claim",
            "/api/daily/city-lord-collect/claim",
            "/api/daily/general-visit/candidates",
            "/api/daily/general-visit/claim",
        )
        for path in paths:
            self.assertIn(f'"{path}"', registrations)
            self.assertNotIn(f'if self.path == "{path}":', source)
        for old_call in (
            "claim_daily_sign_in(",
            "claim_arena_coins(",
            "execute_daily_country_donations(",
            "claim_national_salary(",
            "execute_national_collect(",
            "execute_city_lord_collect(",
            "execute_general_visit(",
            "query_general_visit_candidates(",
        ):
            self.assertNotIn(old_call, route)

    def test_desktop_ministry_and_domestic_routes_only_submit_shared_operations(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        boundaries = (
            ("/api/liubu/hubu/query", "/api/liubu/hubu/plant"),
            ("/api/liubu/hubu/plant", "/api/liubu/save"),
            ("/api/domestic/query", "/api/domestic/action"),
            ("/api/domestic/action", "/api/automation/stop"),
        )
        old_calls = (
            "query_hubu_plant_state(",
            "execute_hubu_batch_plant(",
            "query_fief_buildings(",
            "execute_building_action(",
        )
        for (path, next_path), old_call in zip(boundaries, old_calls):
            route = source.split(
                f'if self.path == "{path}":',
                1,
            )[1].split(f'if self.path == "{next_path}":', 1)[0]
            self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
            self.assertIn(f'"{path}"', route)
            self.assertIn("_desktop_shared_operation_body(body)", route)
            self.assertNotIn(old_call, route)

    def test_desktop_raid_fiefs_only_submits_shared_raw_query(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        route = source.split(
            'if self.path == "/api/raid/fiefs":',
            1,
        )[1].split('if self.path == "/api/raid/execute":', 1)[0]
        self.assertIn("SHARED_PYTHON_CORE.dispatch(", route)
        self.assertIn('"/api/raid/fiefs"', route)
        self.assertNotIn("query_raid_fiefs(", route)
        registrations = source.split(
            "def _register_desktop_shared_expedition_routes()",
            1,
        )[1].split("_register_desktop_shared_expedition_routes()", 1)[0]
        self.assertIn("SHARED_PYTHON_CORE._run_raid_fiefs_game_workflow", registrations)

    def _classified_path(self, path: str) -> bool:
        return path in self.exact_paths or path.startswith("/api/v1/mobile")


if __name__ == "__main__":
    unittest.main()

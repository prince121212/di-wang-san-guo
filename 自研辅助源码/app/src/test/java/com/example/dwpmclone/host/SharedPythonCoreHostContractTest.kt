package com.example.dwpmclone.host

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedPythonCoreHostContractTest {
    @Test
    fun dungeonProductionOwnsNoKotlinProtocolFallback() {
        val sessionClient = source(
            "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
            "src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt"
        )
        val sharedFacade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )

        assertFalse(
            resolve(
                "app/src/main/java/com/example/dwpmclone/domain/protocol/DungeonProtocolShapes.kt",
                "src/main/java/com/example/dwpmclone/domain/protocol/DungeonProtocolShapes.kt"
            ).exists()
        )
        assertFalse(
            resolve(
                "app/src/main/java/com/example/dwpmclone/domain/protocol/DungeonPendingRun.kt",
                "src/main/java/com/example/dwpmclone/domain/protocol/DungeonPendingRun.kt"
            ).exists()
        )
        assertFalse(
            resolve(
                "app/src/main/java/com/example/dwpmclone/host/SharedDungeonActionAdapter.kt",
                "src/main/java/com/example/dwpmclone/host/SharedDungeonActionAdapter.kt"
            ).exists()
        )
        assertFalse(sessionClient.contains("runDungeon"))
        assertFalse(sessionClient.contains("sharedDungeonAction"))
        assertFalse(sessionClient.contains("DungeonProtocolShapes"))
        assertFalse(sessionClient.contains("REAL_DUNGEON_"))
        assertTrue(sharedFacade.contains("automation:dungeon-action:v1"))
        assertTrue(sharedFacade.contains("_run_dungeon_action_game_workflow"))
    }

    @Test
    fun losslessProductionOwnsNoKotlinProtocolFallback() {
        val sessionClient = source(
            "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
            "src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt"
        )
        val sharedFacade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )

        assertFalse(
            resolve(
                "app/src/main/java/com/example/dwpmclone/domain/protocol/LosslessProtocolShapes.kt",
                "src/main/java/com/example/dwpmclone/domain/protocol/LosslessProtocolShapes.kt"
            ).exists()
        )
        assertFalse(
            resolve(
                "app/src/main/java/com/example/dwpmclone/host/SharedLosslessActionAdapter.kt",
                "src/main/java/com/example/dwpmclone/host/SharedLosslessActionAdapter.kt"
            ).exists()
        )
        assertFalse(sessionClient.contains("runLossless"))
        assertFalse(sessionClient.contains("sharedLosslessAction"))
        assertFalse(sessionClient.contains("sendLosslessCommand"))
        assertFalse(sessionClient.contains("REAL_LOSSLESS_DISPATCH_"))
        assertTrue(sharedFacade.contains("automation:lossless-action:v1"))
        assertTrue(sharedFacade.contains("_run_lossless_action_game_workflow"))
    }

    @Test
    fun androidMigratedResidentBackgroundOwnershipIsSharedPythonOnly() {
        val service = source(
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
        )
        val adapter = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val sessionClient = source(
            "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
            "src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt"
        )
        val protocolBoundary = source(
            "app/src/main/java/com/example/dwpmclone/domain/protocol/ProtocolAndTasks.kt",
            "src/main/java/com/example/dwpmclone/domain/protocol/ProtocolAndTasks.kt"
        )

        assertTrue(service.contains("runSharedResidentTicks"))
        assertTrue(service.contains("it.type in SHARED_RESIDENT_TASK_TYPES"))
        assertTrue(service.contains("sharedResidentResults.mapNotNull"))
        assertTrue(
            service.indexOf("if (!refreshNetworkAvailability") <
                service.indexOf("val sharedResidentResults")
        )
        assertTrue(adapter.contains("allowedFeatures"))
        assertTrue(
            adapter.contains(
                "listOf(\"mine\", \"lossless\", \"brush\", \"raid\", \"dungeon\", \"general\", \"ministry\", \"domestic\", \"inventory\", \"alarm\", \"daily\")"
            )
        )
        assertTrue(facade.contains("_run_configured_brush_tick"))
        assertTrue(facade.contains("_run_configured_mine_tick"))
        assertTrue(facade.contains("_run_configured_raid_tick"))
        assertTrue(facade.contains("_run_configured_lossless_tick"))
        assertTrue(facade.contains("_run_configured_dungeon_tick"))
        assertTrue(facade.contains("_run_configured_general_tick"))
        assertTrue(facade.contains("_run_configured_domestic_tick"))
        assertTrue(facade.contains("_run_configured_inventory_tick"))
        assertTrue(facade.contains("_run_configured_alarm_tick"))
        assertTrue(facade.contains("emit_host_alarm_error_json"))
        assertTrue(service.contains("TaskType.AUTO_LOOT"))
        assertTrue(service.contains("TaskType.LOSSLESS"))
        assertTrue(service.contains("TaskType.DUNGEON"))
        assertTrue(service.contains("TaskType.GENERAL"))
        assertTrue(service.contains("TaskType.SIX_MINISTRIES"))
        assertTrue(service.contains("TaskType.ALARM"))
        assertTrue(service.contains("TaskType.INTERNAL"))
        assertTrue(facade.contains("residentAutomationStateJson"))
        assertTrue(facade.contains("_run_configured_ministry_tick"))
        assertTrue(facade.contains("_run_configured_daily_tick"))
        assertTrue(facade.contains("ministryPendingPlantJson"))
        assertTrue(facade.contains("generalMaintenancePendingJson"))
        assertTrue(facade.contains("domesticPendingActionJson"))

        val assistantTasks = source(
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt",
            "src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt"
        )
        val dailyTasks = source(
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/DailyFeatureTasks.kt",
            "src/main/java/com/example/dwpmclone/domain/scheduler/DailyFeatureTasks.kt"
        )
        assertFalse(assistantTasks.contains("ctx.protocol.runAutoLoot"))
        assertFalse(assistantTasks.contains("ctx.protocol.runSixMinistries"))
        assertFalse(assistantTasks.contains("ctx.protocol.runLossless"))
        assertFalse(assistantTasks.contains("ctx.protocol.runDungeon"))
        assertTrue(assistantTasks.contains("sharedOwnerStop(\"掠夺\")"))
        assertTrue(assistantTasks.contains("sharedOwnerStop(\"六部\")"))
        assertTrue(assistantTasks.contains("sharedOwnerStop(\"无损\")"))
        assertTrue(assistantTasks.contains("sharedOwnerStop(\"副本\")"))
        assertTrue(assistantTasks.contains("sharedOwnerStop(\"日常\")"))
        assertTrue(dailyTasks.contains("SharedDailyTask"))
        assertFalse(dailyTasks.contains("ctx.protocol"))
        assertFalse(sessionClient.contains("runAutoLoot"))
        assertFalse(sessionClient.contains("REAL_LOOT_"))
        assertFalse(sessionClient.contains("runSixMinistries"))
        assertFalse(sessionClient.contains("REAL_MINISTRY_"))
        listOf(
            "runAutoLoot",
            "runSixMinistries",
            "runDungeon",
            "runLossless",
            "queryNationalCities",
            "queryNationalCollectStatus",
            "collectNationalCity",
            "queryOwnedFiefs",
            "queryRaidFiefs",
            "collectCityLord",
            "queryVisitGenerals",
            "visitGeneral"
        ).forEach { retiredEntry ->
            assertFalse(sessionClient.contains(retiredEntry))
            assertFalse(protocolBoundary.contains(retiredEntry))
        }
        assertFalse(assistantTasks.contains("REAL_LOSSLESS_DISPATCH_"))
        assertFalse(assistantTasks.contains("SHARED_DUNGEON_UNCERTAIN"))
        assertFalse(assistantTasks.contains("SHARED_LOSSLESS_UNCERTAIN"))
        assertFalse(assistantTasks.contains("REAL_LOOT_DISPATCH_"))
    }

    @Test
    fun androidBuildPackagesTheRepositorySharedSourceInsteadOfACopy() {
        val rootBuild = source("../build.gradle.kts", "build.gradle.kts")
        val appBuild = source("app/build.gradle.kts", "build.gradle.kts")

        assertTrue(rootBuild.contains("id(\"com.chaquo.python\") version \"17.0.0\""))
        assertTrue(appBuild.contains("srcDir(sharedPythonSource.asFile)"))
        assertTrue(appBuild.contains("generateSharedPythonBundle"))
        assertTrue(appBuild.contains("minSdk = 24"))
        assertTrue(appBuild.contains("version = \"3.10\""))
        assertFalse(resolve("app/src/main/python/dwpm_core", "src/main/python/dwpm_core").exists())
    }

    @Test
    fun applicationWarmsTheInterpreterOffTheUiThread() {
        val application = source(
            "app/src/main/java/com/example/dwpmclone/SharedCoreApplication.kt",
            "src/main/java/com/example/dwpmclone/SharedCoreApplication.kt"
        )
        val host = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt",
            "src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt"
        )

        assertTrue(application.contains("warmUpAsync()"))
        assertTrue(host.contains("Thread(runnable, \"shared-python-warmup\")"))
        assertTrue(host.contains("Python.start(AndroidPlatform(appContext))"))
        assertTrue(host.contains("\"create_hosted_core\""))
        assertTrue(host.contains("platformPorts"))
        assertTrue(host.contains("operations-v2.json"))
        assertTrue(host.contains("\"dispatch_json\""))
        assertTrue(host.contains("\"account_lifecycle_snapshot_json\""))
        assertTrue(host.contains("\"account_transition_json\""))
        assertTrue(host.contains("AccountStateTransitionSource"))
        assertTrue(host.contains("\"account_records_snapshot_json\""))
        assertTrue(host.contains("\"account_record_presentation_json\""))
        assertTrue(host.contains("submitAutomationRecoveryTick"))
        assertTrue(host.contains("\"submit_automation_recovery_tick_json\""))
        assertFalse(host.contains("submitLosslessAction"))
        assertFalse(host.contains("submitDungeonAction"))
        assertTrue(host.contains("\"acknowledge_dungeon_defeat_json\""))
        assertTrue(host.contains("SharedAccountStateGateway"))
        assertTrue(host.contains("\"dispatch_json\""))
    }

    @Test
    fun pocOperationIsDurableImmediateAndCannotReachTheNetwork() {
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val operationCore = source(
            "../shared_core/python/dwpm_core/operations.py",
            "../../shared_core/python/dwpm_core/operations.py"
        )

        assertTrue(controller.contains("/api/core/operations/simulate"))
        assertTrue(controller.contains("/api/core/operations/status"))
        assertTrue(controller.contains("/api/core/verification/protocol"))
        assertTrue(controller.contains("ApplicationInfo.FLAG_DEBUGGABLE"))
        assertTrue(operationCore.contains("idempotencyKey"))
        assertTrue(operationCore.contains("temporary.replace(self._path)"))
        assertTrue(operationCore.contains("daemon=True"))
        assertFalse(operationCore.contains("import socket"))
        assertFalse(operationCore.contains("import requests"))
        assertFalse(operationCore.contains("import urllib"))

        val bridgeScript = source(
            "../电脑端辅助前端/assistant-api.js",
            "../../电脑端辅助前端/assistant-api.js"
        )
        assertTrue(bridgeScript.contains("waitForOperation"))
        assertTrue(bridgeScript.contains("/api/core/operations/status"))
    }

    @Test
    fun webBridgeUsesPushEventsWithRecoveryAndSafeCancellation() {
        val bridge = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/AssistantWebBridge.kt",
            "src/main/java/com/example/dwpmclone/ui/web/AssistantWebBridge.kt"
        )
        val bridgeScript = source(
            "../电脑端辅助前端/assistant-api.js",
            "../../电脑端辅助前端/assistant-api.js"
        )
        val frontend = source(
            "../电脑端辅助前端/app.js",
            "../../电脑端辅助前端/app.js"
        )
        val frontendHtml = source(
            "../电脑端辅助前端/index.html",
            "../../电脑端辅助前端/index.html"
        )
        val frontendStyles = source(
            "../电脑端辅助前端/styles.css",
            "../../电脑端辅助前端/styles.css"
        )

        assertTrue(bridge.contains("SharedCoreEventBuffer.subscribe(::deliverEvent)"))
        assertTrue(bridge.contains("window.AssistantApi&&window.AssistantApi.__event"))
        assertTrue(bridge.contains("SharedCoreEventBuffer.unsubscribe(eventSubscription)"))
        assertTrue(bridgeScript.contains("assistant-operation-state"))
        assertTrue(bridgeScript.contains("assistant-operation-recovery"))
        assertTrue(bridgeScript.contains("TRACKED_OPERATIONS_KEY"))
        assertTrue(bridgeScript.contains("cancelOperation"))
        assertFalse(bridgeScript.contains("OPERATION_POLL_MILLIS"))
        assertTrue(frontend.contains("networkOperationTray"))
        assertTrue(frontend.contains("request-already-sent"))
        assertTrue(frontend.contains("回执不明确"))
        assertTrue(frontendHtml.contains("network-operation-tray page-hidden\" hidden"))
        assertTrue(frontendHtml.contains("aria-hidden=\"true\""))
        assertTrue(frontendStyles.contains(".network-operation-tray {\n  display: none !important;"))
    }

    @Test
    fun phaseFiveHostPortsExposeCapabilitiesWithoutDuplicatingBusinessRules() {
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val operations = source(
            "../shared_core/python/dwpm_core/operations.py",
            "../../shared_core/python/dwpm_core/operations.py"
        )

        assertTrue(ports.contains("KeystoreCredentialVault"))
        assertTrue(ports.contains("KeystoreSessionSecretVault"))
        assertTrue(ports.contains("saveSessionSecrets"))
        assertTrue(ports.contains("loadSessionSecrets"))
        assertTrue(ports.contains("networkAvailable"))
        assertTrue(ports.contains("NotificationManager"))
        assertTrue(ports.contains("AlarmManager"))
        assertTrue(ports.contains("TaskLogRepository"))
        assertFalse(ports.contains("0x1522"))
        assertFalse(ports.contains("SessionAwareGameProtocolClient"))
        assertTrue(ports.contains("fun executeRawHttp("))
        assertFalse(ports.contains("executeNetworkOperation"))
        assertFalse(ports.contains("handleSharedCoreNetwork"))

        val runner = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt"
        )
        assertTrue(runner.contains("executeSharedCoreReadOnly"))
        assertTrue(runner.contains("AccountOperationLockRegistry.tryAcquire(accountId)"))
        assertTrue(runner.contains("LOCAL_ACCOUNT_BUSY"))
        val sharedReadOnly = runner
            .substringAfter("fun <T> executeSharedCoreReadOnly")
            .substringBefore("private fun <T> executeInternal")
        assertFalse(sharedReadOnly.contains("AccountOperationLockRegistry.acquire(accountId)"))
        assertTrue(facade.contains("def dispatch("))
        assertTrue(facade.contains("HOST_ACCOUNT_BUSY_CODE"))
        assertTrue(facade.contains("execution.wait(busy_backoff)"))
        assertTrue(facade.contains("sensitive field cannot enter {destination}"))
        assertTrue(facade.contains("destination: str = \"operation ledger\""))
        assertTrue(operations.contains("dwpm-network-"))
        assertTrue(operations.contains("UNCERTAIN"))
        assertTrue(operations.contains("request-already-sent"))

        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val settingsMapper = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalSettingsConfigMapper.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalSettingsConfigMapper.kt"
        )
        val settingsExecutionPolicy = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalSettingsExecutionPolicy.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalSettingsExecutionPolicy.kt"
        )
        val residentAdapter = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt"
        )
        assertTrue(controller.contains("\"/api/military/future/save\""))
        assertTrue(controller.contains("\"/api/liubu/save\""))
        assertTrue(controller.contains("\"/api/accounts/settings\""))
        assertTrue(controller.contains("\"/api/formations/save\""))
        assertTrue(controller.contains("\"/api/mine/save\""))
        assertTrue(controller.contains("\"/api/settings/save\""))
        assertTrue(controller.contains("\"/api/raid/execute\""))
        assertTrue(controller.contains("\"/api/lossless/execute\""))
        assertTrue(controller.contains("\"/api/dungeon/execute\""))
        assertTrue(controller.contains("val dispatched = sharedPythonCore.dispatch("))
        assertTrue(controller.contains("networkRequired"))
        assertTrue(controller.contains("LocalSettingsExecutionPolicy.decide"))
        assertTrue(controller.contains("localWriteCommitted"))
        assertFalse(controller.contains("sharedPythonCore.configureResidentAutomation("))
        assertTrue(settingsExecutionPolicy.contains("accountEnabled && accountRunnable && executionOwnerActive"))
        assertTrue(residentAdapter.contains("runCatching { configure(accountRef, habits) }"))
        assertFalse(settingsMapper.contains("private fun future("))
        assertFalse(settingsMapper.contains("private fun ministries("))
        assertFalse(settingsMapper.contains("private fun formation("))
        assertFalse(settingsMapper.contains("private fun mine("))
        assertFalse(settingsMapper.contains("private fun scoped("))
        assertFalse(settingsMapper.contains("private fun brush("))
        assertFalse(settingsMapper.contains("private fun frequent("))
        assertFalse(settingsMapper.contains("private fun raid("))
        assertFalse(settingsMapper.contains("private fun lossless("))
        assertFalse(settingsMapper.contains("private fun dungeon("))
        assertFalse(settingsMapper.contains("fun map(route:"))
    }

    @Test
    fun formationApplyUsesTheSharedRawCommandWorkflowAndKotlinHasNoRouteAdapter() {
        val hostedCoreFactory = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val runner = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )
        val frontend = source(
            "../电脑端辅助前端/app.js",
            "../../电脑端辅助前端/app.js"
        )

        assertTrue(hostedCoreFactory.contains("/api/formations/apply"))
        assertTrue(hostedCoreFactory.contains("facade._run_formation_apply_game_workflow"))
        assertTrue(hostedCoreFactory.contains("persisted_payload_builder=facade.formation_apply_operation_payload"))
        assertTrue(hostedCoreFactory.contains("coalesce_active=True"))
        assertTrue(facade.contains("def _run_formation_apply_game_workflow("))
        assertTrue(facade.contains("self._run_troop_assign_game_workflow("))
        assertTrue(facade.contains("host_bridge.tryAcquireNetworkOperation(account_ref)"))
        assertTrue(facade.contains("execution.mark_request_sent({"))
        assertTrue(facade.contains("host_bridge.releaseNetworkOperation(account_ref)"))

        assertTrue(controller.contains("\"POST\" to \"/api/formations/apply\" -> submitSharedNetworkOperation"))
        assertTrue(controller.contains("\"/api/formations/apply\","))
        assertTrue(controller.contains("\"owner\", \"shared-python-operation\""))
        assertTrue(ports.contains("fun tryAcquireNetworkOperation("))
        assertTrue(ports.contains("fun releaseNetworkOperation("))
        assertFalse(ports.contains("normalizedPath == \"/api/formations/apply\""))
        assertTrue(ports.contains("fun executeRawHttp("))
        assertFalse(ports.contains("fun executeGameCommand("))
        assertFalse(runner.contains("executeSharedCoreLockedGameCommand"))
        assertTrue(runner.contains("AccountOperationLockRegistry.isHeldByCurrentThread(accountId)"))
        assertFalse(service.contains("applyFormationsFromSharedCore"))
        assertFalse(service.contains("/api/formations/apply"))

        val saveUi = frontend
            .substringAfter("async function saveFormationSettings()")
            .substringBefore("async function saveRaidSettings()")
        assertTrue(saveUi.contains("const data = await apiPost(\"/api/formations/save\""))
        assertTrue(saveUi.contains("void waiter(operationId).then("))
        assertFalse(saveUi.contains("await waiter(operationId)"))
        assertTrue(saveUi.indexOf("showToast(\"\u4fdd\u5b58\u914d\u5175\u8bbe\u7f6e\u6210\u529f\"") > saveUi.indexOf("void waiter(operationId).then("))
    }

    @Test
    fun stateRefreshScopesArePlannedBySharedPythonAndAndroidOnlyExecutesParts() {
        val hostedCoreFactory = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )

        assertTrue(hostedCoreFactory.contains("/api/state/refresh"))
        assertTrue(hostedCoreFactory.contains("persisted_payload_builder=facade.state_refresh_operation_payload"))
        assertTrue(hostedCoreFactory.contains("facade._run_state_refresh_game_workflow"))
        assertTrue(hostedCoreFactory.contains("/api/heartbeat"))
        assertTrue(hostedCoreFactory.contains("facade._run_heartbeat_game_workflow"))
        assertTrue(hostedCoreFactory.contains("facade._run_military_intel_game_workflow"))
        assertTrue(hostedCoreFactory.contains("/api/daily/general-visit/candidates"))
        assertTrue(hostedCoreFactory.contains("facade._run_daily_general_visit_candidates_game_workflow"))
        assertTrue(hostedCoreFactory.contains("/api/raid/fiefs"))
        assertTrue(hostedCoreFactory.contains("host_response_projector=facade.raid_fiefs_operation_result"))
        assertTrue(hostedCoreFactory.contains("facade._run_raid_fiefs_game_workflow"))
        assertTrue(facade.contains("STATE_REFRESH_PARTS_BY_SCOPE"))
        assertTrue(facade.contains("def state_refresh_operation_payload("))
        assertTrue(facade.contains("def _run_state_refresh_game_workflow("))
        assertTrue(facade.contains("def _run_heartbeat_game_workflow("))
        assertTrue(facade.contains("def _run_military_intel_game_workflow("))
        assertTrue(facade.contains("def _run_daily_general_visit_candidates_game_workflow("))
        assertTrue(facade.contains("def raid_fiefs_operation_result("))
        assertTrue(facade.contains("def _run_raid_fiefs_game_workflow("))
        assertTrue(controller.contains("/api/military/intel"))
        assertTrue(controller.contains("/api/state/refresh"))
        assertTrue(controller.contains("/api/heartbeat"))
        assertTrue(controller.contains("body.put(\"scope\", query[\"scope\"]"))
        assertFalse(controller.contains("private fun stateRefresh("))
        assertFalse(ports.contains("normalizedPath == \"/api/state/refresh\""))
        assertFalse(ports.contains("normalizedPath == \"/api/heartbeat\""))
        assertFalse(ports.contains("normalizedPath == \"/api/daily/general-visit/candidates\""))
        assertFalse(ports.contains("normalizedPath == \"/api/raid/fiefs\""))

        assertFalse(service.contains("/api/state/refresh"))
        assertFalse(service.contains("/api/heartbeat"))
        assertFalse(service.contains("/api/military/intel"))
        assertFalse(service.contains("handleSharedCoreNetwork"))
        assertFalse(service.contains("runner.executeSharedCoreReadOnly("))
        assertFalse(service.contains("private fun stateRefresh"))
        assertFalse(service.contains("private fun heartbeat"))
        assertFalse(service.contains("private fun militaryIntel"))
        assertFalse(service.contains("private fun generalVisitCandidates"))
        assertFalse(service.contains("private fun generalVisitClaim"))
        assertFalse(service.contains("private fun raidFiefs"))
        assertFalse(service.contains("raidFiefsFact"))
    }

    @Test
    fun unassignAllUsesTheSharedRawCommandWorkflowAndKotlinHasNoRouteAdapter() {
        val hostedCoreFactory = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )

        assertTrue(hostedCoreFactory.contains("/api/formations/unassign-all"))
        assertTrue(hostedCoreFactory.contains("facade._run_unassign_all_game_workflow"))
        assertTrue(hostedCoreFactory.contains("persisted_payload_builder=facade.unassign_all_operation_payload"))
        assertTrue(hostedCoreFactory.contains("coalesce_active=True"))
        assertTrue(facade.contains("def unassign_all_operation_payload("))
        assertTrue(facade.contains("def _run_unassign_all_game_workflow("))
        assertTrue(facade.contains("self._run_troop_assign_game_workflow("))
        assertTrue(facade.contains("OperationKnownFailureError("))
        assertTrue(facade.contains("\"clearedCount\": cleared"))
        assertTrue(controller.contains("\"/api/formations/unassign-all\""))
        assertFalse(ports.contains("normalizedPath == \"/api/formations/unassign-all\""))
        assertTrue(ports.contains("fun executeRawHttp("))
        assertFalse(ports.contains("fun executeGameCommand("))

        val directRoutes = service
            .substringAfter("fun tryHandle(request: AssistantApiRequest)")
            .substringBefore("fun handleSharedCoreNetwork")
        assertFalse(directRoutes.contains("/api/formations/unassign-all"))
        assertFalse(service.contains("private fun unassignAllTroops"))
        assertFalse(service.contains("unassignAllFact"))
    }

    @Test
    fun troopAndManualInventoryMutationsUsePythonOwnedRawCommandWorkflows() {
        val hostedCoreFactory = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val formation = source(
            "../shared_core/python/dwpm_core/features/formation.py",
            "../../shared_core/python/dwpm_core/features/formation.py"
        )
        val inventory = source(
            "../shared_core/python/dwpm_core/features/inventory.py",
            "../../shared_core/python/dwpm_core/features/inventory.py"
        )
        val hostPorts = source(
            "../shared_core/python/dwpm_core/host_ports.py",
            "../../shared_core/python/dwpm_core/host_ports.py"
        )
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val runner = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationRunner.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )

        assertTrue(hostedCoreFactory.contains("/api/troops/assign"))
        assertTrue(hostedCoreFactory.contains("/api/troops/refill"))
        assertTrue(hostedCoreFactory.contains("/api/troops/heal"))
        assertTrue(hostedCoreFactory.contains("/api/inventory/open-one"))
        assertTrue(hostedCoreFactory.contains("register_host_game_command_route("))
        assertTrue(facade.contains("def troop_assign_operation_payload("))
        assertTrue(facade.contains("def troop_refill_operation_payload("))
        assertTrue(facade.contains("def troop_heal_operation_payload("))
        assertTrue(facade.contains("def inventory_open_one_operation_payload("))
        assertTrue(facade.contains("def _run_troop_assign_game_workflow("))
        assertTrue(facade.contains("def _run_troop_refill_game_workflow("))
        assertTrue(facade.contains("def _run_troop_heal_game_workflow("))
        assertTrue(facade.contains("def _run_inventory_open_one_game_workflow("))
        assertTrue(facade.contains("execution.mark_request_sent({"))
        assertTrue(formation.contains("def plan_troop_assignment("))
        assertTrue(formation.contains("def select_refill_generals("))
        assertTrue(formation.contains("def plan_heal_wounded("))
        assertTrue(inventory.contains("def plan_open_one_inventory("))
        assertTrue(inventory.contains("AUTO_OPEN_KEY_REQUIREMENTS"))
        assertTrue(hostPorts.contains("class HostedRawHttpPort"))
        assertTrue(hostPorts.contains("self._bridge.executeRawHttp("))
        assertTrue(facade.contains("request_body = make_packet("))
        assertTrue(facade.contains("packets = parse_response(raw)"))
        assertTrue(controller.contains("\"/api/troops/assign\""))
        assertTrue(controller.contains("\"/api/troops/refill\""))
        assertTrue(controller.contains("\"/api/troops/heal\""))
        assertTrue(controller.contains("\"/api/inventory/open-one\""))
        assertTrue(controller.contains("LocalSettingsConfigMapper.GENERAL"))
        assertTrue(ports.contains("fun executeRawHttp("))
        assertTrue(ports.contains("requireExecutionOwner"))
        assertFalse(ports.contains("fun executeGameCommand("))
        assertFalse(runner.contains("executeSharedCoreLockedGameCommand"))
        assertFalse(service.contains("fun executeSharedCoreGameCommand("))
        assertFalse(service.contains("gameCommandFact"))

        val directRoutes = service
            .substringAfter("fun tryHandle(request: AssistantApiRequest)")
            .substringBefore("fun handleSharedCoreNetwork")
        assertFalse(directRoutes.contains("/api/troops/assign"))
        assertFalse(directRoutes.contains("/api/troops/refill"))
        assertFalse(directRoutes.contains("/api/troops/heal"))
        assertFalse(directRoutes.contains("/api/inventory/open-one"))
        assertFalse(service.contains("private fun troopsAssign("))
        assertFalse(service.contains("private fun troopsRefill("))
        assertFalse(service.contains("private fun troopsHeal("))
        assertFalse(service.contains("private fun inventoryOpenOne("))
        assertFalse(service.contains("private fun formationAction("))
    }

    @Test
    fun brushSearchUsesPythonOwnedRawCommandsAndNormalizedMapStorage() {
        val hostedCoreFactory = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val hostPorts = source(
            "../shared_core/python/dwpm_core/host_ports.py",
            "../../shared_core/python/dwpm_core/host_ports.py"
        )
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )
        val bridge = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )

        assertTrue(hostedCoreFactory.contains("/api/brush/search"))
        assertTrue(hostedCoreFactory.contains("facade._run_cloud_coordinated_brush_search_game_workflow"))
        assertTrue(facade.contains("def brush_search_operation_payload("))
        assertTrue(facade.contains("def _run_cloud_coordinated_brush_search_game_workflow("))
        assertTrue(facade.contains("def _run_brush_search_game_workflow("))
        assertTrue(facade.contains("parse_bandit_targets(payload)"))
        assertTrue(facade.contains("target_matches_search_filter("))
        assertTrue(hostPorts.contains("class HostedMapSnapshotPort"))
        assertTrue(bridge.contains("fun saveMapSnapshot("))
        assertTrue(bridge.contains("fun invalidateMapTarget("))
        assertTrue(controller.contains("\"/api/brush/search\""))
        val directRoutes = service
            .substringAfter("fun tryHandle(request: AssistantApiRequest)")
            .substringBefore("fun handleSharedCoreNetwork")
        assertFalse(directRoutes.contains("/api/brush/search"))
        assertFalse(service.contains("private fun brushSearch("))
        assertFalse(service.contains("filterBrushTargets"))
    }

    @Test
    fun accountMetadataUsesSharedPythonWhileSecretsRemainInKeystore() {
        val repository = source(
            "app/src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt",
            "src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt"
        )
        val store = source(
            "../shared_core/python/dwpm_core/account/store.py",
            "../../shared_core/python/dwpm_core/account/store.py"
        )

        assertTrue(repository.contains("SharedPythonCoreHost.get(context)"))
        assertTrue(repository.contains("accountRecordsImportIfEmpty"))
        assertTrue(repository.contains("listPublicAccounts"))
        assertTrue(repository.contains("SessionSecretPolicy.publicFields"))
        assertTrue(store.contains("secrets\": \"platform-ports-only"))
        assertTrue(store.contains("sensitive field cannot enter account store"))
        assertFalse(store.contains("load_password("))

        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        assertTrue(controller.contains("GET\" to \"/api/accounts\" -> sharedCoreAccounts"))
        assertTrue(controller.contains("dispatchAccountProjection"))
        assertFalse(controller.contains("private fun accountArray()"))
    }

    @Test
    fun androidAccountAddKeepsTheSelectedGamePlatformForCloudDirectoryAndLogin() {
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val accountModel = source(
            "app/src/main/java/com/example/dwpmclone/domain/model/GameModels.kt",
            "src/main/java/com/example/dwpmclone/domain/model/GameModels.kt"
        )
        val repository = source(
            "app/src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt",
            "src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt"
        )

        assertTrue(controller.contains("JSONArray().put(\"sglm\").put(\"downjoy\")"))
        assertTrue(controller.contains("platformKey = record.getString(\"platformKey\")"))
        assertTrue(accountModel.contains("val platformKey: String = \"sglm\""))
        assertTrue(repository.contains(".put(\"platformKey\", platformKey)"))
        assertTrue(repository.contains(".put(\"serverQuery\", serverQuery)"))
    }

    @Test
    fun accountLoginAndBackgroundReloginUseOneSharedPythonWorkflow() {
        val loginCore = source(
            "../shared_core/python/dwpm_core/account/login.py",
            "../../shared_core/python/dwpm_core/account/login.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val bridge = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val host = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt",
            "src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
        )
        val recovery = source(
            "app/src/main/java/com/example/dwpmclone/data/account/AccountSessionRecovery.kt",
            "src/main/java/com/example/dwpmclone/data/account/AccountSessionRecovery.kt"
        )
        val realClient = source(
            "app/src/main/java/com/example/dwpmclone/data/protocol/RealGameProtocolClient.kt",
            "src/main/java/com/example/dwpmclone/data/protocol/RealGameProtocolClient.kt"
        )
        val legacyLogin = resolve(
            "app/src/main/java/com/example/dwpmclone/data/account/LocalAccountLoginService.kt",
            "src/main/java/com/example/dwpmclone/data/account/LocalAccountLoginService.kt"
        )

        assertTrue(loginCore.contains("def perform_shared_login("))
        assertTrue(loginCore.contains("0x1003"))
        assertTrue(loginCore.contains("parse_8003_login"))
        assertTrue(facade.contains("def register_account_login_routes("))
        assertTrue(facade.contains("def relogin_account("))
        assertTrue(facade.contains("def probe_account_session("))
        assertTrue(facade.contains("0x3110"))
        assertTrue(facade.contains("0x1016"))
        assertTrue(bridge.contains("fun executeRawHttp("))
        assertTrue(bridge.contains("\"/v1/servers/directory/sync\""))
        assertTrue(bridge.contains("\"/v1/servers/directory/query\""))
        assertTrue(bridge.contains("private val accounts by lazy"))
        assertTrue(bridge.contains("fun startAccountHosting("))
        assertTrue(bridge.contains("fun isAccountHosting("))
        assertTrue(bridge.contains("AssistantForegroundService.isExecutionOwnerActive()"))
        assertTrue(service.contains("reloginSource = sharedPythonCore"))
        assertTrue(service.contains("probe = sharedPythonCore"))
        assertTrue(host.contains("SessionHealthProbe"))
        assertTrue(host.contains("\"probe_account_session_json\""))
        assertFalse(recovery.contains("class RealSessionHealthProbe"))
        assertFalse(recovery.contains("State8004GeneralEvidenceParser"))
        assertFalse(service.contains("RealGameProtocolClient("))
        assertFalse(legacyLogin.exists())
        assertFalse(realClient.contains("loginAndFetchState"))
        assertFalse(realClient.contains("parse8003"))
        assertFalse(bridge.contains("executeAccountLifecycleOperation"))
    }

    @Test
    fun localViewsAndLegacySuccessRecognitionAreOwnedBySharedPython() {
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val localViews = source(
            "../shared_core/python/dwpm_core/local_views.py",
            "../../shared_core/python/dwpm_core/local_views.py"
        )
        val legacyPolicy = resolve(
            "app/src/main/java/com/example/dwpmclone/data/local/TaskSuccessRecordPolicy.kt",
            "src/main/java/com/example/dwpmclone/data/local/TaskSuccessRecordPolicy.kt"
        )
        val legacyMapMapper = resolve(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalMapApiMapper.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalMapApiMapper.kt"
        )
        val legacyBrushCenterPolicy = resolve(
            "app/src/main/java/com/example/dwpmclone/domain/protocol/BrushCenterRecommendationPolicy.kt",
            "src/main/java/com/example/dwpmclone/domain/protocol/BrushCenterRecommendationPolicy.kt"
        )

        assertTrue(controller.contains("dispatchSharedLocal"))
        assertTrue(controller.contains("rawLogJson"))
        assertTrue(controller.contains("\"/api/logs/system\""))
        assertTrue(controller.contains("\"/api/logs/account\""))
        assertTrue(controller.contains("\"/api/automation/status\""))
        assertTrue(controller.contains("\"/api/success-records\""))
        assertTrue(controller.contains("\"/api/maps/bandits\""))
        assertTrue(controller.contains("\"/api/maps/mines\""))
        assertTrue(controller.contains("\"/api/brush/recommended-center\" -> brushRecommendedCenter"))
        assertTrue(controller.contains("rawLocalMapJson"))
        assertFalse(controller.contains("private fun logJson("))
        assertFalse(controller.contains("TaskSuccessRecordPolicy"))
        assertFalse(legacyPolicy.exists())
        assertFalse(legacyMapMapper.exists())
        assertFalse(legacyBrushCenterPolicy.exists())
        assertTrue(localViews.contains("def project_system_logs("))
        assertTrue(localViews.contains("def project_success_records("))
        assertTrue(localViews.contains("def _legacy_success_record("))
        assertTrue(localViews.contains("def project_bandit_map("))
        assertTrue(localViews.contains("def project_mine_map("))
        assertTrue(localViews.contains("def recommend_brush_center("))
    }

    @Test
    fun militaryAlarmDecisionsAreSharedAndAndroidOnlyDisplaysTheEvent() {
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val alarm = source(
            "../shared_core/python/dwpm_core/features/alarm.py",
            "../../shared_core/python/dwpm_core/features/alarm.py"
        )
        val bridge = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val service = source(
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
        )
        val legacyDetector = resolve(
            "app/src/main/java/com/example/dwpmclone/domain/alarm/MilitaryAlarmEventDetector.kt",
            "src/main/java/com/example/dwpmclone/domain/alarm/MilitaryAlarmEventDetector.kt"
        )

        assertTrue(alarm.contains("def plan_alarm_observation("))
        assertTrue(alarm.contains("def plan_error_alarm("))
        assertTrue(facade.contains("alarmPendingEventsJson"))
        assertTrue(facade.contains("self._ports.notifications.notify(event)"))
        assertTrue(bridge.contains("event.optBoolean(\"showNotification\", false)"))
        assertTrue(bridge.contains("event.optBoolean(\"vibrate\", false)"))
        assertTrue(bridge.contains("manager.notify(fingerprint.hashCode(), notification)"))
        assertTrue(service.contains("sharedPythonCore.emitHostAlarmError("))
        assertFalse(service.contains("isErrorAlarmEnabled"))
        assertFalse(legacyDetector.exists())
    }

    private fun source(vararg candidates: String): String {
        val file = candidates.asSequence().map(::File).firstOrNull(File::isFile)
        checkNotNull(file) { "Source not found: ${candidates.joinToString()}" }
        return file.readText()
    }

    private fun resolve(vararg candidates: String): File =
        candidates.asSequence().map(::File).firstOrNull(File::exists) ?: File(candidates.first())
}

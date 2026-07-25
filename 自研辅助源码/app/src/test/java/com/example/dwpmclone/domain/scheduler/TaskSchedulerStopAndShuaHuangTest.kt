package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.state.GateResult
import com.example.dwpmclone.domain.state.RuntimeGeneralState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskSchedulerStopAndShuaHuangTest {
    @Test
    fun inventoryCleanupUsesOnlyAvailableKeysAndNeverTouchesUnknownEquipment() {
        val protocol = RecordingProtocol().apply {
            inventory = listOf(
                InventoryItem(58, "青铜宝箱", "box", null, null, false, false, count = 2),
                InventoryItem(59, "青铜钥匙", "item", null, null, false, false, count = 1),
                InventoryItem(9001, "未知装备", "equipment", EquipmentQuality.NORMAL, 1, false, false)
            )
        }
        val task = InventoryCleanupMockTask(
            accountId = 123L,
            config = InventoryConfig(
                enabled = true,
                openBoxes = true,
                openSilverTickets = false,
                discardEquipmentQualities = setOf(EquipmentQuality.NORMAL),
                discardBelowLevel = 10,
                discardItems = emptySet()
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        SuspendRunner.run { task.prepare(ctx) }
        SuspendRunner.run { task.step(ctx) }

        assertEquals(listOf(Triple(58L, InventoryAction.OPEN, 1)), protocol.inventoryActions)
    }

    @Test
    fun duplicateTaskTypeForSameAccountRunsOnlyOncePerBatch() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)
        val first = RecordingTask(session.accountId)
        val duplicate = RecordingTask(session.accountId)

        val reports = SuspendRunner.run {
            scheduler.runOnce(session, listOf(first, duplicate), nowMillis = 1_000L)
        }

        assertEquals(1, reports.size)
        assertEquals(1, first.prepareCount)
        assertEquals(1, first.stepCount)
        assertEquals(0, duplicate.prepareCount)
        assertEquals(0, duplicate.stepCount)
    }

    @Test
    fun stopAllStopsTasksAndLogsOutSession() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = RecordingTask(accountId = 123L)
        val session = GameSession(
            accountId = 123L,
            tokenCiphertext = "unit-token",
            expiresAtMillis = null,
            channelExtra = emptyMap(),
            sourceMode = 0
        )

        val report = SuspendRunner.run { scheduler.stopAll(session, listOf(task), "unit stop") }

        assertEquals(123L, report.accountId)
        assertEquals(listOf(TaskType.SHUA_HUANG), report.stoppedTaskTypes)
        assertTrue(report.logoutRequested)
        assertTrue(report.logoutSucceeded)
        assertEquals("unit stop", task.stoppedReason)
        assertEquals(listOf("logout"), protocol.calls)
    }


    @Test
    fun stopAllWithShuaHuangTaskLogsOutExactlyOnce() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        val report = SuspendRunner.run { scheduler.stopAll(session, listOf(task), "unit shua stop") }

        assertTrue(report.logoutRequested)
        assertTrue(report.logoutSucceeded)
        assertEquals(1, protocol.calls.count { it == "logout" })
    }

    @Test
    fun runOnceStopsOnlyCurrentTaskWhenTaskReturnsStop() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 1,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, mapOf("shuaHuangUsedCount" to "1"), 0)

        val report = SuspendRunner.run {
            scheduler.runOnceAndStopOnTerminal(session, listOf(task), nowMillis = 1_000L, reasonPrefix = "unit lifecycle")
        }

        assertEquals(1, report.runReports.size)
        assertEquals(TaskDecision.Continue, report.runReports.single().decisions.first())
        assertTrue(report.runReports.single().decisions.last() is TaskDecision.Sleep)
        assertEquals(0, report.terminalDecisions.size)
        assertEquals(0, report.localStopReports.size)
        assertTrue(!report.logoutRequested)
        assertEquals(null, report.stopReport)
        assertEquals(listOf("validateSession"), protocol.calls)
    }

    @Test
    fun runOnceAndStopOnTerminalDoesNotLogoutForSleepDecision() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        val report = SuspendRunner.run {
            scheduler.runOnceAndStopOnTerminal(session, listOf(task), nowMillis = 1_000L, reasonPrefix = "unit lifecycle")
        }

        assertEquals(1, report.runReports.size)
        assertEquals(emptyList<TerminalTaskDecision>(), report.terminalDecisions)
        assertEquals(null, report.stopReport)
        assertEquals(false, report.logoutRequested)
        assertTrue("logout" !in protocol.calls)
    }

    @Test
    fun needReloginStillStopsAllTasksAndLogsOutAccount() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)
        val task = object : AssistantTask<Unit> {
            override val accountId: Long = 123L
            override val type: TaskType = TaskType.DAILY
            override val config: Unit = Unit
            override suspend fun prepare(ctx: TaskContext): TaskDecision =
                TaskDecision.NeedRelogin("session expired")
            override suspend fun step(ctx: TaskContext): TaskDecision = TaskDecision.Continue
            override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision =
                TaskDecision.NeedRelogin(error.message ?: "error")
            override suspend fun stop(ctx: TaskContext, reason: String) = Unit
        }

        val report = SuspendRunner.run {
            scheduler.runOnceAndStopOnTerminal(session, listOf(task), nowMillis = 1_000L)
        }

        assertEquals(1, report.terminalDecisions.size)
        assertTrue(report.logoutRequested)
        assertTrue(report.stopReport!!.logoutSucceeded)
        assertEquals(listOf("logout"), protocol.calls)
    }

    @Test
    fun localSchedulerLifecycleRunnerKeepsAccountOnlineForTaskLocalStop() {
        val protocol = RecordingProtocol()
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 1,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val plan = SavedTaskPlan(
            session = GameSession(123L, "unit-token", null, mapOf("shuaHuangUsedCount" to "1"), 0),
            tasks = listOf(task),
            sourceDescription = "unit-service-entry"
        )

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 9, plans = listOf(plan), nowMillis = 1_000L)
        }

        assertEquals(9, batch.tick)
        assertEquals(1, batch.accounts.size)
        assertEquals(1, batch.runReports.size)
        assertEquals(TaskDecision.Continue, batch.runReports.single().decisions.first())
        assertTrue(batch.runReports.single().decisions.last() is TaskDecision.Sleep)
        assertEquals(0, batch.terminalDecisions.size)
        assertEquals(0, batch.stopReports.size)
        assertEquals(0, batch.localStopReports.size)
        assertEquals(listOf("validateSession"), protocol.calls)
    }

    @Test
    fun localSchedulerLifecycleRunnerDoesNotLogoutNonTerminalServiceTick() {
        val protocol = RecordingProtocol()
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val plan = SavedTaskPlan(
            session = GameSession(123L, "unit-token", null, emptyMap(), 0),
            tasks = listOf(task),
            sourceDescription = "unit-service-entry"
        )

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 10, plans = listOf(plan), nowMillis = 1_000L)
        }

        assertEquals(1, batch.runReports.size)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), batch.runReports.single().decisions)
        assertEquals(emptyList<TerminalTaskDecision>(), batch.terminalDecisions)
        assertEquals(emptyList<TaskStopReport>(), batch.stopReports)
        assertTrue("logout" !in protocol.calls)
    }

    @Test
    fun realSessionFormationUpdateWithoutConfirmationStopsBeforeBrushYellowDispatch() {
        val protocol = RecordingProtocol().apply {
            updateFormationResult = ProtocolResult.Err(
                code = "REAL_UPDATE_FORMATION_NOT_IMPLEMENTED",
                message = "真实配兵/编队协议尚未接入",
                retryable = false
            )
        }
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))
        val formationTask = FormationUpdateMockTask(
            accountId = 123L,
            config = FormationConfig(
                formationId = 7L,
                generalIds = listOf(1L),
                autoAssignTroops = true,
                troopType = "轻骑兵",
                troopCount = 200,
                fillToMaxWhenAutoAssignDisabled = false
            )
        )
        val shuaTask = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val plan = SavedTaskPlan(
            session = GameSession(123L, "real-token", null, mapOf("userId" to "u", "serverUrl" to "http://game.example"), 1),
            tasks = listOf(formationTask, shuaTask),
            sourceDescription = "unit-real-session"
        )

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 13, plans = listOf(plan), nowMillis = 1_000L)
        }

        assertEquals(2, batch.runReports.size)
        assertEquals(TaskType.FORMATION, batch.runReports[0].type)
        assertEquals(
            listOf(TaskDecision.Continue, TaskDecision.Stop("真实配兵/编队协议尚未接入")),
            batch.runReports[0].decisions
        )
        assertEquals(TaskType.SHUA_HUANG, batch.runReports[1].type)
        assertTrue(
            (batch.runReports[1].decisions.single() as TaskDecision.Stop).reason
                .contains("formation prerequisite")
        )
        assertEquals(0, batch.terminalDecisions.size)
        assertTrue("dispatchFormation" !in protocol.calls)
        assertTrue("logout" !in protocol.calls)
    }

    @Test
    fun shuaHuangTaskRunsMinimumClosedLoopBeforeDispatch() {
        val protocol = RecordingProtocol()
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 1,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(
            session = GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol = protocol,
            nowMillis = 1_000L
        )

        val prepare = SuspendRunner.run { task.prepare(ctx) }
        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Continue, prepare)
        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(
            listOf(
                "validateSession",
                "queryMonarch",
                "queryResourceState",
                "queryGenerals",
                "queryFormations",
                "searchMap",
                "dispatchFormation"
            ),
            protocol.calls
        )
        assertEquals(7L, protocol.lastDispatchFormationId)
        assertEquals(88L, protocol.lastDispatchTargetId)
    }

    @Test
    fun shuaHuangTaskWaitsUntilConfiguredLocalStartHourBeforeAnyGameRequest() {
        val protocol = RecordingProtocol()
        val now = java.util.Calendar.getInstance().apply {
            set(2026, java.util.Calendar.JULY, 12, 10, 0, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }.timeInMillis
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ConfigDefaults.shuaHuang().copy(
                enabled = true,
                startHour = 18,
                selectedFormationIds = setOf(7L)
            )
        )
        val ctx = TaskContext(
            GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol,
            now
        )

        val decision = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(8 * 60 * 60 * 1000L), decision)
        assertTrue(protocol.calls.isEmpty())
    }

    @Test
    fun shuaHuangDailyLimitKeepsResidentUntilNextDayConfiguredHour() {
        val protocol = RecordingProtocol()
        val now = java.util.Calendar.getInstance().apply {
            set(2026, java.util.Calendar.JULY, 12, 20, 0, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }.timeInMillis
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ConfigDefaults.shuaHuang().copy(
                enabled = true,
                dailyLimit = 2,
                startHour = 18,
                selectedFormationIds = setOf(7L)
            )
        )
        val ctx = TaskContext(
            GameSession(
                123L,
                "unit-token",
                null,
                mapOf("shuaHuangUsedCount" to "2"),
                0
            ),
            protocol,
            now
        )

        val decision = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(22 * 60 * 60 * 1000L), decision)
        assertTrue(protocol.calls.isEmpty())
    }

    @Test
    fun shuaHuangBatchRefillRunsAfterTargetSelectionAndBeforeDispatch() {
        val protocol = RecordingProtocol()
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ConfigDefaults.shuaHuang().copy(
                enabled = true,
                selectedFormationIds = setOf(7L),
                targetType = HuangTargetType.HUANG_JIN,
                replenishTroops = true
            )
        )
        val ctx = TaskContext(
            GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol,
            1_000L
        )

        val decision = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000L), decision)
        assertTrue(protocol.calls.indexOf("searchMap") < protocol.calls.indexOf("updateFormation"))
        assertTrue(protocol.calls.indexOf("updateFormation") < protocol.calls.indexOf("dispatchFormation"))
        assertEquals(1, protocol.calls.count { it == "updateFormation" })
        assertEquals(1, protocol.calls.count { it == "dispatchFormation" })
    }

    @Test
    fun shuaHuangBatchRefillFailureBlocksDispatch() {
        val protocol = RecordingProtocol().apply {
            updateFormationResult = ProtocolResult.Ok(
                StepResult(false, "0x8229未返回全部将领")
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ConfigDefaults.shuaHuang().copy(
                enabled = true,
                selectedFormationIds = setOf(7L),
                targetType = HuangTargetType.HUANG_JIN,
                replenishTroops = true
            )
        )
        val ctx = TaskContext(
            GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol,
            1_000L
        )

        val decision = SuspendRunner.run { task.step(ctx) }

        assertEquals(
            TaskDecision.Stop("刷黄出征前批量补满失败：0x8229未返回全部将领"),
            decision
        )
        assertEquals(1, protocol.calls.count { it == "updateFormation" })
        assertTrue("dispatchFormation" !in protocol.calls)
    }


    @Test
    fun shuaHuangTaskRunsDeleteMailForSpeedOnceBeforeDispatch() {
        val protocol = RecordingProtocol()
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 2,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = true,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val first = SuspendRunner.run { task.step(ctx) }
        val second = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), first)
        assertTrue(second is TaskDecision.Sleep)
        assertTrue((second as TaskDecision.Sleep).millis > 1_000L)
        assertEquals(1, protocol.calls.count { it == "runDailyStep:DELETE_MAIL" })
        assertTrue(protocol.calls.indexOf("runDailyStep:DELETE_MAIL") < protocol.calls.indexOf("queryGenerals"))
        assertEquals(2, protocol.calls.count { it == "dispatchFormation" })
    }

    @Test
    fun shuaHuangTaskStopsWhenDeleteMailForSpeedFails() {
        val protocol = RecordingProtocol().apply {
            dailyStepResults[DailyStep.DELETE_MAIL] = StepResult(false, "删信失败")
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = true,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Stop("delete mail before shua huang failed: 删信失败"), step)
        assertTrue("queryGenerals" !in protocol.calls)
        assertTrue("dispatchFormation" !in protocol.calls)
    }

    @Test
    fun shuaHuangTaskChoosesFormationByConfiguredOrderAndNearestMatchingTarget() {
        val protocol = RecordingProtocol().apply {
            formations = listOf(
                FormationRuntime(8L, "not selected first", listOf(2L), FormationRuntimeStatus.IDLE, 1999),
                FormationRuntime(7L, "selected second", listOf(1L), FormationRuntimeStatus.IDLE, 1999)
            )
            generals = listOf(
                General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100, status = 0),
                General(id = 2L, name = "马超", growth = 90, loyalty = 100, energy = 100, status = 0)
            )
            mapTargets = listOf(
                MapTarget(201L, MapCoordinate(100, 100), "山贼", raw = mapOf("rank" to "1")),
                MapTarget(202L, MapCoordinate(12, 23), "黄巾", raw = mapOf("rank" to "9")),
                MapTarget(203L, MapCoordinate(30, 30), "黄巾", raw = mapOf("rank" to "1"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(7L, 8L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(7L, protocol.lastDispatchFormationId)
        assertEquals(202L, protocol.lastDispatchTargetId)
    }


    @Test
    fun shuaHuangTaskSkipsZeroTroopFormation() {
        val protocol = RecordingProtocol().apply {
            formations = listOf(
                FormationRuntime(7L, "empty troops", listOf(1L), FormationRuntimeStatus.IDLE, 0),
                FormationRuntime(8L, "ready troops", listOf(2L), FormationRuntimeStatus.IDLE, 1999)
            )
            generals = listOf(
                General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100, status = 0),
                General(id = 2L, name = "马超", growth = 90, loyalty = 100, energy = 100, status = 0)
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(7L, 8L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(8L, protocol.lastDispatchFormationId)
    }

    @Test
    fun shuaHuangTaskSkipsFormationWhenGeneralPeiBingFailed() {
        val protocol = RecordingProtocol().apply {
            formations = listOf(
                FormationRuntime(7L, "pei bing failed", listOf(1L), FormationRuntimeStatus.IDLE, 1999),
                FormationRuntime(8L, "ready", listOf(2L), FormationRuntimeStatus.IDLE, 1999)
            )
            generals = listOf(
                General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100, status = 0, isPeiBingFail = true),
                General(id = 2L, name = "马超", growth = 90, loyalty = 100, energy = 100, status = 0, isPeiBingFail = false)
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(7L, 8L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(8L, protocol.lastDispatchFormationId)
    }



    @Test
    fun shuaHuangTaskTreatsRecoveredCommanderMarkersAsHuangJinTargets() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                MapTarget(601L, MapCoordinate(11, 22), "渠帅", raw = mapOf("rank" to "11")),
                MapTarget(602L, MapCoordinate(12, 22), "主将", raw = mapOf("rank" to "12"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(601L, protocol.lastDispatchTargetId)
    }

    @Test
    fun shuaHuangTaskDoesNotTreatCommanderMarkersAsShanZeiTargets() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                MapTarget(701L, MapCoordinate(11, 22), "主将", raw = mapOf("rank" to "12"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.SHAN_ZEI,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(30_000), step)
        assertTrue("dispatchFormation" !in protocol.calls)
    }

    @Test
    fun shuaHuangTaskDoesNotDispatchWhenNoTargetMatchesConfiguredType() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                MapTarget(401L, MapCoordinate(11, 22), "山贼", raw = mapOf("level" to "1")),
                MapTarget(402L, MapCoordinate(12, 22), "SHAN_ZEI", raw = mapOf("level" to "2"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(30_000), step)
        assertTrue("dispatchFormation" !in protocol.calls)
    }

    @Test
    fun shuaHuangTaskDoesNotFallbackToWrongTypeWhenConfiguredTypeFailsFilter() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                MapTarget(501L, MapCoordinate(11, 22), "黄巾", raw = mapOf("level" to "9")),
                MapTarget(502L, MapCoordinate(11, 22), "山贼", raw = mapOf("level" to "1"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false,
                targetFilter = ShuaHuangTargetFilter(maxLevel = 1)
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(30_000), step)
        assertTrue("dispatchFormation" !in protocol.calls)
    }

    @Test
    fun shuaHuangTaskAppliesUnifiedTargetFilterBeforeDispatch() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                MapTarget(202L, MapCoordinate(12, 23), "黄巾", raw = mapOf("level" to "9")),
                MapTarget(203L, MapCoordinate(30, 30), "黄巾", raw = mapOf("level" to "1")),
                MapTarget(204L, MapCoordinate(11, 22), "山贼", raw = mapOf("level" to "1"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false,
                targetFilter = ShuaHuangTargetFilter(maxLevel = 1)
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(7L, protocol.lastDispatchFormationId)
        assertEquals(203L, protocol.lastDispatchTargetId)
    }

    @Test
    fun shuaHuangTaskAppliesCompositionCode5203BeforeDispatch() {
        val protocol = RecordingProtocol().apply {
            mapTargets = listOf(
                // 更近但骑军统领数=1，应该被 5203 的 骑<=0 拦掉。
                MapTarget(401L, MapCoordinate(11, 22), "山贼", raw = mapOf("level" to "1", "compositionCode" to "5213")),
                MapTarget(402L, MapCoordinate(30, 30), "山贼", raw = mapOf("level" to "1", "compositionCode" to "5203"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.SHAN_ZEI,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false,
                targetFilter = ShuaHuangTargetFilter(
                    minLevel = 1,
                    maxLevel = 1,
                    maxFoot = 5,
                    maxBow = 2,
                    maxCavalry = 0,
                    maxChariot = 3
                )
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(7L, protocol.lastDispatchFormationId)
        assertEquals(402L, protocol.lastDispatchTargetId)
    }

    @Test
    fun shuaHuangTaskSupportsPerFormationTargetFilters() {
        val protocol = RecordingProtocol().apply {
            formations = listOf(
                FormationRuntime(7L, "low-level filter", listOf(1L), FormationRuntimeStatus.IDLE, 1999),
                FormationRuntime(8L, "high-level filter", listOf(2L), FormationRuntimeStatus.IDLE, 1999)
            )
            generals = listOf(
                General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100, status = 0),
                General(id = 2L, name = "马超", growth = 90, loyalty = 100, energy = 100, status = 0)
            )
            mapTargets = listOf(
                MapTarget(301L, MapCoordinate(13, 24), "黄巾", raw = mapOf("level" to "5", "drop" to "令牌"))
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(7L, 8L),
                formationFilterMode = FormationFilterMode.PER_FORMATION,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false,
                perFormationTargetFilters = mapOf(
                    7L to ShuaHuangTargetFilter(maxLevel = 1),
                    8L to ShuaHuangTargetFilter(minLevel = 5, requiredKeywords = setOf("令牌"))
                )
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), step)
        assertEquals(8L, protocol.lastDispatchFormationId)
        assertEquals(301L, protocol.lastDispatchTargetId)
    }


    @Test
    fun shuaHuangTaskStopsWhenDispatchResultIsFailure() {
        val protocol = RecordingProtocol().apply {
            dispatchResult = BattleResult(
                success = false,
                consumedTimes = 0,
                raw = mapOf("responseText" to "体力不足，无法出征")
            )
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Stop("shua huang dispatch failed: 体力不足，无法出征"), step)
        assertEquals(7L, protocol.lastDispatchFormationId)
        assertEquals(88L, protocol.lastDispatchTargetId)
    }

    @Test
    fun shuaHuangTaskAccumulatesLocalConsumedTimesAcrossSteps() {
        val protocol = RecordingProtocol().apply {
            dispatchResult = BattleResult(success = true, consumedTimes = 1)
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 2,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val first = SuspendRunner.run { task.step(ctx) }
        val second = SuspendRunner.run { task.step(ctx) }
        val third = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Sleep(1_000), first)
        assertTrue(second is TaskDecision.Sleep)
        assertTrue(third is TaskDecision.Sleep)
        assertEquals(2, protocol.calls.count { it == "dispatchFormation" })
    }


    @Test
    fun shuaHuangTaskAddsPersistedUsedCountAndLocalConsumedTimes() {
        val protocol = RecordingProtocol().apply {
            dispatchResult = BattleResult(success = true, consumedTimes = 1)
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 2,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(
            GameSession(123L, "unit-token", null, mapOf("shuaHuangUsedCount" to "1"), 0),
            protocol,
            1_000L
        )

        val first = SuspendRunner.run { task.step(ctx) }
        val second = SuspendRunner.run { task.step(ctx) }

        assertTrue(first is TaskDecision.Sleep)
        assertTrue(second is TaskDecision.Sleep)
        assertEquals(1, protocol.calls.count { it == "dispatchFormation" })
    }

    @Test
    fun shuaHuangTaskStopsWhenDailyLimitReachedFromSessionMetadata() {
        val protocol = RecordingProtocol()
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 2,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val ctx = TaskContext(
            GameSession(123L, "unit-token", null, mapOf("shuaHuangUsedCount" to "2"), 0),
            protocol,
            1_000L
        )

        val step = SuspendRunner.run { task.step(ctx) }

        assertTrue(step is TaskDecision.Sleep)
        assertTrue((step as TaskDecision.Sleep).millis >= 60_000L)
        assertEquals(emptyList<String>(), protocol.calls)
    }

    @Test
    fun shuaHuangTaskStopsWhenFoodConversionStillCannotMeetCopperReserve() {
        val protocol = RecordingProtocol().apply {
            resources = ResourceState(copper = 5_000L, food = 50_000L)
            convertedResources = ResourceState(copper = 8_000L, food = 20_000L)
        }
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 1,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = true
            )
        )
        val ctx = TaskContext(GameSession(123L, "unit-token", null, emptyMap(), 0), protocol, 1_000L)

        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(
            TaskDecision.Stop("copper still below configured reserve after food conversion: 8000 < 10000"),
            step
        )
        assertEquals(
            listOf("queryMonarch", "queryResourceState", "convertFoodToCopper:FOOD_TO_COPPER_THRESHOLD"),
            protocol.calls
        )
    }

    @Test
    fun realSessionMetadataDrivesOfflineShuaHuangClosedLoopThroughStopLogout() {
        val protocol = SessionAwareGameProtocolClient()
        val events = mutableListOf<String>()
        val scheduler = TaskScheduler(protocol, AutomationRuntimeStateStore(eventSink = events::add))
        val task = ShuaHuangTask(
            accountId = 10001L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 1,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(3L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            sourceMode = 1,
            channelExtra = mapOf(
                "userId" to "u10001",
                "serverUrl" to "http://game.example",
                "dm" to "999",
                "roleName" to "测试君主",
                "level" to "42",
                "nation" to "蜀",
                "copper" to "123456",
                "food" to "654321",
                "state8004TailUtf8Preview" to "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}",
                "xiaohuangPrefsJson" to """{
                    "shuahuangChuzhengBiandui0": true,
                    "bianduihao0": "0000000000000003",
                    "bianduiDejiangling0": "0000000000000007",
                    "bingli0": "1999"
                }""",
                "mapTargetsHex" to "000000000065030005000b0016E9BB84E5B7BE",
                "dispatchResultsJson" to """[
                    {
                      "formationId":3,
                      "targetId":"101",
                      "responseText":"刷黄出征成功！继续搜索... usedAount=1",
                      "targetIdHex":"0000000000000065",
                      "generalIdHexChunks":["0000000000000007"]
                    }
                ]"""
            )
        )

        val reports = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val stop = SuspendRunner.run { scheduler.stopAll(session, listOf(task), "offline closed loop stop") }

        assertEquals(1, reports.size)
        assertEquals(TaskType.SHUA_HUANG, reports.single().type)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), reports.single().decisions)
        assertEquals(null, reports.single().error)
        assertTrue(events.any { it.contains("dispatch-dry-run evidence=2026-07-08 bridge100 flows #30/#31/#32 and #38/#39") })
        assertTrue(events.any { it.contains("networkAllowed=false") && it.contains("1229=000000000000000000091229000001") })
        assertTrue(stop.logoutRequested)
        assertTrue(stop.logoutSucceeded)
        assertEquals("real read-only session marked logged out locally", stop.logoutMessage)
    }

    @Test
    fun fullChannelExtraSampleDrivesKotlinSchedulerAndSessionAwareProtocolClosedLoop() {
        val protocol = RecordingDelegatingProtocol(SessionAwareGameProtocolClient())
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 10001L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 1,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = linkedSetOf(3L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val extra = fullOfflineReplayChannelExtraSample()
        val session = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = extra,
            sourceMode = 1
        )

        val reports = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val stop = SuspendRunner.run { scheduler.stopAll(session, listOf(task), "full sample stop") }

        assertEquals("1", extra["sourceMode"])
        assertTrue(
            extra.filterKeys { it.endsWith("NetworkSendAllowed") || it == "networkSendAllowed" }
                .all { (_, value) -> value == "false" }
        )
        assertEquals(1, reports.size)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), reports.single().decisions)
        assertEquals(null, reports.single().error)
        assertEquals(3L, protocol.lastDispatchFormationId)
        assertEquals(101L, protocol.lastDispatchTargetId)
        assertEquals(
            listOf(
                "validateSession",
                "queryMonarch",
                "queryResourceState",
                "queryGenerals",
                "queryFormations",
                "searchMap",
                "dispatchFormation",
                "logout"
            ),
            protocol.calls
        )
        assertTrue(stop.logoutRequested)
        assertTrue(stop.logoutSucceeded)
        assertEquals("real read-only session marked logged out locally", stop.logoutMessage)
    }

    @Test
    fun dailyPipelineUsesRecoveredExecutionOrder() {
        val protocol = RecordingProtocol()
        val task = DailyPipelineTask(
            accountId = 123L,
            config = DailyConfig(
                enabledSteps = linkedSetOf(
                    DailyStep.DONATE_TECH,
                    DailyStep.SURPRISE_BOX,
                    DailyStep.SIGN_IN,
                    DailyStep.DONATE_COPPER,
                    DailyStep.ADD_LOYALTY
                ),
                vibrateOnAlarm = false,
                stopOnStepFailure = false
            )
        )
        val ctx = TaskContext(
            session = GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol = protocol,
            nowMillis = 1_000L
        )

        val prepare = SuspendRunner.run { task.prepare(ctx) }
        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Continue, prepare)
        assertEquals(TaskDecision.Sleep(24 * 60 * 60 * 1000L), step)
        assertEquals(
            listOf(
                "validateSession",
                "runDailyStep:SIGN_IN",
                "runDailyStep:SURPRISE_BOX",
                "runDailyStep:ADD_LOYALTY",
                "runDailyStep:DONATE_COPPER",
                "runDailyStep:DONATE_TECH"
            ),
            protocol.calls
        )
    }

    @Test
    fun dailyPipelineRoutesConvertHalfFoodToCopperThroughResourceConversion() {
        val protocol = RecordingProtocol()
        val task = DailyPipelineTask(
            accountId = 123L,
            config = DailyConfig(
                enabledSteps = linkedSetOf(
                    DailyStep.DONATE_TECH,
                    DailyStep.CONVERT_HALF_FOOD_TO_COPPER
                ),
                vibrateOnAlarm = false,
                stopOnStepFailure = false
            )
        )
        val ctx = TaskContext(
            session = GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol = protocol,
            nowMillis = 1_000L
        )

        val prepare = SuspendRunner.run { task.prepare(ctx) }
        val step = SuspendRunner.run { task.step(ctx) }

        assertEquals(TaskDecision.Continue, prepare)
        assertEquals(TaskDecision.Sleep(24 * 60 * 60 * 1000L), step)
        assertEquals(
            listOf(
                "validateSession",
                "runDailyStep:DONATE_TECH",
                "convertFoodToCopper:FOOD_TO_COPPER_HALF"
            ),
            protocol.calls
        )
    }

    @Test
    fun dailyPipelineStopsDuringPrepareWhenUnrecoveredStepSelected() {
        val protocol = RecordingProtocol()
        val task = DailyPipelineTask(
            accountId = 123L,
            config = DailyConfig(
                enabledSteps = linkedSetOf(DailyStep.SIGN_IN, DailyStep.LEVEL_GIFT),
                vibrateOnAlarm = false,
                stopOnStepFailure = false
            )
        )
        val ctx = TaskContext(
            session = GameSession(123L, "unit-token", null, emptyMap(), 0),
            protocol = protocol,
            nowMillis = 1_000L
        )

        val prepare = SuspendRunner.run { task.prepare(ctx) }

        assertEquals(TaskDecision.Stop("unrecovered daily steps selected: LEVEL_GIFT"), prepare)
        assertEquals(emptyList<String>(), protocol.calls)
    }

    @Test
    fun schedulerBlocksSecondBrushYellowDispatchWhileGeneralLeaseBusy() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        val first = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val second = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 2_000L) }

        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), first.single().decisions)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(30_000)), second.single().decisions)
        assertEquals(1, protocol.calls.count { it == "dispatchFormation" })
        val lease = scheduler.runtime.snapshotGeneralLeases(123L, 2_000L).single()
        assertEquals(1L, lease.generalId)
        assertEquals(TaskType.SHUA_HUANG, lease.owner)
        assertEquals(RuntimeGeneralState.MARCHING, lease.state)
    }




    @Test
    fun schedulerDoesNotReleaseBusyGeneralFromRecoveredStaticStateEvidence() {
        val protocol = RecordingProtocol().apply {
            generals = listOf(
                General(
                    id = 1L,
                    name = "赵云",
                    growth = 90,
                    loyalty = 100,
                    energy = 100,
                    status = 0,
                    raw = mapOf("source" to "recovered-jiangling")
                )
            )
            formations = listOf(
                FormationRuntime(
                    id = 7L,
                    name = "测试编队",
                    generalIds = listOf(1L),
                    status = FormationRuntimeStatus.IDLE,
                    troopCount = 1999,
                    raw = mapOf("source" to "recovered-shuahuang-shared-prefs")
                )
            )
        }
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        val first = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val secondWithOnlyStaticEvidence = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 12_000L) }

        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), first.single().decisions)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(30_000)), secondWithOnlyStaticEvidence.single().decisions)
        assertEquals(1, protocol.calls.count { it == "dispatchFormation" })
    }

    @Test
    fun stateMachineEventsDescribeBrushYellowLeaseLifecycle() {
        val protocol = RecordingProtocol()
        val events = mutableListOf<String>()
        val scheduler = TaskScheduler(protocol, AutomationRuntimeStateStore(eventSink = events::add))
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 2_000L) }
        SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 12_000L) }

        assertTrue(events.any { it.contains("account=123 state LOGGED_OUT -> RUNNING") })
        assertTrue(events.any { it.contains("brush-yellow step-start") })
        assertTrue(events.any { it.contains("brush-yellow resource copper=") })
        assertTrue(events.any { it.contains("brush-yellow selected formation=7 target=88") })
        assertTrue(events.any { it.contains("brush-yellow dispatch-success formation=7 target=88") })
        assertTrue(events.any { it.contains("reserve formation=7 generals=1") })
        assertTrue(events.any { it.contains("dispatch-sending formation=7 generals=1") })
        assertTrue(events.any { it.contains("dispatch-accepted formation=7 generals=1") })
        assertTrue(events.any { it.contains("reserve blocked") && it.contains("locked by SHUA_HUANG") })
        assertTrue(events.any { it.contains("server-idle-confirm release formations=7") })
    }

    @Test
    fun schedulerReleasesBusyGeneralAfterServerIdleConfirmationWindow() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        val first = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val secondTooSoon = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 2_000L) }
        val thirdAfterServerIdleWindow = SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 12_000L) }

        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), first.single().decisions)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(30_000)), secondTooSoon.single().decisions)
        assertEquals(listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000)), thirdAfterServerIdleWindow.single().decisions)
        assertEquals(2, protocol.calls.count { it == "dispatchFormation" })
        assertEquals(RuntimeGeneralState.MARCHING, scheduler.runtime.snapshotGeneralLeases(123L, 12_000L).single().state)
    }

    @Test
    fun commandGateRejectsDifferentTaskForBusyBrushYellowGeneral() {
        val protocol = RecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = ShuaHuangTask(
            accountId = 123L,
            config = ShuaHuangConfig(
                enabled = true,
                dailyLimit = 500,
                start = MapCoordinate(11, 22),
                minCopperWan = 0,
                targetType = HuangTargetType.HUANG_JIN,
                selectedFormationIds = setOf(7L),
                formationFilterMode = FormationFilterMode.UNIFIED,
                deleteMailForSpeed = false,
                autoConvertFoodToCopper = false
            )
        )
        val session = GameSession(123L, "unit-token", null, emptyMap(), 0)

        SuspendRunner.run { scheduler.runOnce(session, listOf(task), nowMillis = 1_000L) }
        val gate = scheduler.runtime.commandGate.tryReserveFormationForDispatch(
            accountId = 123L,
            owner = TaskType.DUNGEON,
            taskKey = "unit-dungeon",
            formation = protocol.formations.single(),
            nowMillis = 2_000L,
            reason = "unit dungeon conflict probe"
        )

        assertTrue(gate is GateResult.Blocked)
        assertTrue((gate as GateResult.Blocked).reason.contains("locked by SHUA_HUANG"))
        assertEquals(1, protocol.calls.count { it == "dispatchFormation" })
    }

}

private fun fullOfflineReplayChannelExtraSample(): Map<String, String> = mapOf(
    "sourceMode" to "1",
    "userId" to "sample-user-10001",
    "serverUrl" to "http://game.example",
    "dm" to "999",
    "roleName" to "样本君主",
    "level" to "42",
    "nation" to "蜀",
    "copper" to "1234567",
    "food" to "6543210",
    "prestige" to "98765",
    "state8004TailUtf8Preview" to "君主名=样本君主|君主等级=42|国家=蜀|铜钱=1234567|粮食=6543210|" +
        "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}",
    "xiaohuangPrefsJson" to """{"shuahuangChuzhengBiandui0":true,"bianduihao0":"0000000000000003","bianduiDejiangling0":"0000000000000007","bingli0":"1999"}""",
    "mapTargetsJson" to """[
        {"targetIdHex":"0000000000000065","coordX":11,"coordY":22,"targetKind":"渠帅","targetLevel":11,"rawRecord":"sample-041540-huang-target"},
        {"targetID":"102","kv":33,"kw":44,"kind":"山贼","level":4}
    ]""",
    "dispatchResultsJson" to """[
        {
            "bianduihao":"0000000000000003",
            "targetIdHex":"0000000000000065",
            "targetId":"101",
            "status":"成功",
            "usedCount":1,
            "responseBody":"刷黄出征成功！继续搜索... usedCount=1",
            "generalIdHexChunks":["0000000000000007"],
            "raw":{"source":"generate_shuahuang_channel_extra_sample.py"}
        }
    ]""",
    "dailyEnabledSteps" to "SIGN_IN,SURPRISE_BOX,ADD_LOYALTY,COLLECT_TAX,ARENA_REWARD,SALARY,DELETE_MAIL,DONATE_COPPER,DONATE_FOOD,DONATE_TECH,CONVERT_HALF_FOOD_TO_COPPER",
    "dailyStepResultsJson" to """[
        {"step":"SIGN_IN","success":true,"message":"已完成签到！"},
        {"step":"SURPRISE_BOX","success":true,"message":"已领取惊喜宝箱！"},
        {"step":"ADD_LOYALTY","success":true,"message":"已一键加忠！"},
        {"step":"COLLECT_TAX","success":true,"message":"已一键征收！"},
        {"step":"ARENA_REWARD","success":true,"message":"已领取竞技奖励！"},
        {"step":"SALARY","success":true,"message":"已领取俸禄！"},
        {"step":"DELETE_MAIL","success":true,"message":"已删除邮件！"},
        {"step":"DONATE_COPPER","success":true,"message":"已捐献铜钱！"},
        {"step":"DONATE_FOOD","success":true,"message":"已捐献粮食！"},
        {"step":"DONATE_TECH","success":true,"message":"已捐献科技！"},
        {"step":"CONVERT_HALF_FOOD_TO_COPPER","success":true,"message":"已转换一半粮食到铜钱！"}
    ]""",
    "mineTargetsHex" to "0000000001010101000b0016010002D00101000000270F00000000010202020021002c000002D0020200000022B8",
    "selectedFormationIds" to "3",
    "shuaHuangTargetType" to "HUANG_JIN",
    "selectedMineTypes" to "GOLD,SILVER",
    "onlyEmptyMine" to "true",
    "hitEmptyMine" to "true",
    "mineSelectedFormationIds" to "3",
    "networkSendAllowed" to "false",
    "deviceRegressionNetworkSendAllowed" to "false",
    "actionResponseCalibrationNetworkSendAllowed" to "false",
    "nativeWrapperNetworkSendAllowed" to "false",
    "realActionNetworkAllowed" to "false",
    "sampleNetworkSendAllowed" to "false"
)

private class RecordingTask(
    override val accountId: Long
) : AssistantTask<Unit> {
    override val type: TaskType = TaskType.SHUA_HUANG
    override val config: Unit = Unit
    var stoppedReason: String? = null
    var prepareCount: Int = 0
    var stepCount: Int = 0

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        prepareCount += 1
        return TaskDecision.Continue
    }
    override suspend fun step(ctx: TaskContext): TaskDecision {
        stepCount += 1
        return TaskDecision.Continue
    }
    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision = TaskDecision.Stop(error.message ?: "error")
    override suspend fun stop(ctx: TaskContext, reason: String) {
        stoppedReason = reason
    }
}

private class RecordingDelegatingProtocol(
    private val delegate: GameProtocolClient
) : GameProtocolClient by delegate {
    val calls = mutableListOf<String>()
    var lastDispatchFormationId: Long? = null
    var lastDispatchTargetId: Long? = null

    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> {
        calls += "logout"
        return delegate.logout(session)
    }

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        calls += "validateSession"
        return delegate.validateSession(session)
    }

    override suspend fun queryMonarch(session: GameSession): ProtocolResult<MonarchProfile> {
        calls += "queryMonarch"
        return delegate.queryMonarch(session)
    }

    override suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState> {
        calls += "queryResourceState"
        return delegate.queryResourceState(session)
    }

    override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> {
        calls += "queryGenerals"
        return delegate.queryGenerals(session)
    }

    override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> {
        calls += "queryFormations"
        return delegate.queryFormations(session)
    }

    override suspend fun searchMap(
        session: GameSession,
        start: MapCoordinate,
        policy: MapSearchPolicy
    ): ProtocolResult<List<MapTarget>> {
        calls += "searchMap"
        return delegate.searchMap(session, start, policy)
    }

    override suspend fun dispatchFormation(
        session: GameSession,
        formationId: Long,
        target: MapTarget
    ): ProtocolResult<BattleResult> {
        calls += "dispatchFormation"
        lastDispatchFormationId = formationId
        lastDispatchTargetId = target.id
        return delegate.dispatchFormation(session, formationId, target)
    }
}

private class RecordingProtocol : GameProtocolClient {
    val calls = mutableListOf<String>()
    var lastDispatchFormationId: Long? = null
    var lastDispatchTargetId: Long? = null
    var resources: ResourceState = ResourceState(copper = 1_000_000L, food = 1_000_000L)
    var convertedResources: ResourceState = ResourceState(copper = 1_000_000L, food = 900_000L)
    var generals: List<General> = listOf(General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100))
    var formations: List<FormationRuntime> = listOf(
        FormationRuntime(
            id = 7L,
            name = "测试编队",
            generalIds = listOf(1L),
            status = FormationRuntimeStatus.IDLE,
            troopCount = 1999
        )
    )
    var mapTargets: List<MapTarget> = listOf(
        MapTarget(
            id = 88L,
            coordinate = MapCoordinate(11, 22),
            type = HuangTargetType.HUANG_JIN.name,
            raw = mapOf("level" to "1")
        )
    )
    var dispatchResult: BattleResult = BattleResult(success = true, consumedTimes = 1)
    var updateFormationResult: ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "formation"))
    val dailyStepResults: MutableMap<DailyStep, StepResult> = mutableMapOf()
    var inventory: List<InventoryItem> = emptyList()
    val inventoryActions = mutableListOf<Triple<Long, InventoryAction, Int>>()

    override suspend fun login(account: GameAccount): ProtocolResult<GameSession> =
        ProtocolResult.Ok(GameSession(account.id, "unit-token", null, emptyMap(), 0))

    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> {
        calls += "logout"
        return ProtocolResult.Ok(StepResult(true, "logout ok"))
    }

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        calls += "validateSession"
        return ProtocolResult.Ok(LoginState(valid = true))
    }

    override suspend fun queryMonarch(session: GameSession): ProtocolResult<MonarchProfile> {
        calls += "queryMonarch"
        return ProtocolResult.Ok(MonarchProfile(level = 42, nation = "蜀", name = "测试君主"))
    }

    override suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState> {
        calls += "queryResourceState"
        return ProtocolResult.Ok(resources)
    }

    override suspend fun searchMap(session: GameSession, start: MapCoordinate, policy: MapSearchPolicy): ProtocolResult<List<MapTarget>> {
        calls += "searchMap"
        return ProtocolResult.Ok(mapTargets)
    }

    override suspend fun dispatchFormation(session: GameSession, formationId: Long, target: MapTarget): ProtocolResult<BattleResult> {
        calls += "dispatchFormation"
        lastDispatchFormationId = formationId
        lastDispatchTargetId = target.id
        return ProtocolResult.Ok(dispatchResult)
    }

    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> {
        calls += "convertFoodToCopper:$mode"
        return ProtocolResult.Ok(convertedResources)
    }

    override suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>> = ProtocolResult.Ok(emptyList())
    override suspend fun occupyMine(session: GameSession, mine: MineSearchResult, formationId: Long): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "occupy"))
    override suspend fun withdrawMineDefense(session: GameSession, mineId: Long): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "withdraw"))
    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> {
        calls += "runDailyStep:$step"
        return ProtocolResult.Ok(dailyStepResults[step] ?: StepResult(true, "daily"))
    }

    override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> {
        calls += "queryGenerals"
        return ProtocolResult.Ok(generals)
    }

    override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> {
        calls += "queryFormations"
        return ProtocolResult.Ok(formations)
    }

    override suspend fun healGeneral(session: GameSession, generalId: Long): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "heal"))
    override suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "energy"))
    override suspend fun updateFormation(session: GameSession, config: FormationConfig): ProtocolResult<StepResult> {
        calls += "updateFormation"
        return updateFormationResult
    }
    override suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "internal"))
    override suspend fun runDungeon(session: GameSession, config: DungeonConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "dungeon"))
    override suspend fun queryInventory(session: GameSession): ProtocolResult<List<InventoryItem>> = ProtocolResult.Ok(inventory)
    override suspend fun useOrDiscardItem(session: GameSession, itemId: Long, action: InventoryAction, count: Int): ProtocolResult<StepResult> {
        inventoryActions += Triple(itemId, action, count)
        return ProtocolResult.Ok(StepResult(true, "inventory"))
    }
    override suspend fun setVipFeature(session: GameSession, config: VipFeatureConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "vip"))
    override suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "surrender"))
    override suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "send"))
    override suspend fun runAutoLoot(session: GameSession, config: AutoLootConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "loot"))
    override suspend fun scanAlarmAndMaybeWithdraw(session: GameSession, config: AlarmWithdrawConfig): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "alarm"))
    override suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction): ProtocolResult<StepResult> = ProtocolResult.Ok(StepResult(true, "bulk"))
    override suspend fun queryOpenServer(query: OpenServerQuery): ProtocolResult<OpenServerResult> = ProtocolResult.Ok(OpenServerResult(query.serverName, "unit"))
    override suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig): ProtocolResult<List<CitySearchResult>> = ProtocolResult.Ok(emptyList())
    override suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig): ProtocolResult<List<TreasureSearchResult>> = ProtocolResult.Ok(emptyList())
    override suspend fun applyLicense(config: LicenseConfig, action: LicenseAction): ProtocolResult<LicenseStatus> = ProtocolResult.Ok(LicenseStatus(true, null, "license"))
}

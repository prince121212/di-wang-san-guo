package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DailyServiceLifecycleTest {
    @Test
    fun savedUiDailyConfigRunsRecoveredDailyClosedLoopThroughRealSessionServiceLifecycle() {
        val savedPlan = SavedConfigTaskPlanFactory.plan(10001L, dailySavedConfigExport())
        val realSession = GameSession(
            accountId = 10001L,
            tokenCiphertext = "real-session-token",
            expiresAtMillis = null,
            channelExtra = dailyChannelExtra(),
            sourceMode = 1
        )
        val aligned = RealSessionTaskPlanAdapter.attachRealSession(savedPlan, realSession)
        val protocol = RecordingDailyProtocol(SessionAwareGameProtocolClient())
        val runner = LocalSchedulerLifecycleRunner(TaskScheduler(protocol))

        val batch = SuspendRunner.run {
            runner.runPlansOnceAndStopOnTerminal(tick = 21, plans = listOf(aligned), nowMillis = 1_000L)
        }

        assertEquals(
            listOf(TaskType.DAILY, TaskType.DAILY_DONATE, TaskType.DAILY_SALARY),
            batch.runReports.map { it.type }
        )
        assertTrue(
            batch.runReports.all {
                it.decisions == listOf(
                    TaskDecision.Continue,
                    TaskDecision.Sleep(24 * 60 * 60 * 1000L)
                )
            }
        )
        assertEquals(emptyList<TerminalTaskDecision>(), batch.terminalDecisions)
        assertEquals(emptyList<TaskStopReport>(), batch.stopReports)
        assertEquals(
            listOf(
                "validateSession",
                "runDailyStep:SIGN_IN",
                "runDailyStep:ARENA_REWARD",
                "validateSession",
                "runDailyStep:DONATE_COPPER",
                "runDailyStep:DONATE_FOOD",
                "runDailyStep:DONATE_TECH",
                "validateSession",
                "runDailyStep:SALARY"
            ),
            protocol.calls
        )
        assertTrue(aligned.sourceDescription.contains("session-metadata-aligned"))
    }

    private fun dailySavedConfigExport(): JSONObject = JSONObject()
        .put("schema_version", "0.1-static-mock")
        .put(
            "configs",
            JSONObject().put(
                "10001::daily_basic",
                JSONObject().put(
                    "values",
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f0700a2", true) // SIGN_IN
                        .put("APKTOOL_RENAMED_0x7f07009a", true) // 历史宝箱键由 SIGN_IN 闭环替代
                        .put("APKTOOL_RENAMED_0x7f07009d", true) // 历史隐藏键必须忽略
                        .put("APKTOOL_RENAMED_0x7f0700a3", true) // 历史隐藏键必须忽略
                        .put("APKTOOL_RENAMED_0x7f07009c", true) // ARENA_REWARD
                        .put("APKTOOL_RENAMED_0x7f07009b", true) // 待抓包，不进入计划
                        .put("APKTOOL_RENAMED_0x7f070099", true) // 历史隐藏键必须忽略
                        .put("APKTOOL_RENAMED_0x7f0700a1", true) // DONATE_COPPER
                        .put("APKTOOL_RENAMED_0x7f0700a0", true) // DONATE_FOOD
                        .put("APKTOOL_RENAMED_0x7f07009f", true) // 历史键保留但计划必须忽略
                        .put("APKTOOL_RENAMED_0x7f07011d", true) // CONVERT_HALF_FOOD_TO_COPPER
                )
            )
        )

    private fun dailyChannelExtra(): Map<String, String> = mapOf(
        "sourceMode" to "1",
        "userId" to "sample-user-10001",
        "serverUrl" to "http://game.example",
        "dm" to "999",
        "roleName" to "日常样本君主",
        "level" to "42",
        "nation" to "蜀",
        "copper" to "1234567",
        "food" to "6543210",
        "dailyDonationFactorFz" to "1",
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
        "convertedResourceStateJson" to """{"copper":2222222,"food":3333333}""",
        "networkSendAllowed" to "false",
        "realActionNetworkAllowed" to "false",
        "nativeWrapperNetworkSendAllowed" to "false"
    )
}

private class RecordingDailyProtocol(
    private val delegate: GameProtocolClient
) : GameProtocolClient by delegate {
    val calls = mutableListOf<String>()

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        calls += "validateSession"
        return delegate.validateSession(session)
    }

    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> {
        calls += "runDailyStep:$step"
        return delegate.runDailyStep(session, step)
    }

    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> {
        calls += "convertFoodToCopper:$mode"
        return delegate.convertFoodToCopper(session, mode)
    }
}

package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.DailyGeneralVisitConfig
import com.example.dwpmclone.domain.model.DailyNationalCollectConfig
import com.example.dwpmclone.domain.model.DailySalaryConfig
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.DailyScheduleBehaviorContract
import com.example.dwpmclone.domain.state.InMemoryDailyCompletionStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class DailyFeatureParityTest {
    @Test
    fun arenaCompletionSleepsUntilTheNextTwentyTwoBoundary() {
        val china = ZoneId.of("Asia/Shanghai")
        val beforeBoundary = ZonedDateTime.of(2026, 7, 28, 21, 30, 0, 0, china)
            .toInstant().toEpochMilli()
        val afterBoundary = ZonedDateTime.of(2026, 7, 28, 22, 30, 0, 0, china)
            .toInstant().toEpochMilli()

        assertEquals(
            30L * 60L * 1_000L,
            millisUntilNextDailyFeatureCycle(beforeBoundary, "Asia/Shanghai", "arenaCoins")
        )
        assertEquals(
            23L * 60L * 60L * 1_000L + 30L * 60L * 1_000L,
            millisUntilNextDailyFeatureCycle(afterBoundary, "Asia/Shanghai", "arenaCoins")
        )
    }

    @Test
    fun signInUsesIndependentCompletionAndSecondRunDoesNotResend() {
        val completions = InMemoryDailyCompletionStore()
        val protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true)
        val session = realSession(7L,
            "[{\"step\":\"SIGN_IN\",\"success\":true,\"message\":\"签到成功\"}]"
        )
        val task = DailySingleStepTask(7L, DailyStep.SIGN_IN)
        val successes = mutableListOf<Pair<String, String>>()
        val firstContext = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = 1_000L,
            dailyCompletions = completions,
            successSink = { _, category, message -> successes += category to message }
        )

        assertEquals(TaskDecision.Continue, SuspendRunner.run { task.prepare(firstContext) })
        val first = SuspendRunner.run { task.step(firstContext) }
        assertTrue(first is TaskDecision.Sleep)
        assertTrue(completions.isCompleted(7L, "autoSignIn", 1_000L))
        assertEquals(listOf("签到" to "签到成功"), successes)

        val second = SuspendRunner.run { task.prepare(firstContext) }
        assertTrue(second is TaskDecision.Sleep)
        assertTrue((second as TaskDecision.Sleep).millis > 0L)
    }

    @Test
    fun rejectedSignInIsVisibleAndDoesNotMarkCompletion() {
        val completions = InMemoryDailyCompletionStore()
        val protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true)
        val session = realSession(8L,
            "[{\"step\":\"SIGN_IN\",\"success\":false,\"message\":\"本日已关闭\"}]"
        )
        val prompts = mutableListOf<String>()
        val successes = mutableListOf<Pair<String, String>>()
        val task = DailySingleStepTask(8L, DailyStep.SIGN_IN)
        val context = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = 1_000L,
            promptSink = { _, _, message -> prompts += message },
            dailyCompletions = completions,
            successSink = { _, category, message -> successes += category to message }
        )

        val result = SuspendRunner.run { task.step(context) }
        assertTrue(result is TaskDecision.Sleep)
        assertEquals(60_000L, (result as TaskDecision.Sleep).millis)
        assertFalse(completions.isCompleted(8L, "autoSignIn", 1_000L))
        assertTrue(prompts.any { it.contains("失败") })
        assertTrue(successes.isEmpty())
    }

    @Test
    fun rejectedArenaRewardRetriesIndependentlyInsteadOfSleepingUntilTomorrow() {
        val completions = InMemoryDailyCompletionStore()
        val protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true)
        val session = realSession(9L,
            "[{\"step\":\"ARENA_REWARD\",\"success\":false,\"message\":\"竞技场尚未开放\"}]"
        )
        val task = DailySingleStepTask(9L, DailyStep.ARENA_REWARD)
        val context = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = 1_000L,
            dailyCompletions = completions
        )

        val result = SuspendRunner.run { task.step(context) }
        assertEquals(TaskDecision.Sleep(60_000L), result)
        assertFalse(completions.isCompleted(9L, "arenaCoins", 1_000L))
    }

    @Test
    fun failedFeatureRetryComesFromSharedBehaviorContract() {
        val protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true)
        val session = realSession(10L,
            "[{\"step\":\"ARENA_REWARD\",\"success\":false,\"message\":\"稍后再试\"}]"
        )
        val customContract = AssistantBehaviorContract.defaults().copy(
            dailySchedule = DailyScheduleBehaviorContract(
                failedFeatureRetryMillis = 12_345L,
                completedFeatureSleep = "nextChinaDay"
            )
        )
        val context = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = 1_000L,
            behaviorContract = customContract
        )

        assertEquals(
            TaskDecision.Sleep(12_345L),
            SuspendRunner.run { DailySingleStepTask(10L, DailyStep.ARENA_REWARD).step(context) }
        )
    }

    @Test
    fun nationalCitizenOfficeCompletesOnlyTheThreeDesktopSkippedDailyFeatures() {
        val completions = InMemoryDailyCompletionStore()
        val prompts = mutableListOf<String>()
        val context = TaskContext(
            session = GameSession(
                accountId = 11L,
                tokenCiphertext = "real-token",
                expiresAtMillis = null,
                channelExtra = mapOf("title" to "国民"),
                sourceMode = 1
            ),
            protocol = MockGameProtocolClient(),
            nowMillis = 1_000L,
            promptSink = { _, _, message -> prompts += message },
            dailyCompletions = completions
        )
        val tasks = listOf(
            "salary" to DailySalaryTask(11L, DailySalaryConfig(true)),
            "nationalCollect" to DailyNationalCollectTask(11L, DailyNationalCollectConfig(true)),
            "generalVisit" to DailyGeneralVisitTask(
                11L,
                DailyGeneralVisitConfig(true, listOf(101L))
            )
        )

        tasks.forEach { (key, task) ->
            assertTrue(SuspendRunner.run { task.step(context) } is TaskDecision.Sleep)
            assertTrue(completions.isCompleted(11L, key, 1_000L))
        }
        assertEquals(3, prompts.count { it == "国民跳过" })
    }

    private fun realSession(accountId: Long, results: String): GameSession = GameSession(
        accountId = accountId,
        tokenCiphertext = "real-token",
        expiresAtMillis = null,
        channelExtra = mapOf(
            "userId" to "user",
            "serverUrl" to "http://game.example",
            "dailyStepResultsJson" to results,
            "realActionNetworkAllowed" to "false",
            "realActionSendReady" to "false"
        ),
        sourceMode = 1
    )
}

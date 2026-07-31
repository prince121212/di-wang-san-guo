package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.AlarmConfig
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.InternalAffairsConfig
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class StrictStepResultTaskTest {
    @Test
    fun militaryOnlyAlarmDoesNotRequireIncomingKeywords() {
        val task = AlarmTask(
            1L,
            AlarmConfig(
                enabled = true,
                keywords = emptySet(),
                incomingEnabled = false,
                militaryEnabled = true
            )
        )

        val decision = SuspendRunner.run { task.prepare(context(MockGameProtocolClient())) }

        assertEquals(TaskDecision.Continue, decision)
    }

    @Test
    fun rejectedAlarmScanStopsInsteadOfSleeping() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun scanAlarms(
                session: GameSession,
                config: AlarmConfig
            ): ProtocolResult<StepResult> =
                ProtocolResult.Ok(StepResult(false, "警报扫描失败"))
        }
        val task = AlarmTask(
            1L,
            AlarmConfig(enabled = true)
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.Stop("警报扫描失败"), decision)
    }

    @Test
    fun rejectedInternalAffairsReceiptStaysVisibleAndRetries() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runInternalAffairs(
                session: GameSession,
                config: InternalAffairsConfig
            ): ProtocolResult<StepResult> =
                ProtocolResult.Ok(StepResult(false, "建筑资源不足"))
        }
        val task = InternalAffairsTask(
            1L,
            ConfigDefaults.internalAffairs().copy(enabled = true)
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.RetryAfter(10L * 60L * 1_000L), decision)
    }

    @Test
    fun confirmedBuildingSubmissionImmediatelyContinuesFillingAvailableQueues() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runInternalAffairs(
                session: GameSession,
                config: InternalAffairsConfig
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(
                    true,
                    "建筑已确认",
                    mapOf(
                        "actionSubmitted" to "true",
                        "actionKind" to "building",
                        "nextDelayMillis" to (60L * 60L * 1_000L).toString()
                    )
                )
            )
        }
        val task = InternalAffairsTask(
            1L,
            ConfigDefaults.internalAffairs().copy(enabled = true)
        )

        assertEquals(
            TaskDecision.Sleep(1_000L),
            SuspendRunner.run { task.step(context(protocol)) }
        )
    }

    @Test
    fun technologyOnlySubmissionUsesNormalLowPowerPollingDelay() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runInternalAffairs(
                session: GameSession,
                config: InternalAffairsConfig
            ): ProtocolResult<StepResult> = ProtocolResult.Ok(
                StepResult(
                    true,
                    "科技已提交",
                    mapOf(
                        "actionSubmitted" to "true",
                        "actionKind" to "technology",
                        "nextDelayMillis" to (60L * 60L * 1_000L).toString()
                    )
                )
            )
        }
        val task = InternalAffairsTask(
            1L,
            ConfigDefaults.internalAffairs().copy(
                enabled = false,
                upgradeTechnology = true,
                technologyIds = setOf(5)
            )
        )

        assertEquals(
            TaskDecision.Sleep(60L * 60L * 1_000L),
            SuspendRunner.run { task.step(context(protocol)) }
        )
    }

    private fun context(protocol: GameProtocolClient) = TaskContext(
        GameSession(1L, "mock", null, emptyMap(), 0),
        protocol,
        nowMillis = 1_000L
    )
}

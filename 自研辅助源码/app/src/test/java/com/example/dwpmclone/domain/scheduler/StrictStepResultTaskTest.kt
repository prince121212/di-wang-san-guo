package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.AlarmWithdrawConfig
import com.example.dwpmclone.domain.model.BulkToolAction
import com.example.dwpmclone.domain.model.BulkToolConfig
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class StrictStepResultTaskTest {
    @Test
    fun rejectedAlarmScanStopsInsteadOfSleeping() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun scanAlarmAndMaybeWithdraw(
                session: GameSession,
                config: AlarmWithdrawConfig
            ): ProtocolResult<StepResult> =
                ProtocolResult.Ok(StepResult(false, "警报扫描失败"))
        }
        val task = AlarmWithdrawMockTask(
            1L,
            AlarmWithdrawConfig(enabled = true)
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.Stop("警报扫描失败"), decision)
    }

    @Test
    fun rejectedBulkActionStopsBeforeFollowingAction() {
        val calls = mutableListOf<BulkToolAction>()
        val first = BulkToolAction.GENERAL_TOKEN_ADD_COMMAND
        val second = BulkToolAction.USE_SMALL_DRUM_BAGUA
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun runBulkToolAction(
                session: GameSession,
                action: BulkToolAction
            ): ProtocolResult<StepResult> {
                calls += action
                return if (action == first) {
                    ProtocolResult.Ok(StepResult(false, "批量动作失败"))
                } else {
                    ProtocolResult.Ok(StepResult(true, "批量动作成功"))
                }
            }
        }
        val task = BulkToolsMockTask(
            1L,
            BulkToolConfig(
                enabledActions = linkedSetOf(first, second),
                accountIds = setOf(1L)
            )
        )

        val decision = SuspendRunner.run { task.step(context(protocol)) }

        assertEquals(TaskDecision.Stop("批量动作失败"), decision)
        assertEquals(listOf(first), calls)
    }

    private fun context(protocol: GameProtocolClient) = TaskContext(
        GameSession(1L, "mock", null, emptyMap(), 0),
        protocol,
        nowMillis = 1_000L
    )
}

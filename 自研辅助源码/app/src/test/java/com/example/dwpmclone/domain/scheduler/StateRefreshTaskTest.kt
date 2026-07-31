package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.General
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class StateRefreshTaskTest {
    @Test
    fun parserMetadataFailureRetriesInsteadOfPermanentlyStoppingObservation() {
        val protocol = object : GameProtocolClient by MockGameProtocolClient() {
            override suspend fun queryGenerals(
                session: GameSession
            ): ProtocolResult<List<General>> = ProtocolResult.Err(
                "GENERAL_PARSE_MISSING",
                "本轮没有完整将领字段",
                retryable = false
            )
        }
        val context = TaskContext(
            GameSession(7L, "token", null, emptyMap(), sourceMode = 1),
            protocol,
            nowMillis = 1_000L
        )

        val decision = SuspendRunner.run { StateRefreshTask(7L).step(context) }

        assertEquals(
            TaskDecision.RetryAfter(10_000L, "更新角色将领数据失败：本轮没有完整将领字段"),
            decision
        )
    }
}

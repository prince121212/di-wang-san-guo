package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.LoginState
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryCleanupTaskTest {
    @Test
    fun legacyMarkerCannotReachKotlinInventoryProtocol() {
        var validationCalls = 0
        val delegate = MockGameProtocolClient()
        val protocol = object : GameProtocolClient by delegate {
            override suspend fun validateSession(
                session: GameSession,
            ): ProtocolResult<LoginState> {
                validationCalls += 1
                return delegate.validateSession(session)
            }
        }
        val task = InventoryCleanupTask(
            77L,
            ConfigDefaults.inventory().copy(enabled = true),
        )
        val context = TaskContext(
            GameSession(77L, "token", null, emptyMap(), sourceMode = 1),
            protocol,
            nowMillis = 1_000L,
        )

        val prepare = SuspendRunner.run { task.prepare(context) }
        val step = SuspendRunner.run { task.step(context) }

        assertTrue(prepare is TaskDecision.Stop)
        assertTrue(step is TaskDecision.Stop)
        assertTrue((prepare as TaskDecision.Stop).reason.contains("共享 Python"))
        assertTrue((step as TaskDecision.Stop).reason.contains("共享 Python"))
        assertEquals(0, validationCalls)
    }
}

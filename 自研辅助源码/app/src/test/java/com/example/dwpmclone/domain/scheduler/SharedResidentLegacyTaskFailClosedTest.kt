package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.LoginState
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedResidentLegacyTaskFailClosedTest {
    @Test
    fun brushAndMineMarkersCannotReachKotlinProtocolExecution() {
        val protocol = ProtocolCallCounter()
        val context = TaskContext(
            session = GameSession(7L, "token", null, emptyMap(), sourceMode = 1),
            protocol = protocol,
            nowMillis = 1_000L,
        )
        val tasks: List<AssistantTask<*>> = listOf(
            ShuaHuangTask(
                7L,
                ConfigDefaults.shuaHuang().copy(
                    enabled = true,
                    selectedFormationIds = setOf(7L),
                ),
            ),
            MineTask(
                7L,
                ConfigDefaults.mine().copy(
                    enabled = true,
                    selectedFormationIds = setOf(7L),
                ),
            ),
            MineTask(
                7L,
                ConfigDefaults.mine().copy(
                    enabled = false,
                    backgroundSearch = true,
                ),
            ),
        )

        tasks.forEach { task ->
            val prepare = SuspendRunner.run { task.prepare(context) }
            val step = SuspendRunner.run { task.step(context) }
            assertTrue(prepare is TaskDecision.Stop)
            assertTrue(step is TaskDecision.Stop)
            assertTrue((prepare as TaskDecision.Stop).reason.contains("共享 Python"))
            assertTrue((step as TaskDecision.Stop).reason.contains("共享 Python"))
        }
        assertEquals(0, protocol.validationCalls)
    }
}

private class ProtocolCallCounter(
    private val delegate: GameProtocolClient = MockGameProtocolClient(),
) : GameProtocolClient by delegate {
    var validationCalls = 0

    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> {
        validationCalls += 1
        return delegate.validateSession(session)
    }
}

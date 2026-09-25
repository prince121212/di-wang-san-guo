package com.example.dwpmclone.host

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedResidentTaskStatusMapperTest {
    @Test
    fun featureScopedBlockedStatesAreErrorsEvenWhenAccountAttentionIsFalse() {
        listOf("blocked", "defeat-paused", "clear-unconfirmed").forEach { state ->
            val result = result(feature = "dungeon", state = state)

            assertEquals(TaskRuntimeState.ERROR, SharedResidentTaskStatusMapper.stateFor(result))
        }
    }

    @Test
    fun concreteUnknownTerminalStateIsAlsoVisibleAsFeatureError() {
        val result = result(
            feature = "inventory",
            state = "uncertain",
            requiresAttention = false,
        )

        assertEquals(TaskRuntimeState.ERROR, SharedResidentTaskStatusMapper.stateFor(result))
    }

    @Test
    fun isolatedFeatureListMapsAliasesToIndependentTaskRows() {
        val types = SharedResidentTaskStatusMapper.isolatedTypes(
            "inventory|brush|brushYellow|dungeon|unknown|"
        )

        assertEquals(
            listOf(TaskType.INVENTORY, TaskType.SHUA_HUANG, TaskType.DUNGEON),
            types,
        )
        assertTrue(
            SharedResidentTaskStatusMapper.isolatedMessage(TaskType.INVENTORY)
                .contains("背包整理")
        )
    }

    @Test
    fun normalRetryAndRunningStatesKeepTheirExistingMeaning() {
        assertEquals(
            TaskRuntimeState.RETRYING,
            SharedResidentTaskStatusMapper.stateFor(result("brush", "retry")),
        )
        assertEquals(
            TaskRuntimeState.RETRYING,
            SharedResidentTaskStatusMapper.stateFor(
                result("brush", "waiting-resources", nextWakeAtMillis = 60_000L)
            ),
        )
        assertEquals(
            TaskRuntimeState.RUNNING,
            SharedResidentTaskStatusMapper.stateFor(result("brush", "fighting")),
        )
        assertEquals(
            TaskRuntimeState.SLEEPING,
            SharedResidentTaskStatusMapper.stateFor(
                result("brush", "waiting", nextWakeAtMillis = 123L)
            ),
        )
    }

    @Test
    fun cloudDependencyWaitIsRetryingNotAnUncertainFormationError() {
        assertEquals(
            TaskRuntimeState.RETRYING,
            SharedResidentTaskStatusMapper.stateFor(
                result("brush", "waiting-dependency", nextWakeAtMillis = 120_000L)
            ),
        )
    }

    private fun result(
        feature: String,
        state: String,
        requiresAttention: Boolean = false,
        nextWakeAtMillis: Long? = null,
    ) = SharedResidentTickResult(
        accountId = 202L,
        operationId = "op-test",
        feature = feature,
        dailyKey = null,
        state = state,
        message = "fixture",
        nextWakeAtMillis = nextWakeAtMillis,
        requiresAttention = requiresAttention,
        requestSent = false,
    )
}

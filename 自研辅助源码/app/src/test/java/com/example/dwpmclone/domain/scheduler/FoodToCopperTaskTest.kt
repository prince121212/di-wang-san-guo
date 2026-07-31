package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.FoodToCopperConfig
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.ConvertMode
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.ResourceState
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class FoodToCopperTaskTest {
    @Test
    fun belowFloorConvertsOnceAndRecordsConfirmedDelta() {
        val protocol = RecordingFoodProtocol(
            before = ResourceState(copper = 8_000L, food = 100_000L),
            after = ResourceState(copper = 12_000L, food = 86_666L)
        )
        val successes = mutableListOf<Pair<String, String>>()
        val task = FoodToCopperTask(7L, FoodToCopperConfig(true, 1))

        val decision = SuspendRunner.run {
            task.step(context(protocol) { category, message -> successes += category to message })
        }

        assertEquals(listOf("query", "convert:FOOD_TO_COPPER_THRESHOLD"), protocol.calls)
        assertEquals(TaskDecision.Sleep(600_000L, reason = "粮食转铜已达到保底1万"), decision)
        assertEquals("粮食转铜", successes.single().first)
    }

    @Test
    fun copperAlreadyAtFloorDoesNotMutateResources() {
        val protocol = RecordingFoodProtocol(
            before = ResourceState(copper = 10_000L, food = 100_000L),
            after = ResourceState(copper = 10_000L, food = 100_000L)
        )

        val decision = SuspendRunner.run {
            FoodToCopperTask(7L, FoodToCopperConfig(true, 1)).step(context(protocol))
        }

        assertEquals(listOf("query"), protocol.calls)
        assertEquals(TaskDecision.Sleep(600_000L, reason = "铜钱已达到保底1万"), decision)
    }

    private fun context(
        protocol: GameProtocolClient,
        success: (String, String) -> Unit = { _, _ -> }
    ) = TaskContext(
        session = GameSession(7L, "token", null, emptyMap(), sourceMode = 1),
        protocol = protocol,
        nowMillis = 1_000L,
        successSink = { _, category, message -> success(category, message) }
    )
}

private class RecordingFoodProtocol(
    private val before: ResourceState,
    private val after: ResourceState
) : GameProtocolClient by MockGameProtocolClient() {
    val calls = mutableListOf<String>()

    override suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState> {
        calls += "query"
        return ProtocolResult.Ok(before)
    }

    override suspend fun convertFoodToCopper(
        session: GameSession,
        mode: ConvertMode
    ): ProtocolResult<ResourceState> {
        calls += "convert:$mode"
        return ProtocolResult.Ok(after)
    }
}
